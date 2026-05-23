# base_tab.py
import traceback
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import SearchLineEdit, PushButton, PrimaryPushButton, SwitchButton
from ui.table_model import FundTableModel, FundFilterProxyModel, FundTableDelegate

class BaseFundTableTab(QWidget):
    # 定义子 Tab 向主窗口 Controller 汇报的通用信号
    delete_fund_signal = Signal(str)  # 基金代码
    add_fund_signal = Signal(str, str, str, bool)  # 基金代码, 名称, 板块, 是否特别关注
    toggle_pin_signal = Signal(str)  # 基金代码
    toggle_special_signal = Signal(str)  # 基金代码
    show_chart_signal = Signal(str, str)  # 基金代码, 基金名称
    show_backtest_signal = Signal(str, str)  # 基金代码, 基金名称

    def __init__(self, table_type, parent=None):
        """
        :param table_type: 表格类型，如 'special', 'my_fund', 'ranking', 'valuation', 'cycle', 'other'
        """
        super().__init__(parent)
        self.table_type = table_type
        self.headers = []
        self.model = None
        self.proxy = None
        self.delegate = None
        
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # 1. 创建精致的顶部工具栏布局
        self.top_bar_layout = QHBoxLayout()
        self.top_bar_layout.setContentsMargins(0, 0, 0, 5)
        self.top_bar_layout.setSpacing(10)

        # 1.1 如果是 special 或 my_fund，添加“全市场搜索并添加自选”的左侧模块
        if self.table_type in ["special", "my_fund"]:
            self.input_box = SearchLineEdit()
            self.input_box.setPlaceholderText("输入代码/名称搜索添加, 如: 白酒, bj, 004433-消费")
            self.input_box.setFixedWidth(280)
            self.input_box.setFixedHeight(32)
            self.top_bar_layout.addWidget(self.input_box)

            self.btn_add = PrimaryPushButton("➕ 添加自选")
            self.btn_add.setFixedHeight(32)
            self.top_bar_layout.addWidget(self.btn_add)

            self.btn_add_special = PushButton("🔥 特别关注")
            self.btn_add_special.setFixedHeight(32)
            self.btn_add_special.setStyleSheet("color: #e74c3c; border-color: rgba(231, 76, 60, 0.4);")
            self.top_bar_layout.addWidget(self.btn_add_special)
            
            self.top_bar_layout.addSpacing(15)

        # 1.2 本地搜索过滤输入框 (除了'other'之外的 Tab 都有)
        if self.table_type != "other":
            self.filter_input = SearchLineEdit()
            placeholders = {
                "special": "🔍 本地过滤 (名称/代码)...",
                "my_fund": "🔍 本地过滤 (名称/代码)...",
                "ranking": "🔍 在排行榜中搜索 (名称/代码)...",
                "valuation": "🔍 在估值榜中搜索 (名称/代码)...",
                "cycle": "🔍 在周期榜中搜索 (名称/代码/板块)..."
            }
            self.filter_input.setPlaceholderText(placeholders.get(self.table_type, "🔍 本地过滤 (名称/代码)..."))
            self.filter_input.setFixedWidth(220)
            self.filter_input.setFixedHeight(32)
            self.filter_input.textChanged.connect(self.on_filter_text_changed)
            self.top_bar_layout.addWidget(self.filter_input)

        self.top_bar_layout.addStretch()

        # 1.3 统一加上“🔄 刷新全市场”按钮和“自动刷新 (60s)”滑动开关
        self.btn_refresh = PushButton("🔄 刷新全市场")
        self.btn_refresh.setFixedHeight(32)
        self.top_bar_layout.addWidget(self.btn_refresh)

        self.btn_auto = SwitchButton()
        self.btn_auto.setOffText("自动刷新")
        self.btn_auto.setOnText("自动刷新")
        self.btn_auto.setFixedHeight(32)
        self.top_bar_layout.addWidget(self.btn_auto)

        self.layout.addLayout(self.top_bar_layout)

        # 2. 创建表格
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setMouseTracking(True)
        self.layout.addWidget(self.table)

        # 绑定点击与双击信号
        self.table.clicked.connect(self.on_table_clicked)
        self.table.doubleClicked.connect(self.on_table_double_clicked)

        # 右键菜单策略
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

    def on_filter_text_changed(self, text):
        """输入框字符改变，触发局部过滤"""
        if self.proxy:
            self.proxy.setFilterText(text)

    def rebuild_headers(self, headers, hidden_columns_list):
        """重新组装表头和列"""
        self.headers = headers
        self.model = FundTableModel(self.headers, parent=self)
        self.delegate = FundTableDelegate(table_type=self.table_type, parent=self)

        # 挂载前先禁用排序，防范渲染冲突
        self.table.setSortingEnabled(False)

        if self.table_type != "other":
            self.proxy = FundFilterProxyModel(self)
            self.proxy.setSourceModel(self.model)
            self.table.setModel(self.proxy)
        else:
            self.proxy = None
            self.table.setModel(self.model)

        self.table.setItemDelegate(self.delegate)
        self.table.setSortingEnabled(True)

        # 默认列表头大小与交互模式
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Interactive)
        header_view.setDefaultSectionSize(75)
        header_view.setStyleSheet("QHeaderView::section { padding: 2px; }")

        # 单元格默认行高
        self.table.verticalHeader().setDefaultSectionSize(38)

        # 设定具体列宽比
        self.setup_column_widths()

        # 动态隐藏特定列
        for i, h in enumerate(self.headers):
            self.table.setColumnHidden(i, h in hidden_columns_list)

    def setup_column_widths(self):
        """默认表格宽度自适应方案"""
        self.table.setColumnWidth(0, 25)
        self.table.setColumnWidth(1, 35)
        self.table.setColumnWidth(2, 65)
        self.table.setColumnWidth(3, 165)  # 基金名称，支持换行
        self.table.setColumnWidth(4, 85)   # 基金板块，支持换行
        self.table.setColumnWidth(5, 120)  # 最优参数，支持换行
        self.table.setColumnWidth(6, 85)
        self.table.setColumnWidth(7, 75)
        self.table.setColumnWidth(8, 80)
        self.table.setColumnWidth(9, 75)
        self.table.setColumnWidth(10, 60)  # 今日收益/\n收益率
        
        # 批量设置指标列宽度
        for col_idx in range(11, len(self.headers) - 3):
            self.table.setColumnWidth(col_idx, 60)
            
        trend_col_idx = len(self.headers) - 3
        self.table.setColumnWidth(trend_col_idx, 80)
        
        time_col_idx = len(self.headers) - 2
        self.table.setColumnWidth(time_col_idx, 130)
        
        action_col_idx = len(self.headers) - 1
        self.table.horizontalHeader().setSectionResizeMode(action_col_idx, QHeaderView.Fixed)
        self.table.setColumnWidth(action_col_idx, 60)

    # ------------------ 数据交互底层接口映射 (对外屏蔽 Proxy/Model 细节) ------------------
    def clear_all(self):
        if self.model:
            self.model.clear_all()

    def add_row(self, row_data):
        if self.model:
            self.model.add_row(row_data)

    def update_row_by_code(self, code, row_data):
        if self.model:
            rows = self.model.find_all_rows_by_code(code)
            for r in rows:
                self.model.update_row(r, row_data)

    def get_row_data_by_code(self, code):
        if self.model:
            idx = self.model.find_row_by_code(code)
            if idx != -1:
                return self.model.get_row_data(idx)
        return None

    def get_row_data(self, row):
        if self.model:
            return self.model.get_row_data(row)
        return {}

    def rowCount(self):
        return self.model.rowCount() if self.model else 0

    def remove_row_by_code(self, code):
        if self.model:
            return self.model.remove_row_by_code(code)
        return False

    def find_all_rows_by_code(self, code):
        if self.model:
            return self.model.find_all_rows_by_code(code)
        return []

    def find_row_by_code(self, code):
        if self.model:
            return self.model.find_row_by_code(code)
        return -1

    def sort(self, column, order):
        if self.model:
            self.model.sort(column, order)

    def get_sort_indicator(self):
        header = self.table.horizontalHeader()
        return header.sortIndicatorSection(), header.sortIndicatorOrder()

    def trigger_sort_indicator(self):
        sec, order = self.get_sort_indicator()
        if sec != -1:
            self.sort(sec, order)

    # ------------------ 统一点击与双击行为分发 ------------------
    def on_table_clicked(self, index):
        """表格单元格点击处理 (主要是操作列按钮)"""
        if not index.isValid():
            return
        
        column = index.column()
        # 获取被点击列的表头显示名字
        header = self.table.model().headerData(column, Qt.Horizontal, Qt.DisplayRole)
        if header != "操作":
            return

        model = self.table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        
        code = row_data.get("基金代码") or row_data.get("关联基金代码")
        name = row_data.get("基金名称") or row_data.get("关联基金名称")
        action = row_data.get("操作")

        if action == "❌删除":
            self.delete_fund_signal.emit(code)
        elif action == "➕关注":
            sector = row_data.get("基金板块") or row_data.get("周期板块") or ""
            self.add_fund_signal.emit(code, name, sector, False)

    def on_table_double_clicked(self, index):
        """双击处理 (如双击最优参数、双击走势图)"""
        if not index.isValid():
            return

        model = self.table.model()
        row = index.row()
        col = index.column()

        header_text = model.headerData(col, Qt.Horizontal)
        row_data = model.get_row_data(row)
        
        code = row_data.get("基金代码") or row_data.get("关联基金代码")
        name = row_data.get("基金名称") or row_data.get("关联基金名称") or "未知"

        if not code:
            return

        if header_text == "最优参数":
            self.show_backtest_signal.emit(code, name)
        elif header_text == "趋势":
            self.show_chart_signal.emit(code, name)

    def show_context_menu(self, pos):
        """右键菜单 - 由子类覆盖重写"""
        pass
