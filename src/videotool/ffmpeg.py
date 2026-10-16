"""定位 ffmpeg / ffprobe，并做最低层封装。

查找顺序：
1. 随程序打包的 vendor/ffmpeg/bin（开发态）
2. PyInstaller 解包目录（打包态）
3. 系统 PATH
4. Windows 常见安装路径
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
EXE = ".exe" if IS_WINDOWS else ""
# Windows 下避免子进程弹出控制台黑窗
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

_WIN_HINTS = (
    r"C:\ffmpeg\bin",
    r"C:\Program Files\ffmpeg\bin",
    r"C:\Program Files (x86)\ffmpeg\bin",
)


class FFmpegNotFound(RuntimeError):
    """ffmpeg 或 ffprobe 不可用。"""


def app_root() -> Path:
    """开发态返回项目根目录，打包态返回 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs += [Path(meipass) / "ffmpeg" / "bin", Path(meipass)]
    root = app_root()
    dirs += [root / "vendor" / "ffmpeg" / "bin", root / "vendor" / "ffmpeg", root]
    if IS_WINDOWS:
        dirs += [Path(p) for p in _WIN_HINTS]
    return dirs


def find_tool(name: str) -> Path | None:
    """按顺序查找可执行文件，找不到返回 None。"""
    filename = name + EXE
    for directory in _candidate_dirs():
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    return Path(found) if found else None


class Tools:
    """成对持有 ffmpeg / ffprobe 路径，并提供同步调用。"""

    def __init__(self, ffmpeg: Path, ffprobe: Path) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    @classmethod
    def discover(cls) -> "Tools":
        ffmpeg = find_tool("ffmpeg")
        ffprobe = find_tool("ffprobe")
        missing = [n for n, p in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)) if p is None]
        if missing:
            raise FFmpegNotFound("未找到 " + "、".join(missing))
        return cls(ffmpeg, ffprobe)

    @property
    def version(self) -> str:
        """形如 "n7.1"，拿不到就返回空串。"""
        try:
            result = self.run(["-version"], timeout=10)
        except (OSError, subprocess.SubprocessError):
            return ""
        first = (result.stdout or "").splitlines()
        if not first:
            return ""
        # 首行：ffmpeg version n7.1 Copyright (c) ...
        parts = first[0].split()
        return parts[2] if len(parts) > 2 else ""

    def run(
        self,
        args: list[str],
        *,
        timeout: float = 30,
        use_probe: bool = False,
        text: bool = True,
    ):
        """同步执行并捕获输出。text=False 时 stdout 为 bytes（用于抓图）。"""
        tool = self.ffprobe if use_probe else self.ffmpeg
        return subprocess.run(
            [str(tool), *args],
            capture_output=True,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
            timeout=timeout,
            creationflags=NO_WINDOW,
        )


# 可用的硬件编码器，按优先级排列（NVIDIA → Intel → AMD → 通用）
HARDWARE_ENCODERS = (
    ("h264_nvenc", "NVIDIA NVENC"),
    ("h264_qsv", "Intel Quick Sync"),
    ("h264_amf", "AMD AMF"),
    ("h264_mf", "Windows Media Foundation"),
)


def detect_hardware_encoder(tools: "Tools", timeout: float = 20) -> tuple[str, str] | None:
    """探测第一个真正能用的硬件 H.264 编码器。

    只检查 ffmpeg -encoders 里是否存在是不够的：构建里带了 nvenc 但机器没有
    NVIDIA 显卡时，编码器会列出却无法初始化。所以这里实际跑一次极短的编码，
    能成功输出才认为可用。

    返回 (编码器名, 友好名称)；都不可用返回 None。
    """
    listed = tools.run(["-hide_banner", "-encoders"], timeout=timeout)
    available = (listed.stdout or "") + (listed.stderr or "")
    for name, label in HARDWARE_ENCODERS:
        if name not in available:
            continue
        probe = tools.run(
            [
                "-hide_banner", "-v", "error",
                "-f", "lavfi", "-i", "testsrc2=duration=0.1:size=320x240:rate=10",
                "-c:v", name, "-f", "null", "-",
            ],
            timeout=timeout,
        )
        if probe.returncode == 0:
            return name, label
    return None
