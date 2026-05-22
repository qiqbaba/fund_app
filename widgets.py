from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QLabel, 
                               QGroupBox, QGridLayout, QCheckBox, QHBoxLayout, 
                               QPushButton, QMessageBox, QVBoxLayout, QWidget,
                               QTabWidget)
from PySide6.QtGui import QPainter, QPolygonF, QPen, QColor, QFont, QLinearGradient, QBrush, QGradient
from PySide6.QtCore import Qt, QRect, QPointF, QPoint, QMargins
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QAreaSeries
import datetime

class SettingsDialog(QDialog):
    """自定义设置弹窗"""
    def __init__(self, config, current_headers, val_headers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自定义参数与列显示设置")
        self.resize(650, 480)
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
            
            hidden_cols_config = {}
            for tab_key, tab_checkboxes in self.checkboxes.items():
                hidden_cols_config[tab_key] = [h for h, cb in tab_checkboxes.items() if not cb.isChecked()]
            
            self.config["hidden_columns"] = hidden_cols_config
            self.accept()
        except Exception:
            QMessageBox.warning(self, "错误", "请输入正确的数字格式！")

class InteractiveChartView(QChartView):
    """量化交互式图表视图，提供硬件加速、框选放大、滚轮缩放、右键平移和自定义十字辅助线与 Tooltip"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        # 支持框选局部放大
        self.setRubberBand(QChartView.RectangleRubberBand)
        
        # 缓存数据用于十字线绘制
        self.current_dates = []
        self.current_navs = []
        self.current_pcts = []
        self.axis_x = None
        
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
        
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            # 拖拽时临时更改鼠标光标为 SizeAll (十字移动) 样式以增强交互感受
            self.setCursor(Qt.SizeAllCursor)
            event.accept()
        else:
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        self.mouse_pos = event.pos()
        if self.is_dragging:
            delta = event.pos() - self.last_mouse_pos
            self.last_mouse_pos = event.pos()
            
            # 左右、上下拖动平移可视视口
            self.chart().scroll(-delta.x(), delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)
        self.viewport().update()
        
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.is_dragging = False
            self.setCursor(Qt.ArrowCursor) # 恢复默认光标
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
    def leaveEvent(self, event):
        self.mouse_pos = None
        self.viewport().update()
        super().leaveEvent(event)
        
    def wheelEvent(self, event):
        # 滚轮缩放：滚动幅度 y() 正数放大，负数缩小
        factor = 0.9 if event.angleDelta().y() > 0 else 1.1
        self.chart().zoom(factor)
        event.accept()
        
    def doubleClickEvent(self, event):
        # 双击还原缩放
        self.chart().zoomReset()
        event.accept()
        
    def drawForeground(self, painter, rect):
        # 1. 绘制自定义前景层
        if not self.current_pcts or not self.current_dates:
            return
            
        chart = self.chart()
        plot_rect = chart.plotArea()
        
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 2. 动态计算当前可见范围内的日期标签 (最多显示 5 个)
        if self.axis_x:
            x_min = max(0, int(self.axis_x.min() + 0.5))
            x_max = min(len(self.current_dates) - 1, int(self.axis_x.max() + 0.5))
            
            if x_max > x_min:
                painter.setPen(QColor("#7f8c8d"))
                painter.setFont(QFont("Segoe UI", 8))
                
                num_ticks = min(5, x_max - x_min + 1)
                for i in range(num_ticks):
                    idx = int(x_min + i * (x_max - x_min) / (num_ticks - 1))
                    pos_on_chart = chart.mapToPosition(QPointF(idx, 0))
                    x = pos_on_chart.x()
                    
                    # 确保只在绘图视口左右边界内绘制
                    if plot_rect.left() - 5 <= x <= plot_rect.right() + 5:
                        date_str = self.current_dates[idx]
                        tw = painter.fontMetrics().horizontalAdvance(date_str)
                        painter.drawText(x - tw / 2, plot_rect.bottom() + 18, date_str)
                        
            # 3. 标注区间末尾最新点 (若在可见范围内)
            last_idx = len(self.current_pcts) - 1
            if self.axis_x.min() - 0.5 <= last_idx <= self.axis_x.max() + 0.5:
                last_pct = self.current_pcts[-1]
                pos_last = chart.mapToPosition(QPointF(last_idx, last_pct))
                lx, ly = pos_last.x(), pos_last.y()
                
                if plot_rect.left() <= lx <= plot_rect.right() and plot_rect.top() <= ly <= plot_rect.bottom():
                    # 绘制鲜亮小红点
                    painter.setBrush(QColor("#e74c3c"))
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(QPointF(lx, ly), 4, 4)
                    
                    # 绘制最新百分比文字
                    painter.setPen(QColor("#e74c3c"))
                    painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                    val_str = f"{last_pct:+.2f}%"
                    tw = painter.fontMetrics().horizontalAdvance(val_str)
                    painter.drawText(lx - tw - 5, ly - 8, val_str)
                    
        # 4. 绘制十字线与悬浮 Tooltip 窗口
        if self.mouse_pos:
            scene_pos = self.mapToScene(self.mouse_pos)
            if plot_rect.contains(scene_pos):
                val = chart.mapToValue(scene_pos)
                idx = int(val.x() + 0.5)
                idx = max(0, min(len(self.current_pcts) - 1, idx))
                
                if self.axis_x and self.axis_x.min() - 0.5 <= idx <= self.axis_x.max() + 0.5:
                    pct = self.current_pcts[idx]
                    pos_in_chart = chart.mapToPosition(QPointF(idx, pct))
                    px, py = pos_in_chart.x(), pos_in_chart.y()
                    
                    # A. 绘制水平和垂直十字辅助线
                    painter.setPen(QPen(QColor("#7f8c8d"), 1, Qt.DashLine))
                    painter.drawLine(px, plot_rect.top(), px, plot_rect.bottom())
                    painter.drawLine(plot_rect.left(), py, plot_rect.right(), py)
                    
                    # B. 交点圆点高亮
                    painter.setBrush(QColor("#0097e6"))
                    painter.setPen(QPen(Qt.white, 2))
                    painter.drawEllipse(QPointF(px, py), 5, 5)
                    
                    # C. 浮窗 Tooltip 信息
                    tip_date = self.current_dates[idx]
                    v_curr = self.current_navs[idx]
                    
                    # 计算当前区间内最高和最低净值的差距
                    max_nav = max(self.current_navs)
                    min_nav = min(self.current_navs)
                    dist_high = (v_curr - max_nav) / max_nav * 100 if max_nav != 0 else 0
                    dist_low = (v_curr - min_nav) / min_nav * 100 if min_nav != 0 else 0
                    
                    tip_text = f"日期: {tip_date}\n净值: {v_curr:.4f}\n区间涨跌: {pct:+.2f}%\n距最高: {dist_high:+.2f}%\n距最低: {dist_low:+.2f}%"
                    
                    painter.setFont(QFont("Segoe UI", 9))
                    fm = painter.fontMetrics()
                    text_rect = fm.boundingRect(QRect(0, 0, 220, 120), Qt.AlignLeft, tip_text)
                    tip_w = text_rect.width() + 20
                    tip_h = text_rect.height() + 15
                    
                    # 悬停位置微调
                    tx = px + 15
                    ty = py - tip_h - 15
                    if tx + tip_w > plot_rect.right():
                        tx = px - tip_w - 15
                    if ty < plot_rect.top():
                        ty = py + 15
                        
                    tip_rect = QRect(tx, ty, tip_w, tip_h)
                    
                    # 磨砂半透明深色背景
                    painter.setBrush(QColor(45, 52, 71, 220))
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(tip_rect, 5, 5)
                    
                    # 文本白字输出
                    painter.setPen(Qt.white)
                    painter.drawText(tip_rect.adjusted(10, 5, -10, -5), Qt.AlignLeft | Qt.AlignVCenter, tip_text)
        
        painter.restore()


class FundChartDialog(QDialog):
    """基金走势图详情弹窗"""
    
    def __init__(self, code, name, history_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"走势详情: {name} ({code})")
        self.resize(950, 520)
        
        # 处理数据：接口返回通常是倒序，这里统一转为正序
        self.all_navs = history_data.get("navs", [])[::-1]
        self.all_dates = history_data.get("dates", [])[::-1]
        
        # 兼容旧数据：如果没有日期，生成虚拟日期
        if not self.all_dates and self.all_navs:
            self.all_dates = [f"D-{len(self.all_navs)-i}" for i in range(len(self.all_navs))]
            
        self.code = code
        self.name = name
        self.current_navs = []
        self.current_dates = []
        self.current_pcts = []
        
        layout = QVBoxLayout(self)
        
        # 顶部信息与时期选择
        top_ctrl_layout = QHBoxLayout()
        
        self.info_label = QLabel(f"<b>{name} ({code})</b>")
        self.info_label.setStyleSheet("font-size: 15px;")
        top_ctrl_layout.addWidget(self.info_label)
        top_ctrl_layout.addStretch()
        
        # 时期按钮组
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
        
        # 统计信息栏
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #7f8c8d; font-size: 12px; margin-bottom: 5px;")
        layout.addWidget(self.stats_label)
        
        # 专业交互式 QChartView 图表区域
        self.chart_view = InteractiveChartView(self)
        self.chart_view.setMinimumHeight(350)
        self.chart_view.setStyleSheet("background-color: white; border: 1px solid #f1f2f6; border-radius: 4px;")
        layout.addWidget(self.chart_view)
        
        # 创建 QChart 并进行视觉美化
        self.chart = QChart()
        self.chart.legend().hide()
        self.chart.setMargins(QMargins(10, 10, 10, 10))
        self.chart.setBackgroundRoundness(0)
        self.chart.setBackgroundVisible(False) # 使其应用 chart_view 的样式背景色
        
        # 走势折线系列
        self.line_series = QLineSeries()
        pen = QPen(QColor("#0097e6"), 2)
        self.line_series.setPen(pen)
        
        # 面积系列，用于渐变半透明阴影填充
        self.area_upper_series = QLineSeries()
        self.area_lower_series = QLineSeries()
        self.area_series = QAreaSeries(self.area_upper_series, self.area_lower_series)
        
        # 设置渐变填充 Brush
        gradient = QLinearGradient(0, 0, 0, 1)
        gradient.setCoordinateMode(QGradient.ObjectMode)
        gradient.setColorAt(0, QColor(0, 151, 230, 75)) # 顶部青蓝色，带75/255透明度
        gradient.setColorAt(1, QColor(0, 151, 230, 2))  # 底部接近完全透明
        self.area_series.setBrush(QBrush(gradient))
        self.area_series.setPen(Qt.NoPen)
        
        self.chart.addSeries(self.area_series)
        self.chart.addSeries(self.line_series)
        
        # 创建轴
        self.axis_x = QValueAxis()
        self.axis_x.setLabelsVisible(False) # 隐藏原生刻度标签，交由视图绘制日期
        self.axis_x.setGridLinePen(QPen(QColor("#f1f2f6"), 1))
        self.axis_x.setLinePenColor(QColor("#dcdde1"))
        
        self.axis_y = QValueAxis()
        self.axis_y.setLabelFormat("%.2f%%")
        self.axis_y.setLabelsColor(QColor("#7f8c8d"))
        self.axis_y.setGridLinePen(QPen(QColor("#f1f2f6"), 1))
        self.axis_y.setLinePenColor(QColor("#dcdde1"))
        
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        
        self.line_series.attachAxis(self.axis_x)
        self.line_series.attachAxis(self.axis_y)
        self.area_series.attachAxis(self.axis_x)
        self.area_series.attachAxis(self.axis_y)
        
        self.chart_view.setChart(self.chart)
        
        # 绑定 X 轴范围改变信号，实现 Y 轴实时视口自适应
        self.axis_x.rangeChanged.connect(self.handle_x_range_changed)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        # 默认选中“近1年”或可用最大范围
        default_p = "近1年" if len(self.all_navs) >= 252 else "全部"
        if default_p not in self.btns: default_p = "全部"
        
        self.change_period(default_p, periods[3][1] if default_p == "近1年" else 0)
        
    def change_period(self, period_text, days):
        # 更新按钮高亮状态
        for text, btn in self.btns.items():
            btn.setChecked(text == period_text)
            
        # 对数据进行时间切片
        if period_text == "今年以来":
            this_year = str(datetime.datetime.now().year)
            start_idx = -1
            for i, d in enumerate(self.all_dates):
                if d.startswith(this_year):
                    start_idx = i
                    break
            if start_idx != -1:
                self.current_navs = self.all_navs[start_idx:]
                self.current_dates = self.all_dates[start_idx:]
            else:
                self.current_navs = self.all_navs[-21:] if len(self.all_navs) > 21 else self.all_navs
                self.current_dates = self.all_dates[-21:] if len(self.all_dates) > 21 else self.all_dates
        elif days == 0:
            self.current_navs = self.all_navs
            self.current_dates = self.all_dates
        else:
            self.current_navs = self.all_navs[-days:]
            self.current_dates = self.all_dates[-days:]
            
        # 计算区间累计涨跌幅，更新 stats_label 标签
        if len(self.current_navs) > 1:
            start_v = self.current_navs[0]
            end_v = self.current_navs[-1]
            total_change = (end_v - start_v) / start_v * 100 if start_v != 0 else 0
            self.stats_label.setText(
                f"统计周期: {self.current_dates[0]} 至 {self.current_dates[-1]} ({len(self.current_navs)}个交易日) | "
                f"区间涨跌: <span style='color:{'#e74c3c' if total_change>=0 else '#27ae60'}'>{total_change:+.2f}%</span>"
            )
        else:
            self.stats_label.setText(f"统计周期: {self.current_dates[0] if self.current_dates else '-'} | 暂无足够对比数据")
            
        # 重新计算以首日为0%的百分比走势数据
        start_nav = self.current_navs[0] if self.current_navs else 1.0
        self.current_pcts = [(nav - start_nav) / start_nav * 100 for nav in self.current_navs]
        
        # 更新图表内容
        self.update_chart_data()
        
    def update_chart_data(self):
        if not self.current_pcts:
            return
            
        # 清空原有折线和面积数据
        self.line_series.clear()
        self.area_upper_series.clear()
        self.area_lower_series.clear()
        
        min_pct = min(self.current_pcts)
        
        # 塞入切片后的新点
        for i, pct in enumerate(self.current_pcts):
            self.line_series.append(i, pct)
            self.area_upper_series.append(i, pct)
            self.area_lower_series.append(i, min_pct - 2.0) # 下拉下限以实现全填充
            
        # 将数据更新到可视视图缓存中，供 QPainter 日期与十字线绘制
        self.chart_view.update_data(self.current_dates, self.current_navs, self.current_pcts, self.axis_x)
        
        # 重置 X 轴默认可视范围 [0, N-1]。重置时临时阻断信号，避免触发中间过度计算
        self.axis_x.blockSignals(True)
        self.axis_x.setRange(0, max(1, len(self.current_dates) - 1))
        self.axis_x.blockSignals(False)
        
        # 触发一次 Y 轴的自适应高度计算
        self.handle_x_range_changed(0, len(self.current_dates) - 1)
        
    def handle_x_range_changed(self, min_val, max_val):
        """X轴范围改变槽函数，实时自适应视口内的 Y 轴高度范围"""
        if not hasattr(self, 'current_pcts') or not self.current_pcts:
            return
            
        x_min = max(0, int(min_val + 0.5))
        x_max = min(len(self.current_pcts) - 1, int(max_val + 0.5))
        
        if x_max >= x_min:
            visible_pcts = self.current_pcts[x_min: x_max + 1]
            if visible_pcts:
                min_pct = min(visible_pcts)
                max_pct = max(visible_pcts)
                
                range_pct = max_pct - min_pct if max_pct != min_pct else 1.0
                margin_val = range_pct * 0.15 if range_pct > 0 else 1.0
                if margin_val < 0.5: margin_val = 0.5
                
                # 更新 Y 轴自适应范围
                self.axis_y.setRange(min_pct - margin_val, max_pct + margin_val)


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
