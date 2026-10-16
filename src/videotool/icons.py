"""矢量图标。

用内联 SVG 路径 + QSvgRenderer 渲染，任意颜色和尺寸，不依赖图片资源，
也不需要额外的图标字体。命名参考 ui-ux-pro-max skill 的 icons.csv 语义规范。

每个图标按 24×24 网格绘制，线条统一 1.7px、圆角端点，保证视觉重量一致。
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

STROKE = 1.7

# 图标内容：name -> SVG 片段（viewBox 0 0 24 24）
ICONS: dict[str, str] = {
    # 导航
    "folder-open": (
        '<path d="M3 8V6.5A1.5 1.5 0 0 1 4.5 5h4l1.8 2h7.2A1.5 1.5 0 0 1 19 8.5V10"/>'
        '<path d="M2.8 10h18.4l-1.9 8.1A1.5 1.5 0 0 1 17.8 19H5.1a1.5 1.5 0 0 1-1.5-1.3z"/>'
    ),
    "film": (
        '<rect x="3" y="4.5" width="18" height="15" rx="1.5"/>'
        '<path d="M7.5 4.5v15M16.5 4.5v15M3 9.5h4.5M3 14.5h4.5M16.5 9.5H21M16.5 14.5H21"/>'
    ),
    "convert": (
        '<path d="M4 8h12"/><path d="M13 5l3 3-3 3"/>'
        '<path d="M20 16H8"/><path d="M11 13l-3 3 3 3"/>'
    ),
    "queue": (
        '<rect x="4" y="5" width="16" height="4" rx="1"/>'
        '<rect x="4" y="10.5" width="16" height="4" rx="1"/>'
        '<rect x="4" y="16" width="16" height="4" rx="1"/>'
    ),
    "settings": (
        '<path d="M4 7h16M4 12h16M4 17h16"/>'
        '<circle cx="9" cy="7" r="2.2"/><circle cx="15" cy="12" r="2.2"/><circle cx="7" cy="17" r="2.2"/>'
    ),
    "moon": '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2'
        'M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4"/>'
    ),
    "zap": '<path d="M13 3L5.5 13.5H11L10 21l7.5-10.5H12z"/>',
    "info": (
        '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/>'
        '<circle cx="12" cy="7.8" r="0.95" fill="currentColor" stroke="none"/>'
    ),
    # 操作
    "play": '<path d="M8 5.5l11 6.5-11 6.5z"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "trash": (
        '<path d="M4.5 7h15"/>'
        '<path d="M9.5 7V5.2A1.2 1.2 0 0 1 10.7 4h2.6a1.2 1.2 0 0 1 1.2 1.2V7"/>'
        '<path d="M6.5 7l.9 11.6A1.5 1.5 0 0 0 8.9 20h6.2a1.5 1.5 0 0 0 1.5-1.4L17.5 7"/>'
    ),
    "copy": (
        '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/>'
        '<path d="M15.5 5.5H6.5a2 2 0 0 0-2 2v9"/>'
    ),
    "open-external": (
        '<path d="M14 4h6v6"/><path d="M20 4l-8.5 8.5"/>'
        '<path d="M18 14.5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3.5"/>'
    ),
    "terminal": (
        '<rect x="3" y="4.5" width="18" height="15" rx="2"/>'
        '<path d="M7.5 9.5l3 2.5-3 2.5M13 15h4"/>'
    ),
    # 状态
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.8 2.8L16.5 9"/>',
    "warning": (
        '<path d="M12 4.5l8.5 14.5H3.5z"/><path d="M12 10v4"/>'
        '<circle cx="12" cy="16.6" r="0.95" fill="currentColor" stroke="none"/>'
    ),
    # 信息项
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.2 2"/>',
    "monitor": '<rect x="3" y="5" width="18" height="12.5" rx="2"/><path d="M9 20.5h6"/>',
    "music": (
        '<path d="M9 18V6.5l10-2V16"/>'
        '<circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>'
    ),
    "file": (
        '<path d="M13.5 4H7.5A1.5 1.5 0 0 0 6 5.5v13A1.5 1.5 0 0 0 7.5 20h9a1.5 1.5 0 0 0 1.5-1.5V8.5z"/>'
        '<path d="M13.5 4v4.5H18"/>'
    ),
    "gauge": '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/>',
    "save": (
        '<path d="M5 5.5A1.5 1.5 0 0 1 6.5 4h9L20 8.5v10a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 5 18.5z"/>'
        '<path d="M9 4v5h6V4"/><rect x="8.5" y="13" width="7" height="7" rx="1"/>'
    ),
}

_cache: dict[tuple[str, str, int], QIcon] = {}


def svg_markup(name: str, color: str, size: int) -> str:
    body = ICONS[name].replace("currentColor", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="{size}" height="{size}" fill="none" stroke="{color}" '
        f'stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )


def make_icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """生成指定颜色和尺寸的图标。结果按 (名称, 颜色, 尺寸) 缓存。"""
    color = color or theme.COLORS["muted"]
    key = (name, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    # 渲染时留出一点内边距，让图标在按钮里不贴边
    renderer = QSvgRenderer(QByteArray(svg_markup(name, color, size).encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()

    icon = QIcon(pixmap)
    _cache[key] = icon
    return icon


def make_pixmap(name: str, color: str | None = None, size: int = 18) -> QPixmap:
    return make_icon(name, color, size).pixmap(size, size)


def status_dot(color: str, size: int = 10) -> QPixmap:
    """状态圆点，用于表格里的状态列。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(Qt.NoBrush)
    from PySide6.QtGui import QColor, QPen

    pen = QPen(QColor(color))
    pen.setWidth(2)
    painter.setPen(pen)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.end()
    return pixmap
