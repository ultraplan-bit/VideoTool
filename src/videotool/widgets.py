"""可复用控件：面板、指标卡、导航按钮、预览区、信息行。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme


class Panel(QFrame):
    """带标题的卡片面板。"""

    def __init__(self, title: str, icon: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(6)
        if icon:
            glyph = QLabel()
            glyph.setPixmap(icons.make_pixmap(icon, theme.COLORS["muted"], 14))
            glyph.setFixedSize(14, 14)
            glyph.setStyleSheet("background: transparent;")
            head.addWidget(glyph)
        label = QLabel(title.upper() if title.isascii() else title)
        label.setObjectName("panelTitle")
        head.addWidget(label)
        head.addStretch(1)
        self.head = head
        outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)
        self.outer = outer

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body.addLayout(layout, stretch)


class MetricCard(QFrame):
    """指标卡：一个大数字 + 一行小标签。用于时长、大小、码率。"""

    def __init__(self, label: str, value: str = "—", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metric")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.label_label = QLabel(label)
        self.label_label.setObjectName("metricLabel")
        layout.addWidget(self.value_label)
        layout.addWidget(self.label_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class InfoRow(QWidget):
    """一行「标签 —— 值」，值可选中复制。"""

    def __init__(self, label: str, label_width: int = 56, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        key = QLabel(label)
        key.setObjectName("fieldLabel")
        key.setFixedWidth(label_width)
        key.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.value = QLabel("—")
        self.value.setObjectName("fieldValue")
        self.value.setWordWrap(True)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(key)
        layout.addWidget(self.value, 1)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class NavButton(QPushButton):
    """左侧导航项。"""

    def __init__(self, text: str, icon: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._icon_name = icon
        self.refresh_icon()
        self.setIconSize(self.iconSize().scaled(16, 16, Qt.KeepAspectRatio))

    def refresh_icon(self) -> None:
        """按当前主题重新渲染图标。切主题后必须调用，否则图标颜色不会变。"""
        self.setIcon(icons.make_icon(self._icon_name, theme.COLORS["muted"], 16))


class PreviewArea(QLabel):
    """可拖入文件的预览区；没有图时显示提示文字。"""

    # 发出拖入的文件列表；空列表表示"用户点了预览区，请打开文件对话框"
    dropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("dropArea")
        self.setCursor(Qt.PointingHandCursor)
        self._pixmap: QPixmap | None = None
        self.set_hint()

    def set_hint(self, text: str = "把视频或音频拖到这里\n\n或点击打开文件") -> None:
        self._pixmap = None
        self.setPixmap(QPixmap())
        self.setText(text)

    def set_image(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.setText("")
        self._rescale()

    def _rescale(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        self.setPixmap(
            self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.dropped.emit([])


def icon_button(text: str, icon: str, color: str | None = None, primary: bool = False) -> QPushButton:
    """带图标的按钮。"""
    button = QPushButton(text)
    button.setIcon(icons.make_icon(icon, color, 16))
    button.setCursor(Qt.PointingHandCursor)
    if primary:
        button.setObjectName("primary")
    return button


def divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"background: {theme.SEMANTIC['border']}; max-height: 1px; border: none;")
    return line
