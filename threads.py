# threads.py
import json
import re
import time
import random
import requests
from PySide6.QtCore import QThread, Signal
from db_manager import FundHistoryDB

class RankingFetcher(QThread):
    """抓取当日指数/板块场外ETF涨跌排行榜的线程（带板块智能去重去同质化）"""
    ranking_signal = Signal(list, list, bool) # top_list, bot_list, is_success

    def __init__(self, code_to_name_dict, shared_sector_map=None):
        super().__init__()
        self.code_to_name_dict = code_to_name_dict
        self.shared_sector_map = shared_sector_map if shared_sector_map is not None else {}

    def run(self):
        if not self.code_to_name_dict:
            try:
                res = requests.get("http://fund.eastmoney.com/js/fundcode_search.js", timeout=5)
                match = re.search(r'var r = (\[.*\]);', res.text)
                if match:
                    for item in json.loads(match.group(1)):
                        self.code_to_name_dict[item[0]] = item[2]
            except: pass

        headers = {"Referer": "http://fund.eastmoney.com/"}
        # 增加重试逻辑
        for attempt in range(3):
            try:
                url_top = "http://api.fund.eastmoney.com/FundGuZhi/GetFundGZList?type=5&sort=3&orderType=desc&canbuy=0&pageIndex=1&pageSize=200"
                r_top = requests.get(url_top, headers=headers, timeout=5)
                top_data = r_top.json()
                
                url_bot = "http://api.fund.eastmoney.com/FundGuZhi/GetFundGZList?type=5&sort=3&orderType=asc&canbuy=0&pageIndex=1&pageSize=200"
                r_bot = requests.get(url_bot, headers=headers, timeout=5)
                bot_data = r_bot.json()
                
                if top_data.get("Data") and bot_data.get("Data"):
                    top_raw_list = top_data["Data"].get("list", [])
                    bot_raw_list = bot_data["Data"].get("list", [])
                    
                    top_list = self.filter_distinct_sectors(top_raw_list, 10)
                    bot_list = self.filter_distinct_sectors(bot_raw_list, 10)
                    
                    self.ranking_signal.emit(top_list, bot_list, True)
                    return # 成功获取，退出
                elif "网络繁忙" in str(top_data) or "网络繁忙" in str(bot_data):
                    time.sleep(1 + attempt)
                    continue
            except Exception:
                time.sleep(1 + attempt)
                continue
        
        # 多次重试失败
        self.ranking_signal.emit([], [], False)

    def filter_distinct_sectors(self, fund_list, limit=10):
        from utils import extract_fund_sector
        
        result = []
        seen_sectors = set()
        
        for item in fund_list:
            if len(result) >= limit: break
            
            code = item.get("bzdm", "")
            name = self.code_to_name_dict.get(code, "")
            if not name: continue
            
            # 优先从 API 获取的板块库中匹配
            api_sector = self.shared_sector_map.get(code)
            matched_sector = api_sector if api_sector else extract_fund_sector(name, code)
                
            if matched_sector not in seen_sectors:
                seen_sectors.add(matched_sector)
                item['extracted_sector'] = matched_sector
                item['fund_name'] = name 
                result.append(item)
                
        return result
    
class FundDataFetcher(QThread):
    """异步获取基金实时估值及历史数据的线程"""
    update_signal = Signal(dict)
    error_signal = Signal(str, str)
    finish_signal = Signal()

    def __init__(self, fund_codes, config, history_cache, code_to_name_dict, db=None):
        super().__init__()
        self.fund_codes = fund_codes
        self.config = config
        self.history_cache = history_cache
        self.code_to_name_dict = code_to_name_dict
        self.db = db if db else FundHistoryDB()  # 如果没传数据库实例就创建新的

    def fetch_single(self, code, session):
        if self.isInterruptionRequested(): return None
        
        saved_name = self.config.get("funds_info", {}).get(code, {}).get("name", "")
        if not saved_name:
            saved_name = self.code_to_name_dict.get(code, code)
            
        # 【修改点】：增加 gszzl 的默认值，防止 UI 显示 None
        data = {
            'fundcode': code, 
            'name': saved_name,
            'gszzl': "0.00",  # 默认设为 0.00
            'gsz': "0.00",
            'dwjz': "0.00"
        }
        
        # 如果当前名称就是代码（说明没查到名称），且存在全局字典，则尝试补全
        if data['name'] == code and self.code_to_name_dict:
            data['name'] = self.code_to_name_dict.get(code, code)
        
        # ================= 1. 优先检查缓存中是否已有历史数据 =================
        history_success = False
        history_data = None
        
        if code in self.history_cache:
            # 内存中已有数据
            history_data = self.history_cache[code]
        else:
            # 尝试从数据库中读取
            db_history = self.db.get_history(code)
            if db_history:
                self.history_cache[code] = db_history
                history_data = db_history

        if history_data:
            data['new_history'] = history_data
            # 【修复核心】：从缓存/数据库读取数据时，必须像请求接口一样，补齐基础字段兜底！
            if history_data.get('navs') and len(history_data['navs']) > 0:
                latest_nav = str(history_data['navs'][0])
                data['jzrq'] = history_data.get('jzrq', '')
                data['dwjz'] = latest_nav
                data['gsz'] = latest_nav  # 没有实时估值时（如QDII），用最新实际净值代替
                data['gztime'] = f"{data['jzrq']} (实际净值)"
            
            # 如果本地数据已经包含日期，则认为历史数据完整，不再重复抓取
            if history_data.get('dates') and len(history_data['dates']) > 0:
                history_success = True
        
        # ================= 2. 如果本地没有历史数据或数据不全（无日期），则从接口获取 =================
        if not history_success:
            his_url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNHisNetList?FCODE={code}&pageIndex=1&pageSize=2000&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0"
            try:
                r_his = session.get(his_url, timeout=5)
                his_data = r_his.json()
                if his_data.get("ErrCode") == 0 and his_data.get("Datas"):
                    navs = []
                    dates = []
                    for item in his_data.get("Datas"):
                        try:
                            val = item.get("DWJZ")
                            dt = item.get("FSRQ")
                            if val: 
                                navs.append(float(val))
                                dates.append(dt)
                        except ValueError: pass
                    
                    if navs:
                        latest_item = his_data.get("Datas")[0]
                        latest_date = latest_item.get("FSRQ", "")
                        
                        history_data = {'jzrq': latest_date, 'navs': navs, 'dates': dates}
                        data['new_history'] = history_data
                        self.history_cache[code] = history_data
                        
                        # 保存到数据库
                        self.db.save_history(code, latest_date, navs, dates)
                        
                        data['jzrq'] = latest_date
                        data['dwjz'] = latest_item.get("DWJZ", "")
                        data['gsz'] = latest_item.get("DWJZ", "")
                        data['gszzl'] = latest_item.get("JZZZL", "")
                        data['gztime'] = f"{latest_date} (实际净值)"
                        history_success = True
            except Exception:
                pass

        # ================= 3. 尝试获取实时估值数据 (增加重试) =================
        timestamp = int(time.time() * 1000)
        url = f"http://fundgz.1234567.com.cn/js/{code}.js?rt={timestamp}"
        
        for gz_attempt in range(2):
            try:
                response = session.get(url, timeout=3)
                if response.status_code == 200:
                    match = re.search(r'jsonpgz\((.*?)\);', response.text)
                    if match:
                        gz_data = json.loads(match.group(1))
                        if gz_data.get('name'):
                            data['name'] = gz_data.get('name')
                        
                        if gz_data.get('gsz'):
                            data['jzrq'] = gz_data.get('jzrq', data.get('jzrq'))
                            data['dwjz'] = gz_data.get('dwjz', data.get('dwjz'))
                            data['gsz'] = gz_data.get('gsz')
                            data['gszzl'] = gz_data.get('gszzl')
                            data['gztime'] = gz_data.get('gztime')
                        break # 成功
                elif response.status_code == 404:
                    break # 404 没必要重试
            except Exception:
                time.sleep(0.5)

        if not history_success and 'gztime' not in data:
            return {'error': True, 'code': code, 'msg': "暂无数据"}

        # ================= 4. 计算涨跌幅与百分位 =================
        try:
            current_val = float(data.get('gsz', data.get('dwjz', 0)))
            history_navs = self.history_cache.get(code, {}).get('navs', [])
            
            if history_navs:
                full_navs = [current_val] + history_navs 
                
                data['drops'] = {}
                for d in self.config.get('drop_days', []):
                    if len(full_navs) > d:
                        base_nav = full_navs[d]
                        if base_nav != 0:
                            drop = (current_val - base_nav) / base_nav * 100
                            data['drops'][d] = drop
                        
                data['pcts'] = {}
                for m in self.config.get('percentile_months', []):
                    days = m * 21
                    sub_navs = full_navs[:days + 1]
                    if len(sub_navs) > 1:
                        max_v, min_v = max(sub_navs), min(sub_navs)
                        if max_v == min_v: pct = 100.0
                        else: pct = (current_val - min_v) / (max_v - min_v) * 100
                        data['pcts'][m] = pct
        except Exception: 
            pass
            
        return {'error': False, 'data': data}

    def run(self):
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"
        })

        import concurrent.futures
        
        # 使用最大10个线程进行并发请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_code = {executor.submit(self.fetch_single, code, session): code for code in self.fund_codes}
            
            for future in concurrent.futures.as_completed(future_to_code):
                if self.isInterruptionRequested():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                    
                try:
                    res = future.result()
                    if not res: continue
                    if res.get('error'):
                        self.error_signal.emit(res['code'], res['msg'])
                    else:
                        self.update_signal.emit(res['data'])
                except Exception as e:
                    code = future_to_code[future]
                    self.error_signal.emit(code, str(e))
                
        session.close()
        self.finish_signal.emit()

class ValuationFetcher(QThread):
    """抓取全市场指数估值榜 (PE/PB 最高/最低) 的线程"""
    valuation_signal = Signal(list, bool) # valuation_list, is_success

    def __init__(self, all_funds_dict, shared_sector_map=None):
        super().__init__()
        self.all_funds_dict = all_funds_dict
        self.shared_sector_map = shared_sector_map if shared_sector_map is not None else {}

    def find_fund_for_index(self, index_code, index_name, used_fund_codes=None):
        """尝试为指数找到一个对应的场外联接基金代码，优先联接基金。
        used_fund_codes: 已被其他指数占用的基金代码集合，避免多个指数映射到同一基金。
        """
        for _ in range(50):
            if self.all_funds_dict: break
            time.sleep(0.1)
            
        if not self.all_funds_dict:
            try:
                res = requests.get("http://fund.eastmoney.com/js/fundcode_search.js", timeout=5)
                match = re.search(r'var r = (\[.*\]);', res.text)
                if match:
                    for item in json.loads(match.group(1)):
                        self.all_funds_dict[item[2]] = item[0]
            except: pass

        if used_fund_codes is None:
            used_fund_codes = set()

        # 清理指数名称，生成搜索关键词
        # 移除“指”、“指数”、“成指”、“价格”、“全收益”等后缀，保留核心名称
        clean_name = index_name.replace("指数", "").replace("CS", "").replace("TMT50", "TMT")
        # 核心改进：移除“指”、“成指”等后缀，这些后缀在基金名称中通常不存在
        clean_name = re.sub(r'(指数|成指|指|价格|全收益|财富|等权|分级)$', '', clean_name).strip()
        
        search_keys = [index_code, index_name]
        if clean_name and clean_name != index_name:
            search_keys.append(clean_name)
            
        # 增加对“中小100”到“中小板”的兼容（历史遗留问题）
        if "中小100" in clean_name:
            search_keys.append(clean_name.replace("中小100", "中小板"))
            
        # 增加特定板块的别名扩展，提高匹配率
        if "证保" in clean_name:
            search_keys.append(clean_name.replace("证保", "证券保险"))
        if "深证民营" in clean_name:
            search_keys.append("民营")
        if "中创" in clean_name:
            search_keys.append("中创400")

        def is_otc_fund(code):
            """判断是否为场外基金代码（非场内ETF）"""
            return code.startswith('0') or code.startswith('2') or code.startswith('3') or code.startswith('16') or code.startswith('50')

        def is_available(code, fund_name):
            """检查该基金代码是否尚未被其他指数占用，且排除后端收费基金"""
            return code not in used_fund_codes and "后端" not in fund_name

        # 第一优先级：联接基金（一定是场外，数据接口一定支持）
        for key in search_keys:
            for name, code in self.all_funds_dict.items():
                if key in name and "联接" in name and is_available(code, name):
                    return code

        # 第二优先级：场外ETF基金
        for key in search_keys:
            for name, code in self.all_funds_dict.items():
                if key in name and "ETF" in name and is_otc_fund(code) and is_available(code, name):
                    return code

        # 第三优先级：LOF基金或指数基金（场外）
        for key in search_keys:
            for name, code in self.all_funds_dict.items():
                if key in name and ("LOF" in name or "指数" in name) and is_otc_fund(code) and is_available(code, name):
                    return code

        # 第四优先级：任何包含该关键词的场外基金（比如直接叫xx股票）
        for key in search_keys:
            if key == index_code: continue # 纯数字代码不作为宽泛匹配
            for name, code in self.all_funds_dict.items():
                if key in name and is_otc_fund(code) and is_available(code, name):
                    return code

        # 第五优先级：任何ETF（包括场内，可能查不到实时估值但能查历史净值）
        for key in search_keys:
            for name, code in self.all_funds_dict.items():
                if key in name and "ETF" in name and is_available(code, name):
                    return code
                    
        return index_code  # 没找到就用指数代码兜底


    def run(self):
        url = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNIndexValuationList?pageIndex=1&pageSize=500&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15",
            "Referer": "https://unitmob.1234567.com.cn/"
        }
        # 增加重试逻辑
        for attempt in range(3):
            try:
                res = requests.get(url, headers=headers, timeout=10)
                data = res.json()
                if data.get("Success") and data.get("Datas"):
                    all_indices = data["Datas"]
                    
                    # 更新全局板块映射库（从官方指数名称提取）
                    for item in all_indices:
                        idx_name = item.get("INDEXNAME", "")
                        if idx_name:
                            # 清理名称：去掉“指数”、“等权”等，提取核心板块名
                            sector = re.sub(r'(指数|等权|分级|全收益|财富|全指).*', '', idx_name)
                            if sector:
                                 # 尝试寻找该指数对应的基金代码
                                 self.shared_sector_map[item.get("INDEXCODE")] = sector
                                 
                    valid_indices = []
                    seen_index_codes = set()
                    for item in all_indices:
                        try:
                            idx_code = item.get("INDEXCODE")
                            if not idx_code or idx_code in seen_index_codes:
                                continue
                                
                            pe = item.get("PETTM")
                            pb = item.get("PB")
                            pe_pct = item.get("PEP")
                            pb_pct = item.get("PBP")
                            
                            # 【核心修复】：放宽过滤条件，只要 PE 或 PB 有一个有效即保留
                            pe_valid = pe and pe != "--" and pe != ""
                            pb_valid = pb and pb != "--" and pb != ""
                            
                            if pe_valid or pb_valid:
                                seen_index_codes.add(idx_code)
                                
                                # 百分位转换逻辑：如果是 "--" 则设为 -1 表示无效
                                try:
                                    item["pe_pct_float"] = float(pe_pct) * 100 if pe_pct is not None and pe_pct != "" and pe_pct != "--" else -1
                                except: item["pe_pct_float"] = -1
                                
                                try:
                                    item["pb_pct_float"] = float(pb_pct) * 100 if pb_pct is not None and pb_pct != "" and pb_pct != "--" else -1
                                except: item["pb_pct_float"] = -1
                                    
                                try: item["pe_float"] = float(pe) if pe_valid else 0
                                except: item["pe_float"] = 0
                                
                                try: item["pb_float"] = float(pb) if pb_valid else 0
                                except: item["pb_float"] = 0
                                
                                valid_indices.append(item)
                        except: continue

                    # --- 核心逻辑：每类选出 10 个（去重并按板块分布，保证约 40 个） ---
                    
                    # 1. PE 榜单
                    pe_valid_list = [x for x in valid_indices if x["pe_pct_float"] >= 0]
                    high_pe = sorted(pe_valid_list, key=lambda x: x["pe_pct_float"], reverse=True)
                    low_pe = sorted(pe_valid_list, key=lambda x: x["pe_pct_float"])
                    
                    # 2. PB 榜单 (增加兜底逻辑：若 API 缺失 PB 百分位，则按绝对值排序)
                    pb_pct_list = [x for x in valid_indices if x["pb_pct_float"] >= 0]
                    if pb_pct_list:
                        high_pb = sorted(pb_pct_list, key=lambda x: x["pb_pct_float"], reverse=True)
                        low_pb = sorted(pb_pct_list, key=lambda x: x["pb_pct_float"])
                    else:
                        # 兜底：使用 PB 绝对值排序
                        pb_abs_list = [x for x in valid_indices if x["pb_float"] > 0]
                        high_pb = sorted(pb_abs_list, key=lambda x: x["pb_float"], reverse=True)
                        low_pb = sorted(pb_abs_list, key=lambda x: x["pb_float"])

                    combined_dict = {} # 最终合并后的字典
                    used_fund_codes = set()  # 全局去重：已被占用的基金代码

                    def add_to_list(source, short_tag, limit=10):
                        from utils import extract_fund_sector
                        count = 0
                        seen_sectors = set()
                        
                        for item in source:
                            if count >= limit: break
                            
                            index_code = item["INDEXCODE"]
                            index_name = item["INDEXNAME"]
                            
                            # 提取板块用于本类去重
                            api_sector = self.shared_sector_map.get(index_code)
                            sector = api_sector if api_sector else extract_fund_sector(index_name, "")
                            
                            if sector in seen_sectors:
                                continue
                                
                            fund_code = self.find_fund_for_index(index_code, index_name, used_fund_codes)
                            
                            # 如果没找到对应的基金代码（返回了指数代码本身），则跳过
                            if fund_code == index_code:
                                continue
                            
                            if fund_code in combined_dict:
                                existing = combined_dict[fund_code]
                                existing_tags = existing.get("tags", [])
                                
                                # 检查是否存在矛盾：同一维度（PE或PB）不能同时高和低
                                is_conflict = False
                                tag_dimension = short_tag[:2]  # "PE" 或 "PB"
                                for t in existing_tags:
                                    if t[:2] == tag_dimension and t != short_tag:
                                        is_conflict = True
                                        break
                                
                                if is_conflict:
                                    continue
                                
                                if short_tag not in existing_tags:
                                    existing_tags.append(short_tag)
                                    existing["valuation_tag"] = "/".join(existing_tags)
                                    count += 1
                                    seen_sectors.add(sector)
                                continue

                            res_item = {
                                "bzdm": index_code, 
                                "fund_code": fund_code,
                                "fund_name": index_name,
                                "pe": item.get("PETTM", "--"),
                                "pb": item.get("PB", "--"),
                                "pe_percentile": f"{item['pe_pct_float']:.2f}" if item['pe_pct_float'] >= 0 else "--",
                                "pb_percentile": f"{item['pb_pct_float']:.2f}" if item['pb_pct_float'] >= 0 else "--",
                                "valuation_tag": short_tag,
                                "tags": [short_tag],
                                "extracted_sector": sector
                            }
                            combined_dict[fund_code] = res_item
                            used_fund_codes.add(fund_code)
                            seen_sectors.add(sector)
                            count += 1

                    # 按顺序加入
                    add_to_list(high_pe, "PE高", 10)
                    add_to_list(low_pe, "PE低", 10)
                    add_to_list(high_pb, "PB高", 10)
                    add_to_list(low_pb, "PB低", 10)

                    self.valuation_signal.emit(list(combined_dict.values()), True)
                    return # 成功获取，退出
                elif data.get("ErrMsg") == "网络繁忙，请稍后重试！" or not data.get("Success"):
                    time.sleep(1 + attempt)
                    continue
                else:
                    break
            except Exception:
                time.sleep(1 + attempt)
                continue
        
        # 多次重试失败
        self.valuation_signal.emit([], False)
