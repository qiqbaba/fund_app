# main_window.py
import json
import os
import re
import time
import requests
import threading

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLineEdit, QPushButton, QTableView, QHeaderView, 
                               QMessageBox, QTabWidget, QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush, QFont

# 引入拆分出去的模块
from config import CONFIG_FILE
from widgets import SettingsDialog, FundChartDialog
from threads import RankingFetcher, FundDataFetcher, ValuationFetcher
from db_manager import FundHistoryDB
from table_model import (FundTableModel, FundTableDelegate, CheckboxCellWidget, 
                         HoldingInputWidget, ActionButtonWidget)
from utils import extract_fund_sector

class FundApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("场外基金深度监控")
        self.resize(1400, 600)
        
        self.config = self.load_config()
        self.history_cache = {} 
        self.all_funds_dict = {} 
        self.all_funds_code_to_name = {}
        self.fund_search_list = []
        self.shared_sector_map = {} # 新增：全局板块 API 缓存映射库
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
        self.input_box.setPlaceholderText("输入基金代码/名称/拼音首字母搜索, 如: 白酒, bj, 004433-消费")
        self.input_box.setFixedHeight(35)
        self.input_box.textChanged.connect(self.on_search_input_changed)
        
        # 搜索自动补全弹窗
        self.search_popup = QListWidget(self)
        self.search_popup.setWindowFlags(Qt.ToolTip)
        self.search_popup.setFocusPolicy(Qt.NoFocus)
        self.search_popup.setMouseTracking(True)
        self.search_popup.itemClicked.connect(self.on_search_item_clicked)
        self.search_popup.setStyleSheet("""
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #b2bec3;
                border-radius: 4px;
                font-size: 13px;
                padding: 2px 0;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #f1f2f6;
                color: #2d3436;
            }
            QListWidget::item:last-child { border-bottom: none; }
            QListWidget::item:hover {
                background-color: #e8f4fd;
                color: #0097e6;
            }
        """)
        self.search_popup.hide()
        
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
        self.tabs.addTab(self.tab2, "📈 今日指数ETF独立涨跌榜")
        self.tabs.setTabToolTip(1, "已过滤同质化")
        self.tabs.addTab(self.tab3, "💎 估值榜")
        self.tabs.setTabToolTip(2, "PE/PB 最高最低")
        
        layout.addWidget(self.tabs)

        # 绑定双击事件
        self.table1.doubleClicked.connect(lambda index: self.show_detailed_chart(self.table1, index))
        self.table2.doubleClicked.connect(lambda index: self.show_detailed_chart(self.table2, index))
        self.table3.doubleClicked.connect(lambda index: self.show_detailed_chart(self.table3, index))

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
        self.headers.extend(["1年趋势", "更新时间", "操作"])
        
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
            for col_idx in range(10, len(self.headers) - 3):
                table.setColumnWidth(col_idx, 65)
            
            trend_col_index = len(self.headers) - 3
            table.setColumnWidth(trend_col_index, 80)
            
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
        self.fund_search_list = []
        def fetch_dict():
            try:
                res = requests.get("http://fund.eastmoney.com/js/fundcode_search.js", timeout=10)
                match = re.search(r'var r = (\[.*\]);', res.text)
                if match:
                    search_list = []
                    for item in json.loads(match.group(1)):
                        self.all_funds_dict[item[2]] = item[0] 
                        self.all_funds_code_to_name[item[0]] = item[2]
                        # (代码, 拼音缩写, 名称, 类型, 全拼音)
                        search_list.append((item[0], item[1], item[2], item[3], item[4]))
                    self.fund_search_list = search_list
            except: pass
        threading.Thread(target=fetch_dict, daemon=True).start()

    def find_code_by_name(self, name_query):
        for name, code in self.all_funds_dict.items():
            if name_query in name: return code
        return None

    def on_search_input_changed(self, text):
        """输入框文本变化时，执行模糊搜索并显示自动补全弹窗"""
        text = text.strip()
        if ',' in text or '，' in text:
            self.search_popup.hide()
            return
        
        query = text.split('-')[0].strip()
        if len(query) < 1 or not self.fund_search_list:
            self.search_popup.hide()
            return
        
        # 完整6位代码不弹窗
        if query.isdigit() and len(query) == 6:
            self.search_popup.hide()
            return
        
        query_upper = query.upper()
        results = []
        for item in self.fund_search_list:
            code, abbr, name, fund_type, full_pinyin = item
            if (query in name or query in code or
                query_upper in abbr or query_upper in full_pinyin):
                results.append(item)
            if len(results) >= 15:
                break
        
        if results:
            self.search_popup.clear()
            for code, abbr, name, fund_type, _ in results:
                display = f"{code}  {name}  [{fund_type}]"
                list_item = QListWidgetItem(display)
                list_item.setData(Qt.UserRole, code)
                list_item.setData(Qt.UserRole + 1, name)
                self.search_popup.addItem(list_item)
            
            pos = self.input_box.mapToGlobal(self.input_box.rect().bottomLeft())
            popup_h = min(380, len(results) * 28 + 8)
            self.search_popup.setFixedSize(self.input_box.width(), popup_h)
            self.search_popup.move(pos)
            self.search_popup.show()
        else:
            self.search_popup.hide()

    def on_search_item_clicked(self, item):
        """点击补全列表项，直接添加基金到自选"""
        code = item.data(Qt.UserRole)
        name = item.data(Qt.UserRole + 1)
        
        # 提取用户输入的板块后缀
        current_text = self.input_box.text()
        parts = current_text.split('-', 1)
        sector = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
        if not sector:
            sector = extract_fund_sector(name, code)
        
        self.search_popup.hide()
        self.input_box.blockSignals(True)
        self.input_box.clear()
        self.input_box.blockSignals(False)
        
        if code not in self.config.get("funds_info", {}):
            self.config["funds_info"][code] = {"name": name, "sector": sector, "is_held": False, "amount": "", "yield_rate": ""}
            self.save_config()
            self.statusBar().showMessage(f"✅ 已添加: {name} ({code}) [板块: {sector}]", 5000)
            self.refresh_data()
        else:
            self.statusBar().showMessage(f"⚠️ {name} ({code}) 已在自选列表中", 3000)

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
            sector = extract_fund_sector(name, code)

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
        self.ranking_fetcher = RankingFetcher(self.all_funds_code_to_name, self.shared_sector_map) 
        self.ranking_fetcher.ranking_signal.connect(self.on_ranking_fetched)
        self.ranking_fetcher.start()

        self.valuation_fetcher = ValuationFetcher(self.all_funds_dict, self.shared_sector_map)
        self.valuation_fetcher.valuation_signal.connect(self.on_valuation_fetched)
        self.valuation_fetcher.start()
        
        self.statusBar().showMessage("正在抓取市场及估值数据...")

    def on_valuation_fetched(self, valuation_list, is_success):
        if not is_success:
            if self.model3.rowCount() == 0:
                self.statusBar().showMessage("估值榜获取失败（网络繁忙或 API 暂时不可用）")
            else:
                self.statusBar().showMessage("估值榜更新失败，显示历史缓存数据")
            return

        self.model3.clear_all()
        
        self.valuation_mapping = {} # index_code -> fund_code
        fetch_codes = []

        if not valuation_list:
            self.statusBar().showMessage("估值榜暂无符合条件的数据")
        else:
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
                pe_pct_str = item.get("pe_percentile", "--")
                pb_pct_str = item.get("pb_percentile", "--")
                
                # 综合判断估值状态（优先看百分位）
                status = "未知"
                pct_val = -1
                try:
                    # 优先取 PE 百分位，若无效取 PB 百分位
                    if pe_pct_str != "--": pct_val = float(pe_pct_str)
                    elif pb_pct_str != "--": pct_val = float(pb_pct_str)
                    
                    if pct_val >= 0:
                        if pct_val < 10: status = "极低估"
                        elif pct_val < 30: status = "低估"
                        elif pct_val > 90: status = "极高估"
                        elif pct_val > 70: status = "高估"
                        else: status = "适中"
                except: pass
                
                display_info = f"{status}\nPE:{pe_val} ({pe_pct_str}%)\nPB:{pb_val} ({pb_pct_str}%)"
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

    def on_ranking_fetched(self, top_list, bot_list, is_success):
        if not is_success:
            if self.model2.rowCount() == 0:
                self.statusBar().showMessage("排行榜获取失败（网络繁忙或 API 暂时不可用）")
            else:
                self.statusBar().showMessage("排行榜更新失败，显示历史缓存数据")
            return

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
        
        # 保护逻辑：如果新数据中的名称是代码本身（说明没查到名称），且当前已有名称，则不覆盖
        new_name = data.get('name')
        if new_name:
            if new_name == code and row_data.get("基金名称") and row_data["基金名称"] != "加载中..." and not row_data["基金名称"].isdigit():
                pass # 保持原样
            else:
                row_data["基金名称"] = new_name
        
        if is_my_fund:
            sector = self.config["funds_info"].get(code, {}).get("sector", "")
            # 优先检查共享板块库是否有 API 更新的数据
            api_sector = self.shared_sector_map.get(code)
            if api_sector and api_sector != sector:
                sector = api_sector
                self.config["funds_info"][code]["sector"] = sector
                self.need_config_save = True
            
            if not sector or sector == "未知":
                sector = extract_fund_sector(data.get('name', ""), code)
                self.config["funds_info"][code]["sector"] = sector
                self.need_config_save = True
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
        
        # 存储原始历史数据，用于迷你图和详情图
        history_data = self.history_cache.get(code, {})
        row_data["_history"] = history_data
        row_data["_navs"] = history_data.get('navs', [])
        row_data["1年趋势"] = "" # 由 Delegate 绘制
        
        model.update_row(row, row_data)

    def show_detailed_chart(self, table, index):
        """双击行显示详细走势图"""
        model = table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        
        code = row_data.get("基金代码")
        name = row_data.get("基金名称", "未知")
        history = row_data.get("_history", {})
        if not history or not history.get("navs"):
            # 如果内存没有，尝试从数据库获取
            history = self.db.get_history(code) or {}
            
        if history and history.get("navs"):
            dialog = FundChartDialog(code, name, history, self)
            dialog.exec()
        else:
            QMessageBox.information(self, "提示", f"基金 {name} ({code}) 暂无历史走势数据，请等待刷新或手动刷新。")

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
