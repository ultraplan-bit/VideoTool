"""在后台线程里跑 ffmpeg 转换，并解析进度。

进度来源：ffmpeg 的 `-progress pipe:1` 会持续往 stdout 打 key=value 行，
其中 out_time_us 是已处理到的微秒数，除以总时长即为百分比。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .ffmpeg import NO_WINDOW, Tools


class ConversionWorker(QThread):
    progress = Signal(float)   # 0.0 ~ 1.0
    log = Signal(str)          # 一行日志
    succeeded = Signal(str)    # 输出文件路径
    failed = Signal(str)       # 错误信息

    def __init__(
        self,
        tools: Tools,
        args: list[str],
        output: str,
        duration: float | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tools = tools
        self._args = args
        self._output = output
        self._duration = duration or 0.0
        self._process: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process and process.poll() is None:
            process.terminate()

    def run(self) -> None:
        # 批量入队时界面拿不到时长（文件还没被打开预览），这里补测一次。
        # 不做的话进度百分比算不出来，进度条会一直停在 0，直到结束才跳到 100%。
        if self._duration <= 0:
            self._duration = self._probe_duration() or 0.0

        command = [str(self._tools.ffmpeg), *self._args]
        self.log.emit("$ " + " ".join(command))
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=NO_WINDOW,
            )
        except OSError as exc:
            self.failed.emit(f"无法启动 ffmpeg：{exc}")
            return

        assert self._process.stdout is not None
        tail: list[str] = []
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            if "=" in line and not line.startswith(" "):
                key, _, value = line.partition("=")
                if key == "out_time_us" and self._duration > 0:
                    try:
                        done = int(value) / 1_000_000
                    except ValueError:
                        continue
                    self.progress.emit(min(done / self._duration, 1.0))
                continue
            # 其余是 ffmpeg 的普通输出，留最后几行用于报错
            tail.append(line)
            if len(tail) > 8:
                tail.pop(0)

        code = self._process.wait()
        self._process = None

        # 成功优先于取消：用户点取消的瞬间 ffmpeg 可能刚好跑完，
        # 这时输出是完好的成品，按"已取消"处理会把它删掉，用户白转一场。
        if code == 0 and Path(self._output).is_file():
            self.progress.emit(1.0)
            self.succeeded.emit(self._output)
        elif self._cancelled:
            self._discard_output()
            self.failed.emit("已取消")
        else:
            self._discard_output()
            detail = tail[-1] if tail else f"ffmpeg 退出码 {code}"
            self.failed.emit(f"转换失败：{detail}")

    def _probe_duration(self) -> float | None:
        """用 ffprobe 取源文件时长。失败返回 None，不影响转换本身。"""
        source = None
        for index, item in enumerate(self._args):
            if item == "-i" and index + 1 < len(self._args):
                source = self._args[index + 1]
                break
        if source is None:
            return None
        try:
            result = self._tools.run(
                ["-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", source],
                timeout=30,
                use_probe=True,
            )
        except Exception:
            return None
        try:
            value = float((result.stdout or "").strip())
        except ValueError:
            return None
        return value if value > 0 else None

    def _discard_output(self) -> None:
        """失败或取消时清掉半成品，避免留下坏文件。"""
        try:
            Path(self._output).unlink(missing_ok=True)
        except OSError:
            pass
