"""抓取视频缩略图。

命令行要点：`-ss` 放在 `-i` 之前是"快速定位"，不解码前面的内容，
速度快但可能停在关键帧之前抓到黑帧。所以按多个时间点依次尝试，
由调用方通过 accept 回调判断这一帧是否可用。
"""
from __future__ import annotations

from dataclasses import dataclass

from .ffmpeg import Tools

WIDTH = 480                        # 缩略图宽度，高度按比例自适应
_POSITIONS = (0.10, 0.25, 0.50, 0.75)  # 依次尝试的时间点（占总时长比例）


@dataclass
class Thumbnail:
    data: bytes        # PNG 原始数据
    at: float          # 抓取用的时间点（秒）


def grab(
    tools: Tools,
    path: str,
    duration: float | None,
    *,
    accept=None,
    timeout: float = 60,
) -> Thumbnail:
    """抓一帧返回 PNG。accept(bytes)->bool 用来否决黑帧；全部失败则抛 RuntimeError。"""
    errors: list[str] = []

    for ratio in _POSITIONS:
        seek = max((duration or 0) * ratio, 0.0)
        result = tools.run(
            [
                "-ss", f"{seek:.3f}",
                "-i", path,
                "-frames:v", "1",
                "-vf", f"scale={WIDTH}:-2:flags=lanczos",
                "-f", "image2pipe",
                "-vcodec", "png",
                "-v", "error",
                "-",
            ],
            timeout=timeout,
            text=False,
        )
        data = result.stdout or b""
        if result.returncode == 0 and data.startswith(b"\x89PNG"):
            if accept is None or accept(data):
                return Thumbnail(data=data, at=seek)
            errors.append("画面全黑")
        else:
            tail = (result.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            errors.append(tail[-1] if tail else "未知错误")

    raise RuntimeError("无法生成缩略图：" + (errors[0] if errors else "未知错误"))
