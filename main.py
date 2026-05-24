# main.py
import sys
import os
import multiprocessing

# 将当前根目录添加到 sys.path 中，确保子包内可以顺利定位根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def qt_message_handler(mode, context, message):
    """自定义 Qt 消息处理器，过滤特定的底层无害警告"""
    from PySide6.QtCore import QtMsgType
    # 优雅过滤由第三方库（如 qfluentwidgets）或 Qt 底层在高 DPI 缩放/默认字体解析时触发的 setPointSize 负值警告
    if "QFont::setPointSize" in message or "Point size <= 0" in message:
        return
    
    # 正常输出其余的 Qt 内部消息，确保调试日志清晰可见
    if mode == QtMsgType.QtDebugMsg:
        print(f"[Qt Debug] {message}", file=sys.stdout)
    elif mode == QtMsgType.QtInfoMsg:
        print(f"[Qt Info] {message}", file=sys.stdout)
    elif mode == QtMsgType.QtWarningMsg:
        print(f"[Qt Warning] {message}", file=sys.stderr)
    elif mode == QtMsgType.QtCriticalMsg:
        print(f"[Qt Critical] {message}", file=sys.stderr)
    elif mode == QtMsgType.QtFatalMsg:
        print(f"[Qt Fatal] {message}", file=sys.stderr)
        sys.exit(-1)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import qInstallMessageHandler
    from ui.splash_screen import StartupSplashScreen
    from ui.main_window import FundApp
    
    # 安装消息拦截器以过滤无用警告
    qInstallMessageHandler(qt_message_handler)
    
    app = QApplication(sys.argv)
    
    # 实例化并展示具有圆角质感的启动闪屏
    splash = StartupSplashScreen()
    splash.show()
    
    # 启动应用主逻辑，传入闪屏实例以实时更新加载状态
    window = FundApp(splash=splash)
    
    # 主窗口就绪，展示并激活
    window.show()
    
    # 瞬间无缝关闭启动闪屏
    splash.close()
    
    app.exec()
