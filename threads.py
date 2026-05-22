# threads.py
import json
import re
import time
import random
import requests
from PySide6.QtCore import QThread, Signal
from db_manager import FundHistoryDB
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

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
                if self.isInterruptionRequested(): return
                match = re.search(r'var r = (\[.*\]);', res.text)
                if match:
                    for item in json.loads(match.group(1)):
                        if self.isInterruptionRequested(): return
                        self.code_to_name_dict[item[0]] = item[2]
            except: pass

        if self.isInterruptionRequested(): return

        headers = {"Referer": "http://fund.eastmoney.com/"}
        # 增加重试逻辑
        for attempt in range(3):
            if self.isInterruptionRequested(): return
            try:
                url_top = "http://api.fund.eastmoney.com/FundGuZhi/GetFundGZList?type=5&sort=3&orderType=desc&canbuy=0&pageIndex=1&pageSize=200"
                r_top = requests.get(url_top, headers=headers, timeout=5)
                if self.isInterruptionRequested(): return
                top_data = r_top.json()
                
                url_bot = "http://api.fund.eastmoney.com/FundGuZhi/GetFundGZList?type=5&sort=3&orderType=asc&canbuy=0&pageIndex=1&pageSize=200"
                r_bot = requests.get(url_bot, headers=headers, timeout=5)
                if self.isInterruptionRequested(): return
                bot_data = r_bot.json()
                
                if top_data.get("Data") and bot_data.get("Data"):
                    top_raw_list = top_data["Data"].get("list", [])
                    bot_raw_list = bot_data["Data"].get("list", [])
                    
                    if self.isInterruptionRequested(): return
                    top_list = self.filter_distinct_sectors(top_raw_list, 10)
                    if self.isInterruptionRequested(): return
                    bot_list = self.filter_distinct_sectors(bot_raw_list, 10)
                    
                    if self.isInterruptionRequested(): return
                    self.ranking_signal.emit(top_list, bot_list, True)
                    return # 成功获取，退出
                elif "网络繁忙" in str(top_data) or "网络繁忙" in str(bot_data):
                    time.sleep(1 + attempt)
                    continue
            except Exception:
                time.sleep(1 + attempt)
                continue
        
        # 多次重试失败
        if not self.isInterruptionRequested():
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
            
            # 优先从 API 获取的板块库中匹配，并再次通过 extract_fund_sector 标准化
            api_sector = self.shared_sector_map.get(code)
            if api_sector:
                matched_sector = extract_fund_sector(api_sector, code)
            else:
                matched_sector = extract_fund_sector(name, code)
                
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

        # 计算是否需要从 API 更新历史数据，以及更新的拉取条数 (pageSize)
        need_api_update = True
        page_size_to_fetch = 2000

        if history_data:
            data['new_history'] = history_data
            # 【修复核心】：从缓存/数据库读取数据时，必须像请求接口一样，补齐基础字段兜底！
            if history_data.get('navs') and len(history_data['navs']) > 0:
                latest_nav = str(history_data['navs'][0])
                data['jzrq'] = history_data.get('jzrq', '')
                data['dwjz'] = latest_nav
                data['gsz'] = latest_nav  # 没有实时估值时（如QDII），用最新实际净值代替
                data['gztime'] = f"{data['jzrq']} (实际净值)"
            
            # 如果本地数据已经包含日期，则认为已有可用历史数据 (即使 API 失败也可以用作兜底)
            if history_data.get('dates') and len(history_data['dates']) > 0:
                history_success = True
                
                # 判断是否需要从 API 增量/全量更新
                d_max_str = history_data.get('jzrq')
                if d_max_str:
                    try:
                        from datetime import datetime
                        d_max = datetime.strptime(d_max_str, "%Y-%m-%d").date()
                        today = datetime.now().date()
                        days_diff = (today - d_max).days
                        
                        if days_diff == 0:
                            # 最新日期就是今天，无需再次从 API 更新
                            need_api_update = False
                        elif 0 < days_diff <= 5:
                            # 相差在5天以内，只拉取最新一页以节省流量
                            page_size_to_fetch = 30
                        else:
                            # 相差超过 5 天，拉取全部历史数据
                            page_size_to_fetch = 2000
                    except Exception:
                        page_size_to_fetch = 2000
                else:
                    page_size_to_fetch = 2000
        else:
            page_size_to_fetch = 2000

        # ================= 2. 如果本地没有历史数据，或者需要更新（与今天日期不一致），则从接口获取 =================
        if not history_success or need_api_update:
            his_url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNHisNetList?FCODE={code}&pageIndex=1&pageSize={page_size_to_fetch}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0"
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
                        
                        # 如果是增量更新并且本地已有历史数据，进行拼接和去重
                        if page_size_to_fetch < 2000 and history_data:
                            old_dates = history_data.get('dates') or []
                            old_navs = history_data.get('navs') or []
                            
                            # 合并并以日期为键去重
                            combined = {}
                            for d, n in zip(old_dates, old_navs):
                                combined[d] = n
                            for d, n in zip(dates, navs):
                                combined[d] = n
                            
                            # 重新按日期降序排列
                            sorted_items = sorted(combined.items(), key=lambda x: x[0], reverse=True)
                            merged_dates = [item[0] for item in sorted_items]
                            merged_navs = [item[1] for item in sorted_items]
                            
                            history_data = {'jzrq': latest_date, 'navs': merged_navs, 'dates': merged_dates}
                        else:
                            # 首次抓取或全量更新
                            history_data = {'jzrq': latest_date, 'navs': navs, 'dates': dates}
                        
                        data['new_history'] = history_data
                        self.history_cache[code] = history_data
                        
                        # 保存合并/全量后的数据到本地数据库
                        self.db.save_history(code, latest_date, history_data['navs'], history_data['dates'])
                        
                        data['jzrq'] = latest_date
                        data['dwjz'] = str(history_data['navs'][0])
                        data['gsz'] = str(history_data['navs'][0])
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
            if self.isInterruptionRequested(): return
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if self.isInterruptionRequested(): return
                data = res.json()
                if data.get("Success") and data.get("Datas"):
                    all_indices = data["Datas"]
                    
                    # 更新全局板块映射库（从官方指数名称提取）
                    from utils import extract_fund_sector
                    for item in all_indices:
                        if self.isInterruptionRequested(): return
                        idx_name = item.get("INDEXNAME", "")
                        idx_code = item.get("INDEXCODE", "")
                        if idx_name:
                            sector = extract_fund_sector(idx_name, idx_code)
                            if sector:
                                 self.shared_sector_map[idx_code] = sector
                                 
                    valid_indices = []
                    seen_index_codes = set()
                    for item in all_indices:
                        if self.isInterruptionRequested(): return
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

                    if self.isInterruptionRequested(): return

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

                    if self.isInterruptionRequested(): return

                    combined_dict = {} # 最终合并后的字典
                    used_fund_codes = set()  # 全局去重：已被占用的基金代码

                    def add_to_list(source, short_tag, limit=10):
                        from utils import extract_fund_sector
                        count = 0
                        seen_sectors = set()
                        
                        for item in source:
                            if self.isInterruptionRequested(): return
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
                    if self.isInterruptionRequested(): return
                    add_to_list(low_pe, "PE低", 10)
                    if self.isInterruptionRequested(): return
                    add_to_list(high_pb, "PB高", 10)
                    if self.isInterruptionRequested(): return
                    add_to_list(low_pb, "PB低", 10)

                    if self.isInterruptionRequested(): return
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
        if not self.isInterruptionRequested():
            self.valuation_signal.emit([], False)


def run_backtest(all_navs, buy_days, buy_drop_pct, target_profit_pct, hold_max=90):
    """
    模拟回测运算核心函数。
    """
    buy_drop = buy_drop_pct / 100.0
    target_profit = target_profit_pct / 100.0
    
    trades = []
    i = buy_days
    n = len(all_navs)
    while i < n:
        nav_today = all_navs[i]
        nav_past_max = max(all_navs[i - buy_days : i + 1])
        if nav_past_max == 0:
            i += 1
            continue
        drop = (nav_today - nav_past_max) / nav_past_max
        
        if drop <= -buy_drop:
            # 触发买入
            buy_nav = nav_today
            success = False
            actual_hold = 0
            sell_idx = i
            sell_nav = buy_nav
            
            for j in range(1, n - i):
                current_nav = all_navs[i + j]
                profit = (current_nav - buy_nav) / buy_nav
                
                # 7天内扣去1.5%赎回惩罚，所以止盈收益率需要比原目标高1.5%
                target = target_profit + 0.015 if j < 7 else target_profit
                if profit >= target:
                    success = True
                    actual_hold = j
                    sell_idx = i + j
                    sell_nav = current_nav
                    break
                    
                if j >= hold_max:
                    actual_hold = j
                    sell_idx = i + j
                    sell_nav = current_nav
                    break
            else:
                actual_hold = n - 1 - i
                if actual_hold > 0:
                    sell_idx = n - 1
                    sell_nav = all_navs[sell_idx]
                    
            # 计算实际到手收益
            final_profit = (sell_nav - buy_nav) / buy_nav if buy_nav != 0 else 0
            if actual_hold < 7:
                final_profit -= 0.015  # 惩罚赎回费
                
            trades.append({
                "success": success,
                "profit": final_profit
            })
            i = sell_idx + 1
        else:
            i += 1
            
    total_trades = len(trades)
    if total_trades == 0:
        return 0.0, 0.0, 0, False
        
    wins = sum(1 for t in trades if t["success"])
    win_rate = wins / total_trades * 100.0
    avg_profit = sum(t["profit"] for t in trades) / total_trades * 100.0
    is_robust = total_trades >= 5
    
    return win_rate, avg_profit, total_trades, is_robust


def optimize_via_genetic_algorithm(all_navs, progress_callback=None, interrupted_callback=None):
    """
    使用遗传算法（Genetic Algorithm）进行基金策略参数寻优。
    """
    if len(all_navs) < 20:
        return None
        
    hold_min = 7
    hold_max = 90
    
    # 遗传算法超参数
    pop_size = 40
    generations = 25
    crossover_rate = 0.8
    mutation_rate = 0.2
    elitism_count = 2
    
    memo = {}
    
    def evaluate(chrom):
        days = int(round(chrom[0]))
        days = max(2, min(12, days))
        drop_pct = round(chrom[1], 2)
        drop_pct = max(0.5, min(8.0, drop_pct))
        profit_pct = round(chrom[2], 2)
        profit_pct = max(0.5, min(8.0, profit_pct))
        
        key = (days, drop_pct, profit_pct)
        if key in memo:
            return memo[key]
            
        win_rate, avg_profit, total_trades, is_robust = run_backtest(
            all_navs, days, drop_pct, profit_pct, hold_max
        )
        
        if total_trades == 0:
            score = (-2, 0.0, -9999.0, 0)
        else:
            score = (1 if is_robust else 0, win_rate, avg_profit, total_trades)
            
        res = {
            'buy_days': days,
            'buy_drop': drop_pct,
            'target_profit': profit_pct,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'avg_profit': avg_profit,
            'score': score
        }
        memo[key] = res
        return res

    # 1. 初始化种群
    population = []
    for _ in range(pop_size):
        days = random.randint(2, 12)
        drop = random.uniform(0.5, 8.0)
        profit = random.uniform(0.5, 8.0)
        population.append([days, drop, profit])
        
    best_overall = None
    
    # 2. 进化迭代
    for gen in range(generations):
        if interrupted_callback and interrupted_callback():
            return None
            
        # 评估所有个体
        evaluated_pop = []
        for chrom in population:
            eval_res = evaluate(chrom)
            evaluated_pop.append((chrom, eval_res))
            
        # 按照 score 排序
        evaluated_pop.sort(key=lambda x: x[1]['score'], reverse=True)
        
        # 更新历史最佳
        current_best = evaluated_pop[0][1]
        if best_overall is None or current_best['score'] > best_overall['score']:
            best_overall = current_best
            
        # 进度反馈
        if progress_callback:
            progress_callback(gen + 1, generations)
            
        # 产生新一代
        next_generation = []
        
        # 保留精英
        for i in range(elitism_count):
            next_generation.append(evaluated_pop[i][0])
            
        # 锦标赛选择
        def tournament_select(pool):
            candidates = random.sample(pool, 3)
            candidates.sort(key=lambda x: x[1]['score'], reverse=True)
            return candidates[0][0]
            
        while len(next_generation) < pop_size:
            p1 = tournament_select(evaluated_pop)
            p2 = tournament_select(evaluated_pop)
            
            # 交叉
            if random.random() < crossover_rate:
                c1_days = random.choice([p1[0], p2[0]])
                c2_days = random.choice([p1[0], p2[0]])
                
                gamma = random.random()
                c1_drop = gamma * p1[1] + (1 - gamma) * p2[1]
                c2_drop = (1 - gamma) * p1[1] + gamma * p2[1]
                
                gamma = random.random()
                c1_profit = gamma * p1[2] + (1 - gamma) * p2[2]
                c2_profit = (1 - gamma) * p1[2] + gamma * p2[2]
            else:
                c1_days, c1_drop, c1_profit = p1[0], p1[1], p1[2]
                c2_days, c2_drop, c2_profit = p2[0], p2[1], p2[2]
                
            c1 = [c1_days, c1_drop, c1_profit]
            c2 = [c2_days, c2_drop, c2_profit]
            
            # 变异
            def mutate(chrom):
                ch_days, ch_drop, ch_profit = chrom
                if random.random() < mutation_rate:
                    ch_days += random.choice([-2, -1, 1, 2])
                    ch_days = max(2, min(12, ch_days))
                if random.random() < mutation_rate:
                    ch_drop += random.gauss(0, 0.5)
                    ch_drop = max(0.5, min(8.0, ch_drop))
                if random.random() < mutation_rate:
                    ch_profit += random.gauss(0, 0.5)
                    ch_profit = max(0.5, min(8.0, ch_profit))
                return [ch_days, ch_drop, ch_profit]
                
            next_generation.append(mutate(c1))
            if len(next_generation) < pop_size:
                next_generation.append(mutate(c2))
                
        population = next_generation
        
    if best_overall and best_overall['total_trades'] > 0:
        return {
            'buy_days': best_overall['buy_days'],
            'buy_drop': best_overall['buy_drop'],
            'target_profit': best_overall['target_profit'],
            'hold_min': hold_min,
            'hold_max': hold_max,
            'win_rate': best_overall['win_rate'],
            'total_trades': best_overall['total_trades'],
            'avg_profit': best_overall['avg_profit']
        }
    return None


class OptimalStrategyFinder(QThread):
    """基金策略参数后台寻优线程"""
    progress_signal = Signal(int, int)  # current_step, total_steps
    result_signal = Signal(dict)        # 最优参数结果字典
    
    def __init__(self, code, name, history_data, db=None):
        super().__init__()
        self.code = code
        self.name = name
        self.all_navs = history_data.get("navs", [])[::-1]
        self.all_dates = history_data.get("dates", [])[::-1]
        self.db = db if db else FundHistoryDB()
        
        # 兼容无日期情况
        if not self.all_dates and self.all_navs:
            self.all_dates = [f"D-{len(self.all_navs)-i}" for i in range(len(self.all_navs))]

    def run(self):
        if len(self.all_navs) < 20:  # 历史数据太少，无法寻优
            self.result_signal.emit({"error": "历史数据太少，至少需要20个交易日"})
            return
            
        def progress_cb(gen, total_gen):
            if self.isInterruptionRequested():
                return
            self.progress_signal.emit(gen, total_gen)
            
        best = optimize_via_genetic_algorithm(self.all_navs, progress_cb, self.isInterruptionRequested)
        
        if not best:
            self.result_signal.emit({"error": "在此历史数据范围内未能触发任何交易信号"})
            return
            
        # 保存最优参数到本地 SQLite 数据库
        self.db.save_optimal_strategy(
            self.code, self.name, 
            best["buy_days"], best["buy_drop"], best["target_profit"],
            best["hold_min"], best["hold_max"], 
            best["win_rate"], best["total_trades"], best["avg_profit"]
        )
        
        self.result_signal.emit({
            "success": True,
            "buy_days": best["buy_days"],
            "buy_drop": best["buy_drop"],
            "target_profit": best["target_profit"],
            "hold_min": best["hold_min"],
            "hold_max": best["hold_max"],
            "win_rate": best["win_rate"],
            "total_trades": best["total_trades"],
            "avg_profit": best["avg_profit"]
        })


def optimize_single_fund_task(code, name, all_navs):
    """
    单只基金策略参数寻优计算任务（在子进程中运行的纯计算）
    """
    best = optimize_via_genetic_algorithm(all_navs)
    if not best:
        return None
        
    return {
        'code': code,
        'name': name,
        'buy_days': best['buy_days'],
        'buy_drop': best['buy_drop'],
        'target_profit': best['target_profit'],
        'hold_min': best['hold_min'],
        'hold_max': best['hold_max'],
        'win_rate': best['win_rate'],
        'total_trades': best['total_trades'],
        'avg_profit': best['avg_profit']
    }


class BatchOptimalStrategyFinder(QThread):
    """批量基金策略参数后台寻优线程（使用 ProcessPoolExecutor 榨干多核 CPU）"""
    progress_signal = Signal(int, int, str)  # current_fund_idx, total_funds, current_fund_name
    result_signal = Signal(dict)        # 结果汇总
    
    def __init__(self, test_funds, history_cache, db=None):
        super().__init__()
        self.test_funds = test_funds  # list of (code, name)
        self.history_cache = history_cache
        self.db = db if db else FundHistoryDB()
        
    def run(self):
        total_funds = len(self.test_funds)
        success_count = 0
        
        # 1. 准备并行任务所需数据
        tasks = []
        for code, name in self.test_funds:
            if self.isInterruptionRequested():
                return
                
            history_data = self.history_cache.get(code)
            if not history_data:
                history_data = self.db.get_history(code)
                
            if not history_data or not history_data.get('navs'):
                continue
                
            all_navs = history_data.get('navs', [])[::-1]
            if len(all_navs) < 20:
                continue
                
            tasks.append((code, name, all_navs))
            
        if not tasks:
            self.result_signal.emit({'success_count': 0, 'total_funds': total_funds})
            return
            
        to_compute_total = len(tasks)
        results_list = []
        
        # 2. 启动 ProcessPoolExecutor 多进程执行纯数学计算
        max_workers = min(os.cpu_count() or 4, to_compute_total)
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # 提交任务
            future_to_name = {
                executor.submit(optimize_single_fund_task, code, name, navs): name
                for code, name, navs in tasks
            }
            
            completed_count = 0
            for future in as_completed(future_to_name):
                if self.isInterruptionRequested():
                    # 用户取消了任务，强制关闭进程池
                    executor.shutdown(wait=False, cancel_futures=True)
                    return
                    
                name = future_to_name[future]
                try:
                    res = future.result()
                    if res:
                        results_list.append(res)
                except Exception as e:
                    print(f"[多进程寻优异常] 基金 {name} 计算出错: {e}")
                    
                completed_count += 1
                self.progress_signal.emit(completed_count, to_compute_total, name)
                
        # 3. 计算完毕后，在当前 QThread 线程中单线程顺序写入数据库，规避并发写冲突
        for res in results_list:
            if self.isInterruptionRequested():
                return
            self.db.save_optimal_strategy(
                res['code'], res['name'], 
                res['buy_days'], res['buy_drop'], res['target_profit'],
                res['hold_min'], res['hold_max'], 
                res['win_rate'], res['total_trades'], res['avg_profit']
            )
            success_count += 1
            
        self.result_signal.emit({'success_count': success_count, 'total_funds': total_funds})

