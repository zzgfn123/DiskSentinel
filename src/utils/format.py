"""
DiskSentinel - 格式化工具

提供文件大小、日期时间、时长和数字的友好格式化函数。
"""

from datetime import datetime
from typing import Union


def format_size(num_bytes: Union[int, float]) -> str:
    """
    将字节数格式化为人类可读的大小字符串。

    Args:
        num_bytes: 字节数

    Returns:
        格式化字符串，如 '1.5 GB', '300 MB', '45.2 KB'

    Examples:
        >>> format_size(0)
        '0 B'
        >>> format_size(1024)
        '1.0 KB'
        >>> format_size(1536)
        '1.5 KB'
        >>> format_size(1073741824)
        '1.0 GB'
    """
    if num_bytes < 0:
        return f"-{_format_positive_size(-num_bytes)}"
    return _format_positive_size(num_bytes)


def _format_positive_size(num_bytes: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    for unit in units:
        if abs(size) < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"  # fallback


def format_datetime(dt: datetime) -> str:
    """
    将 datetime 对象格式化为 'YYYY-MM-DD HH:MM' 字符串。

    Args:
        dt: datetime 实例

    Returns:
        格式化字符串，如 '2026-06-07 14:30'

    Examples:
        >>> format_datetime(datetime(2026, 6, 7, 14, 30, 0))
        '2026-06-07 14:30'
    """
    if isinstance(dt, str):
        # 支持传入 ISO 格式字符串
        try:
            dt = datetime.fromisoformat(dt)
        except (ValueError, TypeError):
            return dt
    return dt.strftime("%Y-%m-%d %H:%M")


def format_duration(seconds: Union[int, float]) -> str:
    """
    将秒数格式化为人类可读的时长字符串（中文）。

    Args:
        seconds: 秒数

    Returns:
        格式化字符串，如 '2分30秒', '1小时15分', '3秒'

    Examples:
        >>> format_duration(150)
        '2分30秒'
        >>> format_duration(3600)
        '1小时'
        >>> format_duration(3661)
        '1小时1分1秒'
    """
    if seconds < 0:
        return f"-{format_duration(-seconds)}"

    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分")
    if secs > 0 or not parts:
        parts.append(f"{secs}秒")

    return "".join(parts)


def format_number(n: Union[int, float]) -> str:
    """
    将数字格式化为带千分位分隔符的字符串。

    Args:
        n: 数字

    Returns:
        格式化字符串，如 '1,234,567', '12,345.67'

    Examples:
        >>> format_number(1234567)
        '1,234,567'
        >>> format_number(12345.67)
        '12,345.67'
    """
    if isinstance(n, float):
        # 分别处理整数和小数部分
        integer_part = int(abs(n))
        decimal_part = f"{abs(n) - integer_part:.10f}".lstrip("0")  # '.xxx'
        sign = "-" if n < 0 else ""
        formatted_int = f"{integer_part:,}"
        return f"{sign}{formatted_int}{decimal_part}"
    else:
        return f"{n:,}"
