"""
DiskSentinel - 平台工具

提供跨平台的系统信息获取函数，包括磁盘列表、目录路径和权限检测。
"""

import os
import sys
import platform
from pathlib import Path


def get_system_drives() -> list:
    """
    获取系统可用的磁盘/挂载点列表。

    - Windows: 返回可用的驱动器盘符列表，如 ['C:\\\\', 'D:\\\\']
    - Linux/Mac: 返回常见挂载点列表，如 ['/', '/home', '/mnt']

    Returns:
        磁盘路径字符串列表
    """
    system = platform.system()

    if system == "Windows":
        import ctypes
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & 1:
                drive_path = f"{letter}:\\"
                # 检查驱动器是否就绪
                if os.path.exists(drive_path):
                    drives.append(drive_path)
            bitmask >>= 1
        return drives
    else:
        # Linux / macOS
        mounts = ["/"]
        common_mounts = ["/home", "/mnt", "/media", "/opt", "/tmp"]
        for m in common_mounts:
            if os.path.isdir(m) and os.path.ismount(m):
                mounts.append(m)
        # 尝试获取用户特定的挂载点
        if sys.platform == "darwin":
            volumes_dir = "/Volumes"
            if os.path.isdir(volumes_dir):
                for vol in os.listdir(volumes_dir):
                    vol_path = os.path.join(volumes_dir, vol)
                    if os.path.isdir(vol_path):
                        mounts.append(vol_path)
        else:
            # Linux: 检查 /media/<user> 下的挂载
            media_user = os.path.join("/media", os.environ.get("USER", ""))
            if os.path.isdir(media_user):
                for vol in os.listdir(media_user):
                    vol_path = os.path.join(media_user, vol)
                    if os.path.isdir(vol_path):
                        mounts.append(vol_path)
        return mounts


def get_home_directory() -> str:
    """
    获取当前用户的主目录路径。

    Returns:
        主目录的绝对路径
    """
    return str(Path.home())


def get_data_directory() -> str:
    """
    获取 DiskSentinel 应用数据目录 (~/.disksentinel)。

    如果目录不存在会自动创建。

    Returns:
        数据目录的绝对路径
    """
    data_dir = os.path.join(Path.home(), ".disksentinel")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def is_admin() -> bool:
    """
    检测当前进程是否以管理员/root 权限运行。

    Returns:
        True 表示具有管理员权限
    """
    system = platform.system()

    if system == "Windows":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            return False
    else:
        # Linux / macOS
        return os.getuid() == 0
