# db_manager.py
import sqlite3
import json
import os
import queue
import threading
import time
from core.config import BASE_DIR

DB_FILE = os.path.join(BASE_DIR, "fund_history.db")

class FundHistoryDB:
    """管理基金历史净值数据的 SQLite 数据库（单例线程安全队列版）"""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FundHistoryDB, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if FundHistoryDB._initialized:
            return
        self.db_path = DB_FILE
        self._init_db_schema()
        
        # 初始化轻量级线程安全任务队列
        self.task_queue = queue.Queue()
        # 启动唯一的后台写库守护线程
        self.db_thread = threading.Thread(target=self._db_worker, daemon=True, name="FundHistoryDB-Worker")
        self.db_thread.start()
        
        FundHistoryDB._initialized = True

    def _init_db_schema(self):
        """主线程初始化或检查数据库表结构，并执行必要的数据迁移"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            
            # 检查 fund_history 表是否存在以及是否包含 nav_list 字段
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fund_history'")
            table_exists = cursor.fetchone() is not None
            
            has_nav_list = False
            if table_exists:
                cursor.execute("PRAGMA table_info(fund_history)")
                columns = [row[1] for row in cursor.fetchall()]
                has_nav_list = "nav_list" in columns
                
            if table_exists and has_nav_list:
                print("[FundHistoryDB] 检测到旧版数据库结构，正在启动历史净值数据迁移流程...")
                try:
                    # 1. 创建新子表和索引
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS fund_nav_detail (
                            fund_code TEXT,
                            jzrq TEXT,
                            dwjz REAL,
                            PRIMARY KEY (fund_code, jzrq)
                        )
                    ''')
                    cursor.execute('''
                        CREATE INDEX IF NOT EXISTS idx_fund_nav_detail_lookup 
                        ON fund_nav_detail (fund_code, jzrq DESC)
                    ''')
                    
                    # 2. 读取所有的历史大 JSON 净值
                    cursor.execute("SELECT fund_code, jzrq, nav_list, update_time FROM fund_history")
                    rows = cursor.fetchall()
                    
                    all_nav_details = []
                    for fund_code, jzrq, nav_json, update_time in rows:
                        if not nav_json:
                            continue
                        try:
                            data_list = json.loads(nav_json)
                            if not data_list:
                                continue
                            
                            if isinstance(data_list[0], list) and len(data_list[0]) == 2:
                                # 新格式：[[date, nav], [date, nav], ...]
                                for d, n in data_list:
                                    if d and n is not None:
                                        all_nav_details.append((fund_code, d, float(n)))
                            else:
                                # 旧格式：[nav, nav, ...]
                                if data_list:
                                    all_nav_details.append((fund_code, jzrq, float(data_list[0])))
                        except Exception as e:
                            print(f"[Migration Warning] 解析基金 {fund_code} 历史 JSON 失败: {e}")
                            
                    # 3. 批量将数据导入 fund_nav_detail
                    if all_nav_details:
                        cursor.executemany('''
                            INSERT OR REPLACE INTO fund_nav_detail (fund_code, jzrq, dwjz)
                            VALUES (?, ?, ?)
                        ''', all_nav_details)
                        print(f"[FundHistoryDB] 成功迁移了 {len(all_nav_details)} 条净值数据到 fund_nav_detail。")
                        
                    # 4. 重建 fund_history 表以移除 nav_list 字段
                    cursor.execute("ALTER TABLE fund_history RENAME TO fund_history_old")
                    cursor.execute('''
                        CREATE TABLE fund_history (
                            fund_code TEXT PRIMARY KEY,
                            jzrq TEXT,
                            update_time REAL
                        )
                    ''')
                    cursor.execute('''
                        INSERT INTO fund_history (fund_code, jzrq, update_time)
                        SELECT fund_code, jzrq, update_time FROM fund_history_old
                    ''')
                    cursor.execute("DROP TABLE fund_history_old")
                    print("[FundHistoryDB] 数据库成功升级至一对多子表结构！")
                except Exception as ex:
                    print(f"[Migration Error] 数据库迁移中途失败: {ex}")
                    raise ex
            else:
                # 正常初始化（全新的库或已经升级完成的库）
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS fund_history (
                        fund_code TEXT PRIMARY KEY,
                        jzrq TEXT,
                        update_time REAL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS fund_nav_detail (
                        fund_code TEXT,
                        jzrq TEXT,
                        dwjz REAL,
                        PRIMARY KEY (fund_code, jzrq)
                    )
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_fund_nav_detail_lookup 
                    ON fund_nav_detail (fund_code, jzrq DESC)
                ''')
                
            # 创建基金最优策略参数表（保持原样）
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
            
            # 自动清理未来日期的历史数据记录（防止脏数据进入系统污染状态栏或报表）
            cursor.execute("DELETE FROM fund_nav_detail WHERE jzrq > date('now', 'localtime')")
            cursor.execute("DELETE FROM fund_history WHERE jzrq > date('now', 'localtime')")
            conn.commit()

    def _db_worker(self):
        """后台数据库写库守护线程核心循环"""
        conn = None
        cursor = None
        
        def reconnect():
            nonlocal conn, cursor
            is_initial = (conn is None)
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            
            if not is_initial:
                print("[FundHistoryDB-Worker] 正在重新连接数据库...")
                
            retry_interval = 2.0
            while True:
                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    try:
                        cursor.execute("PRAGMA journal_mode=WAL")
                    except sqlite3.Error:
                        pass
                    
                    if not is_initial:
                        print("[FundHistoryDB-Worker] 数据库连接重连成功！")
                    break
                except sqlite3.Error as e:
                    print(f"[FundHistoryDB-Worker] 数据库连接失败: {e}，将在 {retry_interval} 秒后重试...")
                    time.sleep(retry_interval)
                    retry_interval = min(retry_interval * 1.5, 30.0)

        # 初始连接
        reconnect()
            
        while True:
            try:
                task = self.task_queue.get()
                if task is None:
                    break
                
                func_name, args, kwargs, reply_queue = task
                
                max_retries = 3
                retry_count = 0
                while retry_count < max_retries:
                    try:
                        sync_func = getattr(self, f"_sync_{func_name}")
                        result = sync_func(conn, cursor, *args, **kwargs)
                        reply_queue.put((True, result))
                        break  # 执行成功，跳出重试循环
                    except sqlite3.Error as se:
                        retry_count += 1
                        print(f"[FundHistoryDB-Worker SqliteError] 执行 {func_name} 失败 (第 {retry_count}/{max_retries} 次尝试): {se}")
                        # 优雅关闭旧连接并自动休眠重连
                        reconnect()
                        if retry_count >= max_retries:
                            reply_queue.put((False, se))
                    except Exception as e:
                        # 其它非 sqlite3.Error 异常，例如 Python 逻辑错误，不重试，直接返回失败
                        reply_queue.put((False, e))
                        break
                self.task_queue.task_done()
            except Exception as e:
                print(f"[FundHistoryDB-Worker Exception] {e}")
                time.sleep(0.1)
                
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    def _submit_task(self, func_name, *args, **kwargs):
        """提交任务到队列，并同步阻塞等待返回结果"""
        reply_queue = queue.Queue()
        self.task_queue.put((func_name, args, kwargs, reply_queue))
        success, val = reply_queue.get()
        if success:
            return val
        else:
            raise val

    def _read_query(self, func, *args, **kwargs):
        """在前台线程使用临时连接就地执行只读查询"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            return func(conn, cursor, *args, **kwargs)

    # ==================== 外部公开的 API 接口 ====================

    def get_history(self, fund_code):
        """获取基金的历史净值数据"""
        return self._read_query(self._sync_get_history, fund_code)

    def save_history(self, fund_code, jzrq, navs, dates=None):
        """保存或更新基金的历史净值数据"""
        return self._submit_task('save_history', fund_code, jzrq, navs, dates=dates)

    def delete_history(self, fund_code):
        """删除基金的历史数据"""
        return self._submit_task('delete_history', fund_code)

    def clear_all(self):
        """清空所有历史数据"""
        return self._submit_task('clear_all')

    def get_all_fund_codes(self):
        """获取数据库中所有基金代码"""
        return self._read_query(self._sync_get_all_fund_codes)

    def save_optimal_strategy(self, fund_code, fund_name, buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit):
        """保存或更新基金的最优策略参数寻优结果"""
        return self._submit_task(
            'save_optimal_strategy', fund_code, fund_name, buy_days, buy_drop, 
            target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit
        )

    def get_optimal_strategy(self, fund_code):
        """获取基金的最优策略参数"""
        return self._read_query(self._sync_get_optimal_strategy, fund_code)

    def get_all_optimal_strategies(self):
        """获取所有有最优策略参数的基金"""
        return self._read_query(self._sync_get_all_optimal_strategies)

    def get_all_history(self):
        """一次性批量获取所有基金的历史净值数据（超高性能预加载）"""
        return self._read_query(self._sync_get_all_history)

    # ==================== 底层由 Worker 线程执行的同步实现 ====================

    def _sync_get_history(self, conn, cursor, fund_code):
        cursor.execute('''
            SELECT jzrq, dwjz FROM fund_nav_detail 
            WHERE fund_code = ? 
            ORDER BY jzrq DESC
        ''', (fund_code,))
        rows = cursor.fetchall()
        if not rows:
            return None
            
        dates = [row[0] for row in rows]
        navs = [row[1] for row in rows]
        latest_date = dates[0]
        
        return {'jzrq': latest_date, 'navs': navs, 'dates': dates}

    def _sync_save_history(self, conn, cursor, fund_code, jzrq, navs, dates=None):
        today_str = time.strftime('%Y-%m-%d')
        actual_jzrq = jzrq
        
        if dates and len(dates) == len(navs):
            # 新格式：批量写入 (fund_code, date, nav) 记录
            records = []
            for d, n in zip(dates, navs):
                if d and n is not None:
                    if d > today_str:
                        print(f"[FundHistoryDB Warning] 过滤掉未来日期脏数据: {fund_code} - {d} - {n}")
                        continue
                    records.append((fund_code, d, float(n)))
            if records:
                cursor.executemany('''
                    INSERT OR REPLACE INTO fund_nav_detail (fund_code, jzrq, dwjz)
                    VALUES (?, ?, ?)
                ''', records)
                # 重新校准最新日期为合法记录中的最大日期（records已按降序排列，第一条即为最新）
                actual_jzrq = records[0][1]
            else:
                # 没有任何合法记录，直接返回，不更新 fund_history
                return
        else:
            # 容错：如果未提供日期，尝试以 jzrq 写入单条数据
            if navs:
                if jzrq > today_str:
                    print(f"[FundHistoryDB Warning] 过滤掉单条未来日期脏数据: {fund_code} - {jzrq}")
                    return
                latest_nav = navs[0]
                cursor.execute('''
                    INSERT OR REPLACE INTO fund_nav_detail (fund_code, jzrq, dwjz)
                    VALUES (?, ?, ?)
                ''', (fund_code, jzrq, float(latest_nav)))
                actual_jzrq = jzrq
                
        current_time = time.time()
        
        # 更新基金主表中的最新日期和更新时间
        cursor.execute('''
            INSERT OR REPLACE INTO fund_history 
            (fund_code, jzrq, update_time)
            VALUES (?, ?, ?)
        ''', (fund_code, actual_jzrq, current_time))
        conn.commit()

    def _sync_delete_history(self, conn, cursor, fund_code):
        cursor.execute('DELETE FROM fund_history WHERE fund_code = ?', (fund_code,))
        cursor.execute('DELETE FROM fund_nav_detail WHERE fund_code = ?', (fund_code,))
        conn.commit()

    def _sync_clear_all(self, conn, cursor):
        cursor.execute('DELETE FROM fund_history')
        cursor.execute('DELETE FROM fund_nav_detail')
        conn.commit()

    def _sync_get_all_fund_codes(self, conn, cursor):
        cursor.execute('SELECT fund_code FROM fund_history')
        return [row[0] for row in cursor.fetchall()]

    def _sync_save_optimal_strategy(self, conn, cursor, fund_code, fund_name, buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit):
        current_time = time.time()
        cursor.execute('''
            INSERT OR REPLACE INTO fund_optimal_strategy 
            (fund_code, fund_name, buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (fund_code, fund_name, buy_days, buy_drop, target_profit, hold_min, hold_max, win_rate, total_trades, avg_profit, current_time))
        conn.commit()

    def _sync_get_optimal_strategy(self, conn, cursor, fund_code):
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

    def _sync_get_all_optimal_strategies(self, conn, cursor):
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

    def _sync_get_all_history(self, conn, cursor):
        cursor.execute('''
            SELECT fund_code, jzrq, dwjz FROM fund_nav_detail 
            ORDER BY fund_code, jzrq DESC
        ''')
        rows = cursor.fetchall()
        result = {}
        for fund_code, jzrq, dwjz in rows:
            if fund_code not in result:
                result[fund_code] = {'jzrq': jzrq, 'navs': [], 'dates': []}
            result[fund_code]['navs'].append(dwjz)
            result[fund_code]['dates'].append(jzrq)
        return result
