# threads.py
import json
import re
import time
import random
import requests
from PySide6.QtCore import QThread, Signal

class RankingFetcher(QThread):
    """抓取当日指数/板块场外ETF涨跌排行榜的线程（带板块智能去重去同质化）"""
    ranking_signal = Signal(list, list) 

    def __init__(self, code_to_name_dict):
        super().__init__()
        self.code_to_name_dict = code_to_name_dict

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
        try:
            url_top = "http://api.fund.eastmoney.com/FundGuZhi/GetFundGZList?type=5&sort=3&orderType=desc&canbuy=0&pageIndex=1&pageSize=200"
            r_top = requests.get(url_top, headers=headers, timeout=5)
            top_raw_list = r_top.json().get("Data", {}).get("list", [])
            
            url_bot = "http://api.fund.eastmoney.com/FundGuZhi/GetFundGZList?type=5&sort=3&orderType=asc&canbuy=0&pageIndex=1&pageSize=200"
            r_bot = requests.get(url_bot, headers=headers, timeout=5)
            bot_raw_list = r_bot.json().get("Data", {}).get("list", [])
            
            top_list = self.filter_distinct_sectors(top_raw_list, 10)
            bot_list = self.filter_distinct_sectors(bot_raw_list, 10)
            
            self.ranking_signal.emit(top_list, bot_list)
        except Exception:
            self.ranking_signal.emit([], [])

    def filter_distinct_sectors(self, fund_list, limit=10):
        keywords = [
            '半导体', '芯片', '白酒', '中药', '医药', '医疗', '生物', '新能源车', '新能源', '光伏', 
            '电池', '军工', '券商', '证券', '银行', '煤炭', '有色', '黄金', '钢铁', '传媒', 
            '游戏', '动漫', '汽车', '消费', '食品', '饮料', '农业', '养殖', '地产', '房地产', 
            '基建', '环保', '纳斯达克', '纳指', '标普', '恒生科技', '恒生', '沪深300', '中证500', 
            '中证1000', '中证2000', 'A500', '上证50', '红利', '科创50', '科创100', '创业板', 
            '信创', '软件', '计算机', '人工智能', 'AI', '大数据', '云计算', '通信', '5G', '机械', 
            '化工', '旅游', '家电', '微盘', '物联网',
            '互联网', '科技', '碳中和', '原油', '石油', '天然气', '能源', '稀土', '锂', 
            '酒', '猪肉', '畜牧', '电力', '水利', '交通运输', '物流', '航空', '船舶',
            '保险', '期货', '基本面', '价值', '成长', '深证', '上证', '中证A', 
            '机器人', '无人驾驶', '智能', '数字经济', '数据要素', '网络安全', '信息安全',
            '港股', '日经', '德国', '法国', '越南', '印度', '东南亚', '亚太'
        ]
        
        # 基金公司前缀清理列表
        company_prefixes = (
            '华夏|易方达|广发|富国|招商|嘉实|南方|博时|鹏华|汇添富|天弘|华安|国泰|银华|'
            '工银|建信|交银|景顺长城|景顺|中欧|华宝|大成|前海开源|国联安|兴银|永赢|中银|'
            '万家|中融|国金|平安|浦银安盛|长城|长信|长盛|东方|方正富邦|海富通|华泰柏瑞|'
            '华泰|汇安|金鹰|民生加银|民生|农银汇理|农银|诺安|诺德|融通|上投摩根|上投|'
            '泰达宏利|泰达|泰康|西部利得|西部|信达澳亚|信达澳银|信达|兴全|兴业|'
            '鑫元|银河|英大|圆信永丰|招商|中海|中加|中金|中信保诚|中信建投|中信|中邮'
        )
        
        result = []
        seen_sectors = set()
        
        for item in fund_list:
            if len(result) >= limit: break
            
            code = item.get("bzdm", "")
            name = self.code_to_name_dict.get(code, "")
            if not name: continue
            
            matched_sector = None
            # 第一轮：直接用关键词匹配基金全名
            for kw in keywords:
                if kw in name:
                    matched_sector = kw
                    break
            
            # 第二轮：清理后再匹配关键词（去掉公司名和指数系列前缀）
            if not matched_sector:
                clean_name = re.sub(r'(ETF|LOF|联接|发起式|指数|增强|型|证券投资基金|[A-E]\b|\d+).*$', '', name)
                clean_name = re.sub(r'^(' + company_prefixes + ')', '', clean_name)
                clean_name = re.sub(r'^(中证|国证|上证|深证|港股通|CES|CS|MSCI|标普)', '', clean_name)
                clean_name = clean_name.strip()
                
                for kw in keywords:
                    if kw in clean_name:
                        matched_sector = kw
                        break
            
            # 第三轮：取清理后名称的前4个字作为板块
            if not matched_sector:
                matched_sector = clean_name[:4] if len(clean_name) >= 4 else clean_name
                if not matched_sector: matched_sector = "其他指数"
                
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

    def __init__(self, fund_codes, config, history_cache, code_to_name_dict):
        super().__init__()
        self.fund_codes = fund_codes
        self.config = config
        self.history_cache = history_cache
        self.code_to_name_dict = code_to_name_dict

    def run(self):
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"
        })

        for i, code in enumerate(self.fund_codes):
            if self.isInterruptionRequested(): break
            
            saved_name = self.config.get("funds_info", {}).get(code, {}).get("name", "")
            if not saved_name:
                saved_name = self.code_to_name_dict.get(code, code)
                
            data = {'fundcode': code, 'name': saved_name}
            
            # ================= 1. 优先获取历史净值数据 =================
            his_url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNHisNetList?FCODE={code}&pageIndex=1&pageSize=600&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0"
            history_success = False
            
            try:
                r_his = session.get(his_url, timeout=5)
                his_data = r_his.json()
                navs = []
                
                if his_data.get("ErrCode") == 0 and his_data.get("Datas"):
                    for item in his_data.get("Datas"):
                        try:
                            val = item.get("DWJZ")
                            if val: navs.append(float(val))
                        except ValueError: pass
                    
                    if navs:
                        latest_item = his_data.get("Datas")[0]
                        latest_date = latest_item.get("FSRQ", "")
                        
                        data['new_history'] = {'jzrq': latest_date, 'navs': navs}
                        self.history_cache[code] = data['new_history']
                        
                        data['jzrq'] = latest_date
                        data['dwjz'] = latest_item.get("DWJZ", "")
                        data['gsz'] = latest_item.get("DWJZ", "")
                        data['gszzl'] = latest_item.get("JZZZL", "")
                        data['gztime'] = f"{latest_date} (实际净值)"
                        history_success = True
            except Exception:
                pass

            # ================= 2. 尝试获取实时估值数据 =================
            timestamp = int(time.time() * 1000)
            url = f"http://fundgz.1234567.com.cn/js/{code}.js?rt={timestamp}"
            
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
            except Exception:
                pass

            if not history_success and 'gsz' not in data:
                self.error_signal.emit(code, "暂无数据")
                continue

            # ================= 3. 计算涨跌幅与百分位 =================
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
                
            self.update_signal.emit(data)

            if i < len(self.fund_codes) - 1:
                time.sleep(random.uniform(0.1, 0.3)) 
                
        session.close()
        self.finish_signal.emit()

class ValuationFetcher(QThread):
    """抓取全市场指数估值榜 (PE/PB 最高/最低) 的线程"""
    valuation_signal = Signal(list)

    def __init__(self, all_funds_dict):
        super().__init__()
        self.all_funds_dict = all_funds_dict

    def find_fund_for_index(self, index_code, index_name):
        """尝试为指数找到一个对应的场外联接基金代码，优先联接基金"""
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

        # 清理指数名称，生成多个搜索关键词
        clean_name = index_name.replace("指数", "").replace("CS", "").replace("TMT50", "TMT").strip()
        short_name = clean_name[:2] if len(clean_name) >= 2 else ""
        search_keys = [index_code, index_name]
        if clean_name and clean_name != index_name:
            search_keys.append(clean_name)
        if short_name:
            search_keys.append(short_name)

        def is_otc_fund(code):
            """判断是否为场外基金代码（非场内ETF）"""
            return code.startswith('0') or code.startswith('2') or code.startswith('3')

        # 第一优先级：联接基金（一定是场外，数据接口一定支持）
        for key in search_keys:
            for name, code in self.all_funds_dict.items():
                if key in name and "联接" in name:
                    return code

        # 第二优先级：场外ETF基金（代码以0开头等）
        for key in search_keys:
            for name, code in self.all_funds_dict.items():
                if key in name and "ETF" in name and is_otc_fund(code):
                    return code

        # 第三优先级：任何ETF（包括场内，可能查不到实时估值但能查历史净值）
        for key in search_keys:
            for name, code in self.all_funds_dict.items():
                if key in name and "ETF" in name:
                    return code
                    
        return index_code  # 没找到就用指数代码兜底


    def extract_sector_from_name(self, index_name):
        """从指数名称中提取板块关键词"""
        sector_keywords = [
            '半导体', '芯片', '白酒', '中药', '医药', '医疗', '生物', '新能源车', '新能源', '光伏',
            '电池', '军工', '券商', '证券', '银行', '煤炭', '有色', '黄金', '钢铁', '传媒',
            '游戏', '汽车', '消费', '食品', '饮料', '农业', '地产', '房地产', '基建', '环保',
            '互联网', '科技', '碳中和', '原油', '能源', '稀土', '红利', '创业板',
            '信创', '软件', '计算机', '人工智能', '机械', '化工', '旅游', '家电',
            '机器人', '智能', '数字经济', '港股', '保险', '电力', '通信', '物联网'
        ]
        for kw in sector_keywords:
            if kw in index_name:
                return kw
        # 清理后取核心名称
        clean = index_name.replace("指数", "").replace("CS", "").replace("中证", "").replace("国证", "").strip()
        return clean[:4] if len(clean) >= 2 else index_name

    def run(self):
        url = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNIndexValuationList?pageIndex=1&pageSize=500&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15",
            "Referer": "https://unitmob.1234567.com.cn/"
        }
        try:
            res = requests.get(url, headers=headers, timeout=10)
            data = res.json()
            if data.get("Success") and data.get("Datas"):
                all_indices = data["Datas"]
                
                # 过滤掉 PE/PB 为空的数据
                valid_indices = []
                for item in all_indices:
                    try:
                        pe = item.get("PETTM")
                        pb = item.get("PB")
                        if pe and pe != "--" and pb and pb != "--":
                            item["pe_float"] = float(pe)
                            item["pb_float"] = float(pb)
                            item["pe_pct_float"] = float(item.get("PEP", 0)) * 100
                            valid_indices.append(item)
                    except: continue

                # 排序获取四类 Top 10
                high_pe = sorted(valid_indices, key=lambda x: x["pe_float"], reverse=True)[:10]
                low_pe = sorted(valid_indices, key=lambda x: x["pe_float"])[:10]
                high_pb = sorted(valid_indices, key=lambda x: x["pb_float"], reverse=True)[:10]
                low_pb = sorted(valid_indices, key=lambda x: x["pb_float"])[:10]

                combined = []
                seen_codes = set()

                def add_to_list(source, tag):
                    for item in source:
                        code = item["INDEXCODE"]
                        index_name = item["INDEXNAME"]
                        fund_code = self.find_fund_for_index(code, index_name)
                        sector = self.extract_sector_from_name(index_name)
                        res_item = {
                            "bzdm": code, 
                            "fund_code": fund_code,
                            "fund_name": index_name,
                            "pe": item["PETTM"],
                            "pb": item["PB"],
                            "pe_percentile": f"{item['pe_pct_float']:.2f}",
                            "valuation_tag": tag,
                            "extracted_sector": sector
                        }
                        combined.append(res_item)

                add_to_list(high_pe, "🔥 PE最高")
                add_to_list(low_pe, "❄️ PE最低")
                add_to_list(high_pb, "🔥 PB最高")
                add_to_list(low_pb, "❄️ PB最低")

                self.valuation_signal.emit(combined)
        except Exception:
            self.valuation_signal.emit([])