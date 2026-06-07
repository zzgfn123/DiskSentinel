"""
DiskSentinel 打包脚本
使用 PyInstaller 将应用打包为可安装的桌面客户端
"""

import subprocess
import sys
import platform
import os

def build():
    system = platform.system()
    print(f"当前平台: {system}")
    print(f"Python: {sys.version}")

    # PyInstaller 参数
    common_args = [
        "--name=DiskSentinel",
        "--noconfirm",
        "--clean",
        f"--add-data=src{os.pathsep}src",
        "--hidden-import=flet",
        "--hidden-import=watchdog",
        "--hidden-import=apscheduler",
        "--collect-all=flet",
        "main.py",
    ]

    if system == "Windows":
        common_args.extend([
            "--windowed",
            "--icon=assets/icon.ico",
        ])
    elif system == "Darwin":
        common_args.extend([
            "--windowed",
            "--icon=assets/icon.icns",
        ])
    else:  # Linux
        common_args.extend([
            "--windowed",
        ])

    cmd = [sys.executable, "-m", "PyInstaller"] + common_args
    print(f"执行: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print("\n✅ 打包完成！输出目录: dist/DiskSentinel/")

if __name__ == "__main__":
    build()
