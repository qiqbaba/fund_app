# my_funds_tab.py
from ui.tabs.base_tab import BaseFundTableTab
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction

class MyFundsTab(BaseFundTableTab):
    """我的自选基金 Tab"""

    def __init__(self, parent=None):
        super().__init__("my_fund", parent)

    def show_context_menu(self, pos):
        """特化的我的自选右键菜单"""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        model = self.table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        
        code = row_data.get("基金代码")
        name = row_data.get("基金名称") or "未知"
        
        is_pinned = row_data.get("_is_pinned", False)
        is_special = row_data.get("_is_special", False)

        # 向上查找真正的 is_special 状态 (因为从 config 中读出来的配置更准，但在 row_data 也带了)
        # 为求稳妥，我们可以直接用 row_data 中的 `_is_special`
        main_win = self.window()
        if main_win and hasattr(main_win, 'config'):
            is_special = main_win.config.get("funds_info", {}).get(code, {}).get("is_special", False)

        menu = QMenu(self)

        view_chart_action = QAction("📊 查看走势图", self)
        view_chart_action.triggered.connect(lambda: self.show_chart_signal.emit(code, name))
        menu.addAction(view_chart_action)

        backtest_action = QAction("💡 策略回测", self)
        backtest_action.triggered.connect(lambda: self.show_backtest_signal.emit(code, name))
        menu.addAction(backtest_action)

        menu.addSeparator()

        pin_text = "📌 取消置顶" if is_pinned else "📌 置顶基金"
        pin_action = QAction(pin_text, self)
        pin_action.triggered.connect(lambda: self.toggle_pin_signal.emit(code))
        menu.addAction(pin_action)

        special_text = "⭐ 取消特别关注" if is_special else "🔥 添加到特别关注"
        special_action = QAction(special_text, self)
        special_action.triggered.connect(lambda: self.toggle_special_signal.emit(code))
        menu.addAction(special_action)

        delete_action = QAction(f"🗑️ 从自选删除 {name}", self)
        delete_action.triggered.connect(lambda: self.delete_fund_signal.emit(code))
        menu.addAction(delete_action)

        menu.exec(self.table.viewport().mapToGlobal(pos))
