"""校验两套主题的设计令牌对比度，确保正文达到 WCAG AA（4.5:1）。

运行：uv run python tests/test_theme.py
改配色后跑一遍，防止出现看不清的文字。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from videotool import theme  # noqa: E402

passed: list[str] = []
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# (前景令牌, 背景令牌, 最低对比度, 说明)
PAIRS = [
    ("fg", "bg-app", 4.5, "正文 / 应用背景"),
    ("fg", "bg-surface", 4.5, "正文 / 面板"),
    ("fg", "bg-raised", 4.5, "正文 / 卡片"),
    ("fg", "bg-input", 4.5, "正文 / 输入框"),
    ("fg", "bg-hover", 4.5, "正文 / 悬停"),
    ("fg", "bg-active", 4.5, "正文 / 选中"),
    ("fg", "bg-sidebar", 4.5, "正文 / 侧栏"),
    ("fg-muted", "bg-app", 4.5, "次要文字 / 应用背景"),
    ("fg-muted", "bg-surface", 4.5, "次要文字 / 面板"),
    ("fg-muted", "bg-sidebar", 4.5, "次要文字 / 侧栏"),
    ("fg-muted", "bg-input", 4.5, "次要文字 / 输入框"),
    ("fg-on-accent", "accent", 4.5, "主按钮文字 / 主色"),
    ("accent-fg", "bg-surface", 3.0, "主色文字 / 面板（大字号、图标）"),
    ("success", "bg-surface", 3.0, "成功状态 / 面板"),
    ("warning", "bg-surface", 3.0, "警告状态 / 面板"),
    ("danger", "bg-surface", 3.0, "错误状态 / 面板"),
    ("success", "bg-sidebar", 3.0, "成功状态 / 侧栏"),
    ("danger", "bg-sidebar", 3.0, "错误状态 / 侧栏"),
]

REQUIRED = set(theme.SEMANTIC_DARK)


def check_theme(mode: str) -> None:
    theme.set_mode(mode)
    label = theme.MODE_LABELS[mode]
    print("")
    print(f"--- {label}主题 ---")
    for fg_key, bg_key, minimum, what in PAIRS:
        fg = theme.SEMANTIC[fg_key]
        bg = theme.SEMANTIC[bg_key]
        ratio = theme.contrast_ratio(fg, bg)
        check(f"[{label}] {what}", ratio >= minimum,
              f"{ratio:.2f}:1（要求 ≥{minimum}）")


def main() -> int:
    print("=== 对比度校验（WCAG AA）===")

    same_keys = set(theme.SEMANTIC_LIGHT) == REQUIRED
    check("两套主题令牌键一致", same_keys,
          "一致" if same_keys
          else "缺少：" + "、".join(sorted(REQUIRED - set(theme.SEMANTIC_LIGHT))))

    for mode in ("dark", "light"):
        check_theme(mode)

    print("")
    print("--- 样式表 ---")
    theme.set_mode("dark")
    dark_sheet = theme.stylesheet()
    theme.set_mode("light")
    light_sheet = theme.stylesheet()

    check("样式表由令牌生成", bool(dark_sheet) and "{" in dark_sheet,
          f"{len(dark_sheet)} 字符")
    check("两套主题产出不同样式表", dark_sheet != light_sheet, "深色与浅色确有差异")
    check("样式表覆盖关键控件",
          all(sel in dark_sheet for sel in
              ("#sidebar", "#panel", "QPushButton#primary", "QTableWidget",
               "QProgressBar", "QScrollBar", "#logView")),
          "侧栏/面板/主按钮/表格/进度条/滚动条/日志")

    theme.set_mode("dark")
    used = theme.stylesheet() + "".join(theme.COLORS.values())
    unused = [k for k, v in theme.SEMANTIC.items() if v not in used]
    check("语义令牌无遗漏", not unused,
          "未使用：" + "、".join(unused) if unused else "全部被引用")

    # 切主题后 COLORS 表要跟着变，否则图标会保持旧主题的颜色
    theme.set_mode("dark")
    dark_muted = theme.COLORS["muted"]
    theme.set_mode("light")
    light_muted = theme.COLORS["muted"]
    check("切主题后 COLORS 同步更新", dark_muted != light_muted,
          f"{dark_muted} → {light_muted}")

    # 深色主题的背景应该比浅色主题深
    theme.set_mode("dark")
    dark_bg = theme.SEMANTIC["bg-app"]
    theme.set_mode("light")
    light_bg = theme.SEMANTIC["bg-app"]
    check("深色背景比浅色背景暗",
          theme.contrast_ratio(dark_bg, light_bg) > 5,
          f"{dark_bg} vs {light_bg}，对比 {theme.contrast_ratio(dark_bg, light_bg):.1f}:1")

    theme.set_mode("dark")
    print("")
    print(f"通过 {len(passed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：" + "、".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
