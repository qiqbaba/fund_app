
# main_window.py
import json
import os
import re
import time
import requests
import threading

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLineEdit, QPushButton, QTableWidget, QHeaderView, 
                               QMessageBox, QCheckBox, QTabWidget)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush, QFont

# 引入拆分出去的模块
from config import CONFIG_FILE
from widgets import SettingsDialog, SortableTableWidgetItem
from threads import RankingFetcher, FundDataFetcher, ValuationFetcher

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
        
        self.tab1 = QWidget()
        layout1 = QVBoxLayout(self.tab1)
        layout1.setContentsMargins(0, 0, 0, 0)
        self.table1 = QTableWidget()
        self.table1.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table1.setAlternatingRowColors(True)
        self.table1.verticalHeader().setVisible(False)
        layout1.addWidget(self.table1)
        
        self.tab2 = QWidget()
        layout2 = QVBoxLayout(self.tab2)
        layout2.setContentsMargins(0, 0, 0, 0)
        self.table2 = QTableWidget()
        self.table2.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table2.setAlternatingRowColors(True)
        self.table2.verticalHeader().setVisible(False)
        layout2.addWidget(self.table2)

        self.tab3 = QWidget()
        layout3 = QVBoxLayout(self.tab3)
        layout3.setContentsMargins(0, 0, 0, 0)
        self.table3 = QTableWidget()
        self.table3.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table3.setAlternatingRowColors(True)
        self.table3.verticalHeader().setVisible(False)
        layout3.addWidget(self.table3)

        self.tabs.addTab(self.tab1, "⭐ 我的自选基金")
        self.tabs.addTab(self.tab2, "📈 今日指数ETF独立涨跌榜 (已过滤同质化)")
        self.tabs.addTab(self.tab3, "💎 估值榜 (PE/PB 最高最低)")
        
        layout.addWidget(self.tabs)

        self.apply_styles()
        self.rebuild_table_headers()

    def create_held_checkbox(self, code, is_held):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        cb = QCheckBox()
        cb.setChecked(is_held)
        cb.stateChanged.connect(lambda state, c=code: self.update_is_held(c, state))
        layout.addWidget(cb)
        return widget

    def update_is_held(self, code, state):
        if code in self.config.get("funds_info", {}):
            self.config["funds_info"][code]["is_held"] = (state == 2) 
            self.save_config()

    def create_holding_input(self, code, amount, yield_rate):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(2)
        
        amt_input = QLineEdit(str(amount) if amount else "")
        amt_input.setPlaceholderText("金额")
        amt_input.setStyleSheet("background: transparent; border: 1px solid #ced6e0; border-radius: 3px; padding: 1px 3px; font-size: 11px;")
        amt_input.editingFinished.connect(lambda: self.update_holding(code, 'amount', amt_input.text()))
        
        yld_input = QLineEdit(str(yield_rate) if yield_rate else "")
        yld_input.setPlaceholderText("收益率%")
        yld_input.setStyleSheet("background: transparent; border: 1px solid #ced6e0; border-radius: 3px; padding: 1px 3px; font-size: 11px;")
        yld_input.editingFinished.connect(lambda: self.update_holding(code, 'yield_rate', yld_input.text()))
        
        layout.addWidget(amt_input)
        layout.addWidget(yld_input)
        return widget

    def update_holding(self, code, key, value):
        if code in self.config.get("funds_info", {}):
            self.config["funds_info"][code][key] = value
            self.save_config()
            if key == 'amount':
                row = self.get_row_by_code(self.table1, code)
                if row != -1 and self.table1.item(row, 5):
                    self.table1.item(row, 5).setText(str(value) if value else "0")

    def rebuild_table_headers(self):
        self.headers = ["序号", "持有", "基金代码", "基金名称", "基金板块", "持有金额/\n收益率", 
                        "昨日净值", "净值日期", "实时估值", "今日收益/\n收益率"]
        
        self.drop_days = self.config.get("drop_days", [2, 4])
        self.pct_months = self.config.get("percentile_months", [1, 2, 3, 6, 12, 24])
        
        for d in self.drop_days: self.headers.append(f"近{d}日涨跌")
        for m in self.pct_months: self.headers.append(f"近{m}月百分位")
        self.headers.extend(["更新时间", "操作"])
        
        hidden_cols = self.config.get("hidden_columns", [])
        
        for table in [self.table1, self.table2, self.table3]:
            table.setSortingEnabled(False)
            table.setColumnCount(len(self.headers))
            table.setHorizontalHeaderLabels(self.headers)
            
            header_view = table.horizontalHeader()
            header_view.setSectionResizeMode(QHeaderView.Interactive)
            header_view.setDefaultSectionSize(90) 
            
            table.verticalHeader().setDefaultSectionSize(55)
            
            table.setColumnWidth(0, 40)
            table.setColumnWidth(1, 40)
            table.setColumnWidth(2, 70)
            table.setColumnWidth(3, 170)
            table.setColumnWidth(4, 75)
            table.setColumnWidth(5, 95)
            table.setColumnWidth(7, 90)
            table.setColumnWidth(9, 90)
            
            time_col_index = len(self.headers) - 2
            table.setColumnWidth(time_col_index, 140)
            
            action_col_index = len(self.headers) - 1
            header_view.setSectionResizeMode(action_col_index, QHeaderView.Fixed)
            table.setColumnWidth(action_col_index, 60)
            
            for i, h in enumerate(self.headers):
                table.setColumnHidden(i, h in hidden_cols)
                
            table.setSortingEnabled(True)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f6fa; }
            QLineEdit { border: 1px solid #dcdde1; border-radius: 4px; padding: 5px; font-size: 13px;}
            QPushButton { background-color: #0097e6; color: white; border-radius: 4px; font-weight: bold; font-size: 13px; padding: 0 15px;}
            QPushButton:hover { background-color: #00a8ff; }
            QPushButton:disabled { background-color: #a4b0be; }
            QTableWidget { background-color: white; border: 1px solid #dcdde1; border-radius: 4px; font-size: 13px;}
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
        if code not in self.config.get("funds_info", {}):
            self.config["funds_info"][code] = {"name": name, "sector": sector, "is_held": False, "amount": "", "yield_rate": ""}
            self.save_config()
            QMessageBox.information(self, "添加成功", f"已成功将 {name} (板块: {sector}) 放入我的自选基金列表！\n请切换回第一页查看。")
            
            row = self.get_row_by_code(self.table2, code)
            if row != -1:
                btn = self.table2.cellWidget(row, len(self.headers) - 1)
                if btn:
                    btn.setText("已添加")
                    btn.setEnabled(False)
                    btn.setStyleSheet("background-color: #a4b0be; color: white; border-radius: 3px; padding:2px;")

    def get_row_by_code(self, table, code):
        for row in range(table.rowCount()):
            item = table.item(row, 2)
            if item and item.text() == code:
                return row
        return -1

    def get_all_rows_by_code(self, table, code):
        """返回表格中所有匹配该代码的行号列表"""
        rows = []
        for row in range(table.rowCount()):
            item = table.item(row, 2)
            if item and item.text() == code:
                rows.append(row)
        return rows

    def refresh_data(self):
        if not self.btn_refresh.isEnabled(): return

        self.btn_refresh.setEnabled(False)
        self.table1.setSortingEnabled(False)
        self.latest_data_time = ""  # 重置数据源时间
        
        funds = list(self.config.get("funds_info", {}).keys())
        
        for row in range(self.table1.rowCount() - 1, -1, -1):
            code_item = self.table1.item(row, 2)
            if code_item and code_item.text() not in funds:
                self.table1.removeRow(row)
                
        existing_codes = [self.table1.item(i, 2).text() for i in range(self.table1.rowCount()) if self.table1.item(i, 2)]
        
        for code in funds:
            if code not in existing_codes:
                row = self.table1.rowCount()
                self.table1.insertRow(row)
                
                self.table1.setItem(row, 0, SortableTableWidgetItem(str(row + 1)))
                
                is_held = self.config["funds_info"][code].get("is_held", False)
                self.table1.setCellWidget(row, 1, self.create_held_checkbox(code, is_held))
                item_held = SortableTableWidgetItem(str(is_held))
                item_held.setForeground(QBrush(QColor(0,0,0,0)))
                self.table1.setItem(row, 1, item_held)
                
                self.table1.setItem(row, 2, SortableTableWidgetItem(code))
                self.table1.setItem(row, 3, SortableTableWidgetItem("加载中..."))
                
                sector = self.config["funds_info"][code].get("sector", "")
                self.table1.setItem(row, 4, SortableTableWidgetItem(sector))
                
                amount = self.config["funds_info"][code].get("amount", "")
                yield_rate = self.config["funds_info"][code].get("yield_rate", "")
                self.table1.setCellWidget(row, 5, self.create_holding_input(code, amount, yield_rate))
                item_holding = SortableTableWidgetItem(str(amount) if amount else "0")
                item_holding.setForeground(QBrush(QColor(0,0,0,0)))
                self.table1.setItem(row, 5, item_holding)
                
                for col in range(6, len(self.headers) - 1): 
                    self.table1.setItem(row, col, SortableTableWidgetItem("-"))
                
                del_btn = QPushButton("删除")
                del_btn.setStyleSheet("background-color: #ff4757; color: white; border-radius: 3px; padding:2px;")
                del_btn.clicked.connect(lambda checked, c=code: self.delete_fund(c))
                self.table1.setCellWidget(row, len(self.headers) - 1, del_btn)

        self.table1.setSortingEnabled(True)

        self.ranking_fetcher = RankingFetcher(self.all_funds_code_to_name) 
        self.ranking_fetcher.ranking_signal.connect(self.on_ranking_fetched)
        self.ranking_fetcher.start()

        self.valuation_fetcher = ValuationFetcher(self.all_funds_dict)
        self.valuation_fetcher.valuation_signal.connect(self.on_valuation_fetched)
        self.valuation_fetcher.start()

    def on_valuation_fetched(self, valuation_list):
        self.table3.setSortingEnabled(False)
        self.table3.setRowCount(0)
        
        # 将 table3 的"持有"列复用为"估值"列
        if self.table3.columnCount() > 1:
            self.table3.horizontalHeaderItem(1).setText("估值")
            self.table3.setColumnHidden(1, False)
        
        self.valuation_mapping = {} # index_code -> fund_code
        fetch_codes = []

        for i, item in enumerate(valuation_list):
            index_code = item.get("bzdm")
            index_name = item.get("fund_name", "未知名称")
            
            fund_code = item.get("fund_code", index_code)
            self.valuation_mapping[fund_code] = index_code
            fetch_codes.append(fund_code)
            
            row = self.table3.rowCount()
            self.table3.insertRow(row)
            
            self.table3.setItem(row, 0, SortableTableWidgetItem(str(row + 1)))
            
            # col 1: 估值标签（PE最高/PB最低等）
            tag_text = item.get("valuation_tag", "")
            is_high = "高" in tag_text
            tag_item = SortableTableWidgetItem(tag_text)
            tag_item.setForeground(QBrush(QColor("#ff4757" if is_high else "#2ed573")))
            tag_item.setFont(QFont("Arial", 9, QFont.Bold))
            self.table3.setItem(row, 1, tag_item)
            
            self.table3.setItem(row, 2, SortableTableWidgetItem(fund_code))
            
            # col 3: 基金名称，估值高为红色，估值低为绿色
            name_item = SortableTableWidgetItem(index_name)
            name_item.setForeground(QBrush(QColor("#ff4757" if is_high else "#2ed573")))
            self.table3.setItem(row, 3, name_item)
            
            # col 4: 基金板块（实际板块名称）
            sector = item.get("extracted_sector", "")
            sector_item = SortableTableWidgetItem(sector)
            self.table3.setItem(row, 4, sector_item)
            
            pe_val = item.get("pe", "--")
            pb_val = item.get("pb", "--")
            pe_pct = item.get("pe_percentile", "--")
            display_info = f"PE:{pe_val} ({pe_pct}%)\nPB:{pb_val}"
            info_item = SortableTableWidgetItem(display_info)
            self.table3.setItem(row, 5, info_item)
            
            for col in range(6, len(self.headers) - 1):
                self.table3.setItem(row, col, SortableTableWidgetItem("-"))
            
            add_btn = QPushButton()
            if fund_code in self.config.get("funds_info", {}):
                add_btn.setText("已添加")
                add_btn.setEnabled(False)
                add_btn.setStyleSheet("background-color: #a4b0be; color: white; border-radius: 3px; padding:2px;")
            else:
                add_btn.setText("➕关注")
                add_btn.setStyleSheet("background-color: #2ed573; color: white; border-radius: 3px; padding:2px;")
                add_btn.clicked.connect(lambda checked, c=fund_code, n=index_name, s=sector: self.add_from_market(c, n, s))
            
            self.table3.setCellWidget(row, len(self.headers) - 1, add_btn)
            
        self.table3.setSortingEnabled(True)
        if self.table3.columnCount() > 5:
            self.table3.horizontalHeaderItem(5).setText("估值数据\n(PE/PB)")
        
        # 启动数据抓取（合并之前的自选和排行榜）
        my_funds = list(self.config.get("funds_info", {}).keys())
        market_codes = [self.table2.item(i, 2).text() for i in range(self.table2.rowCount()) if self.table2.item(i, 2)]
        all_fetch_codes = list(set(my_funds + market_codes + fetch_codes))
        
        if hasattr(self, "fetcher") and self.fetcher.isRunning():
            self.fetcher.requestInterruption()
            self.fetcher.wait()

        self.fetcher = FundDataFetcher(all_fetch_codes, self.config, self.history_cache, self.all_funds_code_to_name)
        self.fetcher.update_signal.connect(self.dispatch_table_update)
        self.fetcher.error_signal.connect(self.dispatch_table_error)
        self.fetcher.finish_signal.connect(self.on_fetch_finish)
        self.fetcher.start()

    def on_ranking_fetched(self, top_list, bot_list):
        self.table2.setSortingEnabled(False)
        self.table2.setRowCount(0)
        
        market_codes = []
        combined_list = top_list + bot_list
        
        for i, item in enumerate(combined_list):
            code = item.get("bzdm")
            name = item.get("fund_name", "未知名称") 
            sector = item.get("extracted_sector", "未知")
            
            if not code: continue
            
            market_codes.append(code)
            row = self.table2.rowCount()
            self.table2.insertRow(row)
            
            is_top = i < len(top_list)
            
            self.table2.setItem(row, 0, SortableTableWidgetItem(str(row + 1)))
            self.table2.setItem(row, 1, SortableTableWidgetItem("-"))
            self.table2.setItem(row, 2, SortableTableWidgetItem(code))
            self.table2.setItem(row, 3, SortableTableWidgetItem(name))
            
            tag_text = f"{sector}" if is_top else f"{sector}"
            tag_item = SortableTableWidgetItem(tag_text)
            tag_item.setForeground(QBrush(QColor("#ff4757" if is_top else "#2ed573")))
            tag_item.setFont(QFont("Arial", 9, QFont.Bold))
            self.table2.setItem(row, 4, tag_item)
            
            self.table2.setItem(row, 5, SortableTableWidgetItem("-"))
            
            for col in range(6, len(self.headers) - 1): 
                self.table2.setItem(row, col, SortableTableWidgetItem("-"))
            
            add_btn = QPushButton()
            if code in self.config.get("funds_info", {}):
                add_btn.setText("已添加")
                add_btn.setEnabled(False)
                add_btn.setStyleSheet("background-color: #a4b0be; color: white; border-radius: 3px; padding:2px;")
            else:
                add_btn.setText("➕关注")
                add_btn.setStyleSheet("background-color: #2ed573; color: white; border-radius: 3px; padding:2px;")
                add_btn.clicked.connect(lambda checked, c=code, n=name, s=sector: self.add_from_market(c, n, s))
            
            self.table2.setCellWidget(row, len(self.headers) - 1, add_btn)
            
        self.table2.setSortingEnabled(True)
        
        my_funds = list(self.config.get("funds_info", {}).keys())
        valuation_codes = [self.table3.item(i, 2).text() for i in range(self.table3.rowCount()) if self.table3.item(i, 2)]
        all_fetch_codes = list(set(my_funds + market_codes + valuation_codes))
        
        if hasattr(self, "fetcher") and self.fetcher.isRunning():
            self.fetcher.requestInterruption()
            self.fetcher.wait()

        self.fetcher = FundDataFetcher(all_fetch_codes, self.config, self.history_cache, self.all_funds_code_to_name)
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
            self.populate_row_data(self.table1, row1, data, is_my_fund=True)
            
        row2 = self.get_row_by_code(self.table2, code)
        if row2 != -1:
            self.populate_row_data(self.table2, row2, data, is_my_fund=False)
            
        for row3 in self.get_all_rows_by_code(self.table3, code):
            self.populate_row_data(self.table3, row3, data, is_my_fund=False)

    def populate_row_data(self, table, row, data, is_my_fund):
        table.setSortingEnabled(False) 
        code = data.get('fundcode')
        
        table.setItem(row, 3, SortableTableWidgetItem(data.get('name')))
        
        if is_my_fund:
            sector = self.config["funds_info"].get(code, {}).get("sector", "")
            current_sector_item = table.item(row, 4)
            if current_sector_item and current_sector_item.text() != sector:
                current_sector_item.setText(sector)
            
        table.setItem(row, 6, SortableTableWidgetItem(data.get('dwjz')))
        table.setItem(row, 7, SortableTableWidgetItem(data.get('jzrq')))
        table.setItem(row, 8, SortableTableWidgetItem(data.get('gsz')))
        
        change_str = data.get('gszzl')
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
                    
                change_item = SortableTableWidgetItem(display_text)
                change_item.setFont(QFont("Arial", 10, QFont.Bold))
                if val > 0: change_item.setForeground(QBrush(QColor("#ff4757"))) 
                elif val < 0: change_item.setForeground(QBrush(QColor("#2ed573"))) 
            except: 
                change_item = SortableTableWidgetItem(f"-\n{change_str}%")
        else:
            try:
                val = float(change_str)
                display_text = f"-\n{val:+.2f}%"
                change_item = SortableTableWidgetItem(display_text)
                change_item.setFont(QFont("Arial", 10, QFont.Bold))
                if val > 0: change_item.setForeground(QBrush(QColor("#ff4757"))) 
                elif val < 0: change_item.setForeground(QBrush(QColor("#2ed573"))) 
            except:
                change_item = SortableTableWidgetItem(f"-\n{change_str}%")
                
        table.setItem(row, 9, change_item)
        
        col_index = 10
        drops_dict = data.get('drops', {})
        for d in self.drop_days:
            val = drops_dict.get(d)
            if val is not None:
                item = SortableTableWidgetItem(f"{val:+.2f}%")
                if val > 0: item.setForeground(QBrush(QColor("#ff4757")))
                elif val < 0: item.setForeground(QBrush(QColor("#2ed573")))
            else:
                item = SortableTableWidgetItem("-")
            table.setItem(row, col_index, item)
            col_index += 1
            
        pcts_dict = data.get('pcts', {})
        for m in self.pct_months:
            val = pcts_dict.get(m)
            if val is not None:
                item = SortableTableWidgetItem(f"{val:.2f}%")
                if val <= 25: item.setForeground(QBrush(QColor("#2ed573")))
                elif val >= 75: item.setForeground(QBrush(QColor("#ff4757")))
                else: item.setForeground(QBrush(QColor("#57606f")))
            else:
                item = SortableTableWidgetItem("-")
            table.setItem(row, col_index, item)
            col_index += 1

        table.setItem(row, col_index, SortableTableWidgetItem(data.get('gztime')))

        for col in range(len(self.headers) - 1):
            if col not in [1, 5] and table.item(row, col): 
                table.item(row, col).setTextAlignment(Qt.AlignCenter)
            if not is_my_fund and col in [1, 5] and table.item(row, col):
                table.item(row, col).setTextAlignment(Qt.AlignCenter)

        table.setSortingEnabled(True)

    def dispatch_table_error(self, code, error_msg):
        row1 = self.get_row_by_code(self.table1, code)
        if row1 != -1: self.populate_error(self.table1, row1, code, error_msg, is_my_fund=True)
            
        row2 = self.get_row_by_code(self.table2, code)
        if row2 != -1: self.populate_error(self.table2, row2, code, error_msg, is_my_fund=False)
        
        for row3 in self.get_all_rows_by_code(self.table3, code):
            self.populate_error(self.table3, row3, code, error_msg, is_my_fund=False)

    def populate_error(self, table, row, code, error_msg, is_my_fund):
        table.setSortingEnabled(False) 
        
        if is_my_fund:
            config_name = self.config["funds_info"].get(code, {}).get("name")
            real_name = config_name if config_name else getattr(self, "all_funds_code_to_name", {}).get(code, "未知基金(暂无数据)")
            table.setItem(row, 3, SortableTableWidgetItem(real_name))
        
        error_item = SortableTableWidgetItem(f"[{error_msg}]")
        error_item.setForeground(QBrush(QColor("#a4b0be"))) 
        table.setItem(row, 8, error_item) 
        
        for col in range(6, len(self.headers) - 1):
            if col != 8: table.setItem(row, col, SortableTableWidgetItem("-"))
        
        for col in range(len(self.headers) - 1):
            if col not in [1, 5] and table.item(row, col): 
                table.item(row, col).setTextAlignment(Qt.AlignCenter)
                
        table.setSortingEnabled(True)

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