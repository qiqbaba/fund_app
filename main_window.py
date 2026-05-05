# main_window.py
import json
import os
import re
import time
import requests
import threading

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLineEdit, QPushButton, QTableView, QHeaderView, 
                               QMessageBox, QTabWidget)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush, QFont

# 引入拆分出去的模块
from config import CONFIG_FILE
from widgets import SettingsDialog
from threads import RankingFetcher, FundDataFetcher, ValuationFetcher
from db_manager import FundHistoryDB
from table_model import (FundTableModel, FundTableDelegate, CheckboxCellWidget, 
                         HoldingInputWidget, ActionButtonWidget)

class FundApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("场外基金深度监控 (实时估值 + 市场排行 + 多维指标)")
        self.resize(1400, 600)
        
        self.config = self.load_config()
        self.history_cache = {} 
        self.all_funds_dict = {} 
        self.all_funds_code_to_name = {}
        self.need_config_save = False 
        
        # 初始化数据库并从本地加载历史数据
        self.db = FundHistoryDB()
        self.load_history_from_db()
        
        self.refresh_timer = QTimer()
        self.refresh_interval = 60000 
        self.refresh_timer.timeout.connect(self.refresh_data)

        self.init_ui()
        self.load_all_funds_dict() 
        self.refresh_data()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        top_layout = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入 代码/名称[-板块] 添加, 例如: 004433-消费, 半导体设备-科技")
        self.input_box.setFixedHeight(35)
        
        self.btn_add = QPushButton("➕ 添加到自选")
        self.btn_add.setFixedHeight(35)
        self.btn_add.clicked.connect(self.add_funds)

        self.btn_refresh = QPushButton("🔄 刷新全市场")
        self.btn_refresh.setFixedHeight(35)
        self.btn_refresh.clicked.connect(self.refresh_data)

        self.btn_auto = QPushButton("▶ 开启自动刷新(60s)")
        self.btn_auto.setFixedHeight(35)
        self.btn_auto.setStyleSheet("background-color: #2ed573; color: white;") 
        self.btn_auto.clicked.connect(self.toggle_auto_refresh)
        
        self.btn_settings = QPushButton("⚙️ 设置指标与列显示")
        self.btn_settings.setFixedHeight(35)
        self.btn_settings.setStyleSheet("background-color: #747d8c; color: white;")
        self.btn_settings.clicked.connect(self.open_settings)

        top_layout.addWidget(self.input_box)
        top_layout.addWidget(self.btn_add)
        top_layout.addWidget(self.btn_refresh)
        top_layout.addWidget(self.btn_auto) 
        top_layout.addWidget(self.btn_settings)
        layout.addLayout(top_layout)

        self.tabs = QTabWidget()
        
        # Tab 1: 我的自选基金
        self.tab1 = QWidget()
        layout1 = QVBoxLayout(self.tab1)
        layout1.setContentsMargins(0, 0, 0, 0)
        self.table1 = QTableView()
        self.table1.setAlternatingRowColors(True)
        self.table1.verticalHeader().setVisible(False)
        self.table1.setSelectionBehavior(QTableView.SelectRows)
        self.table1.setSelectionMode(QTableView.SingleSelection)
        layout1.addWidget(self.table1)
        
        # Tab 2: 排行榜
        self.tab2 = QWidget()
        layout2 = QVBoxLayout(self.tab2)
        layout2.setContentsMargins(0, 0, 0, 0)
        self.table2 = QTableView()
        self.table2.setAlternatingRowColors(True)
        self.table2.verticalHeader().setVisible(False)
        self.table2.setSelectionBehavior(QTableView.SelectRows)
        self.table2.setSelectionMode(QTableView.SingleSelection)
        layout2.addWidget(self.table2)
        
        # Tab 3: 估值榜
        self.tab3 = QWidget()
        layout3 = QVBoxLayout(self.tab3)
        layout3.setContentsMargins(0, 0, 0, 0)
        self.table3 = QTableView()
        self.table3.setAlternatingRowColors(True)
        self.table3.verticalHeader().setVisible(False)
        self.table3.setSelectionBehavior(QTableView.SelectRows)
        self.table3.setSelectionMode(QTableView.SingleSelection)
        layout3.addWidget(self.table3)
        
        self.tabs.addTab(self.tab1, "⭐ 我的自选基金")
        self.tabs.addTab(self.tab2, "📈 今日指数ETF独立涨跌榜 (已过滤同质化)")
        self.tabs.addTab(self.tab3, "💎 估值榜 (PE/PB 最高最低)")
        
        layout.addWidget(self.tabs)

        self.apply_styles()
        
        # 初始化表格模型和代理 - 将在 rebuild_table_headers 中设置
        self.model1 = None
        self.model2 = None
        self.model3 = None
        self.delegate1 = None
        self.delegate2 = None
        self.delegate3 = None
        
        self.rebuild_table_headers()

    def rebuild_table_headers(self):
        self.headers = ["序号", "持有", "基金代码", "基金名称", "基金板块", "持有金额/\n收益率", 
                        "昨日净值", "净值日期", "实时估值", "今日收益/\n收益率"]
        
        self.drop_days = self.config.get("drop_days", [2, 4])
        self.pct_months = self.config.get("percentile_months", [1, 2, 3, 6, 12, 24])
        
        for d in self.drop_days: self.headers.append(f"近{d}日\n涨跌")
        for m in self.pct_months: self.headers.append(f"近{m}月\n百分位")
        self.headers.extend(["更新时间", "操作"])
        
        hidden_cols = self.config.get("hidden_columns", [])
        
        # 创建模型和代理
        for table, table_type in [(self.table1, "my_fund"), (self.table2, "ranking"), (self.table3, "valuation")]:
            model = FundTableModel(self.headers, parent=self)
            delegate = FundTableDelegate(table_type=table_type, parent=self)
            
            table.setModel(model)
            table.setItemDelegate(delegate)
            
            # 启用排序
            table.setSortingEnabled(True)
            
            # 配置列
            header_view = table.horizontalHeader()
            header_view.setSectionResizeMode(QHeaderView.Interactive)
            header_view.setDefaultSectionSize(75)
            header_view.setStyleSheet("QHeaderView::section { padding: 2px; }")
            
            # 减小行高，提高信息密度
            table.verticalHeader().setDefaultSectionSize(38)
            
            # 设置列宽
            table.setColumnWidth(0, 35)
            table.setColumnWidth(1, 35)
            table.setColumnWidth(2, 65)
            table.setColumnWidth(3, 180)  # 基金名称，支持换行
            table.setColumnWidth(4, 100)  # 基金板块，支持换行
            table.setColumnWidth(5, 85)
            table.setColumnWidth(6, 75)
            table.setColumnWidth(7, 80)
            table.setColumnWidth(8, 75)
            table.setColumnWidth(9, 85)
            
            # 减小数据列宽度
            for col_idx in range(10, len(self.headers) - 2):
                table.setColumnWidth(col_idx, 65)
            
            time_col_index = len(self.headers) - 2
            table.setColumnWidth(time_col_index, 130)
            
            action_col_index = len(self.headers) - 1
            header_view.setSectionResizeMode(action_col_index, QHeaderView.Fixed)
            table.setColumnWidth(action_col_index, 60)
            
            # 隐藏指定列
            for i, h in enumerate(self.headers):
                table.setColumnHidden(i, h in hidden_cols)
            
            # 保存模型和代理引用
            if table == self.table1:
                self.model1 = model
                self.delegate1 = delegate
            elif table == self.table2:
                self.model2 = model
                self.delegate2 = delegate
            else:  # table3
                self.model3 = model
                self.delegate3 = delegate

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f6fa; }
            QLineEdit { border: 1px solid #dcdde1; border-radius: 4px; padding: 5px; font-size: 13px;}
            QPushButton { background-color: #0097e6; color: white; border-radius: 4px; font-weight: bold; font-size: 13px; padding: 0 15px;}
            QPushButton:hover { background-color: #00a8ff; }
            QPushButton:disabled { background-color: #a4b0be; }
            QTableView { background-color: white; border: 1px solid #dcdde1; border-radius: 4px; font-size: 13px;}
            QHeaderView::section { background-color: #f1f2f6; padding: 5px; font-weight: bold; border-right: 1px solid #dcdde1; border-bottom: 1px solid #dcdde1;}
            QTabWidget::pane { border: 1px solid #dcdde1; border-radius: 4px; background: white; margin-top:-1px;}
            QTabBar::tab { background: #f1f2f6; padding: 8px 20px; border: 1px solid #dcdde1; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; font-weight: bold;}
            QTabBar::tab:selected { background: white; border-bottom: 2px solid white; border-top: 3px solid #0097e6; }
        """)

    def load_config(self):
        default_config = {"funds_info": {}, "drop_days": [2, 4], "percentile_months": [1, 2, 3, 6, 9, 12, 24], "hidden_columns": []}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list): 
                        for code in data: default_config["funds_info"][code] = {"name": "", "sector": "", "is_held": False, "amount": "", "yield_rate": ""}
                    else:
                        if "funds" in data and isinstance(data["funds"], list):
                            for code in data["funds"]: default_config["funds_info"][code] = {"name": "", "sector": "", "is_held": False, "amount": "", "yield_rate": ""}
                            del data["funds"]
                        for k, v in data.items():
                            if k == "funds_info": default_config["funds_info"].update(v)
                            else: default_config[k] = v
            except: pass
        return default_config

    def save_config(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    def load_history_from_db(self):
        """从本地数据库加载历史数据到内存缓存"""
        db_fund_codes = self.db.get_all_fund_codes()
        for code in db_fund_codes:
            history_data = self.db.get_history(code)
            if history_data:
                self.history_cache[code] = history_data

    def open_settings(self):
        old_drops = list(self.config.get("drop_days", []))
        old_pcts = list(self.config.get("percentile_months", []))
        
        dialog = SettingsDialog(self.config, self.headers, self)
        if dialog.exec():
            self.save_config()
            self.rebuild_table_headers()
            # 仅当数据参数变化时才刷新数据
            if self.config.get("drop_days") != old_drops or self.config.get("percentile_months") != old_pcts:
                self.refresh_data()

    def toggle_auto_refresh(self):
        if self.refresh_timer.isActive():
            self.refresh_timer.stop()
            self.btn_auto.setText("▶ 开启自动刷新(60s)")
            self.btn_auto.setStyleSheet("background-color: #2ed573; color: white;") 
            self.statusBar().showMessage("已关闭自动刷新")
        else:
            self.refresh_timer.start(self.refresh_interval)
            self.btn_auto.setText("⏸ 停止自动刷新")
            self.btn_auto.setStyleSheet("background-color: #ffa502; color: white;") 
            self.statusBar().showMessage("已开启自动刷新，每60秒更新一次")
            self.refresh_data() 

    def load_all_funds_dict(self):
        self.all_funds_code_to_name = {} 
        def fetch_dict():
            try:
                res = requests.get("http://fund.eastmoney.com/js/fundcode_search.js", timeout=10)
                match = re.search(r'var r = (\[.*\]);', res.text)
                if match:
                    for item in json.loads(match.group(1)):
                        self.all_funds_dict[item[2]] = item[0] 
                        self.all_funds_code_to_name[item[0]] = item[2] 
            except: pass
        threading.Thread(target=fetch_dict, daemon=True).start()

    def find_code_by_name(self, name_query):
        for name, code in self.all_funds_dict.items():
            if name_query in name: return code
        return None

    def add_funds(self):
        text = self.input_box.text().strip()
        if not text: return
        items = text.replace('，', ',').split(',')
        added = 0
        for item in items:
            item = item.strip()
            if not item: continue
            
            parts = item.split('-', 1)
            query = parts[0].strip()
            sector = parts[1].strip() if len(parts) > 1 else ""
            
            code = query if query.isdigit() and len(query) == 6 else self.find_code_by_name(query)
            if code:
                if code not in self.config.get("funds_info", {}):
                    self.config["funds_info"][code] = {"name": "", "sector": sector, "is_held": False, "amount": "", "yield_rate": ""}
                    added += 1
                elif sector: 
                    self.config["funds_info"][code]["sector"] = sector
                    added += 1
                    
        if added > 0:
            self.save_config()
            self.input_box.clear()
            self.refresh_data()

    def delete_fund(self, code):
        if code in self.config.get("funds_info", {}):
            del self.config["funds_info"][code]
            self.save_config()
            self.refresh_data()
            
    def add_from_market(self, code, name, sector):
        if not sector or sector in ["未知", "-", ""] or "最高" in sector or "最低" in sector:
            from utils import extract_fund_sector
            sector = extract_fund_sector(name)

        if code not in self.config.get("funds_info", {}):
            self.config["funds_info"][code] = {"name": name, "sector": sector, "is_held": False, "amount": "", "yield_rate": ""}
            self.save_config()
            QMessageBox.information(self, "添加成功", f"已成功将 {name} (板块: {sector}) 放入我的自选基金列表！\n请切换回第一页查看。")
            
            row = self.get_row_by_code(self.table2, code)
            if row != -1:
                # 更新按钮状态 - 在表2中标记为已添加
                self._update_market_btn_status(self.model2, row)
                
    def _update_market_btn_status(self, model, row):
        """更新市场表的按钮状态"""
        row_data = model.get_row_data(row)
        row_data["操作"] = "已添加"
        model.update_row(row, row_data)

    def get_row_by_code(self, table, code):
        """查找表格中第一个匹配代码的行号"""
        model = table.model()
        if model and hasattr(model, 'find_row_by_code'):
            return model.find_row_by_code(code)
        return -1

    def get_all_rows_by_code(self, table, code):
        """返回表格中所有匹配该代码的行号列表"""
        model = table.model()
        if model and hasattr(model, 'find_all_rows_by_code'):
            return model.find_all_rows_by_code(code)
        return []

    def refresh_data(self):
        if not self.btn_refresh.isEnabled(): return

        self.btn_refresh.setEnabled(False)
        self.latest_data_time = ""  # 重置数据源时间
        
        funds = list(self.config.get("funds_info", {}).keys())
        
        # 清空现有数据
        self.model1.clear_all()
        
        # 添加新的行
        for code in funds:
            row_data = {}
            for header in self.headers:
                row_data[header] = "-"
            
            # 初始化基本信息
            row_data["序号"] = str(len(self.model1.data_rows) + 1)
            row_data["持有"] = "0"  # 用于排序
            row_data["基金代码"] = code
            row_data["基金名称"] = "加载中..."
            
            sector = self.config["funds_info"][code].get("sector", "")
            row_data["基金板块"] = sector
            row_data["持有金额/\n收益率"] = self.config["funds_info"][code].get("amount", "")
            
            self.model1.add_row(row_data)
        
        # 启动排行数据获取
        self.ranking_fetcher = RankingFetcher(self.all_funds_code_to_name) 
        self.ranking_fetcher.ranking_signal.connect(self.on_ranking_fetched)
        self.ranking_fetcher.start()

        self.valuation_fetcher = ValuationFetcher(self.all_funds_dict)
        self.valuation_fetcher.valuation_signal.connect(self.on_valuation_fetched)
        self.valuation_fetcher.start()

    def on_valuation_fetched(self, valuation_list):
        self.model3.clear_all()
        
        self.valuation_mapping = {} # index_code -> fund_code
        fetch_codes = []

        for i, item in enumerate(valuation_list):
            index_code = item.get("bzdm")
            index_name = item.get("fund_name", "未知名称")
            
            fund_code = item.get("fund_code", index_code)
            self.valuation_mapping[fund_code] = index_code
            fetch_codes.append(fund_code)
            
            row_data = {}
            for header in self.headers:
                row_data[header] = "-"
            
            row_data["序号"] = str(i + 1)
            
            # col 1: 估值标签（PE最高/PB最低等）
            tag_text = item.get("valuation_tag", "")
            row_data["持有"] = tag_text
            
            row_data["基金代码"] = fund_code
            row_data["基金名称"] = index_name
            
            # col 4: 基金板块（实际板块名称）
            sector = item.get("extracted_sector", "")
            row_data["基金板块"] = sector
            
            pe_val = item.get("pe", "--")
            pb_val = item.get("pb", "--")
            pe_pct = item.get("pe_percentile", "--")
            display_info = f"PE:{pe_val} ({pe_pct}%)\nPB:{pb_val}"
            row_data["持有金额/\n收益率"] = display_info
            
            row_data["操作"] = "➕关注" if fund_code not in self.config.get("funds_info", {}) else "已添加"
            
            self.model3.add_row(row_data)
        
        # 启动数据抓取（合并之前的自选和排行榜）
        my_funds = list(self.config.get("funds_info", {}).keys())
        market_codes = [self.model2.data_rows[i].get("基金代码") for i in range(len(self.model2.data_rows))]
        all_fetch_codes = list(set(my_funds + market_codes + fetch_codes))
        
        if hasattr(self, "fetcher") and self.fetcher.isRunning():
            self.fetcher.requestInterruption()
            self.fetcher.wait()

        self.fetcher = FundDataFetcher(all_fetch_codes, self.config, self.history_cache, self.all_funds_code_to_name, self.db)
        self.fetcher.update_signal.connect(self.dispatch_table_update)
        self.fetcher.error_signal.connect(self.dispatch_table_error)
        self.fetcher.finish_signal.connect(self.on_fetch_finish)
        self.fetcher.start()

    def on_ranking_fetched(self, top_list, bot_list):
        self.model2.clear_all()
        
        market_codes = []
        combined_list = top_list + bot_list
        
        for i, item in enumerate(combined_list):
            code = item.get("bzdm")
            name = item.get("fund_name", "未知名称") 
            sector = item.get("extracted_sector", "未知")
            
            if not code: continue
            
            market_codes.append(code)
            is_top = i < len(top_list)
            
            row_data = {}
            for header in self.headers:
                row_data[header] = "-"
            
            row_data["序号"] = str(i + 1)
            row_data["持有"] = "-"
            row_data["基金代码"] = code
            row_data["基金名称"] = name
            row_data["基金板块"] = sector
            row_data["持有金额/\n收益率"] = "-"
            
            row_data["操作"] = "已添加" if code in self.config.get("funds_info", {}) else "➕关注"
            
            self.model2.add_row(row_data)
        
        my_funds = list(self.config.get("funds_info", {}).keys())
        valuation_codes = [self.model3.data_rows[i].get("基金代码") for i in range(len(self.model3.data_rows))]
        all_fetch_codes = list(set(my_funds + market_codes + valuation_codes))
        
        if hasattr(self, "fetcher") and self.fetcher.isRunning():
            self.fetcher.requestInterruption()
            self.fetcher.wait()

        self.fetcher = FundDataFetcher(all_fetch_codes, self.config, self.history_cache, self.all_funds_code_to_name, self.db)
        self.fetcher.update_signal.connect(self.dispatch_table_update)
        self.fetcher.error_signal.connect(self.dispatch_table_error)
        self.fetcher.finish_signal.connect(self.on_fetch_finish)
        self.fetcher.start()

    def dispatch_table_update(self, data):
        code = data.get('fundcode')
        name = data.get('name')
        
        # 跟踪最新的数据源时间
        gztime = data.get('gztime', '')
        if gztime and gztime > getattr(self, 'latest_data_time', ''):
            self.latest_data_time = gztime
        
        if 'new_history' in data:
            self.history_cache[code] = data['new_history']
            
        row1 = self.get_row_by_code(self.table1, code)
        if row1 != -1:
            config_name = self.config["funds_info"].get(code, {}).get("name", "")
            if config_name != name:
                self.config["funds_info"][code]["name"] = name
                self.need_config_save = True
            self.populate_row_data(self.model1, row1, data, is_my_fund=True)
            
        row2 = self.get_row_by_code(self.table2, code)
        if row2 != -1:
            self.populate_row_data(self.model2, row2, data, is_my_fund=False)
            
        for row3 in self.get_all_rows_by_code(self.table3, code):
            self.populate_row_data(self.model3, row3, data, is_my_fund=False)

    def populate_row_data(self, model, row, data, is_my_fund):
        """更新行数据"""
        if row < 0 or row >= len(model.data_rows):
            return
        
        row_data = model.get_row_data(row)
        code = data.get('fundcode')
        
        row_data["基金名称"] = data.get('name')
        
        if is_my_fund:
            sector = self.config["funds_info"].get(code, {}).get("sector", "")
            row_data["基金板块"] = sector
            
        row_data["昨日净值"] = data.get('dwjz')
        row_data["净值日期"] = data.get('jzrq')
        row_data["实时估值"] = data.get('gsz')
        
        change_str = data.get('gszzl', "")
        if is_my_fund:
            held_amount_str = self.config["funds_info"].get(code, {}).get("amount", "")
            try: held_amount = float(held_amount_str)
            except ValueError: held_amount = 0.0

            try:
                val = float(change_str)
                if held_amount > 0:
                    today_profit = (held_amount * val) / 100.0
                    display_text = f"{today_profit:+.2f}\n{val:+.2f}%"
                else:
                    display_text = f"-\n{val:+.2f}%"
                row_data["今日收益/\n收益率"] = display_text
            except: 
                row_data["今日收益/\n收益率"] = f"-\n{change_str}%"
        else:
            try:
                val = float(change_str)
                display_text = f"-\n{val:+.2f}%"
                row_data["今日收益/\n收益率"] = display_text
            except:
                row_data["今日收益/\n收益率"] = f"-\n{change_str}%"
        
        # 涨跌幅
        col_index = 0
        drops_dict = data.get('drops', {})
        for d in self.drop_days:
            val = drops_dict.get(d)
            header = f"近{d}日\n涨跌"
            if val is not None:
                row_data[header] = f"{val:+.2f}%"
            else:
                row_data[header] = "-"
        
        # 百分位
        pcts_dict = data.get('pcts', {})
        for m in self.pct_months:
            val = pcts_dict.get(m)
            header = f"近{m}月\n百分位"
            if val is not None:
                row_data[header] = f"{val:.2f}%"
            else:
                row_data[header] = "-"

        row_data["更新时间"] = data.get('gztime', '')
        
        model.update_row(row, row_data)

    def dispatch_table_error(self, code, error_msg):
        row1 = self.get_row_by_code(self.table1, code)
        if row1 != -1: 
            self.populate_error(self.model1, row1, code, error_msg, is_my_fund=True)
            
        row2 = self.get_row_by_code(self.table2, code)
        if row2 != -1: 
            self.populate_error(self.model2, row2, code, error_msg, is_my_fund=False)
        
        for row3 in self.get_all_rows_by_code(self.table3, code):
            self.populate_error(self.model3, row3, code, error_msg, is_my_fund=False)

    def populate_error(self, model, row, code, error_msg, is_my_fund):
        if row < 0 or row >= len(model.data_rows):
            return
        
        row_data = model.get_row_data(row)
        
        if is_my_fund:
            config_name = self.config["funds_info"].get(code, {}).get("name")
            real_name = config_name if config_name else getattr(self, "all_funds_code_to_name", {}).get(code, "未知基金(暂无数据)")
            row_data["基金名称"] = real_name
        
        row_data["实时估值"] = f"[{error_msg}]"
        
        for d in self.drop_days:
            row_data[f"近{d}日\n涨跌"] = "-"
        for m in self.pct_months:
            row_data[f"近{m}月\n百分位"] = "-"
        
        model.update_row(row, row_data)

    def on_fetch_finish(self):
        self.btn_refresh.setEnabled(True)
        if self.need_config_save:
            self.save_config()
            self.need_config_save = False
            
        data_time = getattr(self, 'latest_data_time', '') or '未知'
        fetch_time = time.strftime('%Y-%m-%d %H:%M:%S')
        msg = f"数据时间: {data_time}  |  获取时间: {fetch_time}"
        if self.refresh_timer.isActive():
            msg += "  (自动刷新运行中...)"
        self.statusBar().showMessage(msg)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    window = FundApp()
    window.show()
    app.exec()
