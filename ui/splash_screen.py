# ui/splash_screen.py
import json
import os
import sys

# 确保项目根目录在 sys.path 中，以防直接运行此文件时找不到 core 模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QBrush, QPainter
from core.config import CONFIG_FILE

class StartupSplashScreen(QWidget):
    """一个高阶美学质感的圆角无边框启动闪屏，支持自适应系统保存的明暗主题"""
    def __init__(self):
        super().__init__()
        # 设置无边框、顶层、工具窗口属性 (不显示在任务栏)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True) # 必须开启才能使圆角背景外的空白区域透明
        
        self.setFixedSize(500, 300)
        
        # 读取保存的主题，实现启动画面与软件皮肤的完美统一
        self.theme = self._get_saved_theme()
        self.is_dark = (self.theme == "Dark")
        
        # 居中显示
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 45, 35, 45)
        layout.setSpacing(15)
        
        # 应用中文大标题
        self.title_label = QLabel("场外基金深度监控", self)
        title_font = QFont("Microsoft YaHei", 24, QFont.Bold)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        # 英文副标题
        self.subtitle_label = QLabel("Off-Market Fund Deep Monitor", self)
        sub_font = QFont("Segoe UI", 10)
        sub_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self.subtitle_label.setFont(sub_font)
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subtitle_label)
        
        layout.addStretch()
        
        # 底部任务加载状态描述
        self.status_label = QLabel("正在启动系统服务...", self)
        status_font = QFont("Microsoft YaHei", 10)
        self.status_label.setFont(status_font)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 高清细进度条
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 应用主题色彩样式
        self.apply_theme_styles()
        
    def _get_saved_theme(self):
        """读取持久化配置文件中的主题设置"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data.get("theme", "Light")
        except Exception:
            pass
        return "Light"
        
    def apply_theme_styles(self):
        """根据当前的明/暗主题自适应渲染闪屏内所有标签和进度条的色彩"""
        if self.is_dark:
            # 黑暗模式：高贵明亮白底文本 + 动感极光蓝绿渐变进度条
            self.title_label.setStyleSheet("color: #FFFFFF; background: transparent;")
            self.subtitle_label.setStyleSheet("color: rgba(255, 255, 255, 0.55); background: transparent;")
            self.status_label.setStyleSheet("color: rgba(255, 255, 255, 0.85); background: transparent;")
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: rgba(255, 255, 255, 0.12);
                    border: none;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d2d3, stop:1 #0984e3);
                    border-radius: 2px;
                }
            """)
        else:
            # 浅色模式：儒雅深灰蓝文本 + 经典蔚蓝渐变进度条
            self.title_label.setStyleSheet("color: #2c3e50; background: transparent;")
            self.subtitle_label.setStyleSheet("color: rgba(44, 62, 80, 0.6); background: transparent;")
            self.status_label.setStyleSheet("color: rgba(44, 62, 80, 0.8); background: transparent;")
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: rgba(0, 0, 0, 0.08);
                    border: none;
                    border-radius: 2px;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00a8ff, stop:1 #0097e6);
                    border-radius: 2px;
                }
            """)
            
    def set_progress(self, val, status_text):
        """外部线程或同步调用，用来更新加载进度和当前文案"""
        self.progress_bar.setValue(val)
        self.status_label.setText(status_text)
        QApplication.processEvents() # 强制泵送 Qt 事件，实现实时渲染刷新
        
    def paintEvent(self, event):
        """自绘优雅的圆角窗口渐变背景，明暗两套定制视觉"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        gradient = QLinearGradient(0, 0, 0, self.height())
        if self.is_dark:
            # 精致黑暗模式：高雅青石灰蓝 ➡️ 经典极暗藏青
            gradient.setColorAt(0.0, QColor(41, 55, 72))
            gradient.setColorAt(1.0, QColor(19, 26, 36))
            
            painter.setBrush(QBrush(gradient))
            # 黑暗模式下，加一圈微弱亮灰色边界，让界面轮廓分明
            painter.setPen(QColor(255, 255, 255, 15))
        else:
            # 精致明亮模式：温润通透白 ➡️ 高雅浅灰蓝
            gradient.setColorAt(0.0, QColor(255, 255, 255))
            gradient.setColorAt(1.0, QColor(241, 242, 246))
            
            painter.setBrush(QBrush(gradient))
            # 浅色模式下，加一圈超细半透明灰色阴影边界，消除在白色桌面背景上的生硬感
            painter.setPen(QColor(0, 0, 0, 18))
            
        # 微调 adjusted 以使边框线更加平滑和闭合
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
