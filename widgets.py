from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QLabel, 
                               QGroupBox, QGridLayout, QCheckBox, QHBoxLayout, 
                               QPushButton, QMessageBox, QVBoxLayout, QWidget,
                               QTabWidget)
from PySide6.QtGui import QPainter, QPolygonF, QPen, QColor, QFont, QLinearGradient
from PySide6.QtCore import Qt, QRect, QPointF
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
        
        # 图表区域
        self.chart_widget = QWidget()
        self.chart_widget.setMinimumHeight(350)
        self.chart_widget.setStyleSheet("background-color: white; border: 1px solid #f1f2f6; border-radius: 4px;")
        layout.addWidget(self.chart_widget)
        
        # 开启鼠标追踪及事件，用于显示十字辅助线和 Tooltip
        self.chart_widget.setMouseTracking(True)
        self.mouse_pos = None
        self.chart_widget.mouseMoveEvent = self.chart_mouse_move
        self.chart_widget.leaveEvent = self.chart_mouse_leave
        
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
        
        # 重写 chart_widget 的 paintEvent
        self.chart_widget.paintEvent = self.paint_chart

    def chart_mouse_move(self, event):
        self.mouse_pos = event.pos()
        self.chart_widget.update()

    def chart_mouse_leave(self, event):
        self.mouse_pos = None
        self.chart_widget.update()

    def change_period(self, period_text, days):
        # 更新按钮状态
        for text, btn in self.btns.items():
            btn.setChecked(text == period_text)
            
        # 切片数据
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
            
        # 计算涨跌幅
        if len(self.current_navs) > 1:
            start_v = self.current_navs[0]
            end_v = self.current_navs[-1]
            total_change = (end_v - start_v) / start_v * 100 if start_v != 0 else 0
            self.stats_label.setText(f"统计周期: {self.current_dates[0]} 至 {self.current_dates[-1]} ({len(self.current_navs)}个交易日) | 区间涨跌: <span style='color:{'#e74c3c' if total_change>=0 else '#27ae60'}'>{total_change:+.2f}%</span>")
        else:
            self.stats_label.setText(f"统计周期: {self.current_dates[0] if self.current_dates else '-'} | 暂无足够对比数据")
            
        self.chart_widget.update()

    def paint_chart(self, event):
        if not self.current_navs:
            return
            
        painter = QPainter(self.chart_widget)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.chart_widget.rect()
        padding_l, padding_r, padding_t, padding_b = 60, 40, 40, 40
        chart_rect = rect.adjusted(padding_l, padding_t, -padding_r, -padding_b)
        
        # 画背景网格
        painter.setPen(QPen(QColor("#f1f2f6"), 1))
        for i in range(5):
            y = chart_rect.top() + i * chart_rect.height() / 4
            painter.drawLine(chart_rect.left(), y, chart_rect.right(), y)
        
        # 画坐标轴
        painter.setPen(QPen(QColor("#dcdde1"), 1))
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.bottomRight())
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.topLeft())
        
        # 转换数据为百分比 (以所选区间的第一天作为 0%)
        start_nav = self.current_navs[0] if self.current_navs else 1.0
        current_pcts = [(nav - start_nav) / start_nav * 100 for nav in self.current_navs]
        
        # 计算百分比极值与数值极值
        max_pct = max(current_pcts) if current_pcts else 0
        min_pct = min(current_pcts) if current_pcts else 0
        max_nav = max(self.current_navs) if self.current_navs else 1.0
        min_nav = min(self.current_navs) if self.current_navs else 1.0
        range_pct = max_pct - min_pct if max_pct != min_pct else 1.0
        
        # 留白 15%
        margin_val = range_pct * 0.15 if range_pct > 0 else 1.0
        if margin_val < 0.5: margin_val = 0.5
        
        max_pct_disp = max_pct + margin_val
        min_pct_disp = min_pct - margin_val
        range_disp = max_pct_disp - min_pct_disp
        
        # 画点
        points = QPolygonF()
        x_step = chart_rect.width() / (len(current_pcts) - 1) if len(current_pcts) > 1 else 0
        
        for i, pct in enumerate(current_pcts):
            x = chart_rect.left() + i * x_step
            y = chart_rect.bottom() - (pct - min_pct_disp) / range_disp * chart_rect.height()
            points.append(QPointF(x, y))
            
        # 画零基准线 (如果跨越了0)
        if min_pct_disp < 0 < max_pct_disp:
            zero_y = chart_rect.bottom() - (0 - min_pct_disp) / range_disp * chart_rect.height()
            painter.setPen(QPen(QColor("#bdc3c7"), 1, Qt.DashLine))
            painter.drawLine(chart_rect.left(), zero_y, chart_rect.right(), zero_y)
            
        # 画填充阴影 (渐变效果)
        gradient = QLinearGradient(0, chart_rect.top(), 0, chart_rect.bottom())
        gradient.setColorAt(0, QColor(0, 151, 230, 60))
        gradient.setColorAt(1, QColor(0, 151, 230, 5))
        
        shadow_points = QPolygonF(points)
        shadow_points.append(QPointF(chart_rect.right() if len(points)>1 else points[0].x(), chart_rect.bottom()))
        shadow_points.append(QPointF(chart_rect.left(), chart_rect.bottom()))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(shadow_points)
        
        # 画折线
        painter.setPen(QPen(QColor("#0097e6"), 2))
        if len(points) > 1:
            painter.drawPolyline(points)
        else:
            painter.drawEllipse(points[0], 2, 2)
        
        # 画刻度文本
        painter.setPen(QColor("#7f8c8d"))
        painter.setFont(QFont("Segoe UI", 8))
        
        # Y轴刻度 (百分比)
        for i in range(5):
            y_val = max_pct_disp - i * range_disp / 4
            y_pos = chart_rect.top() + i * chart_rect.height() / 4
            painter.drawText(chart_rect.left() - 55, y_pos + 5, f"{y_val:+.2f}%")
            
        # X轴刻度 (日期) - 均匀显示 5 个日期
        if len(self.current_dates) >= 2:
            num_ticks = min(5, len(self.current_dates))
            for i in range(num_ticks):
                idx = int(i * (len(self.current_dates) - 1) / (num_ticks - 1))
                x = chart_rect.left() + idx * x_step
                date_str = self.current_dates[idx]
                # 动态计算文字宽度以实现精准居中
                tw = painter.fontMetrics().horizontalAdvance(date_str)
                painter.drawText(x - tw / 2, chart_rect.bottom() + 22, date_str)
        
        # 标注最新值
        if points:
            last_p = points[-1]
            painter.setBrush(QColor("#e74c3c"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(last_p, 4, 4)
            painter.setPen(QColor("#e74c3c"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(last_p.x() - 60, last_p.y() - 15, f"{current_pcts[-1]:+.2f}%")

        # --- 增加辅助线与浮窗 (Tooltip) ---
        if self.mouse_pos and len(self.current_navs) > 1:
            mx, my = self.mouse_pos.x(), self.mouse_pos.y()
            if chart_rect.contains(mx, my):
                # 找到最接近的数据索引
                idx = int((mx - chart_rect.left()) / x_step + 0.5)
                idx = max(0, min(len(self.current_navs) - 1, idx))
                
                # 数据点实际坐标
                data_point = points[idx]
                px, py = data_point.x(), data_point.y()
                
                # 1. 画垂直和水平辅助线
                painter.setPen(QPen(QColor("#7f8c8d"), 1, Qt.DashLine))
                painter.drawLine(px, chart_rect.top(), px, chart_rect.bottom())
                painter.drawLine(chart_rect.left(), py, chart_rect.right(), py)
                
                # 2. 高亮当前交点
                painter.setBrush(QColor("#0097e6"))
                painter.setPen(QPen(Qt.white, 2))
                painter.drawEllipse(data_point, 5, 5)
                
                # 3. 绘制浮窗
                tip_date = self.current_dates[idx]
                tip_pct = current_pcts[idx]
                
                # 计算与期间最高/最低的差距
                v_curr = self.current_navs[idx]
                dist_high = (v_curr - max_nav) / max_nav * 100 if max_nav != 0 else 0
                dist_low = (v_curr - min_nav) / min_nav * 100 if min_nav != 0 else 0
                
                tip_text = f"日期: {tip_date}\n涨跌: {tip_pct:+.2f}%\n距最高: {dist_high:+.2f}%\n距最低: {dist_low:+.2f}%"
                
                # 计算文字尺寸以确定浮窗大小
                painter.setFont(QFont("Segoe UI", 9))
                fm = painter.fontMetrics()
                # 稍微多留点边距
                text_rect = fm.boundingRect(QRect(0, 0, 220, 120), Qt.AlignLeft, tip_text)
                tip_w = text_rect.width() + 20
                tip_h = text_rect.height() + 15
                
                # 确定浮窗位置 (尽量不遮挡鼠标和数据点)
                tx = px + 15
                ty = py - tip_h - 15
                
                # 边界检查，防止浮窗超出图表区域
                if tx + tip_w > chart_rect.right() + padding_r:
                    tx = px - tip_w - 15
                if ty < chart_rect.top() - 20:
                    ty = py + 15
                    
                tip_rect = QRect(tx, ty, tip_w, tip_h)
                
                # 绘制半透明背景
                painter.setBrush(QColor(45, 52, 71, 220)) 
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(tip_rect, 5, 5)
                
                # 绘制文字
                painter.setPen(Qt.white)
                painter.drawText(tip_rect.adjusted(10, 5, -10, -5), Qt.AlignLeft | Qt.AlignVCenter, tip_text)


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
