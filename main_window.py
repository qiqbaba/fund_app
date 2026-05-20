# main_window.py
import json
import os
import re
import time
import requests
import threading

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLineEdit, QPushButton, QTableView, QHeaderView, 
                               QMessageBox, QTabWidget, QListWidget, QListWidgetItem,
                               QMenu, QStackedWidget)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush, QFont, QAction

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

        self.btn_add_special = QPushButton("🔥 添加到特别关注")
        self.btn_add_special.setFixedHeight(35)
        self.btn_add_special.setStyleSheet("background-color: #eb4d4b; color: white;")
        self.btn_add_special.clicked.connect(self.add_special_funds)

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
        top_layout.addWidget(self.btn_add_special)
        top_layout.addWidget(self.btn_refresh)
        top_layout.addWidget(self.btn_auto) 
        top_layout.addWidget(self.btn_settings)
        layout.addLayout(top_layout)

        self.tabs = QTabWidget()
        
        # Tab 0: 特别关注
        self.tab0 = QWidget()
        layout0 = QVBoxLayout(self.tab0)
        layout0.setContentsMargins(0, 0, 0, 0)
        self.table0 = QTableView()
        self.table0.setAlternatingRowColors(True)
        self.table0.verticalHeader().setVisible(False)
        self.table0.setSelectionBehavior(QTableView.SelectRows)
        self.table0.setSelectionMode(QTableView.SingleSelection)
        self.table0.setMouseTracking(True)
        layout0.addWidget(self.table0)
        
        # Tab 1: 我的自选基金
        self.tab1 = QWidget()
        layout1 = QVBoxLayout(self.tab1)
        layout1.setContentsMargins(0, 0, 0, 0)
        self.table1 = QTableView()
        self.table1.setAlternatingRowColors(True)
        self.table1.verticalHeader().setVisible(False)
        self.table1.setSelectionBehavior(QTableView.SelectRows)
        self.table1.setSelectionMode(QTableView.SingleSelection)
        self.table1.setMouseTracking(True)
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
        self.table2.setMouseTracking(True)
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
        self.table3.setMouseTracking(True)
        layout3.addWidget(self.table3)
        
        # Tab 4: 其他(已有数据)
        self.tab_other = QWidget()
        layout_other = QVBoxLayout(self.tab_other)
        layout_other.setContentsMargins(0, 0, 0, 0)
        self.table_other = QTableView()
        self.table_other.setAlternatingRowColors(True)
        self.table_other.verticalHeader().setVisible(False)
        self.table_other.setSelectionBehavior(QTableView.SelectRows)
        self.table_other.setSelectionMode(QTableView.SingleSelection)
        self.table_other.setMouseTracking(True)
        layout_other.addWidget(self.table_other)
        
        # Tab 5: 策略中心
        self.tab4 = QWidget()
        layout4 = QHBoxLayout(self.tab4)
        
        self.strategy_list = QListWidget()
        self.strategy_list.setFixedWidth(150)
        self.strategy_list.addItem("📉 抄底止盈回测")
        self.strategy_list.addItem("（待添加策略）")
        
        self.strategy_stack = QStackedWidget()
        
        from batch_backtest_dialog import BatchBacktestWidget
        self.backtest_widget = BatchBacktestWidget(self.get_fund_lists, self.history_cache, self.db, self)
        empty_widget = QWidget()
        
        self.strategy_stack.addWidget(self.backtest_widget)
        self.strategy_stack.addWidget(empty_widget)
        
        self.strategy_list.currentRowChanged.connect(self.strategy_stack.setCurrentIndex)
        
        layout4.addWidget(self.strategy_list)
        layout4.addWidget(self.strategy_stack)
        
        self.tabs.addTab(self.tab0, "🔥 特别关注")
        self.tabs.addTab(self.tab1, "⭐ 我的自选基金")
        self.tabs.addTab(self.tab2, "📈 今日指数ETF独立涨跌榜")
        self.tabs.setTabToolTip(2, "已过滤同质化")
        self.tabs.addTab(self.tab3, "💎 估值榜")
        self.tabs.setTabToolTip(3, "PE/PB 最高最低")
        self.tabs.addTab(self.tab_other, "📦 其他(已有数据)")
        self.tabs.addTab(self.tab4, "💡 策略中心")
        
        layout.addWidget(self.tabs)

        # 绑定点击和双击事件
        self.table0.clicked.connect(lambda index: self.on_table_clicked(self.table0, index))
        self.table1.clicked.connect(lambda index: self.on_table_clicked(self.table1, index))
        self.table2.clicked.connect(lambda index: self.on_table_clicked(self.table2, index))
        self.table3.clicked.connect(lambda index: self.on_table_clicked(self.table3, index))
        
        self.table0.doubleClicked.connect(lambda index: self.show_detailed_chart(self.table0, index))
        self.table1.doubleClicked.connect(lambda index: self.show_detailed_chart(self.table1, index))
        self.table2.doubleClicked.connect(lambda index: self.show_detailed_chart(self.table2, index))
        self.table3.doubleClicked.connect(lambda index: self.show_detailed_chart(self.table3, index))
        self.table_other.clicked.connect(lambda index: self.on_table_clicked(self.table_other, index))
        self.table_other.doubleClicked.connect(lambda index: self.show_detailed_chart(self.table_other, index))

        # 右键菜单
        self.table0.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table0.customContextMenuRequested.connect(lambda pos: self.show_context_menu(self.table0, pos))
        self.table1.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table1.customContextMenuRequested.connect(lambda pos: self.show_context_menu(self.table1, pos))
        self.table2.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table2.customContextMenuRequested.connect(lambda pos: self.show_context_menu(self.table2, pos))
        self.table3.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table3.customContextMenuRequested.connect(lambda pos: self.show_context_menu(self.table3, pos))
        self.table_other.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_other.customContextMenuRequested.connect(lambda pos: self.show_context_menu(self.table_other, pos))

        self.apply_styles()
        
        # 初始化表格模型和代理 - 将在 rebuild_table_headers 中设置
        self.model0 = None
        self.model1 = None
        self.model2 = None
        self.model3 = None
        self.delegate0 = None
        self.delegate1 = None
        self.delegate2 = None
        self.delegate3 = None
        self.model_other = None
        self.delegate_other = None
        
        self.rebuild_table_headers()

    def rebuild_table_headers(self):
        self.headers = ["序号", "持有", "基金代码", "基金名称", "基金板块", "最优参数", "持有金额/\n收益率", 
                        "昨日净值", "净值日期", "实时估值", "今日收益/\n收益率"]
        self.val_headers = ["序号", "估值标签", "基金代码", "基金名称", "基金板块", "最优参数", "估值状态\n(PE/PB)", 
                            "昨日净值", "净值日期", "实时估值", "今日收益/\n收益率"]
        
        self.drop_days = self.config.get("drop_days", [2, 4])
        self.pct_months = self.config.get("percentile_months", [1, 2, 3, 6, 12, 24])
        
        for d in self.drop_days: 
            self.headers.append(f"近{d}日\n涨跌")
            self.val_headers.append(f"近{d}日\n涨跌")
        for m in self.pct_months: 
            self.headers.append(f"近{m}月\n百分位")
            self.val_headers.append(f"近{m}月\n百分位")
            
        self.headers.extend(["趋势", "更新时间", "操作"])
        self.val_headers.extend(["趋势", "更新时间", "操作"])
        
        # 兼容性升级 hidden_columns 为分 Tab 字典格式
        hidden_cols_config = self.config.get("hidden_columns", {})
        if not isinstance(hidden_cols_config, dict):
            old_list = list(hidden_cols_config) if isinstance(hidden_cols_config, list) else []
            hidden_cols_config = {
                "special": list(old_list),
                "my_fund": list(old_list),
                "ranking": list(old_list),
                "valuation": list(old_list),
                "other": list(old_list)
            }
            # 特殊处理估值榜上的老列名转换
            if "持有" in hidden_cols_config["valuation"]:
                hidden_cols_config["valuation"].remove("持有")
                hidden_cols_config["valuation"].append("估值标签")
            if "持有金额/\n收益率" in hidden_cols_config["valuation"]:
                hidden_cols_config["valuation"].remove("持有金额/\n收益率")
                hidden_cols_config["valuation"].append("估值状态\n(PE/PB)")
            self.config["hidden_columns"] = hidden_cols_config
            self.need_config_save = True
        
        # 创建模型和代理
        for table, table_type in [(self.table0, "special"), (self.table1, "my_fund"), 
                                  (self.table2, "ranking"), (self.table3, "valuation"), (self.table_other, "other")]:
            table_headers = self.val_headers if table_type == "valuation" else self.headers
            model = FundTableModel(table_headers, parent=self)
            delegate = FundTableDelegate(table_type=table_type, parent=self)
            
            # 为了避免 Qt 在 setModel 时触发旧列的错误排序，先禁用排序
            table.setSortingEnabled(False)
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
            table.setColumnWidth(5, 120)  # 最优参数，支持换行
            table.setColumnWidth(6, 85)
            table.setColumnWidth(7, 75)
            table.setColumnWidth(8, 80)
            table.setColumnWidth(9, 75)
            table.setColumnWidth(10, 85)
            
            # 减小数据列宽度
            for col_idx in range(11, len(table_headers) - 3):
                table.setColumnWidth(col_idx, 65)
            
            trend_col_index = len(table_headers) - 3
            table.setColumnWidth(trend_col_index, 80)
            
            time_col_index = len(table_headers) - 2
            table.setColumnWidth(time_col_index, 130)
            
            action_col_index = len(table_headers) - 1
            header_view.setSectionResizeMode(action_col_index, QHeaderView.Fixed)
            table.setColumnWidth(action_col_index, 60)
            
            # 隐藏指定列
            table_hidden_cols = hidden_cols_config.get(table_type, [])
            for i, h in enumerate(table_headers):
                table.setColumnHidden(i, h in table_hidden_cols)
            
            # 保存模型和代理引用
            if table == self.table0:
                self.model0 = model
                self.delegate0 = delegate
            elif table == self.table1:
                self.model1 = model
                self.delegate1 = delegate
            elif table == self.table2:
                self.model2 = model
                self.delegate2 = delegate
            elif table == self.table3:
                self.model3 = model
                self.delegate3 = delegate
            else:  # table_other
                self.model_other = model
                self.delegate_other = delegate

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f6fa; }
            QLineEdit { border: 1px solid #dcdde1; border-radius: 4px; padding: 5px; font-size: 13px;}
            QPushButton { background-color: #0097e6; color: white; border-radius: 4px; font-weight: bold; font-size: 13px; padding: 0 15px;}
            QPushButton:hover { background-color: #00a8ff; }
            QPushButton:disabled { background-color: #a4b0be; }
            QTableView { 
                background-color: white; 
                border: 1px solid #dcdde1; 
                border-radius: 4px; 
                font-size: 13px;
                outline: none;
            }
            QTableView::item:hover {
                background-color: transparent;
            }
            QHeaderView::section { 
                background-color: #f1f2f6; 
                padding: 5px; 
                font-weight: bold; 
                border-right: 1px solid #dcdde1; 
                border-bottom: 1px solid #dcdde1;
                color: #2f3542;
            }
            QTabWidget::pane { border: 1px solid #dcdde1; border-radius: 4px; background: white; margin-top:-1px;}
            QTabBar::tab { background: #f1f2f6; padding: 8px 20px; border: 1px solid #dcdde1; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; font-weight: bold;}
            QTabBar::tab:selected { background: white; border-bottom: 2px solid white; border-top: 3px solid #0097e6; }
            QScrollBar:vertical {
                border: none;
                background: #f1f2f6;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #ced6e0;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #a4b0be;
            }
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
        
        dialog = SettingsDialog(self.config, self.headers, self.val_headers, self)
        if dialog.exec():
            self.save_config()
            
            # 如果影响了列的数量（即数据参数变化），需要重建表头和重新获取数据
            if self.config.get("drop_days") != old_drops or self.config.get("percentile_months") != old_pcts:
                self.rebuild_table_headers()
                self.refresh_data()
            else:
                # 如果仅仅是显示/隐藏列变化，不需要重建 model，直接更新视图即可，避免数据消失
                hidden_cols_config = self.config.get("hidden_columns", {})
                for table, table_type, table_headers in [
                    (self.table0, "special", self.headers), 
                    (self.table1, "my_fund", self.headers), 
                    (self.table2, "ranking", self.headers), 
                    (self.table3, "valuation", self.val_headers), 
                    (self.table_other, "other", self.headers)
                ]:
                    table_hidden_cols = hidden_cols_config.get(table_type, [])
                    for i, h in enumerate(table_headers):
                        table.setColumnHidden(i, h in table_hidden_cols)

    def get_fund_lists(self):
        return {
            "特别关注": [(self.model0.get_row_data(i)["基金代码"], self.model0.get_row_data(i)["基金名称"]) for i in range(self.model0.rowCount())] if self.model0 else [],
            "我的自选基金": [(self.model1.get_row_data(i)["基金代码"], self.model1.get_row_data(i)["基金名称"]) for i in range(self.model1.rowCount())] if self.model1 else [],
            "今日指数ETF独立涨跌榜": [(self.model2.get_row_data(i)["基金代码"], self.model2.get_row_data(i)["基金名称"]) for i in range(self.model2.rowCount())] if self.model2 else [],
            "估值榜": [(self.model3.get_row_data(i)["基金代码"], self.model3.get_row_data(i)["基金名称"]) for i in range(self.model3.rowCount())] if self.model3 else [],
            "其他(已有数据)": [(self.model_other.get_row_data(i)["基金代码"], self.model_other.get_row_data(i)["基金名称"]) for i in range(self.model_other.rowCount())] if self.model_other else []
        }

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
            
            # 优化：只向自选表添加一行，而不刷新整个市场
            self.add_single_fund_to_model(code, name, sector)
            # 仅为新添加的基金启动抓取
            self.start_individual_fetcher([code])
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
            # 这里由于可能添加了多个，简单起见重新同步一下表格（但不刷新全市场）
            self.update_my_funds_table()
            self.update_special_funds_table()
            self.start_individual_fetcher(list(self.config.get("funds_info", {}).keys()))

    def add_special_funds(self):
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
                    self.config["funds_info"][code] = {"name": "", "sector": sector, "is_held": False, "amount": "", "yield_rate": "", "is_special": True}
                    added += 1
                else:
                    self.config["funds_info"][code]["is_special"] = True
                    if sector:
                        self.config["funds_info"][code]["sector"] = sector
                    added += 1
                    
        if added > 0:
            self.save_config()
            self.input_box.clear()
            self.update_my_funds_table()
            self.update_special_funds_table()
            self.start_individual_fetcher(list(self.config.get("funds_info", {}).keys()))

    def delete_fund(self, code):
        name = self.config.get("funds_info", {}).get(code, {}).get("name", code)
        reply = QMessageBox.question(self, "确认删除", f"确定要将基金 {name} ({code}) 从自选列表中删除吗？", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if code in self.config.get("funds_info", {}):
                del self.config["funds_info"][code]
                self.save_config()
                self.statusBar().showMessage(f"🗑️ 已删除: {name} ({code})", 3000)
                
                # 优化：从模型中删除，不刷新全市场
                self.model0.remove_row_by_code(code)
                self.model1.remove_row_by_code(code)
                
                # 同步更新排行榜和估值榜中的按钮状态
                self._sync_action_button_status(code, "➕关注")
            
    def on_table_clicked(self, table, index):
        """处理表格点击事件，特别是操作列"""
        column = index.column()
        if column != len(self.headers) - 1: # 仅处理操作列
            return
            
        model = table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        code = row_data.get("基金代码")
        name = row_data.get("基金名称")
        action = row_data.get("操作")
        
        if action == "❌删除":
            self.delete_fund(code)
        elif action == "➕关注":
            sector = row_data.get("基金板块", "")
            self.add_from_market(code, name, sector)

    def show_context_menu(self, table, pos):
        """显示右键菜单"""
        index = table.indexAt(pos)
        if not index.isValid():
            return
            
        model = table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        code = row_data.get("基金代码")
        name = row_data.get("基金名称")
        
        # 获取配置中的信息
        fund_info = self.config.get("funds_info", {}).get(code, {})
        is_pinned = fund_info.get("is_pinned", False)
        is_special = fund_info.get("is_special", False)
        in_my_funds = code in self.config.get("funds_info", {})
        
        menu = QMenu(self)
        
        view_chart_action = QAction(f"📊 查看走势图", self)
        view_chart_action.triggered.connect(lambda: self.show_detailed_chart(table, index))
        menu.addAction(view_chart_action)

        backtest_action = QAction("💡 策略回测", self)
        backtest_action.triggered.connect(lambda: self.show_backtest_dialog(code, name))
        menu.addAction(backtest_action)
        
        menu.addSeparator()
        
        if in_my_funds:
            pin_text = "📌 取消置顶" if is_pinned else "📌 置顶基金"
            pin_action = QAction(pin_text, self)
            pin_action.triggered.connect(lambda: self.toggle_pin_fund(code))
            menu.addAction(pin_action)
            
            special_text = "⭐ 取消特别关注" if is_special else "🔥 添加到特别关注"
            special_action = QAction(special_text, self)
            special_action.triggered.connect(lambda: self.toggle_special_fund(code))
            menu.addAction(special_action)
            
            delete_action = QAction(f"🗑️ 从自选删除 {name}", self)
            delete_action.triggered.connect(lambda: self.delete_fund(code))
            menu.addAction(delete_action)
        else:
            add_my_action = QAction("⭐ 添加到自选", self)
            sector = row_data.get("基金板块", "")
            add_my_action.triggered.connect(lambda: self.add_from_market(code, name, sector))
            menu.addAction(add_my_action)
            
            add_special_action = QAction("🔥 添加到特别关注", self)
            add_special_action.triggered.connect(lambda: self.add_from_market(code, name, sector, to_special=True))
            menu.addAction(add_special_action)
        
        menu.exec(table.viewport().mapToGlobal(pos))

    def show_backtest_dialog(self, code, name):
        """显示策略回测弹窗"""
        # 优先从内存缓存中取数据
        history_data = self.history_cache.get(code)
        if not history_data:
            # 或者尝试从数据库中获取
            history_data = self.db.get_history(code)
            
        if not history_data or not history_data.get("navs"):
            QMessageBox.warning(self, "数据不足", f"没有找到基金 {name} ({code}) 的历史数据，请稍后重试或等待刷新完成。")
            return
            
        from backtest_dialog import BacktestDialog
        dialog = BacktestDialog(code, name, history_data, self)
        dialog.exec()


    def toggle_special_fund(self, code):
        """切换特别关注状态"""
        if code in self.config.get("funds_info", {}):
            current_state = self.config["funds_info"][code].get("is_special", False)
            new_state = not current_state
            self.config["funds_info"][code]["is_special"] = new_state
            self.save_config()
            
            # 更新模型
            if new_state:
                # 添加到特别关注表
                fund_info = self.config["funds_info"][code]
                self.add_single_fund_to_model(code, fund_info.get("name"), fund_info.get("sector"), to_special=True)
                # 触发抓取以确保数据最新
                self.start_individual_fetcher([code])
            else:
                # 从特别关注表移除
                if self.model0:
                    self.model0.remove_row_by_code(code)
            
            self.statusBar().showMessage("✅ 已更新特别关注状态", 2000)

    def toggle_pin_fund(self, code):
        """切换置顶状态"""
        if code in self.config.get("funds_info", {}):
            current_state = self.config["funds_info"][code].get("is_pinned", False)
            new_state = not current_state
            self.config["funds_info"][code]["is_pinned"] = new_state
            self.save_config()
            
            # 优化：同步更新所有涉及该基金的模型数据
            for model, table in [(self.model1, self.table1), (self.model0, self.table0)]:
                if model:
                    row = model.find_row_by_code(code)
                    if row != -1:
                        row_data = model.get_row_data(row)
                        row_data["_is_pinned"] = new_state
                        model.update_row(row, row_data)
                        
                        # 触发排序应用置顶
                        header_view = table.horizontalHeader()
                        model.sort(header_view.sortIndicatorSection(), header_view.sortIndicatorOrder())
                
            self.statusBar().showMessage("✅ 已更新置顶状态", 2000)
    def add_from_market(self, code, name, sector, to_special=False):
        if not sector or sector in ["未知", "-", ""] or "最高" in sector or "最低" in sector:
            sector = extract_fund_sector(name, code)

        if code not in self.config.get("funds_info", {}):
            self.config["funds_info"][code] = {"name": name, "sector": sector, "is_held": False, "amount": "", "yield_rate": "", "is_special": to_special}
            self.save_config()
            
            # 优化：向自选表添加一行
            self.add_single_fund_to_model(code, name, sector)
            if to_special:
                self.add_single_fund_to_model(code, name, sector, to_special=True)
                
            self.start_individual_fetcher([code])
            
            target = "特别关注" if to_special else "我的自选"
            QMessageBox.information(self, "添加成功", f"已成功将 {name} (板块: {sector}) 放入{target}列表！")
            
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

    def _sync_action_button_status(self, code, status_text):
        """同步更新各个表中某基金的操作按钮状态"""
        for model in [self.model2, self.model3, self.model_other]:
            if model:
                rows = model.find_all_rows_by_code(code)
                for r in rows:
                    row_data = model.get_row_data(r)
                    row_data["操作"] = status_text
                    model.update_row(r, row_data)

    def add_single_fund_to_model(self, code, name, sector, to_special=False):
        """向模型添加单个基金行"""
        model = self.model0 if to_special else self.model1
        table = self.table0 if to_special else self.table1
        
        if not model: return

        # 1. 尝试从另一个自选表中查找现有数据（最完整的数据源）
        other_model = self.model1 if to_special else self.model0
        existing_row = -1
        if other_model:
            existing_row = other_model.find_row_by_code(code)
        
        if existing_row != -1:
            row_data = other_model.get_row_data(existing_row).copy()
            # 更新序号为当前模型的序号
            row_data["序号"] = str(model.rowCount() + 1)
        else:
            # 2. 尝试从排行榜或估值榜中查找数据
            found_in_market = False
            for m in [self.model2, self.model3]:
                if m:
                    idx = m.find_row_by_code(code)
                    if idx != -1:
                        row_data = m.get_row_data(idx).copy()
                        row_data["序号"] = str(model.rowCount() + 1)
                        # 重置操作按钮为自选列表的样式
                        row_data["操作"] = "❌删除"
                        found_in_market = True
                        break
            
            if not found_in_market:
                # 3. 都没有，则创建空白行
                row_data = {h: "-" for h in self.headers}
                row_data["序号"] = str(model.rowCount() + 1)
                row_data["持有"] = "0"
                row_data["基金代码"] = code
                row_data["基金名称"] = name if name else "加载中..."
                row_data["基金板块"] = sector
                
                opt = self.db.get_optimal_strategy(code)
                if opt:
                    row_data["最优参数"] = f"买{opt['buy_days']}天>{opt['buy_drop']}% 盈>{opt['target_profit']}%"
                    row_data["_opt_time"] = opt.get('update_time')
                else:
                    row_data["最优参数"] = "-"
                    row_data["_opt_time"] = None
                
                fund_info = self.config.get("funds_info", {}).get(code, {})
                row_data["持有金额/\n收益率"] = fund_info.get("amount", "")
                row_data["操作"] = "❌删除"
                row_data["_is_pinned"] = fund_info.get("is_pinned", False)
        
        # 确保基础元数据正确
        fund_info = self.config.get("funds_info", {}).get(code, {})
        row_data["_is_pinned"] = fund_info.get("is_pinned", False)
        if to_special or not to_special: # 统一设为删除，因为 model0 和 model1 都是自选性质
             row_data["操作"] = "❌删除"

        model.add_row(row_data)
        
        # 应用排序
        if table:
            header_view = table.horizontalHeader()
            model.sort(header_view.sortIndicatorSection(), header_view.sortIndicatorOrder())
        
        # 同步更新其他表的状态
        if not to_special:
            self._sync_action_button_status(code, "已添加")

    def update_my_funds_table(self):
        """仅更新自选基金表格结构，不触发其他 Tab 刷新"""
        funds = sorted(list(self.config.get("funds_info", {}).keys()), 
                       key=lambda x: self.config["funds_info"][x].get("is_pinned", False), 
                       reverse=True)
        
        self.model1.clear_all()
        for code in funds:
            fund_info = self.config["funds_info"][code]
            self.add_single_fund_to_model(code, fund_info.get("name"), fund_info.get("sector"))

    def update_special_funds_table(self):
        """更新特别关注表格结构"""
        funds = [code for code, info in self.config.get("funds_info", {}).items() if info.get("is_special")]
        # 同样按置顶排序
        funds.sort(key=lambda x: self.config["funds_info"][x].get("is_pinned", False), reverse=True)
        
        self.model0.clear_all()
        for code in funds:
            fund_info = self.config["funds_info"][code]
            self.add_single_fund_to_model(code, fund_info.get("name"), fund_info.get("sector"), to_special=True)

    def start_individual_fetcher(self, codes):
        """为特定的一组代码启动抓取线程，不影响排行榜/估值榜列表"""
        if not codes: return
        
        # 合并当前所有需要显示的基金代码，确保数据完整性
        my_funds = list(self.config.get("funds_info", {}).keys())
        market_codes = []
        if self.model2:
            market_codes = [self.model2.data_rows[i].get("基金代码") for i in range(len(self.model2.data_rows))]
        valuation_codes = []
        if self.model3:
            valuation_codes = [self.model3.data_rows[i].get("基金代码") for i in range(len(self.model3.data_rows))]
        other_codes = []
        if hasattr(self, 'model_other') and self.model_other:
            other_codes = [self.model_other.data_rows[i].get("基金代码") for i in range(len(self.model_other.data_rows))]
        
        all_fetch_codes = list(set(my_funds + market_codes + valuation_codes + other_codes))
        
        if hasattr(self, "fetcher") and self.fetcher.isRunning():
            self.fetcher.requestInterruption()
            self.fetcher.wait()

        self.fetcher = FundDataFetcher(all_fetch_codes, self.config, self.history_cache, self.all_funds_code_to_name, self.db)
        self.fetcher.update_signal.connect(self.dispatch_table_update)
        self.fetcher.error_signal.connect(self.dispatch_table_error)
        self.fetcher.finish_signal.connect(self.on_fetch_finish)
        self.fetcher.start()

    def refresh_data(self):
        if not self.btn_refresh.isEnabled(): return

        self.btn_refresh.setEnabled(False)
        self.latest_data_time = ""  # 重置数据源时间
        
        # 获取基金列表，并按照置顶状态进行初始排序（置顶在前）
        funds = sorted(list(self.config.get("funds_info", {}).keys()), 
                       key=lambda x: self.config["funds_info"][x].get("is_pinned", False), 
                       reverse=True)
        
        # 清空现有数据
        self.model0.clear_all()
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
            
            fund_info = self.config["funds_info"][code]
            row_data["基金板块"] = fund_info.get("sector", "")
            
            opt = self.db.get_optimal_strategy(code)
            if opt:
                row_data["最优参数"] = f"买{opt['buy_days']}天>{opt['buy_drop']}% 盈>{opt['target_profit']}%"
                row_data["_opt_time"] = opt.get('update_time')
            else:
                row_data["最优参数"] = "-"
                row_data["_opt_time"] = None
                
            row_data["持有金额/\n收益率"] = fund_info.get("amount", "")
            row_data["操作"] = "❌删除"
            row_data["_is_pinned"] = fund_info.get("is_pinned", False)
            
            self.model1.add_row(row_data)
            
            # 如果是特别关注，也添加到 model0
            if fund_info.get("is_special"):
                # 重新计算 model0 的序号
                special_row = row_data.copy()
                special_row["序号"] = str(len(self.model0.data_rows) + 1)
                self.model0.add_row(special_row)
        
        # 加载完成后，如果表格开启了排序，需要手动触发一次排序以应用置顶逻辑
        if self.table0.horizontalHeader().sortIndicatorSection() != -1:
            self.model0.sort(self.table0.horizontalHeader().sortIndicatorSection(), 
                             self.table0.horizontalHeader().sortIndicatorOrder())
        if self.table1.horizontalHeader().sortIndicatorSection() != -1:
            self.model1.sort(self.table1.horizontalHeader().sortIndicatorSection(), 
                             self.table1.horizontalHeader().sortIndicatorOrder())
        
        # 启动排行数据获取
        self.ranking_fetcher = RankingFetcher(self.all_funds_code_to_name, self.shared_sector_map) 
        self.ranking_fetcher.ranking_signal.connect(self.on_ranking_fetched)
        self.ranking_fetcher.start()

        self.valuation_fetcher = ValuationFetcher(self.all_funds_dict, self.shared_sector_map)
        self.valuation_fetcher.valuation_signal.connect(self.on_valuation_fetched)
        self.valuation_fetcher.start()
        
        self.statusBar().showMessage("正在抓取市场及估值数据...")

    def update_other_funds_table(self):
        """更新'其他'Tab的基金列表，包含有最优参数但不在前4个Tab中的基金"""
        if not hasattr(self, 'model_other') or not self.model_other:
            return []
            
        all_opt_strategies = self.db.get_all_optimal_strategies()
        
        existing_codes = set()
        existing_codes.update(self.config.get("funds_info", {}).keys())
        if self.model2:
            existing_codes.update(self.model2.data_rows[i].get("基金代码") for i in range(len(self.model2.data_rows)))
        if self.model3:
            existing_codes.update(self.model3.data_rows[i].get("基金代码") for i in range(len(self.model3.data_rows)))
            
        other_codes = set(all_opt_strategies.keys()) - existing_codes
        other_codes = sorted(list(other_codes))
        
        self.model_other.clear_all()
        
        for i, code in enumerate(other_codes):
            opt_data = all_opt_strategies[code]
            name = opt_data.get("fund_name", "未知名称")
            
            row_data = {h: "-" for h in self.headers}
            row_data["序号"] = str(i + 1)
            row_data["持有"] = "-"
            row_data["基金代码"] = code
            row_data["基金名称"] = name
            row_data["基金板块"] = "未知"
            
            row_data["最优参数"] = f"买{opt_data['buy_days']}天>{opt_data['buy_drop']}% 盈>{opt_data['target_profit']}%"
            row_data["_opt_time"] = opt_data.get('update_time')
            row_data["持有金额/\n收益率"] = "-"
            row_data["操作"] = "➕关注"
            row_data["_is_pinned"] = False
            
            self.model_other.add_row(row_data)
            
        if self.table_other.horizontalHeader().sortIndicatorSection() != -1:
            self.model_other.sort(self.table_other.horizontalHeader().sortIndicatorSection(), 
                                  self.table_other.horizontalHeader().sortIndicatorOrder())
                                  
        return other_codes

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
                for header in self.val_headers:
                    row_data[header] = "-"
                
                row_data["序号"] = str(i + 1)
                
                # col 1: 估值标签（PE最高/PB最低等）
                tag_text = item.get("valuation_tag", "")
                row_data["估值标签"] = tag_text
                
                row_data["基金代码"] = fund_code
                row_data["基金名称"] = index_name
                
                # col 4: 基金板块（实际板块名称）
                sector = item.get("extracted_sector", "")
                row_data["基金板块"] = sector
                
                opt = self.db.get_optimal_strategy(fund_code)
                if opt:
                    row_data["最优参数"] = f"买{opt['buy_days']}天>{opt['buy_drop']}% 盈>{opt['target_profit']}%"
                    row_data["_opt_time"] = opt.get('update_time')
                else:
                    row_data["最优参数"] = "-"
                    row_data["_opt_time"] = None
                
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
                row_data["估值状态\n(PE/PB)"] = display_info
                
                row_data["操作"] = "➕关注" if fund_code not in self.config.get("funds_info", {}) else "已添加"
                
                self.model3.add_row(row_data)
        
        # 恢复表3可能存在的排序状态
        if self.table3.horizontalHeader().sortIndicatorSection() != -1:
            self.model3.sort(self.table3.horizontalHeader().sortIndicatorSection(), 
                             self.table3.horizontalHeader().sortIndicatorOrder())
        
        # 启动数据抓取（合并之前的自选和排行榜）
        my_funds = list(self.config.get("funds_info", {}).keys())
        market_codes = [self.model2.data_rows[i].get("基金代码") for i in range(len(self.model2.data_rows))]
        valuation_codes = [self.model3.data_rows[i].get("基金代码") for i in range(len(self.model3.data_rows))]
        
        other_codes = self.update_other_funds_table()
        
        all_fetch_codes = list(set(my_funds + market_codes + valuation_codes + other_codes))
        
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
            
            opt = self.db.get_optimal_strategy(code)
            if opt:
                row_data["最优参数"] = f"买{opt['buy_days']}天>{opt['buy_drop']}% 盈>{opt['target_profit']}%"
                row_data["_opt_time"] = opt.get('update_time')
            else:
                row_data["最优参数"] = "-"
                row_data["_opt_time"] = None
                
            row_data["持有金额/\n收益率"] = "-"
            
            row_data["操作"] = "已添加" if code in self.config.get("funds_info", {}) else "➕关注"
            
            self.model2.add_row(row_data)
        
        # 恢复表2可能存在的排序状态
        if self.table2.horizontalHeader().sortIndicatorSection() != -1:
            self.model2.sort(self.table2.horizontalHeader().sortIndicatorSection(), 
                             self.table2.horizontalHeader().sortIndicatorOrder())
        
        my_funds = list(self.config.get("funds_info", {}).keys())
        valuation_codes = [self.model3.data_rows[i].get("基金代码") for i in range(len(self.model3.data_rows))]
        
        other_codes = self.update_other_funds_table()
        
        all_fetch_codes = list(set(my_funds + market_codes + valuation_codes + other_codes))
        
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
            
        row0 = self.get_row_by_code(self.table0, code)
        if row0 != -1:
            self.populate_row_data(self.model0, row0, data, is_my_fund=True)
            
        row2 = self.get_row_by_code(self.table2, code)
        if row2 != -1:
            self.populate_row_data(self.model2, row2, data, is_my_fund=False)
            
        for row3 in self.get_all_rows_by_code(self.table3, code):
            self.populate_row_data(self.model3, row3, data, is_my_fund=False)
            
        if hasattr(self, 'table_other') and self.table_other:
            for row4 in self.get_all_rows_by_code(self.table_other, code):
                self.populate_row_data(self.model_other, row4, data, is_my_fund=False)

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
            
            # 优先从 API 获取的板块库中匹配
            api_sector = self.shared_sector_map.get(code)
            if api_sector:
                # 即使 API 有值，也通过标准化函数跑一遍
                new_sector = extract_fund_sector(api_sector, code)
            else:
                # 否则，根据当前名称和已有板块，尝试获取最新的标准化板块名
                # 如果当前是 "科创创业"，且新规则下应该是 "双创50"，这里会进行更新
                new_sector = extract_fund_sector(new_name or sector, code)
            
            if new_sector and new_sector != sector:
                sector = new_sector
                self.config["funds_info"][code]["sector"] = sector
                self.need_config_save = True
                
            row_data["基金板块"] = sector
            row_data["_is_pinned"] = self.config["funds_info"].get(code, {}).get("is_pinned", False)
            
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
        
        # 操作列
        if is_my_fund:
            row_data["操作"] = "❌删除"
        else:
            row_data["操作"] = "已添加" if code in self.config.get("funds_info", {}) else "➕关注"

        # 存储原始历史数据，用于迷你图和详情图
        history_data = self.history_cache.get(code, {})
        row_data["_history"] = history_data
        row_data["_navs"] = history_data.get('navs', [])
        row_data["趋势"] = "" # 由 Delegate 绘制
        
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
            
        row0 = self.get_row_by_code(self.table0, code)
        if row0 != -1: 
            self.populate_error(self.model0, row0, code, error_msg, is_my_fund=True)
            
        row2 = self.get_row_by_code(self.table2, code)
        if row2 != -1: 
            self.populate_error(self.model2, row2, code, error_msg, is_my_fund=False)
        
        for row3 in self.get_all_rows_by_code(self.table3, code):
            self.populate_error(self.model3, row3, code, error_msg, is_my_fund=False)

        if hasattr(self, 'table_other') and self.table_other:
            for row4 in self.get_all_rows_by_code(self.table_other, code):
                self.populate_error(self.model_other, row4, code, error_msg, is_my_fund=False)

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
