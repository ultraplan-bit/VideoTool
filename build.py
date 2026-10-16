"""打包成 Windows 可执行程序。

用法：uv run python build.py
产物：dist/VideoTool/VideoTool.exe（整个目录一起分发）

用 onedir 而不是 onefile：onefile 每次启动都要把几百 MB 解压到临时目录，
启动要等十几秒，体验很差。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "VideoTool"
FFMPEG_BIN = ROOT / "vendor" / "ffmpeg" / "bin"

# 输出里有中文，而 Windows 上 stdout 的默认编码可能是 cp1252（英文环境），
# 遇到中文会直接抛 UnicodeEncodeError。CI 里已用 PYTHONIOENCODING=utf-8 兜底，
# 这里再防一层，保证脚本单独跑也不挑环境。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure and (getattr(_stream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

# 没用到但会被 hook 顺带收进来的大块头，明确排掉以缩小体积
EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPrintSupport",
    "tkinter", "unittest", "pydoc", "doctest", "email", "http", "xmlrpc",
    "numpy", "PIL", "setuptools", "pip",
]


def _is_running(image: str) -> bool:
    """检查同名进程是否在运行（打包前用来避开文件占用）。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return image.lower() in (result.stdout or "").lower()


def main() -> int:
    for tool in ("ffmpeg.exe", "ffprobe.exe"):
        if not (FFMPEG_BIN / tool).is_file():
            print(f"缺少 {FFMPEG_BIN / tool}")
            print("请先把 ffmpeg.exe 和 ffprobe.exe 放到 vendor/ffmpeg/bin/")
            return 2

    # 上一版程序还在运行的话，dist 里的文件被占用，清理会失败并打出一个残缺的包。
    # 这里先检测并给出明确提示，而不是等到 rmtree 抛 PermissionError。
    if _is_running(f"{APP_NAME}.exe"):
        print(f"{APP_NAME}.exe 正在运行，请先关闭它再打包。")
        print("（程序运行时 Windows 会锁住 dist 里的文件，无法覆盖。）")
        return 3

    # 清理上一次的产物。必须先判断存在：CI 是全新检出，build/ 和 dist/
    # 都不存在，直接 rmtree 会抛 FileNotFoundError（实测踩过）。
    for stale in (ROOT / "build", ROOT / "dist"):
        if not stale.exists():
            continue
        try:
            shutil.rmtree(stale, ignore_errors=False)
        except PermissionError as exc:
            print(f"无法清理 {stale}：{exc}")
            print("可能有程序正在占用这些文件，请关闭后重试。")
            return 3
        except OSError as exc:
            print(f"清理 {stale} 失败：{exc}")
            return 3

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", APP_NAME,
        "--windowed",                      # 不弹控制台
        "--onedir",
        "--paths", str(ROOT / "src"),
        # ffmpeg 放到 exe 同级的 ffmpeg/bin/，与 ffmpeg.py 的查找顺序一致
        "--add-binary", f"{FFMPEG_BIN / 'ffmpeg.exe'}{';'}ffmpeg/bin",
        "--add-binary", f"{FFMPEG_BIN / 'ffprobe.exe'}{';'}ffmpeg/bin",
    ]
    icon_file = ROOT / "assets" / "icon.ico"
    if icon_file.is_file():
        # --icon 把图标嵌进 exe 的资源（任务栏/资源管理器显示用）；
        # --add-data 再放一份到包里，让 app_icon() 能加载它设置窗口图标。
        # 只做前者的话，打包后 setWindowIcon 会拿到空图标。
        args += ["--icon", str(icon_file)]
        args += ["--add-data", f"{icon_file}{';'}assets"]
    license_file = ROOT / "vendor" / "ffmpeg" / "LICENSE.txt"
    if license_file.is_file():
        args += ["--add-data", f"{license_file}{';'}ffmpeg"]
    for module in EXCLUDES:
        args += ["--exclude-module", module]
    # 入口必须是绝对导入的脚本：PyInstaller 把入口当独立脚本执行，
    # 用包内的 __main__.py（相对导入）会导致静态分析收不到 PySide6。
    args.append(str(ROOT / "main.py"))

    print("执行：" + " ".join(args[:8]) + " ...")
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        print("打包失败")
        return result.returncode

    exe = ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"
    if not exe.is_file():
        print(f"未找到产物 {exe}")
        return 1
    total = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file())
    print(f"\n打包完成：{exe}")
    print(f"目录总大小：{total / 1024 / 1024:.0f} MB")
    print("分发时把整个 dist/VideoTool 目录一起给用户，双击 VideoTool.exe 即可运行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
