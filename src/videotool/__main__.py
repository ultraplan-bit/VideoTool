"""程序入口：uv run python -m videotool"""
import sys

from .app import run

if __name__ == "__main__":
    sys.exit(run())
