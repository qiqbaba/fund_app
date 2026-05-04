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
            conn.commit()
    
    def get_history(self, fund_code):
        """获取基金的历史净值数据
        返回: {'jzrq': str, 'navs': [float, ...]} 或 None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT jzrq, nav_list FROM fund_history WHERE fund_code = ?', (fund_code,))
            row = cursor.fetchone()
            
            if row:
                jzrq, nav_json = row
                try:
                    navs = json.loads(nav_json)
                    return {'jzrq': jzrq, 'navs': navs}
                except json.JSONDecodeError:
                    return None
            return None
    
    def save_history(self, fund_code, jzrq, navs):
        """保存或更新基金的历史净值数据
        fund_code: 基金代码
        jzrq: 净值日期
        navs: 净值列表 [float, float, ...]
        """
        import time
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            nav_json = json.dumps(navs)
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
