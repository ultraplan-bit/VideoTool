"""下载 ffmpeg / ffprobe 到 vendor/ffmpeg/bin/。

仓库里不放二进制（两个 exe 加起来 300 多 MB），克隆后跑一次这个脚本即可。
用法：uv run python scripts/fetch_ffmpeg.py

这个脚本也被 CI 用来准备构建环境，所以下载部分带了超时和重试：
190MB 的包在共享 runner 上偶尔会断，一次失败就中断整个构建不划算。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "vendor" / "ffmpeg"

# 输出里有中文，而 Windows 上 stdout 的默认编码可能是 cp1252（英文环境）
# 或 cp936，前者遇到中文会直接抛 UnicodeEncodeError。
# CI 里已用 PYTHONIOENCODING=utf-8 兜底，这里再防一层，保证任何控制台都能跑。
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure and (getattr(stream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

# BtbN 的 Windows 构建。用 gpl 版是因为它含 libx264 / libx265，
# lgpl 版没有这两个编码器，转 H.264 会退化成 libopenh264（画质与兼容性都更差）。
URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
WANTED = ("ffmpeg.exe", "ffprobe.exe")

# 单个连接的超时。下载 190MB 不能按默认（无超时）等，也不能设太短。
TIMEOUT = 120
ATTEMPTS = 3
# GitHub 会拒绝没有 User-Agent 的请求，显式给一个
HEADERS = {"User-Agent": "videotool-fetch-ffmpeg"}


def download(url: str, dest: Path) -> None:
    """下载到 dest，失败重试。"""
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                total = int(response.headers.get("Content-Length") or 0)
                print(f"  第 {attempt} 次尝试，包大小 "
                      f"{total / 1024 / 1024:.0f} MB" if total else
                      f"  第 {attempt} 次尝试")
                with dest.open("wb") as out:
                    shutil.copyfileobj(response, out, length=1024 * 256)
            got = dest.stat().st_size
            # 内容长度对不上说明连接中断了，当作失败重试
            if total and got != total:
                raise OSError(f"下载不完整：收到 {got} 字节，应为 {total}")
            return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = exc
            print(f"  第 {attempt} 次失败：{type(exc).__name__}: {exc}")
            dest.unlink(missing_ok=True)
            if attempt < ATTEMPTS:
                wait = 5 * attempt
                print(f"  {wait} 秒后重试…")
                time.sleep(wait)
    raise RuntimeError(f"下载失败（已重试 {ATTEMPTS} 次）：{last_error}")


def main() -> int:
    if all((TARGET / "bin" / name).is_file() for name in WANTED):
        print(f"已存在：{TARGET / 'bin'}")
        print("如需重新下载，先删除该目录。")
        return 0

    TARGET.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "ffmpeg.zip"
        print(f"下载 {URL}")
        try:
            download(URL, archive)
        except RuntimeError as exc:
            print(exc)
            return 1
        print(f"下载完成 {archive.stat().st_size / 1024 / 1024:.0f} MB，开始解压")

        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            (TARGET / "bin").mkdir(exist_ok=True)
            for name in WANTED:
                # zip 内路径形如 ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe
                member = next(
                    (n for n in names if n.endswith(f"bin/{name}")), None
                )
                if member is None:
                    print(f"压缩包里找不到 {name}")
                    print("包内前几项：" + "、".join(names[:5]))
                    return 1
                with bundle.open(member) as src, (TARGET / "bin" / name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"  {name}  {((TARGET / 'bin' / name).stat().st_size) / 1024 / 1024:.0f} MB")

            license_member = next(
                (n for n in names if n.endswith("LICENSE.txt") and n.count("/") == 1), None
            )
            if license_member:
                with bundle.open(license_member) as src, (TARGET / "LICENSE.txt").open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                print("  LICENSE.txt（分发时必须随程序一起提供）")

    print(f"\n完成：{TARGET / 'bin'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

