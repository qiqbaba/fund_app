# ui/main_window.py
import json
import os
import re
import time
import requests
import threading
import sys

# 临时屏蔽第三方库 qfluentwidgets 导入时的广告打印
class _SilenceStdout:
    def __enter__(self):
        self._orig_stdout = sys.stdout
        sys.stdout = self
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self._orig_stdout
    def write(self, *args, **kwargs):
        pass
    def flush(self, *args, **kwargs):
        pass

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QMessageBox, QListWidget, QListWidgetItem,
                               QMenu, QStackedWidget, QLabel)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush, QFont, QAction

with _SilenceStdout():
    from qfluentwidgets import MSFluentWindow, Theme, setTheme, toggleTheme, NavigationItemPosition, InfoBar, InfoBarPosition
    from qfluentwidgets import FluentIcon as FIF


# 引入拆分出去的模块（绝对导入包修正）
from core.config import CONFIG_FILE
from ui.widgets import SettingsDialog, FundChartDialog, StrategyNotificationToast
from core.threads import RankingFetcher, FundDataFetcher, ValuationFetcher
from core.db_manager import FundHistoryDB
from ui.table_model import (FundTableModel, FundTableDelegate, CheckboxCellWidget, 
                          HoldingInputWidget, ActionButtonWidget, FundFilterProxyModel)
from core.utils import extract_fund_sector

# 引入新拆分的 Tab 页模块组件
from ui.tabs.special_attention_tab import SpecialAttentionTab
from ui.tabs.my_funds_tab import MyFundsTab
from ui.tabs.ranking_tab import RankingTab
from ui.tabs.valuation_tab import ValuationTab
from ui.tabs.cycle_board_tab import CycleBoardTab
from ui.tabs.other_funds_tab import OtherFundsTab
from ui.tabs.strategy_center_tab import StrategyCenterTab


CYCLE_FUNDS = [
    {
        "code": "014414",
        "name": "招商中证畜牧养殖ETF联接A",
        "sector": "生猪养殖",
        "pct_default": 15.0,
        "stage_default": "萧条筑底期",
        "advice": "猪价处于周期底部亏损区间，母猪产能持续去化，适合逢低分批布局，耐心等待周期拐点。"
    },
    {
        "code": "008887",
        "name": "华夏国证半导体芯片ETF联接A",
        "sector": "半导体存储",
        "pct_default": 35.0,
        "stage_default": "复苏拉升期",
        "advice": "全球存储芯片巨头减产成效显现，合约价探底回升，AI算力需求高增驱动周期上行，建议逢低积极配置。"
    },
    {
        "code": "008279",
        "name": "国泰中证煤炭ETF联接A",
        "sector": "煤炭能源",
        "pct_default": 55.0,
        "stage_default": "繁荣适中期",
        "advice": "煤炭行业高红利、高现金流属性明显，供需结构维持紧平衡，股价高位震荡，建议作为长线收息底仓持有。"
    },
    {
        "code": "004432",
        "name": "南方中证申万有色金属ETF联接A",
        "sector": "有色金属",
        "pct_default": 75.0,
        "stage_default": "繁荣后期",
        "advice": "美联储降息预期及地缘政治溢价推高黄金和铜铝价格，工业金属进入景气度后半程，注意追高风险，可逐步分批止盈。"
    },
    {
        "code": "161725",
        "name": "招商中证白酒指数A",
        "sector": "白酒消费",
        "pct_default": 45.0,
        "stage_default": "繁荣适中期",
        "advice": "白酒行业分化加剧，高端白酒韧性强但次高端面临去库存压力。目前估值已回落至中枢以下，适合定投慢慢收集筹码。"
    },
    {
        "code": "004890",
        "name": "广发中证全指建筑材料ETF联接A",
        "sector": "基建建材",
        "pct_default": 10.0,
        "stage_default": "萧条筑底期",
        "advice": "地产链持续承压导致建材需求低迷，估值和价格均处于历史极低水平。政策托底意图明显，适合作为长线左侧埋伏。"
    },
    {
        "code": "012701",
        "name": "南方中证全指证券公司ETF联接A",
        "sector": "证券金融",
        "pct_default": 25.0,
        "stage_default": "复苏拉升期",
        "advice": "券商作为牛市风向标，估值处于历史低位，行业并购重组预期升温，市场成交量回暖时弹性极强，建议震荡期逢低布局。"
    },
    {
        "code": "012929",
        "name": "广发中证光伏产业ETF联接A",
        "sector": "新能源光伏",
        "pct_default": 20.0,
        "stage_default": "复苏拉升期",
        "advice": "光伏产业链价格触底，行业面临产能出清，供给侧改革预期强烈。估值极具吸引力，可关注出清加快后的右侧机会。"
    },
    {
        "code": "003017",
        "name": "易方达中证军工指数A",
        "sector": "国防军工",
        "pct_default": 30.0,
        "stage_default": "复苏拉升期",
        "advice": "国防装备建设进入'十四五'后半程换装高峰，地缘局势不确定性加大，基本面触底回升，具备较强的抗周期与弹性属性。"
    }
]

class FakeStatusBar:
    def __init__(self, parent):
        self.parent = parent
        
    def showMessage(self, text, timeout=0):
        # 兼容处理 timeout 参数
        duration = timeout if isinstance(timeout, (int, float)) and timeout > 0 else 2000
        
        if "✅" in text:
            InfoBar.success(
                title="成功",
                content=text.replace("✅", "").strip(),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=duration,
                parent=self.parent
            )
        elif "⚠️" in text:
            InfoBar.warning(
                title="提示",
                content=text.replace("⚠️", "").strip(),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=duration,
                parent=self.parent
            )
        elif "🗑️" in text:
            InfoBar.info(
                title="删除",
                content=text.replace("🗑️", "").strip(),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=duration,
                parent=self.parent
            )
        elif "失败" in text or "错误" in text:
            InfoBar.error(
                title="错误",
                content=text,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=duration + 1000,
                parent=self.parent
            )
        else:
            self.parent.setStatusTip(text)

class FundApp(MSFluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("场外基金深度监控")
        self.resize(1400, 600)
        
        self.config = self.load_config()
        
        # 加载并应用持久化主题设置
        from qfluentwidgets import setTheme, Theme
        theme_str = self.config.get("theme", "Light")
        if theme_str == "Dark":
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)
            
        self.history_cache = {} 
        self.all_funds_dict = {} 
        self.all_funds_code_to_name = {}
        self.fund_search_list = []
        self.shared_sector_map = {} # 全局板块 API 缓存映射库
        self.need_config_save = False 
        self.active_buy_signals = {} 
        self.is_refreshing = False
        self._status_bar = FakeStatusBar(self)
        
        # 初始化数据库（不再在主线程同步循环加载，改为后台子线程极速批量预载入，耗时仅需数十毫秒，实现秒开且不卡加载）
        self.db = FundHistoryDB()
        
        def preload_history():
            try:
                all_history = self.db.get_all_history()
                if all_history:
                    self.history_cache.update(all_history)
            except Exception as e:
                print(f"[Preload Warning] 批量预加载历史数据失败: {e}")
                
        threading.Thread(target=preload_history, daemon=True).start()
        
        self.refresh_timer = QTimer()
        self.refresh_interval = 60000 
        self.refresh_timer.timeout.connect(self.refresh_data)

        self.init_ui()
        self.load_all_funds_dict() 
        self.refresh_data()

    def statusBar(self):
        return self._status_bar

    def init_ui(self):
        # 1. 实例化各个拆分后的 Tab 页面
        self.special_tab = SpecialAttentionTab(self)
        self.my_funds_tab = MyFundsTab(self)
        self.ranking_tab = RankingTab(self)
        self.valuation_tab = ValuationTab(self)
        self.cycle_tab = CycleBoardTab(self)
        self.other_tab = OtherFundsTab(self)
        self.strategy_tab = StrategyCenterTab(self.get_fund_lists, self.history_cache, self.db, self)

        # 2. 设置唯一的 ObjectName，这是 qfluentwidgets 子窗口切换所必需的
        self.special_tab.setObjectName("special_tab")
        self.my_funds_tab.setObjectName("my_funds_tab")
        self.ranking_tab.setObjectName("ranking_tab")
        self.valuation_tab.setObjectName("valuation_tab")
        self.cycle_tab.setObjectName("cycle_tab")
        self.other_tab.setObjectName("other_tab")
        self.strategy_tab.setObjectName("strategy_tab")

        # 3. 兼容性挂载表格变量引用，使得其他地方直接调用如 self.table0 依旧畅通无阻
        self.table0 = self.special_tab.table
        self.table1 = self.my_funds_tab.table
        self.table2 = self.ranking_tab.table
        self.table3 = self.valuation_tab.table
        self.table_cycle = self.cycle_tab.table
        self.table_other = self.other_tab.table
        
        self.tab0 = self.special_tab
        self.tab1 = self.my_funds_tab
        self.tab2 = self.ranking_tab
        self.tab3 = self.valuation_tab
        self.tab_cycle = self.cycle_tab
        self.tab_other = self.other_tab
        self.tab4 = self.strategy_tab
        self.backtest_widget = self.strategy_tab.backtest_widget
        
        # 4. 注册到左侧优雅导航栏
        self.addSubInterface(self.special_tab, FIF.PIN, "特别关注")
        self.addSubInterface(self.my_funds_tab, FIF.HEART, "自选基金")
        self.addSubInterface(self.ranking_tab, FIF.UP, "ETF涨跌榜")
        self.addSubInterface(self.valuation_tab, FIF.TILES, "估值榜")
        self.addSubInterface(self.cycle_tab, FIF.CALENDAR, "周期榜")
        self.addSubInterface(self.other_tab, FIF.FOLDER, "其他")
        self.addSubInterface(self.strategy_tab, FIF.ROBOT, "策略中心")

        # 5. 在左下角导航栏底部注册常驻控制项
        self.navigationInterface.addItem(
            routeKey="theme_toggle",
            icon=FIF.CONSTRACT,
            text="切换主题",
            onClick=self.toggle_app_theme,
            position=NavigationItemPosition.BOTTOM
        )
        self.navigationInterface.addItem(
            routeKey="settings_btn",
            icon=FIF.SETTING,
            text="配置",
            onClick=self.open_settings,
            position=NavigationItemPosition.BOTTOM
        )

        # 6. 初始化搜索自动补全弹窗 (父对象设为主窗口以跨页面悬浮)
        self.search_popup = QListWidget(self)
        self.search_popup.setWindowFlags(Qt.ToolTip)
        self.search_popup.setFocusPolicy(Qt.NoFocus)
        self.search_popup.setMouseTracking(True)
        self.search_popup.itemClicked.connect(self.on_search_item_clicked)
        self.apply_theme_styles()
        self.search_popup.hide()
        self.active_input_box = self.special_tab.input_box # 默认激活的输入框

        # 7. 桥接并绑定各个 Tab 页面的顶级工具栏事件
        tabs_list = [self.special_tab, self.my_funds_tab, self.ranking_tab, self.valuation_tab, self.cycle_tab, self.other_tab]
        
        # 7.1 特化桥接：特别关注 和 我的自选 顶部的全市场添加搜索联想
        for tab in [self.special_tab, self.my_funds_tab]:
            tab.input_box.textChanged.connect(self.on_search_input_changed)
            tab.btn_add.clicked.connect(self.add_funds)
            tab.btn_add_special.clicked.connect(self.add_special_funds)

        # 7.2 统一桥接：刷新按钮和自动刷新滑动开关
        for tab in tabs_list:
            tab.btn_refresh.clicked.connect(self.refresh_data)
            tab.btn_auto.checkedChanged.connect(self.on_tab_auto_refresh_toggled)

        # 8. 批量绑定子 Tab 的高级事件信号到 Controller (FundApp) 的对应业务函数
        for tab in tabs_list:
            tab.delete_fund_signal.connect(self.delete_fund)
            tab.add_fund_signal.connect(self.add_from_market)
            tab.toggle_pin_signal.connect(self.toggle_pin_fund)
            tab.toggle_special_signal.connect(self.toggle_special_fund)
            tab.show_chart_signal.connect(self.show_detailed_chart_by_code)
            tab.show_backtest_signal.connect(self.show_backtest_dialog)

        self.apply_styles()
        
        # 初始化表格模型和代理 - 将在 rebuild_table_headers 中设置与映射
        self.model0 = None
        self.model1 = None
        self.model2 = None
        self.model3 = None
        self.model_cycle = None
        self.delegate0 = None
        self.delegate1 = None
        self.delegate2 = None
        self.delegate3 = None
        self.delegate_cycle = None
        self.model_other = None
        self.delegate_other = None
        
        self.proxy0 = None
        self.proxy1 = None
        self.proxy2 = None
        self.proxy3 = None
        self.proxy_cycle = None
        
        self.rebuild_table_headers()

    def rebuild_table_headers(self):
        self.headers = ["序号", "持有", "基金代码", "基金名称", "基金板块", "最优参数", "持有金额/\n收益率", 
                        "昨日净值", "净值日期", "实时估值", "今日收益/\n收益率"]
        self.val_headers = ["序号", "估值标签", "基金代码", "基金名称", "基金板块", "最优参数", "估值状态\n(PE/PB)", 
                            "昨日净值", "净值日期", "实时估值", "今日收益/\n收益率"]
        self.cycle_headers = ["序号", "周期板块", "周期当前位置", "关联基金代码", "关联基金名称", "昨日净值", "净值日期", 
                              "实时估值", "今日收益/\n收益率", "近12月百分位", "趋势", "投资参考建议", "操作"]
        
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
                "cycle": [],
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
        
        if "cycle" not in hidden_cols_config:
            hidden_cols_config["cycle"] = []
            self.config["hidden_columns"] = hidden_cols_config
            self.need_config_save = True
        
        # 让各个 Tab 分别重建自己的表头
        self.special_tab.rebuild_headers(self.headers, hidden_cols_config.get("special", []))
        self.my_funds_tab.rebuild_headers(self.headers, hidden_cols_config.get("my_fund", []))
        self.ranking_tab.rebuild_headers(self.headers, hidden_cols_config.get("ranking", []))
        self.valuation_tab.rebuild_headers(self.val_headers, hidden_cols_config.get("valuation", []))
        self.cycle_tab.rebuild_headers(self.cycle_headers, hidden_cols_config.get("cycle", []))
        self.other_tab.rebuild_headers(self.headers, hidden_cols_config.get("other", []))

        # 兼容性挂载变量引用，使得主窗体的原有逻辑直接存取模型和代理
        self.model0 = self.special_tab.model
        self.delegate0 = self.special_tab.delegate
        self.proxy0 = self.special_tab.proxy

        self.model1 = self.my_funds_tab.model
        self.delegate1 = self.my_funds_tab.delegate
        self.proxy1 = self.my_funds_tab.proxy

        self.model2 = self.ranking_tab.model
        self.delegate2 = self.ranking_tab.delegate
        self.proxy2 = self.ranking_tab.proxy

        self.model3 = self.valuation_tab.model
        self.delegate3 = self.valuation_tab.delegate
        self.proxy3 = self.valuation_tab.proxy

        self.model_cycle = self.cycle_tab.model
        self.delegate_cycle = self.cycle_tab.delegate
        self.proxy_cycle = self.cycle_tab.proxy

        self.model_other = self.other_tab.model
        self.delegate_other = self.other_tab.delegate

    def apply_styles(self):
        # 兼容性包装：直接路由至统一的主题样式处理器，避免产生 setStyleSheet 样式表冲突覆盖
        self.apply_theme_styles()

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
        old_history_source = self.config.get("history_source", "Auto")
        old_valuation_source = self.config.get("valuation_source", "Auto")
        
        dialog = SettingsDialog(self.config, self.headers, self.val_headers, self)
        if dialog.exec():
            self.save_config()
            
            # 如果影响了列的数量（即数据参数变化），或者手动切换了数据源，需要重建表头或重新获取数据
            source_changed = (self.config.get("history_source", "Auto") != old_history_source or 
                              self.config.get("valuation_source", "Auto") != old_valuation_source)
            
            if self.config.get("drop_days") != old_drops or self.config.get("percentile_months") != old_pcts:
                self.rebuild_table_headers()
                self.refresh_data()
            elif source_changed:
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
            "自选基金": [(self.model1.get_row_data(i)["基金代码"], self.model1.get_row_data(i)["基金名称"]) for i in range(self.model1.rowCount())] if self.model1 else [],
            "ETF涨跌榜": [(self.model2.get_row_data(i)["基金代码"], self.model2.get_row_data(i)["基金名称"]) for i in range(self.model2.rowCount())] if self.model2 else [],
            "估值榜": [(self.model3.get_row_data(i)["基金代码"], self.model3.get_row_data(i)["基金名称"]) for i in range(self.model3.rowCount())] if self.model3 else [],
            "其他": [(self.model_other.get_row_data(i)["基金代码"], self.model_other.get_row_data(i)["基金名称"]) for i in range(self.model_other.rowCount())] if self.model_other else []
        }

    def apply_theme_styles(self):
        """动态应用主框架、自定义组件及子页面在当前明暗主题下的专属样式"""
        from qfluentwidgets import isDarkTheme
        is_dark = isDarkTheme()
        if is_dark:
            # 黑暗模式：强制将主视窗口、子 Tab 容器、侧边导航栏区域及表头全部统一为高阶暗黑色系
            self.setStyleSheet("""
                FundApp {
                    background-color: #202020;
                }
                /* 各个子 Tab 页面背景同步 */
                QWidget#special_tab, QWidget#my_funds_tab, QWidget#ranking_tab, 
                QWidget#valuation_tab, QWidget#cycle_tab, QWidget#other_tab, QWidget#strategy_tab {
                    background-color: #202020;
                }
                QWidget#AlertCard {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #20bf6b, stop:1 #05c46b);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    margin-top: 5px;
                    margin-bottom: 5px;
                }
                QTableView::item:hover {
                    background-color: transparent;
                }
                /* 表格表头自适应黑暗模式样式 */
                QHeaderView::section {
                    background-color: #2c2c2c;
                    color: #f1f2f6;
                    border: 1px solid #3a3a3a;
                }
            """)
            
            self.search_popup.setStyleSheet("""
                QListWidget {
                    background-color: #2c2c2c;
                    border: 1px solid #404040;
                    border-radius: 6px;
                    font-size: 13px;
                    padding: 2px 0;
                    outline: none;
                    color: #f1f2f6;
                }
                QListWidget::item {
                    padding: 6px 10px;
                    border-bottom: 1px solid #3c3c3c;
                    color: #f1f2f6;
                }
                QListWidget::item:last-child { border-bottom: none; }
                QListWidget::item:hover {
                    background-color: #3e3e3e;
                    color: #0097e6;
                }
            """)
        else:
            # 明亮模式：恢复经典大气质感亮色系
            self.setStyleSheet("""
                FundApp {
                    background-color: #f8f9fa;
                }
                QWidget#special_tab, QWidget#my_funds_tab, QWidget#ranking_tab, 
                QWidget#valuation_tab, QWidget#cycle_tab, QWidget#other_tab, QWidget#strategy_tab {
                    background-color: #ffffff;
                }
                QWidget#AlertCard {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #20bf6b, stop:1 #05c46b);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    margin-top: 5px;
                    margin-bottom: 5px;
                }
                QTableView::item:hover {
                    background-color: transparent;
                }
                QHeaderView::section {
                    background-color: #f1f2f6;
                    color: #2f3542;
                    border: 1px solid #dcdde1;
                }
            """)
            
            self.search_popup.setStyleSheet("""
                QListWidget {
                    background-color: white;
                    border: 1px solid #dcdde1;
                    border-radius: 6px;
                    font-size: 13px;
                    padding: 2px 0;
                    outline: none;
                }
                QListWidget::item {
                    padding: 6px 10px;
                    border-bottom: 1px solid #f1f2f6;
                    color: #2f3542;
                }
                QListWidget::item:last-child { border-bottom: none; }
                QListWidget::item:hover {
                    background-color: #e8f4fd;
                    color: #0097e6;
                }
            """)

    def toggle_app_theme(self):
        """一键无缝切换明暗主题并保存与重绘样式"""
        toggleTheme()
        
        from qfluentwidgets import isDarkTheme
        self.config["theme"] = "Dark" if isDarkTheme() else "Light"
        self.save_config()
        
        self.apply_theme_styles()
        
        # 强制更新表格视口渲染，使 Delegate 重新获取新主题颜色，消除置顶行白底白字
        for table in [self.table0, self.table1, self.table2, self.table3, self.table_cycle, self.table_other]:
            if table and table.viewport():
                table.viewport().update()

    def on_tab_auto_refresh_toggled(self, checked):
        """响应任何子 Tab 内 SwitchButton 滑动开关的状态变更"""
        if self.refresh_timer.isActive() != checked:
            self.toggle_auto_refresh(checked)

    def toggle_auto_refresh(self, checked=None):
        """实现全局自动刷新状态同步"""
        if checked is None:
            checked = not self.refresh_timer.isActive()
            
        if checked:
            if not self.refresh_timer.isActive():
                self.refresh_timer.start(self.refresh_interval)
                self.statusBar().showMessage("已开启自动刷新，每60秒更新一次")
                self.refresh_data()
        else:
            if self.refresh_timer.isActive():
                self.refresh_timer.stop()
                self.statusBar().showMessage("已关闭自动刷新")
                
        # 批量同步更新所有 Tab 内 SwitchButton 的状态以保持全局视觉一致
        for tab in [self.special_tab, self.my_funds_tab, self.ranking_tab, self.valuation_tab, self.cycle_tab, self.other_tab]:
            if hasattr(tab, 'btn_auto'):
                tab.btn_auto.blockSignals(True)
                tab.btn_auto.setChecked(checked)
                tab.btn_auto.blockSignals(False) 

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
        sender_widget = self.sender()
        if sender_widget:
            self.active_input_box = sender_widget
            
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
            
            pos = self.active_input_box.mapToGlobal(self.active_input_box.rect().bottomLeft())
            popup_h = min(380, len(results) * 28 + 8)
            self.search_popup.setFixedSize(self.active_input_box.width(), popup_h)
            self.search_popup.move(pos)
            self.search_popup.show()
        else:
            self.search_popup.hide()

    def on_search_item_clicked(self, item):
        """点击补全列表项，直接添加基金到自选"""
        code = item.data(Qt.UserRole)
        name = item.data(Qt.UserRole + 1)
        
        # 提取用户输入的板块后缀
        current_text = self.active_input_box.text()
        parts = current_text.split('-', 1)
        sector = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
        if not sector:
            sector = extract_fund_sector(name, code)
        
        self.search_popup.hide()
        self.active_input_box.blockSignals(True)
        self.active_input_box.clear()
        self.active_input_box.blockSignals(False)
        
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
        text = self.active_input_box.text().strip()
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
            self.active_input_box.clear()
            # 这里由于可能添加了多个，简单起见重新同步一下表格（但不刷新全市场）
            self.update_my_funds_table()
            self.update_special_funds_table()
            self.start_individual_fetcher(list(self.config.get("funds_info", {}).keys()))

    def add_special_funds(self):
        text = self.active_input_box.text().strip()
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
            self.active_input_box.clear()
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
        header = table.model().headerData(column, Qt.Horizontal, Qt.DisplayRole)
        if header != "操作": # 仅处理操作列
            return
            
        model = table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        code = row_data.get("基金代码") or row_data.get("关联基金代码")
        name = row_data.get("基金名称") or row_data.get("关联基金名称")
        action = row_data.get("操作")
        
        if action == "❌删除":
            self.delete_fund(code)
        elif action == "➕关注":
            sector = row_data.get("基金板块") or row_data.get("周期板块") or ""
            self.add_from_market(code, name, sector)

    def show_context_menu(self, table, pos):
        """显示右键菜单"""
        index = table.indexAt(pos)
        if not index.isValid():
            return
            
        model = table.model()
        row = index.row()
        row_data = model.get_row_data(row)
        code = row_data.get("基金代码") or row_data.get("关联基金代码")
        name = row_data.get("基金名称") or row_data.get("关联基金名称")
        
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
            sector = row_data.get("基金板块") or row_data.get("周期板块") or ""
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
            
        from ui.dialogs.backtest_dialog import BacktestDialog
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
        """查找表格中第一个匹配代码的行号 (返回源模型行号)"""
        model = table.model()
        if model and hasattr(model, 'sourceModel'):
            return model.sourceModel().find_row_by_code(code)
        if model and hasattr(model, 'find_row_by_code'):
            return model.find_row_by_code(code)
        return -1

    def get_all_rows_by_code(self, table, code):
        """返回表格中所有匹配该代码的源模型行号列表"""
        model = table.model()
        if model and hasattr(model, 'sourceModel'):
            return model.sourceModel().find_all_rows_by_code(code)
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

        if hasattr(self, 'model_cycle') and self.model_cycle:
            cycle_rows = self.get_all_rows_by_assoc_code(self.table_cycle, code)
            for r in cycle_rows:
                row_data = self.model_cycle.get_row_data(r)
                row_data["操作"] = status_text
                self.model_cycle.update_row(r, row_data)

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

    def get_cycle_codes(self):
        return ["014414", "008887", "008279", "004432", "161725", "004890", "012701", "012929", "003017"]

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
        
        cycle_codes = self.get_cycle_codes()
        all_fetch_codes = list(set(my_funds + market_codes + valuation_codes + other_codes + cycle_codes))
        
        if hasattr(self, "fetcher") and self.fetcher.isRunning():
            self.fetcher.requestInterruption()
            self.fetcher.wait()

        self.fetcher = FundDataFetcher(all_fetch_codes, self.config, self.history_cache, self.all_funds_code_to_name, self.db)
        self.fetcher.update_signal.connect(self.dispatch_table_update)
        self.fetcher.error_signal.connect(self.dispatch_table_error)
        self.fetcher.finish_signal.connect(self.on_fetch_finish)
        self.fetcher.start()

    def refresh_data(self):
        if getattr(self, 'is_refreshing', False):
            return
        
        self.is_refreshing = True
        for tab in [self.special_tab, self.my_funds_tab, self.ranking_tab, self.valuation_tab, self.cycle_tab, self.other_tab]:
            if hasattr(tab, 'btn_refresh'):
                tab.btn_refresh.setEnabled(False)

        self.latest_data_time = ""  # 重置数据源时间
        
        # 获取基金列表，并按照置顶状态进行初始排序（置顶在前）
        funds = sorted(list(self.config.get("funds_info", {}).keys()), 
                       key=lambda x: self.config["funds_info"][x].get("is_pinned", False), 
                       reverse=True)
        
        # 清空现有数据
        self.model0.clear_all()
        self.model1.clear_all()
        if hasattr(self, 'model_cycle') and self.model_cycle:
            self.model_cycle.clear_all()
        
        # 一次性批量获取所有有最优策略参数的基金，大幅减少磁盘 I/O 带来的主线程阻塞
        all_opts = self.db.get_all_optimal_strategies() or {}
        
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
            
            # 从批量获取的内存字典中查找策略参数，性能由 O(N) 磁盘 I/O 降为 O(1) 内存查表
            opt = all_opts.get(code)
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
        
        # 灌入周期榜静态配置的基础数据行
        if hasattr(self, 'model_cycle') and self.model_cycle:
            for i, cf in enumerate(CYCLE_FUNDS):
                row_data = {h: "-" for h in self.cycle_headers}
                row_data["序号"] = str(i + 1)
                row_data["周期板块"] = cf["sector"]
                row_data["周期当前位置"] = f"{cf['pct_default']}%|{cf['stage_default']}"
                row_data["关联基金代码"] = cf["code"]
                row_data["关联基金名称"] = cf["name"]
                
                # 从内存字典中快速查找周期基金的策略参数
                opt = all_opts.get(cf["code"])
                if opt:
                    row_data["_opt_time"] = opt.get('update_time')
                else:
                    row_data["_opt_time"] = None
                
                row_data["近12月百分位"] = "-"
                row_data["投资参考建议"] = cf["advice"]
                row_data["操作"] = "已添加" if cf["code"] in self.config.get("funds_info", {}) else "➕关注"
                
                self.model_cycle.add_row(row_data)
        
        # 加载完成后，如果表格开启了排序，需要手动触发一次排序以应用置顶逻辑
        if self.table0.horizontalHeader().sortIndicatorSection() != -1:
            self.model0.sort(self.table0.horizontalHeader().sortIndicatorSection(), 
                             self.table0.horizontalHeader().sortIndicatorOrder())
        if self.table1.horizontalHeader().sortIndicatorSection() != -1:
            self.model1.sort(self.table1.horizontalHeader().sortIndicatorSection(), 
                             self.table1.horizontalHeader().sortIndicatorOrder())
        if hasattr(self, 'table_cycle') and self.table_cycle.horizontalHeader().sortIndicatorSection() != -1:
            self.model_cycle.sort(self.table_cycle.horizontalHeader().sortIndicatorSection(), 
                                  self.table_cycle.horizontalHeader().sortIndicatorOrder())
        
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
            row_data["基金板块"] = extract_fund_sector(name, code)
            
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
        
        cycle_codes = self.get_cycle_codes()
        all_fetch_codes = list(set(my_funds + market_codes + valuation_codes + other_codes + cycle_codes))
        
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
        
        cycle_codes = self.get_cycle_codes()
        all_fetch_codes = list(set(my_funds + market_codes + valuation_codes + other_codes + cycle_codes))
        
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
            
        if hasattr(self, 'table_cycle') and self.table_cycle:
            for row_cycle in self.get_all_rows_by_assoc_code(self.table_cycle, code):
                self.populate_cycle_row_data(self.model_cycle, row_cycle, data)
            
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
        else:
            api_sector = self.shared_sector_map.get(code)
            if api_sector:
                sector = extract_fund_sector(api_sector, code)
            else:
                current_sector = row_data.get("基金板块", "")
                if current_sector in ["未知", "-", ""]:
                    current_sector = ""
                sector = extract_fund_sector(new_name or current_sector, code)
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

    def get_all_rows_by_assoc_code(self, table, code):
        """返回周期表格中所有匹配关联基金代码的源模型行号列表"""
        model = table.model()
        if not model: return []
        source_model = model.sourceModel() if hasattr(model, 'sourceModel') else model
        rows = []
        for i, row_data in enumerate(source_model.data_rows):
            if row_data.get("关联基金代码") == code:
                rows.append(i)
        return rows

    def populate_cycle_row_data(self, model, row, data):
        """更新周期表格行数据"""
        if row < 0 or row >= len(model.data_rows):
            return
        
        row_data = model.get_row_data(row)
        code = data.get('fundcode')
        
        new_name = data.get('name')
        if new_name:
            if new_name == code and row_data.get("关联基金名称") and row_data["关联基金名称"] != "加载中..." and not row_data["关联基金名称"].isdigit():
                pass
            else:
                row_data["关联基金名称"] = new_name
                
        row_data["昨日净值"] = data.get('dwjz')
        row_data["净值日期"] = data.get('jzrq')
        row_data["实时估值"] = data.get('gsz')
        
        change_str = data.get('gszzl', "")
        try:
            val = float(change_str)
            row_data["今日收益/\n收益率"] = f"-\n{val:+.2f}%"
        except:
            row_data["今日收益/\n收益率"] = f"-\n{change_str}%"
            
        pcts_dict = data.get('pcts', {})
        val_12m = pcts_dict.get(12)
        
        pct_val = None
        if val_12m is not None:
            row_data["近12月百分位"] = f"{val_12m:.2f}%"
            pct_val = val_12m
        else:
            row_data["近12月百分位"] = "-"
            try:
                parts = row_data.get("周期当前位置", "").split('|')
                pct_val = float(parts[0].replace('%', '').strip())
            except:
                pct_val = 50.0

        if val_12m is not None:
            if pct_val <= 20.0:
                stage_str = "萧条筑底期"
            elif pct_val <= 40.0:
                stage_str = "复苏拉升期"
            elif pct_val <= 60.0:
                stage_str = "繁荣适中期"
            elif pct_val <= 80.0:
                stage_str = "繁荣后期"
            else:
                stage_str = "高位见顶期"
            row_data["周期当前位置"] = f"{pct_val:.2f}%|{stage_str}"
            
        row_data["操作"] = "已添加" if code in self.config.get("funds_info", {}) else "➕关注"
        
        history_data = self.history_cache.get(code, {})
        row_data["_history"] = history_data
        row_data["_navs"] = history_data.get('navs', [])
        row_data["趋势"] = ""
        
        model.update_row(row, row_data)

    def on_table_double_clicked(self, table, index):
        """统一处理表格双击事件"""
        if not index.isValid():
            return
            
        model = table.model()
        row = index.row()
        col = index.column()
        
        # 获取当前双击列的标题名
        header_text = model.headerData(col, Qt.Horizontal)
        
        # 获取行数据
        row_data = model.get_row_data(row)
        code = row_data.get("基金代码") or row_data.get("关联基金代码")
        name = row_data.get("基金名称") or row_data.get("关联基金名称") or "未知"
        
        if not code:
            return
            
        if header_text == "最优参数":
            self.show_backtest_dialog(code, name)
        elif header_text == "趋势":
            self.show_detailed_chart(table, index)

    def show_detailed_chart_by_code(self, code, name):
        """通过基金代码和名称展示详细走势图"""
        import traceback
        try:
            # 优先从内存缓存中获取历史净值数据
            history = self.history_cache.get(code)
            if not history:
                # 尝试从所有已加载的模型中寻找
                for model in [self.model0, self.model1, self.model2, self.model3, self.model_cycle, self.model_other]:
                    if model:
                        idx = model.find_row_by_code(code)
                        if idx != -1:
                            row_data = model.get_row_data(idx)
                            history = row_data.get("_history")
                            if history:
                                break
            
            if not history:
                # 如果内存依然没有，尝试从数据库获取
                history = self.db.get_history(code) or {}
                
            if history and history.get("navs"):
                dialog = FundChartDialog(code, name, history, self)
                dialog.exec()
            else:
                QMessageBox.information(self, "提示", f"基金 {name} ({code}) 暂无历史走势数据，请等待刷新或手动刷新。")
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "走势图载入错误", f"发生未捕获异常:\n{e}\n\n堆栈信息:\n{tb}")

    def show_detailed_chart(self, table, index):
        """双击行显示详细走势图"""
        import traceback
        try:
            model = table.model()
            row = index.row()
            row_data = model.get_row_data(row)
            
            code = row_data.get("基金代码") or row_data.get("关联基金代码")
            name = row_data.get("基金名称") or row_data.get("关联基金名称") or "未知"
            history = row_data.get("_history", {})
            if not history or not history.get("navs"):
                # 如果内存没有，尝试从数据库获取
                history = self.db.get_history(code) or {}
                
            if history and history.get("navs"):
                dialog = FundChartDialog(code, name, history, self)
                dialog.exec()
            else:
                QMessageBox.information(self, "提示", f"基金 {name} ({code}) 暂无历史走势数据，请等待刷新或手动刷新。")
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "走势图载入错误", f"发生未捕获异常:\n{e}\n\n堆栈信息:\n{tb}")

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
        self.is_refreshing = False
        for tab in [self.special_tab, self.my_funds_tab, self.ranking_tab, self.valuation_tab, self.cycle_tab, self.other_tab]:
            if hasattr(tab, 'btn_refresh'):
                tab.btn_refresh.setEnabled(True)
                
        if self.need_config_save:
            self.save_config()
            self.need_config_save = False
            
        data_time = getattr(self, 'latest_data_time', '') or '未知'
        fetch_time = time.strftime('%Y-%m-%d %H:%M:%S')
        msg = f"数据时间: {data_time}  |  获取时间: {fetch_time}"
        if self.refresh_timer.isActive():
            msg += "  (自动刷新运行中...)"
        self.statusBar().showMessage(msg)
        
        # 抓取数据全部完成后，进行量化策略抄底信号检测
        self.check_buy_signals()

    def check_buy_signals(self):
        """核心抄底策略条件判定算法"""
        self.active_buy_signals = {}
        all_opts = self.db.get_all_optimal_strategies()
        if not all_opts:
            return
            
        # 2. 遍历拥有最优参数的所有基金
        for code, opt in all_opts.items():
            buy_days = opt.get('buy_days')
            buy_drop_pct = opt.get('buy_drop')
            
            # [DEBUG MOCK] 开启调试强制触发，以验证最优参数列的提醒
            DEBUG_FORCE_TRIGGER = False
            if DEBUG_FORCE_TRIGGER and buy_drop_pct is not None:
                buy_drop_pct = -100.0  # 使得 drop_pct <= 100.0 恒成立，百分百触发抄底
                
            if not buy_days or not buy_drop_pct:
                continue
                
            # 获取历史净值数据
            history_data = self.history_cache.get(code)
            if not history_data or not history_data.get('navs'):
                continue
                
            # 获取最新的实时估值
            current_val = None
            for model in [self.model1, self.model0, self.model2, self.model3, self.model_other]:
                if model:
                    row = model.find_row_by_code(code)
                    if row != -1:
                        row_data = model.get_row_data(row)
                        gsz_str = row_data.get("实时估值", "-")
                        try:
                            # 过滤掉暂无、错误及加载中
                            if gsz_str != "-" and not gsz_str.startswith("[") and "加载" not in gsz_str:
                                current_val = float(gsz_str)
                                break
                        except ValueError:
                            pass
                            
            history_navs = history_data['navs']
            if current_val is None and history_navs:
                current_val = history_navs[0]
                
            if current_val is None or not history_navs:
                continue
                
            # 如果历史实际净值长度不足以支持 buy_days 交易日，则跳过
            if len(history_navs) < buy_days:
                continue
                
            # 拼装包含今日最新估值在内的完整价格序列
            full_navs = [current_val] + history_navs
            
            # 计算包含今天在内的 buy_days + 1 天内的最高点
            nav_past_max = max(full_navs[0 : buy_days + 1])
            if nav_past_max == 0:
                continue
                
            # 计算今日价格较该最高点的跌幅
            drop_pct = (current_val - nav_past_max) / nav_past_max * 100.0
            
            # 策略核心买入判定：跌幅大于等于最优跌幅参数
            if drop_pct <= -buy_drop_pct:
                self.active_buy_signals[code] = {
                    'fund_code': code,
                    'fund_name': opt.get('fund_name', code),
                    'buy_days': buy_days,
                    'buy_drop': buy_drop_pct,
                    'current_drop': drop_pct,
                    'win_rate': opt.get('win_rate', 0.0),
                    'total_trades': opt.get('total_trades', 0),
                    'avg_profit': opt.get('avg_profit', 0.0)
                }
                
        # 3. 如果有买入信号激活，通知所有模型进行数据重绘，以展示最新的最优参数发光绿色高亮
        if self.active_buy_signals:
            for model in [self.model1, self.model0, self.model2, self.model3, self.model_other]:
                if model:
                    model.layoutAboutToBeChanged.emit()
                    model.layoutChanged.emit()

    def update_optimal_params(self, code_list=None):
        """重新从数据库中加载最优策略参数，并更新所有表格中对应基金的最优参数列显示"""
        all_opts = self.db.get_all_optimal_strategies()
        
        # 确定需要更新的基金代码集合
        if code_list is not None:
            codes_to_update = set(code_list)
        else:
            codes_to_update = set(all_opts.keys())
            
        models = [self.model0, self.model1, self.model2, self.model3, self.model_other]
        for model in models:
            if not model:
                continue
            
            for row_idx in range(model.rowCount()):
                row_data = model.get_row_data(row_idx)
                code = row_data.get("基金代码")
                if not code or code not in codes_to_update:
                    continue
                
                opt = all_opts.get(code)
                new_row_data = row_data.copy()
                if opt:
                    new_row_data["最优参数"] = f"买{opt['buy_days']}天>{opt['buy_drop']}% 盈>{opt['target_profit']}%"
                    new_row_data["_opt_time"] = opt.get('update_time')
                else:
                    new_row_data["最优参数"] = "-"
                    new_row_data["_opt_time"] = None
                
                model.update_row(row_idx, new_row_data)
                
        # 顺便更新'其他'Tab的基金列表，以呈现新产生最优参数的基金
        self.update_other_funds_table()
        
        # 重新检测抄底信号，使最新最优参数能立刻生效，并刷新高亮/报警横幅
        self.check_buy_signals()

    def closeEvent(self, event):
        """
        接管主窗口关闭事件，优雅停止所有活跃后台线程，确保数据写入完整且零报错退出。
        """
        # 1. 停止刷新定时器
        if hasattr(self, 'refresh_timer') and self.refresh_timer.isActive():
            self.refresh_timer.stop()

        # 2. 收集所有可能的活跃后台线程
        active_threads = []
        
        # 2.1 主窗口直接管理的数据抓取线程
        if hasattr(self, 'fetcher') and self.fetcher and self.fetcher.isRunning():
            active_threads.append(("自选/关注数据抓取线程", self.fetcher))
            
        if hasattr(self, 'ranking_fetcher') and self.ranking_fetcher and self.ranking_fetcher.isRunning():
            active_threads.append(("涨跌榜抓取线程", self.ranking_fetcher))
            
        if hasattr(self, 'valuation_fetcher') and self.valuation_fetcher and self.valuation_fetcher.isRunning():
            active_threads.append(("估值榜抓取线程", self.valuation_fetcher))

        # 2.2 策略中心批量寻优线程
        if hasattr(self, 'backtest_widget') and self.backtest_widget:
            if hasattr(self.backtest_widget, 'batch_finder') and self.backtest_widget.batch_finder and self.backtest_widget.batch_finder.isRunning():
                active_threads.append(("批量最优策略寻优线程", self.backtest_widget.batch_finder))

        if active_threads:
            print(f"[退出清理] 正在尝试优雅停止 {len(active_threads)} 个活跃后台线程...")
            # 第一步：向所有活跃线程发送中断请求
            for name, thread in active_threads:
                print(f"[退出清理] 正在请求中断线程: {name}")
                thread.requestInterruption()
            
            # 第二步：等待所有线程安全中止 (最多等待3秒)
            start_time = time.time()
            timeout = 3.0  # 3秒超时
            
            for name, thread in active_threads:
                elapsed = time.time() - start_time
                remaining = max(0.1, timeout - elapsed)
                print(f"[退出清理] 正在等待线程 {name} 结束，剩余等待时间: {remaining:.2f}秒...")
                # QThread.wait(msecs) 接受毫秒数，传入剩余时间的毫秒数
                success = thread.wait(int(remaining * 1000))
                if success:
                    print(f"[退出清理] 线程 {name} 已安全退出。")
                else:
                    print(f"[退出清理] 警告：线程 {name} 未能在超时时间内正常退出。")

        # 3. 执行默认的窗口关闭与资源销毁
        event.accept()

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    window = FundApp()
    window.show()
    app.exec()
