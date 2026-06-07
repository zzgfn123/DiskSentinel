"""DiskSentinel - 磁盘文件变化监控工具 启动入口"""

import sys
import os

# 将 src 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app import main
import flet as ft

if __name__ == "__main__":
    ft.app(target=main)
