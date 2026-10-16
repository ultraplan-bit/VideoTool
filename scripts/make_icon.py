"""生成应用图标 assets/icon.ico。

用 PySide6 把 SVG 渲染成多档尺寸的 PNG，再按 ICO 容器格式打包。
ICO 允许直接内嵌 PNG（Vista 以后支持），所以不需要额外的图像库。
用法：uv run python scripts/make_icon.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icon.ico"

# 图标设计：圆角方块 + 白色播放三角 + 转换箭头。
# 16px 下细节会糊，所以主体只用大色块和粗线条。
SIZE = 256
SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3b82f6"/>
      <stop offset="1" stop-color="#1d4ed8"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="240" height="240" rx="54" fill="url(#bg)"/>
  <path d="M104 82 L104 174 L180 128 Z" fill="#ffffff"/>
  <path d="M60 110 A44 44 0 0 1 96 70"
        fill="none" stroke="#ffffff" stroke-width="13" stroke-linecap="round" opacity="0.85"/>
  <path d="M196 146 A44 44 0 0 1 160 186"
        fill="none" stroke="#ffffff" stroke-width="13" stroke-linecap="round" opacity="0.85"/>
  <path d="M96 62 L104 70 L96 78 Z" fill="#ffffff" opacity="0.85"/>
  <path d="M160 194 L152 186 L160 178 Z" fill="#ffffff" opacity="0.85"/>
</svg>
"""


def png_bytes(size: int) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(QByteArray(SVG.encode("utf-8")))
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()

    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def build_ico(images: list[tuple[int, bytes]]) -> bytes:
    """按 ICO 容器格式打包（每档尺寸内嵌一张 PNG）。"""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)      # reserved, type=icon, count
    offset = 6 + 16 * count
    entries, payloads = b"", b""
    for size, data in images:
        # 256 在 ICO 里用 0 表示
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset
        )
        payloads += data
        offset += len(data)
    return header + entries + payloads


def main() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [(size, png_bytes(size)) for size in sizes]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_ico(images))
    print(f"已生成 {OUT}（{len(sizes)} 档尺寸，{OUT.stat().st_size} 字节）")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
