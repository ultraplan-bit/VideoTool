"""生成测试用的样本文件（需要项目内置的 ffmpeg）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from videotool.ffmpeg import Tools

OUT = Path(__file__).resolve().parent / "samples"


def main() -> int:
    tools = Tools.discover()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        (
            OUT / "sample.mp4",
            ["-f", "lavfi", "-i", "testsrc2=duration=5:size=640x480:rate=30",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest"],
        ),
        (
            OUT / "sample.mp3",
            ["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "libmp3lame"],
        ),
    ]
    # --long 额外生成一个 60 秒 720p 素材，用于对比软硬件编码速度
    if "--long" in sys.argv:
        jobs.append((
            OUT / "long.mp4",
            ["-f", "lavfi", "-i", "testsrc2=duration=60:size=1280x720:rate=30",
             "-f", "lavfi", "-i", "sine=duration=60",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest"],
        ))

    for path, args in jobs:
        result = subprocess.run(
            [str(tools.ffmpeg), "-hide_banner", "-y", *args, str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        status = "OK" if result.returncode == 0 else "失败"
        print(f"[{status}] {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
