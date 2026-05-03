# config.py
import os
import sys

# 配置文件保存路径
# 获取当前脚本运行的所在目录
if getattr(sys, 'frozen', False):
    # 如果后续使用 PyInstaller 打包成 exe 程序，则获取 exe 所在的目录
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 如果是直接运行 py 文件，则获取 py 文件所在的目录
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "my_funds.json")
