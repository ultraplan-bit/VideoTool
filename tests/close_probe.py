"""子进程探针：在后台线程还在跑时关窗，检查进程能否干净退出。

单独放一个文件是为了避开"在字符串里嵌多行代码"的转义麻烦。
由 tests/test_interaction.py 调用，也可以单独跑：
    uv run python tests/close_probe.py
退出码 0 表示干净退出；0xC0000409 之类表示 Qt 因线程未收干净而 abort。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from videotool import theme  # noqa: E402
from videotool.app import MainWindow  # noqa: E402
from videotool.ffmpeg import Tools  # noqa: E402


def main() -> int:
    app = QApplication([])
    app.setStyleSheet(theme.stylesheet())
    window = MainWindow(Tools.discover())
    window.quiet = True
    window.show()

    # 立刻加载文件：LoadWorker 还在跑
    sample = ROOT / "tests" / "samples" / "sample.mp4"
    if sample.is_file():
        window.load(str(sample))

    # 马上关窗，此时加载线程（以及可能的硬件探测线程）都还没结束
    QTimer.singleShot(60, window.close)
    QTimer.singleShot(4000, app.quit)
    app.exec()
    print("EXIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
