"""主界面：企业级桌面客户端布局。

布局结构：
    ┌──────────┬────────────────────────────────────────┐
    │ 导航栏    │ 顶部工具条（页面标题 + 主操作）           │
    │ (侧栏)    ├────────────────────────────────────────┤
    │          │ 内容区（堆叠页面：转换 / 队列 / 设置 / 关于）│
    ├──────────┴────────────────────────────────────────┤
    │ 状态栏（ffmpeg 版本、队列统计、整体进度）              │
    └───────────────────────────────────────────────────┘

转换本身在后台线程跑，界面线程只负责渲染，所以队列执行时界面不卡。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons, presets as preset_mod, theme
from .ffmpeg import FFmpegNotFound, Tools, detect_hardware_encoder
from .jobs import Job, Queue, Status
from .probe import MediaInfo, read_info
from .thumbnail import grab
from .util import human_bitrate, human_duration, human_fps, human_size
from .widgets import InfoRow, MetricCard, NavButton, Panel, PreviewArea, icon_button
from .worker import ConversionWorker

MEDIA_FILTER = (
    "媒体文件 (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.wmv *.m4v *.ts *.mpg *.mpeg "
    "*.mp3 *.m4a *.aac *.flac *.wav *.ogg *.opus *.wma);;所有文件 (*)"
)
VIDEO_EXT = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mpg", ".mpeg",
}

COL_NAME, COL_PRESET, COL_OUTPUT, COL_STATUS, COL_PROGRESS = range(5)


def looks_black(data: bytes) -> bool:
    """判断一帧是否全黑：缩小后取平均亮度。用于否决黑帧缩略图。"""
    from PySide6.QtGui import QImage

    image = QImage.fromData(data)
    if image.isNull():
        return False
    small = image.scaled(32, 32, Qt.IgnoreAspectRatio, Qt.FastTransformation)
    total = 0
    for y in range(small.height()):
        for x in range(small.width()):
            color = small.pixelColor(x, y)
            total += (color.red() + color.green() + color.blue()) / 3
    return total / (small.width() * small.height() or 1) <= 16


class LoadWorker(QThread):
    """后台读取媒体信息并抓缩略图。"""

    loaded = Signal(object, object)   # MediaInfo, PNG bytes | None
    failed = Signal(str)

    def __init__(self, tools: Tools, path: str, parent=None) -> None:
        super().__init__(parent)
        self._tools = tools
        self._path = path

    @property
    def path(self) -> str:
        """本次读取的文件路径，供界面校验结果是否还是当前请求的那个。"""
        return self._path

    def run(self) -> None:
        try:
            info = read_info(self._tools, self._path)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        image = None
        if info.has_video:
            try:
                image = grab(
                    self._tools, self._path, info.duration,
                    accept=lambda data: not looks_black(data),
                ).data
            except Exception:
                image = None
        self.loaded.emit(info, image)


class HardwareProbe(QThread):
    """后台探测硬件编码器。

    探测要实际跑一次编码，会花一两秒，放主线程会让窗口启动时卡一下。
    """

    found = Signal(object)   # (编码器名, 友好名称) 或 None

    def __init__(self, tools: Tools, parent=None) -> None:
        super().__init__(parent)
        self._tools = tools

    def run(self) -> None:
        try:
            self.found.emit(detect_hardware_encoder(self._tools))
        except Exception:
            self.found.emit(None)


class MainWindow(QMainWindow):
    def __init__(self, tools: Tools) -> None:
        super().__init__()
        self.tools = tools
        self.info: MediaInfo | None = None
        self.queue = Queue()
        self.worker: ConversionWorker | None = None
        self.loader: LoadWorker | None = None
        # 自动化测试设为 True，抑制模态提示框（离屏环境没人点确认，会挂住）
        self.quiet = False
        # 记住上次用的预设/画质/主题/硬件开关，省得每次重设
        self.settings = QSettings("VideoTool", "VideoTool")
        self.hw_encoder: tuple[str, str] | None = None
        self.hw_enabled = False
        self.running = False        # 转换进行中：相关设置项要禁用
        self.probe: HardwareProbe | None = None
        self.last_output_dir: str = ""

        self.setWindowTitle("VideoTool — 视频转换器")
        self.resize(1180, 780)
        self.setMinimumSize(940, 620)
        self._build_ui()
        self._build_menu()
        self._build_shortcuts()
        self._restore_settings()
        self._refresh_status()
        self._refresh_queue_table()
        self._start_hardware_probe()

    # ==================== 界面搭建 ====================

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_main(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(186)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand = QLabel("VideoTool")
        brand.setObjectName("brand")
        sub = QLabel("ffmpeg 视频转换")
        sub.setObjectName("brandSub")
        layout.addWidget(brand)
        layout.addWidget(sub)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.pages = QStackedWidget()

        items = [
            ("转换", "convert", self._page_convert),
            ("队列", "queue", self._page_queue),
            ("设置", "settings", self._page_settings),
            ("关于", "info", self._page_about),
        ]
        for index, (text, icon, builder) in enumerate(items):
            button = NavButton(text, icon)
            button.clicked.connect(lambda _checked=False, i=index: self._switch_page(i))
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
            self.pages.addWidget(builder())

        layout.addStretch(1)
        self.nav_group.button(0).setChecked(True)
        return bar

    def _build_main(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self.pages, 1)
        return container

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(58)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = QLabel("转换")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("")
        self.page_subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.add_button = icon_button("添加文件", "folder-open")
        self.add_button.clicked.connect(self.open_dialog)
        self.start_button = icon_button("开始转换", "play", theme.PRIMITIVE["white"], primary=True)
        self.start_button.clicked.connect(self.on_start)
        self.start_button.setEnabled(False)
        self.cancel_button = icon_button("停止", "stop")
        self.cancel_button.clicked.connect(self.on_cancel)
        self.cancel_button.setEnabled(False)

        self.theme_button = icon_button("深色", "moon")
        self.theme_button.setToolTip("切换深色 / 浅色主题")
        self.theme_button.clicked.connect(self.on_toggle_theme)

        for button in (self.add_button, self.cancel_button, self.start_button):
            layout.addWidget(button)
        layout.addWidget(self.theme_button)
        return bar

    # ---------- 页面 1：转换 ----------

    def _page_convert(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        # 左列：预览 + 指标
        left = QVBoxLayout()
        left.setSpacing(12)
        preview_panel = Panel("预览", "film")
        self.preview = PreviewArea()
        self.preview.dropped.connect(self.on_dropped)
        preview_panel.add(self.preview, 1)
        left.addWidget(preview_panel, 1)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.metric_duration = MetricCard("时长")
        self.metric_size = MetricCard("文件大小")
        self.metric_bitrate = MetricCard("总码率")
        for card in (self.metric_duration, self.metric_size, self.metric_bitrate):
            metrics.addWidget(card)
        left.addLayout(metrics)
        columns.addLayout(left, 3)

        # 右列：媒体信息 + 输出设置
        right = QVBoxLayout()
        right.setSpacing(12)

        info_panel = Panel("媒体信息", "info")
        self.info_rows: dict[str, InfoRow] = {}
        for key, label in (
            ("file", "文件"), ("container", "容器"), ("video", "视频"),
            ("fps", "帧率"), ("audio", "音频"), ("streams", "流"),
        ):
            row = InfoRow(label)
            self.info_rows[key] = row
            info_panel.add(row)
        info_panel.body.addStretch(1)
        right.addWidget(info_panel)

        out_panel = Panel("输出设置", "settings")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        self.preset_box = QComboBox()
        for preset in preset_mod.PRESETS:
            self.preset_box.addItem(preset.label, preset.key)
        self.preset_box.currentIndexChanged.connect(self.on_preset_changed)
        self.preset_hint = QLabel()
        self.preset_hint.setObjectName("fieldLabel")
        self.preset_hint.setWordWrap(True)

        self.quality_box = QComboBox()
        self.quality_box.currentIndexChanged.connect(self._on_quality_changed)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("选择输出位置")
        self.output_edited = False
        self.output_edit.textEdited.connect(self._mark_output_edited)
        browse = icon_button("浏览", "folder-open")

        def on_browse() -> None:
            self.on_browse_output()

        browse.clicked.connect(on_browse)

        grid.addWidget(self._label("转换预设"), 0, 0)
        grid.addWidget(self.preset_box, 0, 1)
        grid.addWidget(self._label("画质"), 0, 2)
        grid.addWidget(self.quality_box, 0, 3)
        grid.addWidget(self.preset_hint, 1, 1, 1, 3)
        grid.addWidget(self._label("输出到"), 2, 0)
        grid.addWidget(self.output_edit, 2, 1, 1, 2)
        grid.addWidget(browse, 2, 3)

        self.hw_check = QCheckBox("硬件加速编码")
        self.hw_check.setToolTip("用显卡编码，速度快很多；未探测到可用显卡时不可选")
        self.hw_check.setEnabled(False)   # 探测到可用编码器后 on_hardware_found 会放开
        self.hw_check.toggled.connect(self.on_hardware_toggled)
        self.hw_label = QLabel("正在检测显卡…")
        self.hw_label.setObjectName("fieldLabel")
        grid.addWidget(self.hw_check, 3, 1)
        grid.addWidget(self.hw_label, 3, 2, 1, 2)
        out_panel.add_layout(grid)
        right.addWidget(out_panel)
        right.addStretch(1)
        columns.addLayout(right, 2)

        outer.addLayout(columns, 1)

        # 日志
        log_panel = Panel("日志", "terminal")
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(600)
        self.log_view.setFixedHeight(112)
        log_panel.add(self.log_view)
        outer.addWidget(log_panel)

        self.on_preset_changed()
        return page

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    # ---------- 页面 2：队列 ----------

    def _page_queue(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        panel = Panel("转换队列", "queue")
        self.queue_table = QTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(
            ["文件", "预设", "输出位置", "状态", "进度"]
        )
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.queue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        self.queue_table.setShowGrid(False)
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_PRESET, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_OUTPUT, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_PROGRESS, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(COL_PROGRESS, 120)
        panel.add(self.queue_table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        remove = icon_button("移除选中", "trash", theme.COLORS["danger"])
        remove.clicked.connect(self.on_remove_selected)
        clear = icon_button("清空已结束", "x")
        clear.clicked.connect(self.on_clear_finished)
        self.queue_summary = QLabel()
        self.queue_summary.setObjectName("fieldLabel")
        actions.addWidget(remove)
        actions.addWidget(clear)
        actions.addStretch(1)
        actions.addWidget(self.queue_summary)
        panel.add_layout(actions)

        outer.addWidget(panel, 1)
        return page

    # ---------- 页面 3：设置 ----------

    def _page_settings(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        look_panel = Panel("外观", "settings")
        look_grid = QGridLayout()
        look_grid.setHorizontalSpacing(10)
        look_grid.setColumnStretch(1, 1)
        self.theme_box = QComboBox()
        for key in ("dark", "light"):
            self.theme_box.addItem(theme.MODE_LABELS[key], key)
        self.theme_box.setCurrentIndex(0 if theme.is_dark() else 1)
        self.theme_box.currentIndexChanged.connect(self.on_theme_selected)
        look_grid.addWidget(self._label("主题"), 0, 0)
        look_grid.addWidget(self.theme_box, 0, 1)
        look_panel.add_layout(look_grid)
        outer.addWidget(look_panel)

        hw_panel = Panel("硬件加速", "gauge")
        self.hw_detail = QLabel("正在检测…")
        self.hw_detail.setObjectName("fieldValue")
        self.hw_detail.setWordWrap(True)
        hw_panel.add(self.hw_detail)
        hw_note = QLabel(
            "硬件编码（NVENC / Quick Sync / AMF）比软件编码快数倍，"
            "但同码率下画质略逊于 libx264。对速度和画质都敏感时建议先小段试转。"
        )
        hw_note.setObjectName("fieldLabel")
        hw_note.setWordWrap(True)
        hw_panel.add(hw_note)
        outer.addWidget(hw_panel)

        ff_panel = Panel("ffmpeg 运行时", "terminal")
        self.ffmpeg_rows = {}
        for key, label in (("ffmpeg", "ffmpeg"), ("ffprobe", "ffprobe"), ("version", "版本")):
            row = InfoRow(label, label_width=68)
            row.set_value({
                "ffmpeg": str(self.tools.ffmpeg),
                "ffprobe": str(self.tools.ffprobe),
                "version": self.tools.version or "未知",
            }[key])
            self.ffmpeg_rows[key] = row
            ff_panel.add(row)
        ff_panel.body.addStretch(1)
        outer.addWidget(ff_panel)

        hint_panel = Panel("查找顺序", "info")
        hint = QLabel(
            "程序按以下顺序查找 ffmpeg，第一个找到的生效：\n\n"
            "  1. 随程序打包的 ffmpeg/bin/（发布版走这条）\n"
            "  2. PyInstaller 解包目录\n"
            "  3. 系统 PATH\n"
            "  4. Windows 常见安装路径（C:\\ffmpeg\\bin 等）\n\n"
            "都找不到时会弹窗提示，而不是崩溃。"
        )
        hint.setObjectName("fieldValue")
        hint.setWordWrap(True)
        hint_panel.add(hint)
        outer.addWidget(hint_panel)
        outer.addStretch(1)
        return page

    # ---------- 页面 4：关于 ----------

    def _page_about(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        panel = Panel("关于 VideoTool", "info")
        body = QLabel(
            "<p style='font-size:15px; font-weight:600;'>VideoTool</p>"
            "<p>一个基于 ffmpeg 命令行的视频格式转换工具。</p>"
            "<p style='color:#8e99b3;'>界面：Python + PySide6（Qt Widgets）<br>"
            "转换：调用 ffmpeg 命令行，不链接其库<br>"
            "打包：PyInstaller（onedir）</p>"
            "<p style='color:#8e99b3;'>内置 ffmpeg 为 BtbN 的 GPL 构建，"
            "按 GPL 要求随程序提供许可证全文，见 vendor/ffmpeg/LICENSE.txt。</p>"
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        panel.add(body)
        outer.addWidget(panel)
        outer.addStretch(1)
        return page

    # ==================== 菜单与快捷键 ====================

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        for text, shortcut, slot in (
            ("打开文件…", QKeySequence.Open, self.open_dialog),
            # 这一项只往队列里加，不改变当前预览，和"打开文件"是两件事。
            # 之前两项连的是同一个函数，等于同一个操作放了两个菜单项。
            ("添加文件到队列…", "Ctrl+Shift+O", self.add_files_to_queue),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        about = QAction("关于", self)
        about.triggered.connect(lambda: self._switch_page(3))
        help_menu.addAction(about)

    def _build_shortcuts(self) -> None:
        for key, slot in (
            ("Ctrl+R", self.on_start),
            ("Delete", self.on_remove_selected),
            ("Escape", self.on_cancel),
        ):
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

    def _switch_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        button = self.nav_group.button(index)
        if button:
            button.setChecked(True)
        titles = {
            0: ("转换", "加载媒体文件，选择预设后开始转换"),
            1: ("队列", "查看和管理转换任务"),
            2: ("设置", "ffmpeg 运行时信息"),
            3: ("关于", "版本与许可证"),
        }
        title, subtitle = titles.get(index, ("转换", ""))
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)

    # ==================== 加载文件 ====================

    def open_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "打开媒体文件", "", MEDIA_FILTER)
        if paths:
            self.accept_files(list(paths))

    def on_dropped(self, paths: list[str]) -> None:
        if paths:
            self.accept_files(paths)
        else:
            self.open_dialog()

    def accept_files(self, paths: list[str]) -> None:
        """统一处理选中的文件：第一个加载到预览，其余直接进队列。

        这样一次拖多个文件时行为是可预期的——用户看到第一个的详情，
        其余的排队等着，不用再手动一个个加。
        """
        valid = [p for p in paths if Path(p).is_file()]
        skipped = len(paths) - len(valid)
        if skipped:
            self.log(f"跳过 {skipped} 个不存在的路径")
        if not valid:
            if skipped:
                self.warn("打不开", "选中的文件都不存在。")
            return
        self.load(valid[0])
        for path in valid[1:]:
            self.enqueue(path)
        if len(valid) > 1:
            self.log(f"另有 {len(valid) - 1} 个文件已加入队列")

    def load(self, path: str) -> None:
        if not Path(path).is_file():
            self.warn("打不开", "文件不存在：" + chr(10) + path)
            return
        self.info = None
        self.start_button.setEnabled(False)
        self.output_edited = False
        self.preview.set_hint("正在读取…")
        self._fill_info(None)
        self.log(f"读取 {path}")

        loader = LoadWorker(self.tools, path, self)
        self.loader = loader
        loader.loaded.connect(lambda info, image, w=loader: self.on_loaded(w, info, image))
        loader.failed.connect(lambda message, w=loader: self.on_load_failed(w, message))
        loader.start()

    def on_loaded(self, worker: "LoadWorker", info: MediaInfo, image: bytes | None) -> None:
        # 用户可能连续打开多个文件，只有最后那个请求的结果才算数。
        # 不校验的话，先打开的大文件读得慢、结果后到，会把后打开的文件信息覆盖掉。
        if worker is not self.loader:
            self.log(f"忽略过期结果：{Path(info.path).name}")
            return
        self.info = info
        self._fill_info(info)
        if image:
            pixmap = QPixmap()
            if pixmap.loadFromData(image):
                self.preview.set_image(pixmap)
            else:
                self.preview.set_hint("缩略图解析失败")
        else:
            self.preview.set_hint("无法生成缩略图")
        self._sync_output_name()
        self.start_button.setEnabled(True)
        self.log(f"就绪：{Path(info.path).name}")

    def on_load_failed(self, worker: "LoadWorker", message: str) -> None:
        if worker is not self.loader:
            self.log(f"忽略过期错误：{message}")
            return
        self.preview.set_hint("读取失败")
        self.start_button.setEnabled(False)
        self.warn("读取失败", message)

    def _fill_info(self, info: MediaInfo | None) -> None:
        if info is None:
            for row in self.info_rows.values():
                row.set_value("—")
            for card in (self.metric_duration, self.metric_size, self.metric_bitrate):
                card.set_value("—")
            return
        video, audio = info.video, info.audio
        values = {
            "file": Path(info.path).name,
            "container": info.container,
            "video": f"{video.codec} · {video.detail}" if video else "无",
            "fps": human_fps((video.raw if video else {}).get("avg_frame_rate")),
            "audio": f"{audio.codec} · {audio.detail}" if audio else "无",
            "streams": f"{len(info.streams)} 条（{len([s for s in info.streams if s.kind == 'video'])} 视频 / "
                       f"{len([s for s in info.streams if s.kind == 'audio'])} 音频 / "
                       f"{len([s for s in info.streams if s.kind == 'subtitle'])} 字幕）",
        }
        for key, value in values.items():
            self.info_rows[key].set_value(value)
        self.metric_duration.set_value(human_duration(info.duration))
        self.metric_size.set_value(human_size(info.size))
        self.metric_bitrate.set_value(human_bitrate(info.bitrate))

    # ==================== 输出设置 ====================

    def current_preset(self) -> preset_mod.Preset:
        return preset_mod.BY_KEY[self.preset_box.currentData()]

    def on_preset_changed(self) -> None:
        preset = self.current_preset()
        self.preset_hint.setText(preset.summary)
        self.quality_box.blockSignals(True)
        self.quality_box.clear()
        self.quality_box.addItems(preset.quality_choices)
        if preset.default_quality:
            self.quality_box.setCurrentText(preset.default_quality)
        self.quality_box.blockSignals(False)
        self.quality_box.setEnabled(bool(preset.quality_choices))
        self._sync_hardware_availability()
        self._sync_output_name()
        if hasattr(self, "settings"):
            self._save_settings()

    def _mark_output_edited(self) -> None:
        self.output_edited = True

    def _on_quality_changed(self) -> None:
        """画质或预设变了就记下来，下次打开还是这套设置。"""
        self._sync_output_name()
        self._save_settings()

    def _sync_output_name(self) -> None:
        """推导输出路径。

        用户手动改过路径时保留他选的名字和目录，但**扩展名始终对齐当前预设**——
        否则改了预设扩展名不跟着变，会把 VP9 数据写进 .mp4 容器，
        产出的文件容器和命名都不对。
        """
        if not self.info:
            return
        preset = self.current_preset()
        current = self.output_edit.text().strip()
        if self.output_edited and current:
            target = Path(current).with_suffix(preset.suffix)
            if str(target) != current:
                self.output_edit.setText(str(target))
            return

        source = Path(self.info.path)
        target = source.with_suffix(preset.suffix)
        if target == source:
            # 预设后缀与源文件相同时加后缀，避免一上手就覆盖原文件
            target = source.with_name(f"{source.stem}_converted{target.suffix}")
        self.output_edit.setText(str(target))

    def on_browse_output(self) -> None:
        preset = self.current_preset()
        if self.info:
            suggested = self.output_edit.text() or str(
                Path(self.info.path).with_suffix(preset.suffix)
            )
        else:
            suggested = self.output_edit.text()
        path, _ = QFileDialog.getSaveFileName(
            self, "保存为", suggested, f"{preset.label} (*{preset.suffix});;所有文件 (*)"
        )
        if path:
            self.output_edit.setText(path)
            self.output_edited = True
            self.last_output_dir = str(Path(path).parent)
            self._save_settings()

    # ==================== 队列操作 ====================

    def enqueue(self, source: str, duration: float | None = None) -> Job | None:
        """把一个文件加入队列。预览已加载的文件复用它的信息。"""
        preset = self.current_preset()
        quality = self.quality_box.currentText() if preset.quality_choices else ""
        source_path = Path(source)
        if source_path.suffix.lower() not in VIDEO_EXT and preset.needs_video:
            self.log(f"跳过 {source_path.name}：预设「{preset.label}」需要视频轨")
            return None

        if self.info and Path(self.info.path) == source_path and self.output_edit.text():
            output = self.output_edit.text().strip()
        else:
            target = source_path.with_suffix(preset.suffix)
            if target == source_path:
                target = source_path.with_name(f"{source_path.stem}_converted{target.suffix}")
            output = str(target)

        if not output:
            return None
        if self.queue.output_taken(output):
            output = str(Path(output).with_name(f"{Path(output).stem}_{len(self.queue) + 1}"
                                                f"{Path(output).suffix}"))

        job = Job(
            source=str(source_path),
            preset_key=preset.key,
            preset_label=preset.label,
            quality=quality,
            output=output,
            encoder=self.current_encoder(),
            duration=duration if duration is not None else (self.info.duration if self.info else None),
        )
        self.queue.add(job)
        self._refresh_queue_table()
        self.log(f"加入队列：{job.name} → {Path(output).name}")
        return job

    def add_files_to_queue(self) -> None:
        """选文件直接入队，不改变当前预览。

        和「打开文件」的区别：那个会把第一个文件加载到预览区，
        这个纯粹往队列里加，适合已经预览着一个文件、想再排几个进去的场景。
        """
        paths, _ = QFileDialog.getOpenFileNames(
            self, "添加文件到队列", self.last_output_dir or "", MEDIA_FILTER
        )
        if not paths:
            return
        added = 0
        for path in paths:
            if not Path(path).is_file():
                self.log(f"跳过不存在的路径：{path}")
                continue
            if self.enqueue(path):
                added += 1
        if added:
            self.notify("已加入队列", f"新增 {added} 个文件到转换队列。")
            self._switch_page(1)
    def on_remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.queue_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        refused = 0
        for row in rows:
            if 0 <= row < len(self.queue.jobs):
                job = self.queue.jobs[row]
                if job.status is Status.RUNNING:
                    refused += 1
                    continue
                self.queue.remove(job)
        if refused:
            # 静默无反应会让用户以为按钮坏了，说明为什么删不掉
            self.notify("无法移除", f"{refused} 个任务正在转换中，要等它结束或先点「停止」。")
        self._refresh_queue_table()

    def on_clear_finished(self) -> None:
        removed = self.queue.clear_finished()
        if removed:
            self.log(f"清除了 {removed} 条已结束的作业")
        self._refresh_queue_table()

    def _refresh_queue_table(self) -> None:
        table = self.queue_table
        table.setRowCount(len(self.queue.jobs))
        for row, job in enumerate(self.queue.jobs):
            name = QTableWidgetItem(job.name)
            name.setToolTip(job.source)
            table.setItem(row, COL_NAME, name)
            table.setItem(row, COL_PRESET, QTableWidgetItem(job.preset_label.split("（")[0]))

            output = QTableWidgetItem(Path(job.output).name)
            output.setToolTip(job.output)
            table.setItem(row, COL_OUTPUT, output)

            status = QTableWidgetItem(job.status.value)
            colors = {
                Status.DONE: theme.COLORS["success"],
                Status.FAILED: theme.COLORS["danger"],
                Status.RUNNING: theme.COLORS["accent"],
                Status.PENDING: theme.COLORS["muted"],
                Status.CANCELLED: theme.COLORS["muted"],
            }
            status.setIcon(icons.make_icon("check-circle", colors[job.status], 14)
                           if job.status is Status.DONE else
                           icons.make_icon("warning", colors[job.status], 14)
                           if job.status is Status.FAILED else
                           icons.make_icon("clock", colors[job.status], 14))
            if job.message:
                status.setToolTip(job.message)
            table.setItem(row, COL_STATUS, status)

            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(int(job.progress * 1000))
            bar.setTextVisible(False)
            table.setCellWidget(row, COL_PROGRESS, bar)

        counts = self.queue.counts
        self.queue_summary.setText(
            f"共 {counts['total']} 项 · 完成 {counts['done']} · 失败 {counts['failed']} · 待处理 {counts['pending']}"
        )
        self._refresh_status()

    def _refresh_status(self) -> None:
        counts = self.queue.counts
        parts = [f"ffmpeg {self.tools.version or '未知'}"]
        if counts["total"]:
            parts.append(f"队列 {counts['done']}/{counts['total']}")
            if counts["failed"]:
                parts.append(f"失败 {counts['failed']}")
        self.statusBar().showMessage("　·　".join(parts))

    # ==================== 转换执行 ====================

    def on_start(self) -> None:
        """开始转换。

        判断依据是「有没有待处理任务」，而不是「队列是否为空」。
        上一轮转换结束后队列里留着已完成的记录，若按队列是否为空来判断，
        用户改了设置再点开始就会被告知"任务都已结束"，没法重来。
        """
        if self.worker:
            # 取消后 worker 需要一点时间才真正退出，这期间再点开始会被忽略。
            # 静默返回会让用户以为快捷键失灵，所以给个提示。
            self.log("上一个任务还在收尾，请稍候再试")
            return

        pending = [j for j in self.queue.jobs if j.status is Status.PENDING]
        if not pending:
            # 队列里没有待处理的：把当前预览的文件按当前设置入队，实现"改设置后重来一遍"
            if self.info:
                job = self.enqueue(self.info.path, self.info.duration)
                if job:
                    self.log(f"按当前设置重新入队：{job.name}")
                pending = [j for j in self.queue.jobs if j.status is Status.PENDING]
            if not pending:
                self.notify(
                    "没有待处理任务",
                    "队列里的任务都已结束。" + chr(10) * 2
                    + "请打开要转换的文件，或切换预设后再点开始。",
                )
                return

        if not self._confirm_overwrite(pending):
            return

        self.queue.cancelled = False
        self._set_running(True)
        self.log_view.clear()
        self._run_next()

    @staticmethod
    def _existing_outputs(pending: list[Job]) -> list[Job]:
        """挑出输出文件已经存在的作业。抽出来是为了能单独测，不用弹对话框。"""
        return [j for j in pending if Path(j.output).exists()]

    def _confirm_overwrite(self, pending: list[Job]) -> bool:
        """输出文件已存在时先问一次。返回 False 表示用户取消了这次转换。

        批量场景下逐条询问很烦，所以合并成一次提示，并提供"跳过已存在"，
        便于中断后续跑（已转好的不用重来）。
        """
        existing = self._existing_outputs(pending)
        if not existing or self.quiet:
            return True

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("输出文件已存在")
        listed = "\n".join(f"  · {Path(j.output).name}" for j in existing[:8])
        more = f"\n  …共 {len(existing)} 个" if len(existing) > 8 else ""
        box.setText(
            "以下输出文件已存在：" + chr(10) * 2 + listed + more
            + chr(10) * 2 + "要继续吗？"
        )
        overwrite = box.addButton("覆盖", QMessageBox.DestructiveRole)
        skip = box.addButton("跳过已存在", QMessageBox.ActionRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is overwrite:
            return True
        if clicked is skip:
            for job in existing:
                job.status = Status.CANCELLED
                job.message = "输出文件已存在，已跳过"
            self._refresh_queue_table()
            remaining = [j for j in pending if j.status is Status.PENDING]
            if not remaining:
                self.log("待处理的输出文件都已存在，没有需要转换的任务")
                return False
            return True
        self.log("已取消")
        return False

    def _run_next(self) -> None:
        job = self.queue.next_pending()
        if job is None:
            self._finish_queue()
            return

        # 转换前先做检查。这些情况让 ffmpeg 自己报错的话，用户看到的是一串
        # "Error opening output files"，看不出该怎么办。
        problem = self._precheck(job)
        if problem:
            job.status = Status.FAILED
            job.message = problem
            self.log(f"跳过（{job.name}）：{problem}")
            self._refresh_queue_table()
            self._run_next()
            return

        preset = preset_mod.BY_KEY[job.preset_key]
        args = preset_mod.build_args(
            preset, job.source, job.output, job.quality, job.encoder
        )
        job.status = Status.RUNNING
        job.progress = 0.0
        self.queue.current = job
        self._refresh_queue_table()

        self.worker = ConversionWorker(
            self.tools, args, job.output, job.duration, self
        )
        self.worker.progress.connect(lambda value, j=job: self._on_job_progress(j, value))
        self.worker.log.connect(self.log)
        self.worker.succeeded.connect(lambda path, j=job: self._on_job_done(j, path))
        self.worker.failed.connect(lambda message, j=job: self._on_job_failed(j, message))
        self.worker.start()

    @staticmethod
    def _precheck(job: Job) -> str:
        """转换前的检查，返回空串表示可以开始。

        覆盖三类常见问题：源文件没了（入队后被删/移走）、输出目录不存在、
        输出路径指向一个目录。
        """
        source = Path(job.source)
        if not source.is_file():
            return f"源文件不存在：{source}"

        target = Path(job.output)
        if target.is_dir():
            return f"输出路径是一个目录：{target}"

        parent = target.parent
        if not parent.exists():
            # 输出目录不存在就建出来。用户手填路径时经常遇到，
            # 不该让他在资源管理器里先手动建好目录。
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return f"无法创建输出目录 {parent}：{exc}"
        return ""

    def _on_job_progress(self, job: Job, value: float) -> None:
        job.progress = value
        row = self._row_of(job)
        if row is not None:
            widget = self.queue_table.cellWidget(row, COL_PROGRESS)
            if isinstance(widget, QProgressBar):
                widget.setValue(int(value * 1000))
        self._refresh_status()

    def _on_job_done(self, job: Job, path: str) -> None:
        job.status = Status.DONE
        job.progress = 1.0
        job.message = path
        self.log(f"完成：{path}")
        self.worker = None
        self._refresh_queue_table()
        self._run_next()

    def _on_job_failed(self, job: Job, message: str) -> None:
        job.status = Status.CANCELLED if message == "已取消" else Status.FAILED
        job.message = message
        self.log(f"错误（{job.name}）：{message}")
        self.worker = None
        self._refresh_queue_table()
        if self.queue.cancelled:
            self._finish_queue()
        else:
            self._run_next()

    def _finish_queue(self) -> None:
        self.queue.mark_cancelled_pending()
        self.queue.current = None
        self._set_running(False)
        self._refresh_queue_table()

        counts = self.queue.counts
        if self.queue.cancelled:
            self.statusBar().showMessage("已取消")
            return
        self.statusBar().showMessage(
            f"全部结束：成功 {counts['done']}，失败 {counts['failed']}"
        )
        if self.quiet:
            return
        done_jobs = [j for j in self.queue.jobs if j.status is Status.DONE]
        if counts["failed"]:
            title = "部分任务失败"
            text = ("成功 " + str(counts["done"]) + " 项，失败 "
                    + str(counts["failed"]) + " 项。详情见队列页和日志。")
            icon = QMessageBox.Warning
        else:
            title = "全部完成"
            text = "已成功转换 " + str(counts["done"]) + " 个文件。"
            icon = QMessageBox.Information
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        open_button = box.addButton("打开输出目录", QMessageBox.ActionRole)
        box.addButton("知道了", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() is open_button and done_jobs:
            self.on_open_output_dir(done_jobs[-1].output)

    def on_cancel(self) -> None:
        if not self.worker:
            return
        self.queue.cancelled = True
        self.worker.cancel()
        self.log("已请求取消…")

    def _row_of(self, job: Job) -> int | None:
        try:
            return self.queue.jobs.index(job)
        except ValueError:
            return None

    def _set_running(self, running: bool) -> None:
        self.running = running
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.add_button.setEnabled(not running)
        for widget in (self.preset_box, self.output_edit):
            widget.setEnabled(not running)
        self.quality_box.setEnabled(
            not running and bool(self.current_preset().quality_choices)
        )
        # 硬件勾选框也要跟着禁用，否则转换中改了它，界面上显示的状态
        # 和正在跑的作业用的编码器就对不上了
        self._sync_hardware_availability()

    # ==================== 主题 ====================

    def on_toggle_theme(self) -> None:
        self.apply_theme("light" if theme.is_dark() else "dark")

    def on_theme_selected(self, _index: int) -> None:
        self.apply_theme(self.theme_box.currentData())

    def apply_theme(self, mode: str) -> None:
        """切换主题并刷新所有依赖颜色的部件。

        样式表能自动生效，但图标和状态点是我们自己渲染成固定颜色的位图，
        换主题后必须重建，否则浅色主题下会出现深色主题的浅色图标。
        """
        theme.set_mode(mode)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(theme.stylesheet())

        self.theme_button.setText(theme.MODE_LABELS[mode])
        self.theme_button.setIcon(
            icons.make_icon("moon" if mode == "dark" else "sun",
                            theme.COLORS["muted"], 16)
        )
        # 设置页的下拉框也要跟着走。不同步的话，工具栏切到浅色后下拉仍显示"深色"，
        # 用户再去点"深色"时 index 没变化、信号不触发，看起来像点了没反应。
        if hasattr(self, "theme_box"):
            self.theme_box.blockSignals(True)
            index = self.theme_box.findData(mode)
            if index >= 0:
                self.theme_box.setCurrentIndex(index)
            self.theme_box.blockSignals(False)
        # 导航图标、按钮图标都要跟着换色
        for index in range(self.nav_group.buttons().__len__()):
            button = self.nav_group.button(index)
            if isinstance(button, NavButton):
                button.refresh_icon()
        self.add_button.setIcon(icons.make_icon("folder-open", theme.COLORS["muted"], 16))
        self.cancel_button.setIcon(icons.make_icon("stop", theme.COLORS["muted"], 16))
        self._refresh_queue_table()
        self._refresh_status()
        self._save_settings()

    # ==================== 硬件加速 ====================

    def _start_hardware_probe(self) -> None:
        self.probe = HardwareProbe(self.tools, self)
        self.probe.found.connect(self.on_hardware_found)
        self.probe.start()

    def on_hardware_found(self, result: object) -> None:
        self.hw_encoder = result if isinstance(result, tuple) else None
        if self.hw_encoder:
            name, label = self.hw_encoder
            self.hw_detail.setText(f"检测到可用的硬件编码器：<b>{label}</b>（{name}）")
            self.hw_check.setChecked(bool(self.settings.value("hardware", False)))
            self._sync_hardware_availability()
        else:
            self.hw_detail.setText(
                "没有检测到可用的硬件编码器，将使用软件编码（libx264）。" + chr(10) * 2
                + "只检查 ffmpeg 支持哪些编码器是不够的——机器没有对应显卡时，"
                + "编码器会列出却无法初始化，所以这里实际跑了一次极短编码来确认。"
            )
            self._sync_hardware_availability()
        self.hw_check.toggled.connect(self._save_hardware_setting)

    def _save_hardware_setting(self, _checked: bool) -> None:
        self._save_settings()

    def on_hardware_toggled(self, checked: bool) -> None:
        self.hw_enabled = checked
        if checked and self.hw_encoder:
            self.log(f"已启用硬件加速：{self.hw_encoder[1]}")
        elif not checked:
            self.log("已切回软件编码")

    def _sync_hardware_availability(self) -> None:
        """只有支持硬件编码的预设才放开勾选框。

        WebM 容器不接受 H.264，GIF/音频/换壳预设不编码视频，
        对这些预设放开只会让用户撞上 ffmpeg 报错。
        """
        preset = self.current_preset()
        usable = self.hw_encoder is not None and preset.hardware_ok and not self.running
        self.hw_check.setEnabled(usable)
        if not usable:
            if self.hw_encoder and preset.hardware_ok and self.running:
                # 运行中只是暂时不可改，勾选状态保留
                self.hw_label.setText("转换进行中，结束后可修改")
            else:
                if self.hw_check.isChecked():
                    self.hw_check.setChecked(False)
                if self.hw_encoder and not preset.hardware_ok:
                    self.hw_label.setText("当前预设不使用 H.264，无法硬件加速")
                elif not self.hw_encoder:
                    self.hw_label.setText("未检测到可用的硬件编码器")
        elif self.hw_encoder:
            self.hw_label.setText(f"可用：{self.hw_encoder[1]}（{self.hw_encoder[0]}）")

    def current_encoder(self) -> str | None:
        """当前该用的编码器：勾了硬件且确实可用才返回硬件编码器。"""
        if self.hw_enabled and self.hw_encoder:
            return self.hw_encoder[0]
        return None

    # ==================== 设置记忆 ====================

    def _restore_settings(self) -> None:
        """恢复上次的预设、画质、主题。"""
        mode = str(self.settings.value("theme", "dark"))
        theme.set_mode(mode)
        self.theme_box.setCurrentIndex(0 if mode == "dark" else 1)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(theme.stylesheet())
        self.theme_button.setText(theme.MODE_LABELS[theme.mode()])
        self.theme_button.setIcon(
            icons.make_icon("moon" if theme.is_dark() else "sun",
                            theme.COLORS["muted"], 16)
        )

        preset_key = str(self.settings.value("preset", ""))
        if preset_key in preset_mod.BY_KEY:
            index = self.preset_box.findData(preset_key)
            if index >= 0:
                self.preset_box.setCurrentIndex(index)
        quality = str(self.settings.value("quality", ""))
        if quality:
            self.quality_box.setCurrentText(quality)
        self.last_output_dir = str(self.settings.value("output_dir", ""))

    def _save_settings(self) -> None:
        self.settings.setValue("theme", theme.mode())
        self.settings.setValue("preset", self.preset_box.currentData())
        self.settings.setValue("quality", self.quality_box.currentText())
        self.settings.setValue("hardware", self.hw_check.isChecked())
        if self.last_output_dir:
            self.settings.setValue("output_dir", self.last_output_dir)

    # ==================== 输出目录 ====================

    def on_open_output_dir(self, path: str) -> None:
        """在资源管理器里定位到输出文件。"""
        target = Path(path)
        if not target.exists():
            self.notify("文件不在了", "找不到：" + chr(10) + path)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))

    # ==================== 杂项 ====================

    def notify(self, title: str, message: str) -> None:
        """普通提示。自动化测试下静默，否则离屏环境没人点确认会挂住。"""
        self.log(f"{title}：{message}")
        if self.quiet:
            return
        QMessageBox.information(self, title, message)

    def warn(self, title: str, message: str) -> None:
        """警告提示。同样受 quiet 抑制。"""
        self.log(f"{title}：{message}")
        if self.quiet:
            return
        QMessageBox.warning(self, title, message)

    def log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def closeEvent(self, event) -> None:
        """关窗前把三个后台线程都收干净。

        漏掉任何一个都会崩：QThread 以 self 为 parent，窗口析构时线程对象被销毁，
        而线程还在跑，Qt 会直接 abort（实测退出码 0xC0000409）。
        """
        if self.worker:
            self.queue.cancelled = True
            self.worker.cancel()
            self.worker.wait(8000)

        # 加载和硬件探测线程：请求中断后等它退出，超时也不能放行
        for thread in (self.loader, self.probe):
            if thread is None or not thread.isRunning():
                continue
            thread.requestInterruption()
            if not thread.wait(8000):
                # 还没退出就再等一轮，宁可多等也不能让线程对象被析构
                thread.wait()

        super().closeEvent(event)


def app_icon() -> QIcon:
    """窗口与任务栏图标。打包后从解包目录取，开发态从 assets/ 取。"""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "icon.ico")
    root = (Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[2])
    candidates.append(root / "assets" / "icon.ico")
    candidates.append(root / "_internal" / "assets" / "icon.ico")
    for path in candidates:
        if path.is_file():
            return QIcon(str(path))
    return QIcon()


def run() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("VideoTool")
    # 主题偏好要在建窗口前读出来，否则会先闪一下深色再切成浅色
    stored = QSettings("VideoTool", "VideoTool")
    theme.set_mode(str(stored.value("theme", "dark")))
    app.setStyleSheet(theme.stylesheet())
    app.setWindowIcon(app_icon())
    try:
        tools = Tools.discover()
    except FFmpegNotFound as exc:
        QMessageBox.critical(
            None,
            "缺少 ffmpeg",
            f"{exc}\n\n请把 ffmpeg.exe 和 ffprobe.exe 放到 vendor/ffmpeg/bin/ 目录，"
            "或安装 ffmpeg 并加入 PATH。",
        )
        return 1
    window = MainWindow(tools)
    window.show()
    return app.exec()
