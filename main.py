# main.py
import sys
import os
import multiprocessing

# 将当前根目录添加到 sys.path 中，确保子包内可以顺利定位根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from PySide6.QtWidgets import QApplication
    from ui.main_window import FundApp
    
    app = QApplication([])
    window = FundApp()
    window.show()
    app.exec()
