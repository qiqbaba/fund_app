# db_manager.py
import sqlite3
import json
import os
from config import BASE_DIR

DB_FILE = os.path.join(BASE_DIR, "fund_history.db")

class FundHistoryDB:
    """管理基金历史净值数据的 SQLite 数据库"""
    
    def __init__(self):
        self.db_path = DB_FILE
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 创建基金历史数据表
            # fund_code: 基金代码
            # jzrq: 净值日期（最新的日期）
            # nav_list: JSON 格式的净值列表
            # update_time: 数据更新时间戳
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fund_history (
                    fund_code TEXT PRIMARY KEY,
                    jzrq TEXT,
                    nav_list TEXT,
                    update_time REAL
                )
            ''')
            # 创建基金最优策略参数表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fund_optimal_strategy (
                    fund_code TEXT PRIMARY KEY,
                    fund_name TEXT,
                    buy_days INTEGER,
                    buy_drop REAL,
                    target_profit REAL,
                    hold_min INTEGER,
                    hold_max INTEGER,
                    win_rate REAL,
                    total_trades INTEGER,
                    avg_profit REAL,
                    update_time REAL
                )
            ''')
            conn.commit()
    
    def get_history(self, fund_code):
        """获取基金的历史净值数据
        返回: {'jzrq': str, 'navs': [float, ...], 'dates': [str, ...]} 或 None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT jzrq, nav_list FROM fund_history WHERE fund_code = ?', (fund_code,))
            row = cursor.fetchone()
            
            if row:
                jzrq, nav_json = row
                try:
                    data_list = json.loads(nav_json)
                    if not data_list:
                        return None
                    
                    # 检查是否是新格式 [[date, nav], ...]
                    if isinstance(data_list[0], list) and len(data_list[0]) == 2:
                        dates = [item[0] for item in data_list]
                        navs = [item[1] for item in data_list]
                        return {'jzrq': jzrq, 'navs': navs, 'dates': dates}
                    else:
                        # 旧格式 [nav, nav, ...]
                        return {'jzrq': jzrq, 'navs': data_list, 'dates': []}
                except (json.JSONDecodeError, IndexError):
                    return None
            return None
    
    def save_history(self, fund_code, jzrq, navs, dates=None):
        """保存或更新基金的历史净值数据
        fund_code: 基金代码
        jzrq: 净值日期
        navs: 净值列表 [float, float, ...]
        dates: 日期列表 [str, str, ...]
        """
        import time
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if dates and len(dates) == len(navs):
                # 新格式：存储 [date, nav] 对
                data_to_save = [[d, n] for d, n in zip(dates, navs)]
            else:
                # 兼容旧格式或无日期情况
                data_to_save = navs
                
            nav_json = json.dumps(data_to_save)
            current_time = time.time()
            
            cursor.execute('''
                INSERT OR REPLACE INTO fund_history 
                (fund_code, jzrq, nav_list, update_time)
                VALUES (?, ?, ?, ?)
            ''', (fund_code, jzrq, nav_json, current_time))
            conn.commit()
    
    def delete_history(self, fund_code):
        """删除基金的历史数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM fund_history WHERE fund_code = ?', (fund_code,))
            conn.commit()
    
    def clear_all(self):
        """清空所有历史数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM fund_history')
            conn.commit()
    
    def get_all_fund_codes(self):
        """获取数据库中所有基金代码"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT fund_code FROM fund_history')
            return [row[0] for row in cursor.fetchall()]

    def save_optimal_strategy(self, fund_code, fund_name, buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit):
        """保存或更新基金的最优策略参数寻优结果"""
        import time
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            current_time = time.time()
            cursor.execute('''
                INSERT OR REPLACE INTO fund_optimal_strategy 
                (fund_code, fund_name, buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit, update_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (fund_code, fund_name, buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit, current_time))
            conn.commit()

    def get_optimal_strategy(self, fund_code):
        """获取基金的最优策略参数
        返回: dict 或 None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit, update_time 
                FROM fund_optimal_strategy WHERE fund_code = ?
            ''', (fund_code,))
            row = cursor.fetchone()
            if row:
                return {
                    'buy_days': row[0],
                    'buy_drop': row[1],
                    'target_profit': row[2],
                    'hold_min': row[3],
                    'hold_max': row[4],
                    'win_rate': row[5],
                    'total_trades': row[6],
                    'avg_profit': row[7],
                    'update_time': row[8] if len(row) > 8 else None
                }
            return None

    def get_all_optimal_strategies(self):
        """获取所有有最优策略参数的基金
        返回: dict, {fund_code: {'buy_days': ..., 'fund_name': ...}}
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT fund_code, fund_name, buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit, update_time 
                FROM fund_optimal_strategy
            ''')
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                result[row[0]] = {
                    'fund_name': row[1],
                    'buy_days': row[2],
                    'buy_drop': row[3],
                    'target_profit': row[4],
                    'hold_min': row[5],
                    'hold_max': row[6],
                    'win_rate': row[7],
                    'total_trades': row[8],
                    'avg_profit': row[9],
                    'update_time': row[10] if len(row) > 10 else None
                }
            return result
