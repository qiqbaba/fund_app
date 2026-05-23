# strategy_center_tab.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QListWidget, QStackedWidget
from PySide6.QtCore import Qt

class StrategyCenterTab(QWidget):
    """策略中心 Tab"""

    def __init__(self, get_fund_lists_func, history_cache, db, parent=None):
        super().__init__(parent)
        self.get_fund_lists_func = get_fund_lists_func
        self.history_cache = history_cache
        self.db = db
        
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 左侧策略选择列表
        self.strategy_list = QListWidget()
        self.strategy_list.setFixedWidth(150)
        self.strategy_list.addItem("📉 抄底止盈回测")
        self.strategy_list.addItem("（待添加策略）")

        # 右侧堆栈视图
        self.strategy_stack = QStackedWidget()

        # 实例化批量寻优和回测面板
        from ui.dialogs.batch_backtest_dialog import BatchBacktestWidget
        self.backtest_widget = BatchBacktestWidget(
            self.get_fund_lists_func, 
            self.history_cache, 
            self.db, 
            self
        )
        empty_widget = QWidget()

        self.strategy_stack.addWidget(self.backtest_widget)
        self.strategy_stack.addWidget(empty_widget)

        # 绑定列表选择联动切换
        self.strategy_list.currentRowChanged.connect(self.strategy_stack.setCurrentIndex)

        layout.addWidget(self.strategy_list)
        layout.addWidget(self.strategy_stack)
