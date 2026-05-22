# ranking_tab.py
from base_tab import BaseFundTableTab
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction

class RankingTab(BaseFundTableTab):
    """今日指数ETF独立涨跌榜 Tab"""

    def __init__(self, parent=None):
        super().__init__("ranking", parent)

    def show_context_menu(self, pos):
        """特化的市场排行榜右键菜单"""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        model = self.table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        
        code = row_data.get("基金代码")
        name = row_data.get("基金名称") or "未知"
        sector = row_data.get("基金板块") or ""

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
