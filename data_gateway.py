import requests
import json
import re
import time

class FundDataGateway:
    """
    抽象数据网关层，用于管理基金历史数据和实时估值的多渠道抓取。
    当天天基金接口不可用或返回网络繁忙时，能够以毫秒级自动重试并降级切换至备用链路。
    """
    def __init__(self, session=None, history_source="Auto", valuation_source="Auto"):
        self.session = session if session else requests.Session()
        # 初始化默认头部。核心：必须使用移动端 User-Agent 以免天天基金移动端 API 拒绝访问
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"
        })
        self.history_source = history_source
        self.valuation_source = valuation_source

    def fetch_history(self, code, page_size=2000):
        """
        高可用获取基金历史净值。
        顺序链路：天天基金移动端 -> 天天基金网页端F10 -> AkShare -> Tushare
        """
        source = self.history_source
        
        # 1. 尝试天天基金移动端 API
        def try_eastmoney_mobile():
            try:
                url = f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNHisNetList?FCODE={code}&pageIndex=1&pageSize={page_size}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0"
                r = self.session.get(url, timeout=3)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("ErrCode") == 0 and data.get("Datas"):
                        navs = []
                        dates = []
                        for item in data.get("Datas"):
                            try:
                                val = item.get("DWJZ")
                                dt = item.get("FSRQ")
                                if val is not None and dt:
                                    navs.append(float(val))
                                    dates.append(dt)
                            except (ValueError, TypeError):
                                pass
                        if navs and dates:
                            return {
                                'source': 'EastMoneyMobile',
                                'jzrq': dates[0],
                                'navs': navs,
                                'dates': dates,
                                'latest_item': data.get("Datas")[0]
                            }
            except Exception:
                pass
            return None

        # 2. 降级尝试天天基金网页端 F10 接口 (超高可用网页端 HTML 解析)
        def try_eastmoney_web():
            try:
                url = f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per={page_size}"
                r = self.session.get(url, timeout=3)
                if r.status_code == 200:
                    # 匹配日期和单位净值
                    # HTML格式：<tr><td>2026-05-22</td><td class='tor bold'>1.3090</td>...
                    pattern = r"<tr><td>(\d{4}-\d{2}-\d{2})</td><td class='tor bold'>([\d\.]*?)</td>"
                    items = re.findall(pattern, r.text)
                    if items:
                        navs = []
                        dates = []
                        for dt, val in items:
                            try:
                                navs.append(float(val))
                                dates.append(dt)
                            except ValueError:
                                pass
                        if navs and dates:
                            return {
                                'source': 'EastMoneyWeb',
                                'jzrq': dates[0],
                                'navs': navs,
                                'dates': dates,
                                'latest_item': {'DWJZ': str(navs[0]), 'FSRQ': dates[0], 'JZZZL': '0.00'}
                            }
            except Exception:
                pass
            return None

        # 3. 降级调用 AkShare 兜底（动态导入，防止本地未安装时抛出导入异常）
        def try_akshare():
            try:
                import akshare as ak
                df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
                if df is not None and not df.empty:
                    df_sorted = df.sort_values(by="净值日期", ascending=False)
                    navs = df_sorted["单位净值"].astype(float).tolist()
                    dates = df_sorted["净值日期"].astype(str).tolist()
                    # 截取所需大小
                    if len(navs) > page_size:
                        navs = navs[:page_size]
                        dates = dates[:page_size]
                    if navs and dates:
                        return {
                            'source': 'AkShare',
                            'jzrq': dates[0],
                            'navs': navs,
                            'dates': dates,
                            'latest_item': {'DWJZ': str(navs[0]), 'FSRQ': dates[0], 'JZZZL': '0.00'}
                        }
            except Exception:
                pass
            return None

        # 4. 降级调用 Tushare 兜底
        def try_tushare():
            try:
                import tushare as ts
                pro = ts.pro_api()
                df = pro.fund_nav(ts_code=f"{code}.OF")
                if df is not None and not df.empty:
                    import pandas as pd
                    df_sorted = df.sort_values(by="end_date", ascending=False)
                    navs = df_sorted["unit_nav"].astype(float).tolist()
                    dates = pd.to_datetime(df_sorted["end_date"]).dt.strftime('%Y-%m-%d').tolist()
                    if len(navs) > page_size:
                        navs = navs[:page_size]
                        dates = dates[:page_size]
                    if navs and dates:
                        return {
                            'source': 'Tushare',
                            'jzrq': dates[0],
                            'navs': navs,
                            'dates': dates,
                            'latest_item': {'DWJZ': str(navs[0]), 'FSRQ': dates[0], 'JZZZL': '0.00'}
                        }
            except Exception:
                pass
            return None

        if source == "EastMoneyMobile":
            return try_eastmoney_mobile()
        elif source == "EastMoneyWeb":
            return try_eastmoney_web()
        elif source == "AkShare":
            return try_akshare()
        elif source == "Tushare":
            return try_tushare()
        else: # "Auto"
            res = try_eastmoney_mobile()
            if res: return res
            res = try_eastmoney_web()
            if res: return res
            res = try_akshare()
            if res: return res
            res = try_tushare()
            return res

    def fetch_valuation(self, code):
        """
        高可用获取基金实时估值。
        顺序链路：天天基金 -> 新浪财经 -> 腾讯财经 -> 网易财经
        """
        source = self.valuation_source
        timestamp = int(time.time() * 1000)
        
        # 1. 尝试天天基金估值
        def try_eastmoney_gz():
            try:
                url = f"http://fundgz.1234567.com.cn/js/{code}.js?rt={timestamp}"
                r = self.session.get(url, timeout=2)
                if r.status_code == 200:
                    match = re.search(r'jsonpgz\((.*?)\);', r.text)
                    if match:
                        gz_data = json.loads(match.group(1))
                        return {
                            'source': 'EastMoneyGz',
                            'name': gz_data.get('name'),
                            'jzrq': gz_data.get('jzrq'),
                            'dwjz': gz_data.get('dwjz'),
                            'gsz': gz_data.get('gsz'),
                            'gszzl': gz_data.get('gszzl'),
                            'gztime': gz_data.get('gztime')
                        }
            except Exception:
                pass
            return None

        # 2. 降级尝试新浪财经接口 (真实参数结构已修正)
        # 返回格式如：var hq_str_fu_000001="华夏成长混合A,16:04:00,1.2966,1.2870,3.8600,0,0.7459,2026-05-22,1.3065,1.5152";
        def try_sina_gz():
            try:
                url = f"http://hq.sinajs.cn/list=fu_{code}"
                headers = {"Referer": "https://finance.sina.com.cn"}
                r = self.session.get(url, headers=headers, timeout=2)
                if r.status_code == 200:
                    match = re.search(r'hq_str_fu_\d+="([^"]+)"', r.text)
                    if match:
                        parts = match.group(1).split(',')
                        if len(parts) >= 8:
                            name = parts[0]
                            v_time = parts[1]
                            gsz = parts[2]
                            dwjz = parts[3] # 昨日实际净值
                            gszzl = parts[6] # 估值涨跌幅 (%)
                            jzrq = parts[7] # 估值日期
                            
                            gztime = f"{jzrq} {v_time}"
                            return {
                                'source': 'SinaGz',
                                'name': name,
                                'jzrq': jzrq,
                                'dwjz': dwjz,
                                'gsz': gsz,
                                'gszzl': gszzl,
                                'gztime': gztime
                            }
            except Exception:
                pass
            return None

        # 3. 降级尝试腾讯财经接口 (真实参数结构已修正)
        # 返回格式如：v_jj000001="000001~华夏成长混合~0.0000~0.0000~~1.3090~3.8820~1.7094~2026-05-22~";
        def try_tencent_gz():
            try:
                url = f"http://qt.gtimg.cn/q=jj{code}"
                r = self.session.get(url, timeout=2)
                if r.status_code == 200:
                    match = re.search(r'v_jj\d+="([^"]+)"', r.text)
                    if match:
                        parts = match.group(1).split('~')
                        if len(parts) >= 9:
                            name = parts[1]
                            gsz = parts[5] # 当前净值/估值
                            dwjz = gsz # 降级时用估值代替昨日净值
                            gszzl = parts[7] # 涨跌幅 (%)
                            jzrq = parts[8] # 估值日期
                            gztime = f"{jzrq} 15:00:00"
                            return {
                                'source': 'TencentGz',
                                'name': name,
                                'jzrq': jzrq,
                                'dwjz': dwjz,
                                'gsz': gsz,
                                'gszzl': gszzl,
                                'gztime': gztime
                            }
            except Exception:
                pass
            return None

        # 4. 降级尝试网易财经
        def try_netease_gz():
            try:
                url = f"https://api.money.126.net/data/feed/jj{code},money.api"
                r = self.session.get(url, timeout=2)
                if r.status_code == 200:
                    match = re.search(r'_ntes_quote_callback\((.*?)\);', r.text)
                    if match:
                        big_data = json.loads(match.group(1))
                        key = f"jj{code}"
                        if key in big_data:
                            gz_data = big_data[key]
                            name = gz_data.get('name')
                            gsz = str(gz_data.get('netValue'))
                            dwjz = str(gz_data.get('yestValue'))
                            gszzl = gz_data.get('percent')
                            if gszzl is not None:
                                gszzl = f"{float(gszzl) * 100:.2f}"
                            else:
                                gszzl = "0.00"
                            gztime = gz_data.get('time')
                            jzrq = gztime.split(' ')[0] if gztime and ' ' in gztime else gztime
                            return {
                                'source': 'NetEaseGz',
                                'name': name,
                                'jzrq': jzrq,
                                'dwjz': dwjz,
                                'gsz': gsz,
                                'gszzl': gszzl,
                                'gztime': gztime
                            }
            except Exception:
                pass
            return None

        if source == "EastMoneyGz":
            return try_eastmoney_gz()
        elif source == "SinaGz":
            return try_sina_gz()
        elif source == "TencentGz":
            return try_tencent_gz()
        elif source == "NetEaseGz":
            return try_netease_gz()
        else: # "Auto"
            res = try_eastmoney_gz()
            if res: return res
            res = try_sina_gz()
            if res: return res
            res = try_tencent_gz()
            if res: return res
            res = try_netease_gz()
            return res
