"""把裸数字变成人能读的字符串。"""
from __future__ import annotations


def human_size(num: float | int | None) -> str:
    if not num:
        return "未知"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "未知"


def human_duration(seconds: float | None) -> str:
    """01:23:45.678，不足一小时省略小时位。"""
    if seconds is None or seconds <= 0:
        return "未知"
    total = float(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours >= 1:
        return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"
    return f"{int(minutes):02d}:{secs:06.3f}"


def human_bitrate(bits: int | None) -> str:
    if not bits:
        return "未知"
    return f"{bits / 1000:.0f} kbps"


def human_fps(rate: str | None) -> str:
    """把 ffprobe 的 "30000/1001" 变成 "29.97"。"""
    if not rate or rate in ("0/0", "N/A"):
        return "未知"
    try:
        num, _, den = rate.partition("/")
        value = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return "未知"
    if value <= 0:
        return "未知"
    return f"{value:.2f}".rstrip("0").rstrip(".") + " fps"
