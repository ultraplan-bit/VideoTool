"""验证打包产物：PySide6 是否进包、exe 能否真正启动出窗口、并截图留证。

用法：uv run python tests/test_package.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "VideoTool" / "VideoTool.exe"
INTERNAL = ROOT / "dist" / "VideoTool" / "_internal"
SHOT = ROOT / "tests" / "out_exe.png"

passed: list[str] = []
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _pid_alive(pid: int) -> bool:
    """按 PID 判断进程是否还在。比按镜像名查可靠——同名残留不会干扰判断。"""
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, timeout=30,
    )
    return str(pid) in (result.stdout or "")


def main() -> int:
    check("产物 exe 存在", EXE.is_file(), str(EXE))
    if not EXE.is_file():
        return 1

    # 1. 关键依赖是否真的进了包（上一版就因为入口写错，PySide6 一个都没收进去）
    pyside_dirs = [p for p in INTERNAL.rglob("PySide6*") if p.is_dir()]
    check("PySide6 已打进包", bool(pyside_dirs),
          f"{len(pyside_dirs)} 个目录" if pyside_dirs else "完全没有 PySide6")
    qt_core = list(INTERNAL.rglob("QtCore.pyd")) + list(INTERNAL.rglob("QtCore*.dll"))
    check("QtCore 已打进包", bool(qt_core),
          qt_core[0].name if qt_core else "缺失")
    platform_plugins = list(INTERNAL.rglob("platforms/qwindows.dll"))
    check("Qt 平台插件已打进包", bool(platform_plugins),
          "qwindows.dll" if platform_plugins else "缺失，程序无法起窗口")

    # 图标：既要嵌进 exe 资源，也要作为数据文件在包里，
    # 否则打包后 setWindowIcon 拿到空图标（窗口和任务栏都没有图标）。
    embedded = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Add-Type -AssemblyName System.Drawing;"
         f"$i=[System.Drawing.Icon]::ExtractAssociatedIcon('{EXE}');"
         "if($i){Write-Output ('ok:' + $i.Width)}else{Write-Output 'none'}"],
        capture_output=True, text=True, timeout=60,
    ).stdout.strip()
    check("图标已嵌入 exe 资源", embedded.startswith("ok:"), embedded or "读取失败")
    icon_data = list(INTERNAL.rglob("assets/icon.ico"))
    check("图标已作为数据文件进包", bool(icon_data),
          str(icon_data[0].relative_to(INTERNAL)) if icon_data else "缺失，窗口图标会是空的")

    # 2. 内置 ffmpeg 可用
    for tool in ("ffmpeg.exe", "ffprobe.exe"):
        found = list(INTERNAL.rglob(f"ffmpeg/bin/{tool}"))
        check(f"内置 {tool}", bool(found), str(found[0].relative_to(INTERNAL)) if found else "缺失")
    ffmpeg = next(INTERNAL.rglob("ffmpeg/bin/ffmpeg.exe"), None)
    if ffmpeg:
        result = subprocess.run([str(ffmpeg), "-hide_banner", "-version"],
                                capture_output=True, text=True, timeout=60)
        check("内置 ffmpeg 可执行", result.returncode == 0,
              (result.stdout or "").splitlines()[0][:60] if result.stdout else "无输出")

    # 3. 真正启动 exe，确认没有闪退，并截图
    proc = subprocess.Popen([str(EXE)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(15)
    if proc.poll() is not None:
        _out, err = proc.communicate()
        proc.kill()
        check("exe 启动后保持运行", False,
              ((err or b"").decode("utf-8", "replace").strip().splitlines() or ["无错误输出"])[-1])
        print(f"\n通过 {len(passed)} 项，失败 {len(failed)} 项")
        return 1

    check("exe 启动后保持运行", True, "未闪退")

    # 用 PowerShell 抓窗口截图（离屏抓不到 exe 的窗口）
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$p=Get-Process VideoTool -ErrorAction SilentlyContinue|Select-Object -First 1;"
        "if($p){"
        "Add-Type -Namespace W -Name U -MemberDefinition '[DllImport(\"user32.dll\")]"
        "public static extern bool SetForegroundWindow(IntPtr h);';"
        "[W.U]::SetForegroundWindow($p.MainWindowHandle)|Out-Null;"
        "Start-Sleep -Milliseconds 800;"
        "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
        "$img=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
        "$g=[System.Drawing.Graphics]::FromImage($img);"
        "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
        f"$img.Save('{SHOT}');"
        "Write-Output ('window_title=' + $p.MainWindowTitle)"
        "}else{Write-Output 'no_process'}"
    )
    shot_result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, timeout=120,
    )
    title_line = (shot_result.stdout or "").strip()
    check("窗口标题正常", "视频转换器" in title_line, title_line or "未取到标题")
    check("已截取运行截图", SHOT.is_file(), str(SHOT))

    # --windowed 打包的程序没有控制台，terminate() 发出的信号它收不到，
    # 进程会一直留着并锁住 dist 目录（下次打包就会 PermissionError）。所以直接 kill。
    proc.kill()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass
    # 按 PID 判定，而不是按镜像名查。
    # 按名字查会把机器上更早留下的同名残留误判成"自己没关干净"（实测踩过），
    # 而且 Windows 释放句柄不是瞬时的，所以轮询几次。
    leftover = True
    for _ in range(10):
        time.sleep(0.8)
        leftover = _pid_alive(proc.pid)
        if not leftover:
            break
    check("exe 已彻底关闭（不残留进程）", not leftover,
          f"PID {proc.pid} 仍存活" if leftover else "无残留")

    print(f"\n通过 {len(passed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：" + "、".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
