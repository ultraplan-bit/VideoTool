"""程序入口。

PyInstaller 会把入口文件当独立脚本执行，此时相对导入（from .app import run）会失败，
静态分析也无法跟进包内模块，导致 PySide6 收不进包里。
所以这里单独放一个用绝对导入的入口。
"""
import sys

from videotool.app import run

if __name__ == "__main__":
    sys.exit(run())
