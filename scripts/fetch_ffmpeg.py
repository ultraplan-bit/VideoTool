"""下载 ffmpeg / ffprobe 到 vendor/ffmpeg/bin/。

仓库里不放二进制（两个 exe 加起来 300 多 MB），克隆后跑一次这个脚本即可。
用法：uv run python scripts/fetch_ffmpeg.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "vendor" / "ffmpeg"

# BtbN 的 Windows 构建。用 gpl 版是因为它含 libx264 / libx265，
# lgpl 版没有这两个编码器，转 H.264 会退化成 libopenh264（画质与兼容性都更差）。
URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
WANTED = ("ffmpeg.exe", "ffprobe.exe")


def main() -> int:
    if all((TARGET / "bin" / name).is_file() for name in WANTED):
        print(f"已存在：{TARGET / 'bin'}")
        print("如需重新下载，先删除该目录。")
        return 0

    TARGET.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "ffmpeg.zip"
        print(f"下载 {URL}")
        with urllib.request.urlopen(URL) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
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
