from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QLabel, 
                               QGroupBox, QGridLayout, QCheckBox, QHBoxLayout, 
                               QPushButton, QMessageBox, QVBoxLayout, QWidget,
                               QTabWidget, QComboBox)
from PySide6.QtGui import QPainter, QPolygonF, QPen, QColor, QFont, QLinearGradient, QBrush, QGradient
from PySide6.QtCore import Qt, QRect, QPointF, QPoint, QMargins
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QAreaSeries
import datetime

class SettingsDialog(QDialog):
    """自定义设置弹窗"""
    def __init__(self, config, current_headers, val_headers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自定义参数与列显示设置")
        self.resize(650, 560)
        self.config = config
        self.current_headers = current_headers
        self.val_headers = val_headers
        
        main_layout = QVBoxLayout(self)
        
        # 参数设置区域
        param_group = QGroupBox("量化分析参数")
        param_layout = QFormLayout(param_group)
        
        self.drop_input = QLineEdit(", ".join(map(str, config.get("drop_days", [2, 4]))))
        self.pct_input = QLineEdit(", ".join(map(str, config.get("percentile_months", [1, 2, 3, 6, 12, 24]))))
        
        param_layout.addRow(QLabel("跌幅计算天数 (逗号分隔):"), self.drop_input)
        param_layout.addRow(QLabel("百分位计算月数 (逗号分隔):"), self.pct_input)
        main_layout.addWidget(param_group)

        # 数据源手动切换设置
        source_group = QGroupBox("数据源手动切换设置")
        source_layout = QFormLayout(source_group)
        
        self.history_combo = QComboBox()
        self.history_combo.addItems([
            "智能自动切换 (默认降级)",
            "天天基金移动端 API",
            "天天基金网页端 F10",
            "AkShare 量化接口",
            "Tushare 量化接口"
        ])
        self.history_sources = ["Auto", "EastMoneyMobile", "EastMoneyWeb", "AkShare", "Tushare"]
        current_his = config.get("history_source", "Auto")
        if current_his in self.history_sources:
            self.history_combo.setCurrentIndex(self.history_sources.index(current_his))
            
        self.valuation_combo = QComboBox()
        self.valuation_combo.addItems([
            "智能自动切换 (默认降级)",
            "天天基金实时估值",
            "新浪财经实时估值",
            "腾讯财经实时估值",
            "网易财经实时估值"
        ])
        self.valuation_sources = ["Auto", "EastMoneyGz", "SinaGz", "TencentGz", "NetEaseGz"]
        current_val = config.get("valuation_source", "Auto")
        if current_val in self.valuation_sources:
            self.valuation_combo.setCurrentIndex(self.valuation_sources.index(current_val))
            
        source_layout.addRow(QLabel("历史净值数据源:"), self.history_combo)
        source_layout.addRow(QLabel("实时估值数据源:"), self.valuation_combo)
        main_layout.addWidget(source_group)
        
        # 各 Tab 列显示设置区域
        col_group = QGroupBox("表格列显示配置 (取消勾选即可隐藏)")
        col_layout = QVBoxLayout(col_group)
        
        self.tab_widget = QTabWidget()
        self.checkboxes = {} # tab_key -> {header: checkbox}
        
        # 兼容性读取字典格式
        hidden_cols_config = config.get("hidden_columns", {})
        if not isinstance(hidden_cols_config, dict):
            old_list = list(hidden_cols_config) if isinstance(hidden_cols_config, list) else []
            hidden_cols_config = {
                "special": list(old_list),
                "my_fund": list(old_list),
                "ranking": list(old_list),
                "valuation": list(old_list),
                "other": list(old_list)
            }
            
        tabs_info = [
            ("special", "🔥 特别关注", self.current_headers),
            ("my_fund", "⭐ 我的自选基金", self.current_headers),
            ("ranking", "📈 今日指数ETF独立涨跌榜", self.current_headers),
            ("valuation", "💎 估值榜", self.val_headers),
            ("other", "📦 其他(已有数据)", self.current_headers)
        ]
        
        for tab_key, tab_title, tab_headers in tabs_info:
            tab_widget = QWidget()
            grid = QGridLayout(tab_widget)
            grid.setContentsMargins(10, 10, 10, 10)
            grid.setSpacing(8)
            
            tab_checkboxes = {}
            hidden_cols = hidden_cols_config.get(tab_key, [])
            
            row, col = 0, 0
            for h in tab_headers:
                if h == "操作": continue
                cb = QCheckBox(h)
                cb.setChecked(h not in hidden_cols)
                tab_checkboxes[h] = cb
                grid.addWidget(cb, row, col)
                
                col += 1
                if col > 2: # 每行显示3个勾选框
                    col = 0
                    row += 1
                    
            tab_widget.setLayout(grid)
            self.tab_widget.addTab(tab_widget, tab_title)
            self.checkboxes[tab_key] = tab_checkboxes
            
        col_layout.addWidget(self.tab_widget)
        main_layout.addWidget(col_group)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存配置")
        save_btn.setFixedHeight(35)
        save_btn.setStyleSheet("background-color: #0097e6; color: white; font-weight: bold;")
        save_btn.clicked.connect(self.save_and_accept)
        btn_layout.addWidget(save_btn)
        main_layout.addLayout(btn_layout)

    def save_and_accept(self):
        try:
            drops = [int(x.strip()) for x in self.drop_input.text().split(",") if x.strip().isdigit()]
            pcts = [int(x.strip()) for x in self.pct_input.text().split(",") if x.strip().isdigit()]
            self.config["drop_days"] = drops if drops else [2, 4]
            self.config["percentile_months"] = pcts if pcts else [1, 2, 3, 6, 12, 24]
            
            # 保存手动选择的数据源
            self.config["history_source"] = self.history_sources[self.history_combo.currentIndex()]
            self.config["valuation_source"] = self.valuation_sources[self.valuation_combo.currentIndex()]
            
            hidden_cols_config = {}
            for tab_key, tab_checkboxes in self.checkboxes.items():
                hidden_cols_config[tab_key] = [h for h, cb in tab_checkboxes.items() if not cb.isChecked()]
            
            self.config["hidden_columns"] = hidden_cols_config
            self.accept()
        except Exception:
            QMessageBox.warning(self, "错误", "请输入正确的数字格式！")

class InteractiveChartView(QChartView):
    """量化交互式图表视图，提供硬件加速、框选放大、滚轮缩放、右键平移和跨图同步十字辅助线与 Tooltip"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        # 支持框选局部放大
        self.setRubberBand(QChartView.RectangleRubberBand)
        
        # 联动相关的成员变量
        self.linked_view = None
        self.remote_hover_idx = None
        self.is_top = True  # True 表示上方主图，False 表示下方副图
        self.indicator_type = "temperature"  # "temperature", "macd", "kdj", "rsi"
        
        # 缓存基础数据
        self.current_dates = []
        self.current_navs = []
        self.current_pcts = []
        self.axis_x = None
        
        # 缓存指标数据
        self.current_ma5 = []
        self.current_ma10 = []
        self.current_ma20 = []
        
        self.current_val_pcts = []
        self.macd_diff = []
        self.macd_dea = []
        self.macd_bar = []
        self.kdj_k = []
        self.kdj_d = []
        self.kdj_j = []
        self.rsi6 = []
        self.rsi12 = []
        
        self.mouse_pos = None
        self.setMouseTracking(True)
        
        # 右键拖拽平移相关
        self.is_dragging = False
        self.last_mouse_pos = QPoint()
        
    def update_data(self, dates, navs, pcts, axis_x):
        self.current_dates = dates
        self.current_navs = navs
        self.current_pcts = pcts
        self.axis_x = axis_x
        self.viewport().update()
        
    def update_indicators(self, **kwargs):
        """用于更新各种计算出的指标数据"""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.viewport().update()
        
    def set_hover_idx(self, idx):
        """接收联动视图传来的 hover 索引，触发本地重绘"""
        self.remote_hover_idx = idx
        self.viewport().update()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.SizeAllCursor)
            event.accept()
        else:
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        self.mouse_pos = event.pos()
        plot_rect = self.chart().plotArea()
        
        if self.is_dragging:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            self.chart().scroll(-delta.x(), delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)
            
        # 同步 hover 状态给联动的视图
        if self.linked_view:
            scene_pos = self.mapToScene(event.pos())
            if plot_rect.contains(scene_pos) and self.current_pcts:
                val = self.chart().mapToValue(scene_pos)
                idx = int(val.x() + 0.5)
                idx = max(0, min(len(self.current_pcts) - 1, idx))
                self.linked_view.set_hover_idx(idx)
            else:
                self.linked_view.set_hover_idx(None)
                
        self.viewport().update()
        
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.is_dragging = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
    def leaveEvent(self, event):
        self.mouse_pos = None
        if self.linked_view:
            self.linked_view.set_hover_idx(None)
        self.viewport().update()
        super().leaveEvent(event)
        
    def wheelEvent(self, event):
        factor = 0.9 if event.angleDelta().y() > 0 else 1.1
        self.chart().zoom(factor)
        event.accept()
        
    def doubleClickEvent(self, event):
        self.chart().zoomReset()
        event.accept()
        
    def drawForeground(self, painter, rect):
        if not self.current_dates:
            return
            
        chart = self.chart()
        plot_rect = chart.plotArea()
        
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 1. 动态计算当前可见范围内的日期标签 (对于主图可见，副图也可以隐藏以腾出视觉空间)
        if self.axis_x and self.is_top:
            x_min = max(0, int(self.axis_x.min() + 0.5))
            x_max = min(len(self.current_dates) - 1, int(self.axis_x.max() + 0.5))
            
            if x_max > x_min:
                painter.setPen(QColor("#7f8c8d"))
                painter.setFont(QFont("Segoe UI", 8))
                
                num_ticks = min(5, x_max - x_min + 1)
                # 防止 num_ticks == 1 时除零崩溃
                divisor = max(1, num_ticks - 1)
                for i in range(num_ticks):
                    idx = int(x_min + i * (x_max - x_min) / divisor)
                    pos_on_chart = chart.mapToPosition(QPointF(idx, 0))
                    x = pos_on_chart.x()
                    
                    if plot_rect.left() - 5 <= x <= plot_rect.right() + 5:
                        date_str = self.current_dates[idx]
                        tw = painter.fontMetrics().horizontalAdvance(date_str)
                        # 在主图底部和副图连通的交界处绘制
                        painter.drawText(int(x - tw / 2), int(plot_rect.bottom() + 14), date_str)
                        
            # 2. 标注区间末尾最新点 (主图百分比走势最新点)
            last_idx = len(self.current_pcts) - 1
            if self.axis_x.min() - 0.5 <= last_idx <= self.axis_x.max() + 0.5:
                last_pct = self.current_pcts[-1]
                pos_last = chart.mapToPosition(QPointF(last_idx, last_pct))
                lx, ly = pos_last.x(), pos_last.y()
                
                if plot_rect.left() <= lx <= plot_rect.right() and plot_rect.top() <= ly <= plot_rect.bottom():
                    painter.setBrush(QColor("#e74c3c"))
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(QPointF(lx, ly), 4, 4)
                    
                    painter.setPen(QColor("#e74c3c"))
                    painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                    val_str = f"{last_pct:+.2f}%"
                    tw = painter.fontMetrics().horizontalAdvance(val_str)
                    painter.drawText(int(lx - tw - 5), int(ly - 8), val_str)
                    
        # 3. 跨图联动的十字线与悬浮 Tooltip 绘制
        active_idx = None
        is_local_hover = False
        
        # 确定当前的 hover 数据索引
        if self.mouse_pos:
            scene_pos = self.mapToScene(self.mouse_pos)
            if plot_rect.contains(scene_pos):
                val = chart.mapToValue(scene_pos)
                active_idx = int(val.x() + 0.5)
                active_idx = max(0, min(len(self.current_dates) - 1, active_idx))
                is_local_hover = True
        elif self.remote_hover_idx is not None:
            active_idx = self.remote_hover_idx
            
        if active_idx is not None and self.axis_x and (self.axis_x.min() - 0.5 <= active_idx <= self.axis_x.max() + 0.5):
            # 获取对应的 X 屏幕坐标
            pos_x_ref = chart.mapToPosition(QPointF(active_idx, 0)).x()
            
            # A. 绘制垂直十字辅助线（上下图贯通）
            painter.setPen(QPen(QColor("#7f8c8d"), 1, Qt.DashLine))
            painter.drawLine(pos_x_ref, plot_rect.top(), pos_x_ref, plot_rect.bottom())
            
            # B. 只有当鼠标位于当前图内时，才绘制水平十字线
            if is_local_hover:
                py = self.mouse_pos.y()
                if plot_rect.top() <= py <= plot_rect.bottom():
                    painter.drawLine(plot_rect.left(), py, plot_rect.right(), py)
            
            # C. 高亮当前图内所有的折线交点与圆圈
            if self.is_top:
                # 绘制主净值交点
                pct_y = self.current_pcts[active_idx]
                pos_pct = chart.mapToPosition(QPointF(active_idx, pct_y))
                if plot_rect.top() <= pos_pct.y() <= plot_rect.bottom():
                    painter.setBrush(QColor("#0097e6"))
                    painter.setPen(QPen(Qt.white, 2))
                    painter.drawEllipse(pos_pct, 5, 5)
                
                # 绘制 MA 均线交点（如果有）
                ma_configs = [
                    (self.current_ma5, "#2ed573"),
                    (self.current_ma10, "#ffa502"),
                    (self.current_ma20, "#9b59b6")
                ]
                for ma_list, color in ma_configs:
                    if len(ma_list) > active_idx:
                        ma_val = ma_list[active_idx]
                        pos_ma = chart.mapToPosition(QPointF(active_idx, ma_val))
                        if plot_rect.top() <= pos_ma.y() <= plot_rect.bottom():
                            painter.setBrush(QColor(color))
                            painter.setPen(QPen(Qt.white, 1.5))
                            painter.drawEllipse(pos_ma, 4, 4)
            else:
                # 下方副图交点高亮
                if self.indicator_type == "temperature" and len(self.current_val_pcts) > active_idx:
                    val_y = self.current_val_pcts[active_idx]
                    pos_val = chart.mapToPosition(QPointF(active_idx, val_y))
                    if plot_rect.top() <= pos_val.y() <= plot_rect.bottom():
                        painter.setBrush(QColor("#ffa502"))
                        painter.setPen(QPen(Qt.white, 2))
                        painter.drawEllipse(pos_val, 5, 5)
                elif self.indicator_type == "macd" and len(self.macd_diff) > active_idx:
                    # 高亮 DIFF 与 DEA 的点
                    for y_val, color in [(self.macd_diff[active_idx], "#00bcff"), (self.macd_dea[active_idx], "#e67e22")]:
                        pos_macd = chart.mapToPosition(QPointF(active_idx, y_val))
                        if plot_rect.top() <= pos_macd.y() <= plot_rect.bottom():
                            painter.setBrush(QColor(color))
                            painter.setPen(QPen(Qt.white, 1.5))
                            painter.drawEllipse(pos_macd, 4, 4)
                elif self.indicator_type == "kdj" and len(self.kdj_k) > active_idx:
                    for y_val, color in [(self.kdj_k[active_idx], "#9b59b6"), (self.kdj_d[active_idx], "#f1c40f"), (self.kdj_j[active_idx], "#e74c3c")]:
                        pos_kdj = chart.mapToPosition(QPointF(active_idx, y_val))
                        if plot_rect.top() <= pos_kdj.y() <= plot_rect.bottom():
                            painter.setBrush(QColor(color))
                            painter.setPen(QPen(Qt.white, 1.5))
                            painter.drawEllipse(pos_kdj, 4, 4)
                elif self.indicator_type == "rsi" and len(self.rsi6) > active_idx:
                    for y_val, color in [(self.rsi6[active_idx], "#fd79a8"), (self.rsi12[active_idx], "#00b894")]:
                        pos_rsi = chart.mapToPosition(QPointF(active_idx, y_val))
                        if plot_rect.top() <= pos_rsi.y() <= plot_rect.bottom():
                            painter.setBrush(QColor(color))
                            painter.setPen(QPen(Qt.white, 1.5))
                            painter.drawEllipse(pos_rsi, 4, 4)
                            
            # D. 渲染各自区域的 Tooltip 浮窗
            tip_text = ""
            date_str = self.current_dates[active_idx]
            
            if self.is_top:
                # 净值信息
                nav_val = self.current_navs[active_idx]
                pct_val = self.current_pcts[active_idx]
                max_nav = max(self.current_navs)
                min_nav = min(self.current_navs)
                dist_high = (nav_val - max_nav) / max_nav * 100 if max_nav != 0 else 0
                dist_low = (nav_val - min_nav) / min_nav * 100 if min_nav != 0 else 0
                
                tip_text = (
                    f"日期: {date_str}\n"
                    f"净值: {nav_val:.4f}\n"
                    f"区间涨跌: {pct_val:+.2f}%\n"
                    f"距最高: {dist_high:+.2f}%\n"
                    f"距最低: {dist_low:+.2f}%"
                )
                if len(self.current_ma5) > active_idx:
                    tip_text += f"\nMA5: {self.current_ma5[active_idx]:+.2f}%"
                if len(self.current_ma10) > active_idx:
                    tip_text += f"\nMA10: {self.current_ma10[active_idx]:+.2f}%"
                if len(self.current_ma20) > active_idx:
                    tip_text += f"\nMA20: {self.current_ma20[active_idx]:+.2f}%"
            else:
                # 技术指标信息
                if self.indicator_type == "temperature" and len(self.current_val_pcts) > active_idx:
                    val_pct = self.current_val_pcts[active_idx]
                    status = "适中"
                    if val_pct < 10: status = "极低估"
                    elif val_pct < 30: status = "低估"
                    elif val_pct > 90: status = "极高估"
                    elif val_pct > 70: status = "高估"
                    tip_text = f"指标: 历史百分位\n百分位: {val_pct:.2f}%\n估值状态: {status}"
                elif self.indicator_type == "macd" and len(self.macd_diff) > active_idx:
                    tip_text = (
                        f"指标: MACD\n"
                        f"DIFF: {self.macd_diff[active_idx]:.4f}\n"
                        f"DEA: {self.macd_dea[active_idx]:.4f}\n"
                        f"MACD: {self.macd_bar[active_idx]:.4f}"
                    )
                elif self.indicator_type == "kdj" and len(self.kdj_k) > active_idx:
                    tip_text = (
                        f"指标: KDJ (9,3,3)\n"
                        f"K值: {self.kdj_k[active_idx]:.2f}\n"
                        f"D值: {self.kdj_d[active_idx]:.2f}\n"
                        f"J值: {self.kdj_j[active_idx]:.2f}"
                    )
                elif self.indicator_type == "rsi" and len(self.rsi6) > active_idx:
                    tip_text = (
                        f"指标: RSI (6,12)\n"
                        f"RSI6: {self.rsi6[active_idx]:.2f}\n"
                        f"RSI12: {self.rsi12[active_idx]:.2f}"
                    )
                    
            if tip_text:
                painter.setFont(QFont("Segoe UI", 9))
                fm = painter.fontMetrics()
                # 计算浮窗尺寸
                lines = tip_text.count("\n") + 1
                tip_w = 165
                tip_h = lines * 18 + 12
                
                # 浮窗位置计算 (X 轴左右侧跟随，Y 轴在对应系列的中间或特定高度)
                tx = pos_x_ref + 15
                if tx + tip_w > plot_rect.right():
                    tx = pos_x_ref - tip_w - 15
                    
                # Y 轴直接定位在绘图区顶部偏下 10 像素，避免跨屏跳动
                ty = plot_rect.top() + 10
                
                # QRect 需要整数参数，避免传入 float 导致崩溃
                tip_rect = QRect(int(tx), int(ty), int(tip_w), int(tip_h))
                
                # 绘制毛玻璃效果磨砂背景
                painter.setBrush(QColor(30, 39, 46, 220))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(tip_rect, 6, 6)
                
                # 绘制文字
                painter.setPen(Qt.white)
                painter.drawText(tip_rect.adjusted(10, 6, -10, -6), Qt.AlignLeft | Qt.AlignTop, tip_text)
                
        painter.restore()


class FundChartDialog(QDialog):
    """基金走势图详情弹窗（双子图平滑联动与量化分析深度版）"""
    
    def __init__(self, code, name, history_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"走势详情: {name} ({code})")
        self.resize(960, 620)
        
        # 1. 整理数据并统一转换为正序
        self.all_navs = history_data.get("navs", [])[::-1]
        self.all_dates = history_data.get("dates", [])[::-1]
        
        if not self.all_dates and self.all_navs:
            self.all_dates = [f"D-{len(self.all_navs)-i}" for i in range(len(self.all_navs))]
            
        self.code = code
        self.name = name
        
        # 缓存当前区间内的数据
        self.current_navs = []
        self.current_dates = []
        self.current_pcts = []
        self.current_ma5_pct = []
        self.current_ma10_pct = []
        self.current_ma20_pct = []
        self.current_val_pcts = []
        self.current_macd_diff = []
        self.current_macd_dea = []
        self.current_macd_bar = []
        self.current_kdj_k = []
        self.current_kdj_d = []
        self.current_kdj_j = []
        self.current_rsi6 = []
        self.current_rsi12 = []
        self._bg_series = []
        
        # 2. 预先在完整历史序列上计算所有技术指标
        self.calculate_all_indicators()
        
        # 3. 构建 UI 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)
        
        # A. 顶部信息与周期选择
        top_ctrl_layout = QHBoxLayout()
        self.info_label = QLabel(f"<b>{name} ({code})</b>")
        self.info_label.setStyleSheet("font-size: 15px; color: #2f3542;")
        top_ctrl_layout.addWidget(self.info_label)
        top_ctrl_layout.addStretch()
        
        self.btn_group_layout = QHBoxLayout()
        self.btns = {}
        periods = [
            ("近1月", 21), ("近3月", 63), ("近6月", 126), ("近1年", 252), 
            ("近3年", 756), ("近5年", 1260), ("今年以来", "YTD"), ("全部", 0)
        ]
        for text, days in periods:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedWidth(70)
            btn.setStyleSheet("""
                QPushButton { background-color: #f1f2f6; color: #2f3542; border: 1px solid #dcdde1; border-radius: 4px; padding: 4px;}
                QPushButton:hover { background-color: #dfe4ea; }
                QPushButton:checked { background-color: #0097e6; color: white; border-color: #0097e6; font-weight: bold;}
            """)
            btn.clicked.connect(lambda checked, d=days, t=text: self.change_period(t, d))
            self.btn_group_layout.addWidget(btn)
            self.btns[text] = btn
        top_ctrl_layout.addLayout(self.btn_group_layout)
        layout.addLayout(top_ctrl_layout)
        
        # B. 统计区间涨跌的 Label
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #7f8c8d; font-size: 12px; margin-bottom: 2px;")
        layout.addWidget(self.stats_label)
        
        # C. 上方主图区域 (净值折线 + MA5/10/20)
        self.top_chart_view = InteractiveChartView(self)
        self.top_chart_view.is_top = True
        self.top_chart_view.setMinimumHeight(240)
        self.top_chart_view.setStyleSheet("background-color: white; border: 1px solid #f1f2f6; border-radius: 4px;")
        layout.addWidget(self.top_chart_view)
        
        # D. 中间技术指标选择控制栏
        ctrl_bar_layout = QHBoxLayout()
        ctrl_bar_layout.setContentsMargins(5, 2, 5, 2)
        
        indicator_title = QLabel("📊 量化分析指标子图:")
        indicator_title.setStyleSheet("font-weight: bold; color: #2f3542; font-size: 12px;")
        ctrl_bar_layout.addWidget(indicator_title)
        
        from PySide6.QtWidgets import QComboBox
        self.indicator_combo = QComboBox()
        self.indicator_combo.setFixedWidth(210)
        self.indicator_combo.addItems([
            "🌡️ 估值百分位温度带",
            "📊 MACD 强弱趋势",
            "📈 KDJ 超买超卖",
            "📉 RSI 强弱强弱"
        ])
        self.indicator_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #dcdde1; border-radius: 4px; padding: 4px 10px; background: white; color: #2f3542; font-size: 12px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left-width: 0px;
            }
            QComboBox:hover {
                border-color: #0097e6;
            }
        """)
        self.indicator_combo.currentIndexChanged.connect(self.handle_indicator_changed)
        ctrl_bar_layout.addWidget(self.indicator_combo)
        ctrl_bar_layout.addStretch()
        layout.addLayout(ctrl_bar_layout)
        
        # E. 下方副图区域 (各技术指标)
        self.bottom_chart_view = InteractiveChartView(self)
        self.bottom_chart_view.is_top = False
        self.bottom_chart_view.setMinimumHeight(180)
        self.bottom_chart_view.setStyleSheet("background-color: white; border: 1px solid #f1f2f6; border-radius: 4px;")
        layout.addWidget(self.bottom_chart_view)
        
        # F. 跨图联动 hover 状态互指绑定
        self.top_chart_view.linked_view = self.bottom_chart_view
        self.bottom_chart_view.linked_view = self.top_chart_view
        
        # 4. 创建上方的 QChart 与折线系列
        self.top_chart = QChart()
        self.top_chart.legend().setVisible(True)
        self.top_chart.legend().setAlignment(Qt.AlignTop)
        self.top_chart.legend().setBackgroundVisible(False)
        self.top_chart.setMargins(QMargins(10, 5, 10, 5))
        self.top_chart.setBackgroundRoundness(0)
        self.top_chart.setBackgroundVisible(False)
        
        self.line_series = QLineSeries()
        self.line_series.setName("净值走势")
        self.line_series.setPen(QPen(QColor("#0097e6"), 2))
        
        self.area_upper_series = QLineSeries()
        self.area_lower_series = QLineSeries()
        self.area_series = QAreaSeries(self.area_upper_series, self.area_lower_series)
        gradient = QLinearGradient(0, 0, 0, 1)
        gradient.setCoordinateMode(QGradient.ObjectMode)
        gradient.setColorAt(0, QColor(0, 151, 230, 60))
        gradient.setColorAt(1, QColor(0, 151, 230, 1))
        self.area_series.setBrush(QBrush(gradient))
        self.area_series.setPen(Qt.NoPen)
        # 隐藏面积图例，避免视觉冗余
        self.area_series.setPointsVisible(False)
        
        # 增加 MA 均线系列
        self.ma5_series = QLineSeries()
        self.ma5_series.setName("MA5")
        self.ma5_series.setPen(QPen(QColor("#2ed573"), 1.2))
        
        self.ma10_series = QLineSeries()
        self.ma10_series.setName("MA10")
        self.ma10_series.setPen(QPen(QColor("#ffa502"), 1.2))
        
        self.ma20_series = QLineSeries()
        self.ma20_series.setName("MA20")
        self.ma20_series.setPen(QPen(QColor("#9b59b6"), 1.2))
        
        self.top_chart.addSeries(self.area_series)
        self.top_chart.addSeries(self.line_series)
        self.top_chart.addSeries(self.ma5_series)
        self.top_chart.addSeries(self.ma10_series)
        self.top_chart.addSeries(self.ma20_series)
        
        # 隐藏面积图例
        self.safe_hide_legend_marker(self.top_chart, self.area_series)
        
        # 5. 创建下方的 QChart
        self.bottom_chart = QChart()
        self.bottom_chart.legend().setVisible(True)
        self.bottom_chart.legend().setAlignment(Qt.AlignTop)
        self.bottom_chart.legend().setBackgroundVisible(False)
        self.bottom_chart.setMargins(QMargins(10, 5, 10, 5))
        self.bottom_chart.setBackgroundRoundness(0)
        self.bottom_chart.setBackgroundVisible(False)
        
        # 6. 配置联动 X 轴与各自的 Y 轴
        self.top_axis_x = QValueAxis()
        self.top_axis_x.setLabelsVisible(False)
        self.top_axis_x.setGridLinePen(QPen(QColor("#f1f2f6"), 1))
        self.top_axis_x.setLinePenColor(QColor("#dcdde1"))
        
        self.top_axis_y = QValueAxis()
        self.top_axis_y.setLabelFormat("%.2f%%")
        self.top_axis_y.setLabelsColor(QColor("#7f8c8d"))
        self.top_axis_y.setGridLinePen(QPen(QColor("#f1f2f6"), 1))
        self.top_axis_y.setLinePenColor(QColor("#dcdde1"))
        
        self.top_chart.addAxis(self.top_axis_x, Qt.AlignBottom)
        self.top_chart.addAxis(self.top_axis_y, Qt.AlignLeft)
        
        # 绑定上方图 Series 到轴
        self.line_series.attachAxis(self.top_axis_x)
        self.line_series.attachAxis(self.top_axis_y)
        self.area_series.attachAxis(self.top_axis_x)
        self.area_series.attachAxis(self.top_axis_y)
        self.ma5_series.attachAxis(self.top_axis_x)
        self.ma5_series.attachAxis(self.top_axis_y)
        self.ma10_series.attachAxis(self.top_axis_x)
        self.ma10_series.attachAxis(self.top_axis_y)
        self.ma20_series.attachAxis(self.top_axis_x)
        self.ma20_series.attachAxis(self.top_axis_y)
        
        # 副图的轴定义
        self.bottom_axis_x = QValueAxis()
        self.bottom_axis_x.setLabelsVisible(False)
        self.bottom_axis_x.setGridLinePen(QPen(QColor("#f1f2f6"), 1))
        self.bottom_axis_x.setLinePenColor(QColor("#dcdde1"))
        
        self.bottom_axis_y = QValueAxis()
        self.bottom_axis_y.setLabelsColor(QColor("#7f8c8d"))
        self.bottom_axis_y.setGridLinePen(QPen(QColor("#f1f2f6"), 1))
        self.bottom_axis_y.setLinePenColor(QColor("#dcdde1"))
        
        self.bottom_chart.addAxis(self.bottom_axis_x, Qt.AlignBottom)
        self.bottom_chart.addAxis(self.bottom_axis_y, Qt.AlignLeft)
        
        # 将 QChart 装载进各自的 View
        self.top_chart_view.setChart(self.top_chart)
        self.bottom_chart_view.setChart(self.bottom_chart)
        
        # 绑定平滑联动范围改变信号 (双向阻断绑定)
        self.top_axis_x.rangeChanged.connect(self.sync_top_to_bottom_x)
        self.bottom_axis_x.rangeChanged.connect(self.sync_bottom_to_top_x)
        
        # 独立触发 Y 轴可视窗口自适应高度计算
        self.top_axis_x.rangeChanged.connect(self.handle_top_x_range_changed)
        self.bottom_axis_x.rangeChanged.connect(self.handle_bottom_x_range_changed)
        
        # G. 底部关闭按钮
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(85)
        close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        # 默认切片到“近1年”或全部
        default_p = "近1年" if len(self.all_navs) >= 252 else "全部"
        if default_p not in self.btns: default_p = "全部"
        
        self.change_period(default_p, periods[3][1] if default_p == "近1年" else 0)
        
    def safe_hide_legend_marker(self, chart, series):
        """安全地隐藏指定 series 的 legend marker，避免 IndexError 崩溃"""
        markers = chart.legend().markers(series)
        if markers:
            markers[0].setVisible(False)
            
    def calculate_all_indicators(self):
        """核心指标数学计算引擎（在完整正序价格序列上运行）"""
        navs = self.all_navs
        if not navs:
            return
            
        # 1. 均线 MA 计算
        def calc_ma(period):
            ma = []
            for i in range(len(navs)):
                window = navs[max(0, i - period + 1) : i + 1]
                ma.append(sum(window) / len(window))
            return ma
        self.all_ma5 = calc_ma(5)
        self.all_ma10 = calc_ma(10)
        self.all_ma20 = calc_ma(20)
        
        # 2. 估值百分位温度带（252个交易日窗口）
        self.all_val_pcts = []
        for i in range(len(navs)):
            window = navs[max(0, i - 251) : i + 1]
            val = navs[i]
            less = sum(1 for x in window if x < val)
            equal = sum(1 for x in window if x == val)
            pct = (less + 0.5 * equal) / len(window) * 100.0
            self.all_val_pcts.append(pct)
            
        # 3. MACD 强弱指标 (12, 26, 9)
        def get_ema(data, period):
            ema = []
            k = 2.0 / (period + 1.0)
            for i, val in enumerate(data):
                if i == 0:
                    ema.append(val)
                else:
                    ema.append(val * k + ema[-1] * (1.0 - k))
            return ema
        ema12 = get_ema(navs, 12)
        ema26 = get_ema(navs, 26)
        self.all_macd_diff = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
        self.all_macd_dea = get_ema(self.all_macd_diff, 9)
        self.all_macd_bar = [2.0 * (d - a) for d, a in zip(self.all_macd_diff, self.all_macd_dea)]
        
        # 4. KDJ (9, 3, 3) 超买超卖指标
        self.all_kdj_k = []
        self.all_kdj_d = []
        self.all_kdj_j = []
        curr_k, curr_d = 50.0, 50.0
        for i in range(len(navs)):
            window = navs[max(0, i - 8) : i + 1]
            high = max(window)
            low = min(window)
            rsv = (navs[i] - low) / (high - low) * 100.0 if high != low else 50.0
            curr_k = (2.0 / 3.0) * curr_k + (1.0 / 3.0) * rsv
            curr_d = (2.0 / 3.0) * curr_d + (1.0 / 3.0) * curr_k
            curr_j = 3.0 * curr_k - 2.0 * curr_d
            self.all_kdj_k.append(curr_k)
            self.all_kdj_d.append(curr_d)
            self.all_kdj_j.append(curr_j)
            
        # 5. RSI 强弱强弱指标 (6, 12)
        def calc_rsi(period):
            if len(navs) < 2:
                return [50.0] * len(navs)
            deltas = [0.0]
            for j in range(1, len(navs)):
                deltas.append(navs[j] - navs[j-1])
            rsi = []
            up_ema = 0.0
            down_ema = 0.0
            alpha = 1.0 / period
            for j in range(len(navs)):
                up = max(0.0, deltas[j])
                down = max(0.0, -deltas[j])
                if j == 0:
                    up_ema, down_ema = up, down
                else:
                    up_ema = alpha * up + (1.0 - alpha) * up_ema
                    down_ema = alpha * down + (1.0 - alpha) * down_ema
                if (up_ema + down_ema) != 0:
                    rsi.append(up_ema / (up_ema + down_ema) * 100.0)
                else:
                    rsi.append(50.0)
            return rsi
        self.all_rsi6 = calc_rsi(6)
        self.all_rsi12 = calc_rsi(12)
        
    def sync_top_to_bottom_x(self, min_val, max_val):
        """X轴联动：主图同步给副图"""
        if self.bottom_axis_x.min() != min_val or self.bottom_axis_x.max() != max_val:
            self.bottom_axis_x.blockSignals(True)
            self.bottom_axis_x.setRange(min_val, max_val)
            self.bottom_axis_x.blockSignals(False)
            self.handle_bottom_x_range_changed(min_val, max_val)

    def sync_bottom_to_top_x(self, min_val, max_val):
        """X轴联动：副图同步给主图"""
        if self.top_axis_x.min() != min_val or self.top_axis_x.max() != max_val:
            self.top_axis_x.blockSignals(True)
            self.top_axis_x.setRange(min_val, max_val)
            self.top_axis_x.blockSignals(False)
            self.handle_top_x_range_changed(min_val, max_val)
            
    def handle_top_x_range_changed(self, min_val, max_val):
        """上方主图自适应 Y 轴高度范围"""
        if not hasattr(self, 'current_pcts') or not self.current_pcts:
            return
        x_min = max(0, int(min_val + 0.5))
        x_max = min(len(self.current_pcts) - 1, int(max_val + 0.5))
        
        if x_max >= x_min:
            # 合并主净值和均线，找到最佳区间
            visible_vals = self.current_pcts[x_min : x_max + 1]
            for ma_list in [self.current_ma5_pct, self.current_ma10_pct, self.current_ma20_pct]:
                if len(ma_list) > x_max:
                    visible_vals.extend(ma_list[x_min : x_max + 1])
                    
            if visible_vals:
                min_v = min(visible_vals)
                max_v = max(visible_vals)
                rng = max_v - min_v if max_v != min_v else 1.0
                margin = max(0.4, rng * 0.12)
                self.top_axis_y.setRange(min_v - margin, max_v + margin)
                
    def handle_bottom_x_range_changed(self, min_val, max_val):
        """下方副图自适应 Y 轴高度范围"""
        if not self.current_dates:
            return
        x_min = max(0, int(min_val + 0.5))
        x_max = min(len(self.current_dates) - 1, int(max_val + 0.5))
        
        if x_max < x_min:
            return
            
        t = self.indicator_combo.currentIndex()
        if t == 0:  # 估值百分位固定为 0 到 100
            self.bottom_axis_y.setRange(-2.0, 102.0)
        elif t == 1:  # MACD
            if len(self.current_macd_diff) > x_max:
                visible = self.current_macd_diff[x_min : x_max + 1] + self.current_macd_dea[x_min : x_max + 1] + self.current_macd_bar[x_min : x_max + 1]
                if visible:
                    min_v, max_v = min(visible), max(visible)
                    margin = max(0.005, (max_v - min_v) * 0.15 if max_v != min_v else 0.01)
                    self.bottom_axis_y.setRange(min_v - margin, max_v + margin)
        elif t == 2:  # KDJ 固定为 0 到 100 (或自适应)
            self.bottom_axis_y.setRange(-5.0, 105.0)
        elif t == 3:  # RSI
            self.bottom_axis_y.setRange(-5.0, 105.0)
            
    def change_period(self, period_text, days):
        """响应时期选择，切片所需范围"""
        for text, btn in self.btns.items():
            btn.setChecked(text == period_text)
            
        if period_text == "今年以来":
            this_year = str(datetime.datetime.now().year)
            start_idx = -1
            for i, d in enumerate(self.all_dates):
                if d.startswith(this_year):
                    start_idx = i
                    break
            if start_idx == -1:
                start_idx = max(0, len(self.all_navs) - 21)
        elif days == 0:
            start_idx = 0
        else:
            start_idx = max(0, len(self.all_navs) - days)
            
        self.current_navs = self.all_navs[start_idx:]
        self.current_dates = self.all_dates[start_idx:]
        
        if len(self.current_navs) > 1:
            start_v = self.current_navs[0]
            end_v = self.current_navs[-1]
            total_change = (end_v - start_v) / start_v * 100 if start_v != 0 else 0
            self.stats_label.setText(
                f"统计周期: {self.current_dates[0]} 至 {self.current_dates[-1]} ({len(self.current_navs)}个交易日) | "
                f"区间涨跌: <span style='color:{'#e74c3c' if total_change>=0 else '#27ae60'}'>{total_change:+.2f}%</span>"
            )
        else:
            self.stats_label.setText(f"统计周期: {self.current_dates[0] if self.current_dates else '-'} | 暂无对比数据")
            
        # 重新计算以首日为0%的百分比走势数据
        start_nav = self.current_navs[0] if self.current_navs else 1.0
        self.current_pcts = [(nav - start_nav) / start_nav * 100.0 for nav in self.current_navs]
        
        # 将均线切片转换
        self.current_ma5_pct = [(ma - start_nav) / start_nav * 100.0 for ma in self.all_ma5[start_idx:]]
        self.current_ma10_pct = [(ma - start_nav) / start_nav * 100.0 for ma in self.all_ma10[start_idx:]]
        self.current_ma20_pct = [(ma - start_nav) / start_nav * 100.0 for ma in self.all_ma20[start_idx:]]
        
        # 指标直接切片
        self.current_val_pcts = self.all_val_pcts[start_idx:]
        self.current_macd_diff = self.all_macd_diff[start_idx:]
        self.current_macd_dea = self.all_macd_dea[start_idx:]
        self.current_macd_bar = self.all_macd_bar[start_idx:]
        self.current_kdj_k = self.all_kdj_k[start_idx:]
        self.current_kdj_d = self.all_kdj_d[start_idx:]
        self.current_kdj_j = self.all_kdj_j[start_idx:]
        self.current_rsi6 = self.all_rsi6[start_idx:]
        self.current_rsi12 = self.all_rsi12[start_idx:]
        
        # 分发更新数据缓存
        self.top_chart_view.update_data(self.current_dates, self.current_navs, self.current_pcts, self.top_axis_x)
        self.top_chart_view.update_indicators(
            current_ma5=self.current_ma5_pct,
            current_ma10=self.current_ma10_pct,
            current_ma20=self.current_ma20_pct
        )
        
        self.bottom_chart_view.update_data(self.current_dates, self.current_navs, self.current_pcts, self.bottom_axis_x)
        self.bottom_chart_view.update_indicators(
            current_val_pcts=self.current_val_pcts,
            macd_diff=self.current_macd_diff,
            macd_dea=self.current_macd_dea,
            macd_bar=self.current_macd_bar,
            kdj_k=self.current_kdj_k,
            kdj_d=self.current_kdj_d,
            kdj_j=self.current_kdj_j,
            rsi6=self.current_rsi6,
            rsi12=self.current_rsi12
        )
        
        # 刷新主图和副图
        self.update_main_chart()
        self.update_secondary_chart()
        
    def update_main_chart(self):
        """刷新上方主图"""
        if not self.current_pcts:
            return
            
        # 一次性生成折线的所有点列表，随后进行原子级 replace，彻底消除 QAreaSeries 在逐步 append 填充中数据点数不一致导致底层 C++ 断言闪退的问题
        line_pts = []
        upper_pts = []
        lower_pts = []
        ma5_pts = []
        ma10_pts = []
        ma20_pts = []
        
        min_pct = min(self.current_pcts)
        
        for i, pct in enumerate(self.current_pcts):
            line_pts.append(QPointF(i, pct))
            upper_pts.append(QPointF(i, pct))
            lower_pts.append(QPointF(i, min_pct - 2.0))
            
            if len(self.current_ma5_pct) > i:
                ma5_pts.append(QPointF(i, self.current_ma5_pct[i]))
            if len(self.current_ma10_pct) > i:
                ma10_pts.append(QPointF(i, self.current_ma10_pct[i]))
            if len(self.current_ma20_pct) > i:
                ma20_pts.append(QPointF(i, self.current_ma20_pct[i]))
                
        # 原子性整块替换，提高百倍更新速度并保障多图重绘时的内存绝对安全性
        self.line_series.replace(line_pts)
        self.area_upper_series.replace(upper_pts)
        self.area_lower_series.replace(lower_pts)
        self.ma5_series.replace(ma5_pts)
        self.ma10_series.replace(ma10_pts)
        self.ma20_series.replace(ma20_pts)
        
        # 设定 X 范围并重置
        self.top_axis_x.blockSignals(True)
        self.top_axis_x.setRange(0, max(1, len(self.current_dates) - 1))
        self.top_axis_x.blockSignals(False)
        
        # 触发一次 Y 轴的自适应高度计算
        self.handle_top_x_range_changed(0, len(self.current_dates) - 1)
        
    def handle_indicator_changed(self, index):
        """下拉框指标选择切换槽函数"""
        indicator_types = ["temperature", "macd", "kdj", "rsi"]
        self.bottom_chart_view.indicator_type = indicator_types[index]
        self.update_secondary_chart()
        
        # 强制联动 X 轴，同步当前可视范围内的 Y 自适应高度
        self.bottom_axis_x.blockSignals(True)
        self.bottom_axis_x.setRange(self.top_axis_x.min(), self.top_axis_x.max())
        self.bottom_axis_x.blockSignals(False)
        self.handle_bottom_x_range_changed(self.top_axis_x.min(), self.top_axis_x.max())
        
    def update_secondary_chart(self):
        """刷新下方副图的 QChart，根据选中的量化指标渲染不同类型的 Series"""
        self.bottom_chart.removeAllSeries()
        self._bg_series = []
        
        # 绝不销毁和重建 bottom_axis_y，仅修改其参数以防止 PySide C++ 野指针异常
        self.bottom_axis_y.setLabelsColor(QColor("#7f8c8d"))
        self.bottom_axis_y.setGridLinePen(QPen(QColor("#f1f2f6"), 1))
        self.bottom_axis_y.setLinePenColor(QColor("#dcdde1"))
        
        t = self.indicator_combo.currentIndex()
        
        if t == 0:  # 🌡️ 估值百分位温度带
            self.bottom_axis_y.setLabelFormat("%.1f%%")
            self.bottom_axis_y.setRange(-2.0, 102.0)
            
            # 安全参考虚线：20% (极低估) 与 80% (极高估)
            for level, color in [(20.0, "#3498db"), (80.0, "#e74c3c")]:
                hline = QLineSeries()
                hline.setPen(QPen(QColor(color), 1, Qt.DashLine))
                # 覆盖全时间段
                hline.append(0, level)
                hline.append(max(1, len(self.current_dates) - 1), level)
                hline.setPointsVisible(False)
                # 不在图例中显示
                self.bottom_chart.addSeries(hline)
                hline.attachAxis(self.bottom_axis_x)
                hline.attachAxis(self.bottom_axis_y)
                self.safe_hide_legend_marker(self.bottom_chart, hline)
                
            # 冰冻抄底区 (0%-20%) 的淡蓝色半透明面积阴影
            ref_low_lower = QLineSeries()
            ref_low_upper = QLineSeries()
            self._bg_series.extend([ref_low_lower, ref_low_upper])
            for i in range(len(self.current_dates)):
                ref_low_lower.append(i, 0.0)
                ref_low_upper.append(i, 20.0)
            low_area = QAreaSeries(ref_low_upper, ref_low_lower)
            low_area.setBrush(QBrush(QColor(52, 152, 219, 30)))
            low_area.setPen(Qt.NoPen)
            self.bottom_chart.addSeries(low_area)
            low_area.attachAxis(self.bottom_axis_x)
            low_area.attachAxis(self.bottom_axis_y)
            self.safe_hide_legend_marker(self.bottom_chart, low_area)
            
            # 沸腾高抛区 (80%-100%) 的淡红色半透明面积阴影
            ref_high_lower = QLineSeries()
            ref_high_upper = QLineSeries()
            self._bg_series.extend([ref_high_lower, ref_high_upper])
            for i in range(len(self.current_dates)):
                ref_high_lower.append(i, 80.0)
                ref_high_upper.append(i, 100.0)
            high_area = QAreaSeries(ref_high_upper, ref_high_lower)
            high_area.setBrush(QBrush(QColor(231, 76, 60, 30)))
            high_area.setPen(Qt.NoPen)
            self.bottom_chart.addSeries(high_area)
            high_area.attachAxis(self.bottom_axis_x)
            high_area.attachAxis(self.bottom_axis_y)
            self.safe_hide_legend_marker(self.bottom_chart, high_area)
            
            # 估值百分位金色主折线
            val_pct_series = QLineSeries()
            val_pct_series.setName("估值温度(%)")
            val_pct_series.setPen(QPen(QColor("#ffa502"), 2))
            for i, pct in enumerate(self.current_val_pcts):
                val_pct_series.append(i, pct)
            self.bottom_chart.addSeries(val_pct_series)
            val_pct_series.attachAxis(self.bottom_axis_x)
            val_pct_series.attachAxis(self.bottom_axis_y)
            
        elif t == 1:  # 📊 MACD 趋势指标
            self.bottom_axis_y.setLabelFormat("%.4f")
            
            # 零线辅助线
            zero_line = QLineSeries()
            zero_line.setPen(QPen(QColor("#7f8c8d"), 1, Qt.DashLine))
            zero_line.append(0, 0.0)
            zero_line.append(max(1, len(self.current_dates) - 1), 0.0)
            self.bottom_chart.addSeries(zero_line)
            zero_line.attachAxis(self.bottom_axis_x)
            zero_line.attachAxis(self.bottom_axis_y)
            self.safe_hide_legend_marker(self.bottom_chart, zero_line)
            
            # 正 MACD 柱的绿色半透明面积阴影
            ref_pos_zero = QLineSeries()
            ref_pos_val = QLineSeries()
            # 负 MACD 柱的红色半透明面积阴影
            ref_neg_zero = QLineSeries()
            ref_neg_val = QLineSeries()
            self._bg_series.extend([ref_pos_zero, ref_pos_val, ref_neg_zero, ref_neg_val])
            
            for i, val in enumerate(self.current_macd_bar):
                if val >= 0:
                    ref_pos_zero.append(i, 0.0)
                    ref_pos_val.append(i, val)
                    ref_neg_zero.append(i, 0.0)
                    ref_neg_val.append(i, 0.0)
                else:
                    ref_pos_zero.append(i, 0.0)
                    ref_pos_val.append(i, 0.0)
                    ref_neg_zero.append(i, 0.0)
                    ref_neg_val.append(i, val)
                    
            pos_macd_area = QAreaSeries(ref_pos_val, ref_pos_zero)
            pos_macd_area.setBrush(QBrush(QColor(46, 213, 115, 60)))
            pos_macd_area.setPen(Qt.NoPen)
            self.bottom_chart.addSeries(pos_macd_area)
            pos_macd_area.attachAxis(self.bottom_axis_x)
            pos_macd_area.attachAxis(self.bottom_axis_y)
            self.safe_hide_legend_marker(self.bottom_chart, pos_macd_area)
            
            neg_macd_area = QAreaSeries(ref_neg_val, ref_neg_zero)
            neg_macd_area.setBrush(QBrush(QColor(255, 71, 87, 60)))
            neg_macd_area.setPen(Qt.NoPen)
            self.bottom_chart.addSeries(neg_macd_area)
            neg_macd_area.attachAxis(self.bottom_axis_x)
            neg_macd_area.attachAxis(self.bottom_axis_y)
            self.safe_hide_legend_marker(self.bottom_chart, neg_macd_area)
            
            # DIFF 与 DEA 曲线
            diff_series = QLineSeries()
            diff_series.setName("DIFF")
            diff_series.setPen(QPen(QColor("#00bcff"), 1.5))
            for i, val in enumerate(self.current_macd_diff):
                diff_series.append(i, val)
            self.bottom_chart.addSeries(diff_series)
            diff_series.attachAxis(self.bottom_axis_x)
            diff_series.attachAxis(self.bottom_axis_y)
            
            dea_series = QLineSeries()
            dea_series.setName("DEA")
            dea_series.setPen(QPen(QColor("#e67e22"), 1.5))
            for i, val in enumerate(self.current_macd_dea):
                dea_series.append(i, val)
            self.bottom_chart.addSeries(dea_series)
            dea_series.attachAxis(self.bottom_axis_x)
            dea_series.attachAxis(self.bottom_axis_y)
            
        elif t == 2:  # 📈 KDJ 超买超卖
            self.bottom_axis_y.setLabelFormat("%.1f")
            self.bottom_axis_y.setRange(-5.0, 105.0)
            
            # 20/80 灰色强弱辅助水平线
            for val in [20.0, 80.0]:
                hline = QLineSeries()
                hline.setPen(QPen(QColor("#7f8c8d"), 1, Qt.DashLine))
                hline.append(0, val)
                hline.append(max(1, len(self.current_dates) - 1), val)
                self.bottom_chart.addSeries(hline)
                hline.attachAxis(self.bottom_axis_x)
                hline.attachAxis(self.bottom_axis_y)
                self.safe_hide_legend_marker(self.bottom_chart, hline)
                
            # K、D、J 折线
            k_series = QLineSeries()
            k_series.setName("K")
            k_series.setPen(QPen(QColor("#9b59b6"), 1.3))
            for i, val in enumerate(self.current_kdj_k):
                k_series.append(i, val)
            self.bottom_chart.addSeries(k_series)
            k_series.attachAxis(self.bottom_axis_x)
            k_series.attachAxis(self.bottom_axis_y)
            
            d_series = QLineSeries()
            d_series.setName("D")
            d_series.setPen(QPen(QColor("#f1c40f"), 1.3))
            for i, val in enumerate(self.current_kdj_d):
                d_series.append(i, val)
            self.bottom_chart.addSeries(d_series)
            d_series.attachAxis(self.bottom_axis_x)
            d_series.attachAxis(self.bottom_axis_y)
            
            j_series = QLineSeries()
            j_series.setName("J")
            j_series.setPen(QPen(QColor("#e74c3c"), 1.3))
            for i, val in enumerate(self.current_kdj_j):
                j_series.append(i, val)
            self.bottom_chart.addSeries(j_series)
            j_series.attachAxis(self.bottom_axis_x)
            j_series.attachAxis(self.bottom_axis_y)
            
        elif t == 3:  # 📉 RSI 强弱强弱
            self.bottom_axis_y.setLabelFormat("%.1f")
            self.bottom_axis_y.setRange(-5.0, 105.0)
            
            # 20/80 灰色强弱辅助水平线
            for val in [20.0, 80.0]:
                hline = QLineSeries()
                hline.setPen(QPen(QColor("#7f8c8d"), 1, Qt.DashLine))
                hline.append(0, val)
                hline.append(max(1, len(self.current_dates) - 1), val)
                self.bottom_chart.addSeries(hline)
                hline.attachAxis(self.bottom_axis_x)
                hline.attachAxis(self.bottom_axis_y)
                self.safe_hide_legend_marker(self.bottom_chart, hline)
                
            # RSI6 与 RSI12 折线
            rsi6_series = QLineSeries()
            rsi6_series.setName("RSI6")
            rsi6_series.setPen(QPen(QColor("#fd79a8"), 1.4))
            for i, val in enumerate(self.current_rsi6):
                rsi6_series.append(i, val)
            self.bottom_chart.addSeries(rsi6_series)
            rsi6_series.attachAxis(self.bottom_axis_x)
            rsi6_series.attachAxis(self.bottom_axis_y)
            
            rsi12_series = QLineSeries()
            rsi12_series.setName("RSI12")
            rsi12_series.setPen(QPen(QColor("#00b894"), 1.4))
            for i, val in enumerate(self.current_rsi12):
                rsi12_series.append(i, val)
            self.bottom_chart.addSeries(rsi12_series)
            rsi12_series.attachAxis(self.bottom_axis_x)
            rsi12_series.attachAxis(self.bottom_axis_y)
            
        # 同步副图 X 轴范围并触发一次自适应高度
        self.bottom_axis_x.blockSignals(True)
        self.bottom_axis_x.setRange(0, max(1, len(self.current_dates) - 1))
        self.bottom_axis_x.blockSignals(False)
        self.handle_bottom_x_range_changed(self.bottom_axis_x.min(), self.bottom_axis_x.max())


class StrategyNotificationToast(QWidget):
    """优雅滑入的 Glassmorphism 策略买入提醒悬浮通知窗"""
    
    def __init__(self, signals, main_window, parent=None):
        from PySide6.QtCore import Qt
        # 设为 Tool 避免在任务栏生成独立窗口，StaysOnTop 置顶，FramelessWindowHint 无边框
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.signals = signals  # 激活的买入信号字典 {code: signal_info}
        self.main_window = main_window  # 主窗口指针，用于联动跳转
        self.setAttribute(Qt.WA_TranslucentBackground, True)  # 支持透明底色
        
        self.init_ui()
        self.setup_animations()
        
    def init_ui(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)  # 为发光边框留出 1 像素
        
        # 磨砂玻璃质感容器
        self.container = QWidget(self)
        self.container.setObjectName("ToastContainer")
        self.container.setStyleSheet("""
            QWidget#ToastContainer {
                background-color: #1a202c;
                border: 1px solid rgba(46, 213, 115, 0.85);  /* 增强绿发光圆角边框对比度 */
                border-radius: 12px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(16, 14, 16, 14)
        container_layout.setSpacing(10)
        
        # 头部布局：小图标 + 标题 + 关闭按钮
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)
        
        icon_label = QLabel("🎯")
        icon_label.setStyleSheet("font-size: 16px;")
        
        title_label = QLabel("抄底策略买入预警")
        title_label.setStyleSheet("color: #2ed573; font-weight: bold; font-size: 13px; font-family: 'Segoe UI', 'Microsoft YaHei';")
        
        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a4b0be;
                font-weight: bold;
                font-size: 12px;
                border: none;
                padding: 0;
            }
            QPushButton:hover {
                color: #ff4757;
            }
        """)
        close_btn.clicked.connect(self.fade_out)
        header_layout.addWidget(close_btn)
        
        container_layout.addLayout(header_layout)
        
        # 分割线
        line_top = QWidget()
        line_top.setFixedHeight(1)
        line_top.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
        container_layout.addWidget(line_top)
        
        # 中部布局：显示触发买入条件的基金
        max_display = 2
        signal_list = list(self.signals.values())
        
        for idx, sig in enumerate(signal_list[:max_display]):
            name = sig['fund_name']
            code = sig['fund_code']
            drop = sig['current_drop']
            win = sig['win_rate']
            
            sig_label = QLabel(
                f"📈 <b>{name} ({code})</b><br>"
                f"今日估值跌幅达 <span style='color:#2ed573;font-weight:bold;'>{drop:+.2f}%</span> (触发 买{sig['buy_days']}天>{sig['buy_drop']}% 最优)<br>"
                f"历史回测胜率: <span style='color:#ffa502;font-weight:bold;'>{win:.1f}%</span>"
            )
            sig_label.setStyleSheet("color: #ffffff; font-size: 11px; font-family: 'Segoe UI', 'Microsoft YaHei'; line-height: 1.4;")
            container_layout.addWidget(sig_label)
            
            if idx < len(signal_list[:max_display]) - 1 or len(signal_list) > max_display:
                item_line = QWidget()
                item_line.setFixedHeight(1)
                item_line.setStyleSheet("background-color: rgba(255, 255, 255, 0.12);")
                container_layout.addWidget(item_line)
                
        if len(signal_list) > max_display:
            more_label = QLabel(f"✨ 还有 {len(signal_list) - max_display} 只基金同样触发了买入条件")
            more_label.setStyleSheet("color: #a4b0be; font-size: 10px; font-style: italic; font-family: 'Microsoft YaHei';")
            container_layout.addWidget(more_label)
            
        # 底部操作区
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.addStretch()
        
        view_btn = QPushButton("📊 立即前往查看")
        view_btn.setCursor(Qt.PointingHandCursor)
        view_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10ac84, stop:1 #2ed573);
                color: white;
                font-weight: bold;
                font-size: 11px;
                font-family: 'Microsoft YaHei';
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f9b75, stop:1 #26af5f);
            }
        """)
        view_btn.clicked.connect(self.go_to_details)
        btn_layout.addWidget(view_btn)
        
        container_layout.addLayout(btn_layout)
        layout.addWidget(self.container)
        
        # 动态调节高度
        calc_height = 145 + len(signal_list[:max_display]) * 55 + (20 if len(signal_list) > max_display else 0)
        self.setFixedSize(320, calc_height)
        
    def setup_animations(self):
        from PySide6.QtCore import QPoint, QPropertyAnimation, QEasingCurve, QTimer
        from PySide6.QtWidgets import QApplication
        
        # 1. 确定在屏幕右下角的位置
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        
        self.end_x = geo.right() - self.width() - 20
        self.end_y = geo.bottom() - self.height() - 20
        
        self.start_x = self.end_x
        self.start_y = geo.bottom() + 50  # 起始于屏幕底部外侧 50 像素
        
        self.move(self.start_x, self.start_y)
        self.setWindowOpacity(0.0)
        
        # 2. 位移滑入动画
        self.pos_anim = QPropertyAnimation(self, b"pos", self)
        self.pos_anim.setDuration(600)
        self.pos_anim.setStartValue(QPoint(self.start_x, self.start_y))
        self.pos_anim.setEndValue(QPoint(self.end_x, self.end_y))
        self.pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        # 3. 渐变淡入动画
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.opacity_anim.setDuration(500)
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        
        # 4. 自动关闭定时器
        self.timer = QTimer(self)
        self.timer.setInterval(8000)  # 默认展示 8 秒
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fade_out)
        
    def show_elegant(self):
        self.show()
        self.pos_anim.start()
        self.opacity_anim.start()
        self.timer.start()
        
    def enterEvent(self, event):
        # 鼠标移入，取消自动关闭
        self.timer.stop()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        # 鼠标移出，重新计时 4 秒后关闭
        self.timer.setInterval(4000)
        self.timer.start()
        super().leaveEvent(event)
        
    def fade_out(self):
        from PySide6.QtCore import QPoint, QPropertyAnimation, QEasingCurve
        self.timer.stop()
        
        # 渐变淡出
        self.fade_out_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_out_anim.setDuration(450)
        self.fade_out_anim.setStartValue(self.windowOpacity())
        self.fade_out_anim.setEndValue(0.0)
        
        # 向下滑出
        self.slide_out_anim = QPropertyAnimation(self, b"pos", self)
        self.slide_out_anim.setDuration(450)
        self.slide_out_anim.setStartValue(self.pos())
        self.slide_out_anim.setEndValue(QPoint(self.start_x, self.start_y))
        self.slide_out_anim.setEasingCurve(QEasingCurve.InCubic)
        
        self.fade_out_anim.finished.connect(self.close)
        
        self.fade_out_anim.start()
        self.slide_out_anim.start()
        
    def go_to_details(self):
        if not self.main_window:
            self.fade_out()
            return
            
        # 切换至我的自选基金 Tab (Index 是 1)
        self.main_window.tabs.setCurrentIndex(1)
        
        # 定位第一个买入信号的基金行并高亮
        if self.signals:
            first_code = list(self.signals.keys())[0]
            model = self.main_window.model1
            table = self.main_window.table1
            
            row = model.find_row_by_code(first_code)
            if row != -1:
                idx = model.index(row, 0)
                table.scrollTo(idx)
                table.selectRow(row)
                
                # 双击行以展示详细走势图
                self.main_window.show_detailed_chart(table, idx)
                
        self.fade_out()
