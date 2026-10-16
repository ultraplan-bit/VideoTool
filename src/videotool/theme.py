"""设计令牌与样式表，支持深色/浅色两套主题。

三层结构（参考 design-system skill 的令牌架构）：
    原始值 primitive → 语义 semantic → 组件 component

界面代码只引用语义令牌，不出现裸色值。切换主题时只换语义层。
两套主题的所有前景/背景组合都由 tests/test_theme.py 校验对比度，
正文不低于 4.5:1（WCAG AA）。
"""
from __future__ import annotations

# ---------- 第一层：原始值 ----------

PRIMITIVE = {
    # 深色主题的中性色（偏冷灰，企业工具常用）
    "dark-990": "#0b0d12",
    "dark-950": "#101319",
    "dark-900": "#151922",
    "dark-880": "#1a1f2a",
    "dark-860": "#1f2532",
    "dark-840": "#252c3b",
    "dark-800": "#2d3547",
    "dark-700": "#3b4559",
    "dark-600": "#4e5a72",
    "dark-500": "#6b7691",
    "dark-400": "#8e99b3",
    "dark-300": "#aeb8cd",
    "dark-200": "#cdd5e3",
    "dark-100": "#e6ebf4",
    # 浅色主题的中性色
    "light-000": "#ffffff",
    "light-050": "#f6f8fc",
    "light-100": "#eef2f8",
    "light-150": "#e5eaf3",
    "light-200": "#dce3ee",
    "light-250": "#cbd4e3",
    "light-300": "#b3bed0",
    "light-400": "#8b97ad",
    "light-500": "#6b7690",
    "light-600": "#4d5872",
    "light-700": "#333c52",
    "light-800": "#1f2739",
    "light-900": "#141a28",
    "white": "#ffffff",
    # 主色（蓝）
    "blue-800": "#1e40af",
    "blue-700": "#1d4ed8",
    "blue-600": "#2563eb",
    "blue-500": "#3b82f6",
    "blue-400": "#60a5fa",
    "blue-300": "#93c5fd",
    # 状态色（深色主题用亮色，浅色主题用暗色）
    "green-700": "#15803d",
    "green-500": "#22c55e",
    "green-400": "#4ade80",
    "amber-700": "#b45309",
    "amber-500": "#f59e0b",
    "amber-400": "#fbbf24",
    "red-700": "#b91c1c",
    "red-500": "#ef4444",
    "red-400": "#f87171",
    # 尺寸与字体
    "radius-sm": "4px",
    "radius-md": "6px",
    "radius-lg": "10px",
    "space-1": "4px",
    "space-2": "8px",
    "space-3": "12px",
    "space-4": "16px",
    "space-5": "24px",
    "font-xs": "11px",
    "font-sm": "12px",
    "font-md": "13px",
    "font-lg": "15px",
    "font-xl": "18px",
    "font-mono": "Consolas, 'Cascadia Mono', 'Courier New', monospace",
}

P = PRIMITIVE

# ---------- 第二层：语义（两套） ----------

# 背景层次从最深到最浅，形成「桌面 → 面板 → 卡片」的层级
SEMANTIC_DARK = {
    "bg-app": P["dark-950"],
    "bg-sidebar": P["dark-990"],
    "bg-surface": P["dark-900"],
    "bg-raised": P["dark-880"],
    "bg-input": P["dark-860"],
    "bg-hover": P["dark-840"],
    "bg-active": P["dark-800"],
    "fg": P["dark-100"],
    "fg-muted": P["dark-400"],
    "fg-subtle": P["dark-500"],
    "fg-on-accent": P["white"],
    "border": P["dark-840"],
    "border-strong": P["dark-700"],
    "accent": P["blue-600"],
    "accent-hover": P["blue-500"],
    "accent-fg": P["blue-400"],
    "accent-soft": P["dark-800"],
    "success": P["green-400"],
    "warning": P["amber-400"],
    "danger": P["red-400"],
}

SEMANTIC_LIGHT = {
    "bg-app": P["light-050"],
    "bg-sidebar": P["light-000"],
    "bg-surface": P["light-000"],
    "bg-raised": P["light-100"],
    "bg-input": P["light-000"],
    "bg-hover": P["light-100"],
    "bg-active": P["light-200"],
    "fg": P["light-900"],
    "fg-muted": P["light-600"],
    "fg-subtle": P["light-500"],
    "fg-on-accent": P["white"],
    "border": P["light-200"],
    "border-strong": P["light-300"],
    "accent": P["blue-600"],
    "accent-hover": P["blue-700"],
    "accent-fg": P["blue-700"],
    "accent-soft": P["light-150"],
    "success": P["green-700"],
    "warning": P["amber-700"],
    "danger": P["red-700"],
}

THEMES = {"dark": SEMANTIC_DARK, "light": SEMANTIC_LIGHT}
MODE_LABELS = {"dark": "深色", "light": "浅色"}

# ---------- 当前主题（模块级状态，set_mode 原地更新） ----------

_mode = "dark"
SEMANTIC: dict[str, str] = dict(SEMANTIC_DARK)


def mode() -> str:
    return _mode


def is_dark() -> bool:
    return _mode == "dark"


def set_mode(value: str) -> None:
    """切换主题。原地更新字典，这样已持有引用的模块也能拿到新值。"""
    global _mode
    if value not in THEMES:
        return
    _mode = value
    SEMANTIC.clear()
    SEMANTIC.update(THEMES[value])
    COLORS.clear()
    COLORS.update(_colors_of(SEMANTIC))


def _colors_of(semantic: dict[str, str]) -> dict[str, str]:
    """供界面代码取色的简表（图标、状态点等需要在代码里用色值）。"""
    return {
        "success": semantic["success"],
        "warning": semantic["warning"],
        "danger": semantic["danger"],
        "muted": semantic["fg-muted"],
        "accent": semantic["accent-fg"],
        "fg": semantic["fg"],
    }


COLORS: dict[str, str] = _colors_of(SEMANTIC)


def contrast_ratio(fg: str, bg: str) -> float:
    """计算两色的对比度（WCAG 公式）。用于自检。"""
    def luminance(color: str) -> float:
        color = color.lstrip("#")
        channels = []
        for i in (0, 2, 4):
            value = int(color[i:i + 2], 16) / 255
            channels.append(value / 12.92 if value <= 0.03928
                            else ((value + 0.055) / 1.055) ** 2.4)
        r, g, b = channels
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    a, b = luminance(fg), luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def stylesheet() -> str:
    """由当前主题的语义令牌生成全局样式表。"""
    s = SEMANTIC
    return f"""
QWidget {{
    background: {s['bg-app']};
    color: {s['fg']};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: {P['font-md']};
}}

/* ---------- 左侧导航栏 ---------- */
#sidebar {{
    background: {s['bg-sidebar']};
    border-right: 1px solid {s['border']};
}}
#brand {{
    color: {s['fg']};
    font-size: {P['font-lg']};
    font-weight: 600;
    padding: {P['space-5']} {P['space-4']} {P['space-4']} {P['space-4']};
    background: transparent;
}}
#brandSub {{
    color: {s['fg-subtle']};
    font-size: {P['font-xs']};
    padding: 0 {P['space-4']} {P['space-4']} {P['space-4']};
    background: transparent;
}}
#navButton {{
    background: transparent;
    border: none;
    border-left: 2px solid transparent;
    border-radius: 0;
    color: {s['fg-muted']};
    padding: {P['space-3']} {P['space-4']};
    text-align: left;
    font-size: {P['font-md']};
    min-height: 22px;
}}
#navButton:hover {{
    background: {s['bg-hover']};
    color: {s['fg']};
}}
#navButton:checked {{
    background: {s['bg-active']};
    border-left: 2px solid {s['accent-fg']};
    color: {s['fg']};
    font-weight: 600;
}}

/* ---------- 顶部工具条 ---------- */
#toolbar {{
    background: {s['bg-surface']};
    border-bottom: 1px solid {s['border']};
}}
#pageTitle {{
    font-size: {P['font-xl']};
    font-weight: 600;
    background: transparent;
}}
#pageSubtitle {{
    color: {s['fg-subtle']};
    font-size: {P['font-sm']};
    background: transparent;
}}

/* ---------- 面板与分组 ---------- */
#panel {{
    background: {s['bg-surface']};
    border: 1px solid {s['border']};
    border-radius: {P['radius-lg']};
}}
#panelTitle {{
    font-size: {P['font-sm']};
    font-weight: 600;
    color: {s['fg-muted']};
    background: transparent;
    letter-spacing: 0.4px;
}}
#fieldLabel {{
    color: {s['fg-subtle']};
    font-size: {P['font-sm']};
    background: transparent;
}}
#fieldValue {{
    color: {s['fg']};
    font-size: {P['font-md']};
    background: transparent;
}}
#metric {{
    background: {s['bg-raised']};
    border: 1px solid {s['border']};
    border-radius: {P['radius-md']};
}}
#metricValue {{
    font-size: {P['font-lg']};
    font-weight: 600;
    background: transparent;
}}
#metricLabel {{
    color: {s['fg-subtle']};
    font-size: {P['font-xs']};
    background: transparent;
}}

/* ---------- 预览区 ---------- */
#dropArea {{
    background: {s['bg-raised']};
    border: 1px dashed {s['border-strong']};
    border-radius: {P['radius-lg']};
    color: {s['fg-subtle']};
    font-size: {P['font-md']};
}}
#dropArea:hover {{
    border-color: {s['accent-fg']};
    color: {s['fg-muted']};
}}

/* ---------- 表格（转换队列） ---------- */
QTableWidget {{
    background: {s['bg-surface']};
    alternate-background-color: {s['bg-raised']};
    border: 1px solid {s['border']};
    border-radius: {P['radius-md']};
    gridline-color: {s['border']};
    selection-background-color: {s['accent-soft']};
    selection-color: {s['fg']};
    outline: none;
}}
QTableWidget::item {{
    padding: {P['space-2']} {P['space-3']};
    border: none;
}}
QTableWidget::item:selected {{
    background: {s['accent-soft']};
    color: {s['fg']};
}}
QHeaderView::section {{
    background: {s['bg-raised']};
    color: {s['fg-muted']};
    border: none;
    border-bottom: 1px solid {s['border']};
    border-right: 1px solid {s['border']};
    padding: {P['space-2']} {P['space-3']};
    font-size: {P['font-sm']};
    font-weight: 600;
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTableCornerButton::section {{
    background: {s['bg-raised']};
    border: none;
}}

/* ---------- 日志 ---------- */
#logView {{
    background: {s['bg-raised']};
    border: 1px solid {s['border']};
    border-radius: {P['radius-md']};
    color: {s['fg-muted']};
    font-family: {P['font-mono']};
    font-size: {P['font-sm']};
    padding: {P['space-2']};
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: {s['bg-raised']};
    border: 1px solid {s['border-strong']};
    border-radius: {P['radius-md']};
    color: {s['fg']};
    padding: {P['space-2']} {P['space-4']};
    min-height: 20px;
}}
QPushButton:hover {{
    background: {s['bg-hover']};
    border-color: {s['fg-subtle']};
}}
QPushButton:pressed {{
    background: {s['bg-active']};
}}
QPushButton:disabled {{
    background: {s['bg-raised']};
    color: {s['fg-subtle']};
    border-color: {s['border']};
}}
QPushButton#primary {{
    background: {s['accent']};
    border: 1px solid {s['accent']};
    color: {s['fg-on-accent']};
    font-weight: 600;
    padding: {P['space-2']} {P['space-5']};
}}
QPushButton#primary:hover {{
    background: {s['accent-hover']};
    border-color: {s['accent-hover']};
}}
QPushButton#primary:disabled {{
    background: {s['bg-active']};
    border-color: {s['border']};
    color: {s['fg-subtle']};
}}
QPushButton#danger {{
    color: {s['danger']};
}}
QPushButton#danger:hover {{
    background: {s['bg-hover']};
    border-color: {s['danger']};
}}

/* ---------- 输入控件 ---------- */
QComboBox, QLineEdit {{
    background: {s['bg-input']};
    border: 1px solid {s['border-strong']};
    border-radius: {P['radius-md']};
    padding: {P['space-2']} {P['space-3']};
    color: {s['fg']};
    selection-background-color: {s['accent']};
    selection-color: {s['fg-on-accent']};
}}
QComboBox:hover, QLineEdit:hover {{
    border-color: {s['fg-subtle']};
}}
QComboBox:focus, QLineEdit:focus {{
    border-color: {s['accent-fg']};
}}
QComboBox:disabled, QLineEdit:disabled {{
    color: {s['fg-subtle']};
    background: {s['bg-raised']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {s['bg-surface']};
    border: 1px solid {s['border-strong']};
    selection-background-color: {s['accent']};
    selection-color: {s['fg-on-accent']};
    outline: none;
}}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background: {s['bg-active']};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {s['accent']};
    border-radius: 3px;
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {s['border-strong']};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {s['fg-subtle']};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {s['border-strong']};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ---------- 其他 ---------- */
QMenuBar {{
    background: {s['bg-surface']};
    border-bottom: 1px solid {s['border']};
}}
QMenuBar::item {{
    background: transparent;
    padding: {P['space-2']} {P['space-3']};
}}
QMenuBar::item:selected {{
    background: {s['bg-hover']};
}}
QMenu {{
    background: {s['bg-surface']};
    border: 1px solid {s['border-strong']};
    padding: {P['space-1']};
}}
QMenu::item {{
    padding: {P['space-2']} {P['space-5']};
    border-radius: {P['radius-sm']};
}}
QMenu::item:selected {{
    background: {s['accent']};
    color: {s['fg-on-accent']};
}}
QMenu::separator {{
    height: 1px;
    background: {s['border']};
    margin: {P['space-1']} {P['space-2']};
}}
QStatusBar {{
    background: {s['bg-sidebar']};
    border-top: 1px solid {s['border']};
    color: {s['fg-subtle']};
    font-size: {P['font-sm']};
}}
QStatusBar::item {{
    border: none;
}}
QToolTip {{
    background: {s['bg-surface']};
    color: {s['fg']};
    border: 1px solid {s['border-strong']};
    border-radius: {P['radius-sm']};
    padding: {P['space-1']} {P['space-2']};
}}
QSplitter::handle {{
    background: transparent;
}}
QMessageBox {{
    background: {s['bg-surface']};
}}
QMessageBox QLabel {{
    background: transparent;
}}
QCheckBox {{
    background: transparent;
    spacing: {P['space-2']};
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {s['border-strong']};
    border-radius: 3px;
    background: {s['bg-input']};
}}
QCheckBox::indicator:checked {{
    background: {s['accent']};
    border-color: {s['accent']};
}}
"""
