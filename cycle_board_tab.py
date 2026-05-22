# cycle_board_tab.py
from base_tab import BaseFundTableTab
from PySide6.QtWidgets import QHeaderView, QMenu
from PySide6.QtGui import QAction

class CycleBoardTab(BaseFundTableTab):
    """周期榜 Tab"""

    def __init__(self, parent=None):
        super().__init__("cycle", parent)

    def setup_column_widths(self):
        """周期表特化的列宽度设置"""
        self.table.setColumnWidth(0, 25)   # 序号
        self.table.setColumnWidth(1, 85)   # 周期板块
        self.table.setColumnWidth(2, 160)  # 周期当前位置
        self.table.setColumnWidth(3, 70)   # 关联基金代码
        self.table.setColumnWidth(4, 160)  # 关联基金名称
        self.table.setColumnWidth(5, 75)   # 昨日净值
        self.table.setColumnWidth(6, 80)   # 净值日期
        self.table.setColumnWidth(7, 75)   # 实时估值
        self.table.setColumnWidth(8, 60)   # 今日收益/\n收益率
        self.table.setColumnWidth(9, 60)   # 近12月百分位
        self.table.setColumnWidth(10, 80)  # 趋势
        self.table.setColumnWidth(11, 280) # 投资参考建议
        self.table.setColumnWidth(12, 60)  # 操作
        self.table.horizontalHeader().setSectionResizeMode(12, QHeaderView.Fixed)

    def show_context_menu(self, pos):
        """周期板块中关联基金的特化右键菜单"""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        model = self.table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        
        code = row_data.get("关联基金代码")
        name = row_data.get("关联基金名称") or "未知"
        sector = row_data.get("周期板块") or ""

        if not code or code == "-":
            return

        menu = QMenu(self)

        view_chart_action = QAction("📊 查看走势图", self)
        view_chart_action.triggered.connect(lambda: self.show_chart_signal.emit(code, name))
        menu.addAction(view_chart_action)

        backtest_action = QAction("💡 策略回测", self)
        backtest_action.triggered.connect(lambda: self.show_backtest_signal.emit(code, name))
        menu.addAction(backtest_action)

        menu.addSeparator()

        add_my_action = QAction("⭐ 添加到自选", self)
        add_my_action.triggered.connect(lambda: self.add_fund_signal.emit(code, name, sector, False))
        menu.addAction(add_my_action)

        add_special_action = QAction("🔥 添加到特别关注", self)
        add_special_action.triggered.connect(lambda: self.add_fund_signal.emit(code, name, sector, True))
        menu.addAction(add_special_action)

        menu.exec(self.table.viewport().mapToGlobal(pos))
