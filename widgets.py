from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QLabel, 
                               QGroupBox, QGridLayout, QCheckBox, QHBoxLayout, 
                               QPushButton, QMessageBox, QVBoxLayout, QWidget)
from PySide6.QtGui import QPainter, QPolygonF, QPen, QColor, QFont, QLinearGradient
from PySide6.QtCore import Qt, QRect, QPointF
import datetime

class SettingsDialog(QDialog):
    """自定义设置弹窗"""
    def __init__(self, config, current_headers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自定义参数与列显示设置")
        self.resize(520, 250)
        self.config = config
        self.current_headers = current_headers
        
        layout = QFormLayout(self)
        
        self.drop_input = QLineEdit(", ".join(map(str, config.get("drop_days", [2, 4]))))
        self.pct_input = QLineEdit(", ".join(map(str, config.get("percentile_months", [1, 2, 3, 6, 12, 24]))))
        
        layout.addRow(QLabel("跌幅计算天数 (逗号分隔):"), self.drop_input)
        layout.addRow(QLabel("百分位计算月数 (逗号分隔):"), self.pct_input)
        
        self.col_group = QGroupBox("表格列显示设置 (取消勾选即可隐藏)")
        grid = QGridLayout()
        self.checkboxes = {}
        
        hidden_cols = config.get("hidden_columns", [])
        
        row, col = 0, 0
        for h in current_headers:
            if h == "操作": continue 
            cb = QCheckBox(h)
            cb.setChecked(h not in hidden_cols) 
            self.checkboxes[h] = cb
            grid.addWidget(cb, row, col)
            
            col += 1
            if col > 3: 
                col = 0
                row += 1
                
        self.col_group.setLayout(grid)
        layout.addRow(self.col_group)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存配置")
        save_btn.setStyleSheet("background-color: #0097e6; color: white;")
        save_btn.clicked.connect(self.save_and_accept)
        btn_layout.addWidget(save_btn)
        layout.addRow(btn_layout)

    def save_and_accept(self):
        try:
            drops = [int(x.strip()) for x in self.drop_input.text().split(",") if x.strip().isdigit()]
            pcts = [int(x.strip()) for x in self.pct_input.text().split(",") if x.strip().isdigit()]
            self.config["drop_days"] = drops if drops else [2, 4]
            self.config["percentile_months"] = pcts if pcts else [1, 2, 3, 6, 12, 24]
            
            hidden_cols = [h for h, cb in self.checkboxes.items() if not cb.isChecked()]
            self.config["hidden_columns"] = hidden_cols
            
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
        
        # 计算百分比极值
        max_pct = max(current_pcts) if current_pcts else 0
        min_pct = min(current_pcts) if current_pcts else 0
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
                tip_text = f"日期: {tip_date}\n涨跌: {tip_pct:+.2f}%"
                
                # 计算文字尺寸以确定浮窗大小
                painter.setFont(QFont("Segoe UI", 9))
                fm = painter.fontMetrics()
                # 稍微多留点边距
                text_rect = fm.boundingRect(QRect(0, 0, 200, 100), Qt.AlignLeft, tip_text)
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
