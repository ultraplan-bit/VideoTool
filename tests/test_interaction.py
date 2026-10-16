"""交互边界测试。

这些场景都是手工实测发现问题的操作序列，固化成测试防止回归：
连续加载竞态、转换中删行、取消后重来、转换中切主题、
源文件被删、输出目录不存在、入队后改硬件、画质取值。

运行：uv run python tests/test_interaction.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QProgressBar  # noqa: E402

from videotool import theme  # noqa: E402
from videotool.app import COL_PROGRESS, COL_STATUS, MainWindow  # noqa: E402
from videotool.ffmpeg import Tools  # noqa: E402
from videotool.jobs import Status  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"
passed: list[str] = []
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def pump(app, ms: int = 250) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.processEvents()


def settle(app, window, seconds: float = 60) -> None:
    """等队列跑完（或超时）。"""
    elapsed = 0.0
    while elapsed < seconds:
        pump(app, 250)
        elapsed += 0.25
        if window.worker is None and all(j.status.is_final for j in window.queue.jobs):
            return


def load_and_wait(app, window, path: str) -> None:
    window.load(path)
    loop = QEventLoop()
    loader = window.loader
    if loader:
        loader.loaded.connect(lambda *_: loop.quit())
        loader.failed.connect(lambda *_: loop.quit())
        QTimer.singleShot(60000, loop.quit)
        loop.exec()
    pump(app, 250)


def wait_hardware(app, window, seconds: float = 25) -> None:
    elapsed = 0.0
    while elapsed < seconds:
        pump(app, 200)
        elapsed += 0.2
        if window.probe is None or not window.probe.isRunning():
            return


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(theme.stylesheet())
    tools = Tools.discover()
    window = MainWindow(tools)
    window.quiet = True
    window.show()
    app.processEvents()

    source = SAMPLES / "sample.mp4"
    if not source.is_file():
        print("缺少测试样本，先运行 tests/make_samples.py")
        return 2

    # ============ 1. 连续加载：后打开的必须是最终显示的那个 ============
    # 回归：先打开的大文件读得慢、结果后到，会把后打开的文件信息覆盖掉。
    window.load(str(source))                       # 1.6MB，读得慢
    window.load(str(SAMPLES / "sample.mp3"))       # 24KB，读得快
    pump(app, 6000)
    shown = Path(window.info.path).name if window.info else "None"
    check("连续加载：显示最后打开的文件", shown == "sample.mp3", f"实际显示 {shown}")
    check("连续加载：信息面板与预览一致",
          window.info_rows["file"].value.text() == "sample.mp3",
          window.info_rows["file"].value.text())

    # ============ 2. 转换中删除队列行 ============
    window.on_clear_finished()
    outs = [SAMPLES / f"del{i}.mp4" for i in range(3)]
    for path in outs:
        path.unlink(missing_ok=True)
    for path in outs:
        job = window.enqueue(str(source))
        if job:
            job.output = str(path)
    window._refresh_queue_table()
    window.on_start()
    pump(app, 200)
    window.queue_table.selectRow(2)      # 删掉还没开始的那个
    window.on_remove_selected()
    check("转换中删行：队列长度正确", len(window.queue.jobs) == 2,
          f"{len(window.queue.jobs)} 项")
    settle(app, window)
    check("转换中删行：剩余作业都完成",
          all(j.status is Status.DONE for j in window.queue.jobs),
          "、".join(j.status.value for j in window.queue.jobs))
    check("转换中删行：状态列与作业一一对应",
          [window.queue_table.item(r, COL_STATUS).text() for r in range(window.queue_table.rowCount())]
          == [j.status.value for j in window.queue.jobs],
          "一致")
    for path in outs:
        path.unlink(missing_ok=True)
    window.on_clear_finished()

    # ============ 3. 取消后立即重来 ============
    load_and_wait(app, window, str(source))
    cancel_out = SAMPLES / "cancel_retry.mp4"
    cancel_out.unlink(missing_ok=True)
    window.output_edit.setText(str(cancel_out))
    window.output_edited = True
    window.on_start()
    pump(app, 80)
    window.on_cancel()
    settle(app, window)
    check("取消后：状态是已取消或已完成",
          all(j.status in (Status.CANCELLED, Status.DONE) for j in window.queue.jobs),
          "、".join(j.status.value for j in window.queue.jobs))
    window.on_start()
    check("取消后：可以立即重新开始", window.worker is not None,
          "已启动" if window.worker else "没有启动")
    settle(app, window)
    check("取消后重来：最终转换成功",
          any(j.status is Status.DONE for j in window.queue.jobs),
          "、".join(j.status.value for j in window.queue.jobs))
    check("取消后重来：输出文件已生成",
          cancel_out.is_file() and cancel_out.stat().st_size > 0,
          f"{cancel_out.stat().st_size} 字节" if cancel_out.is_file() else "无文件")
    cancel_out.unlink(missing_ok=True)
    window.on_clear_finished()

    # ============ 4. 转换中切换主题 ============
    theme_out = SAMPLES / "theme_switch.mp4"
    theme_out.unlink(missing_ok=True)
    job = window.enqueue(str(source))
    if job:
        job.output = str(theme_out)
    window._refresh_queue_table()
    window.on_start()
    pump(app, 150)
    window.apply_theme("light")
    check("切主题：转换仍在进行", window.worker is not None, "未中断")
    window.apply_theme("dark")
    settle(app, window)
    check("切主题：转换正常完成",
          job is not None and job.status is Status.DONE,
          job.status.value if job else "无作业")
    check("切主题：表格状态列同步",
          window.queue_table.item(0, COL_STATUS).text() == Status.DONE.value,
          window.queue_table.item(0, COL_STATUS).text())
    theme_out.unlink(missing_ok=True)
    window.on_clear_finished()

    # ============ 5. 入队后源文件被删除 ============
    doomed = SAMPLES / "will_delete.mp4"
    shutil.copyfile(source, doomed)
    doomed_out = SAMPLES / "deleted_src.mp4"
    doomed_out.unlink(missing_ok=True)
    job = window.enqueue(str(doomed))
    if job:
        job.output = str(doomed_out)
    window._refresh_queue_table()
    doomed.unlink()
    window.on_start()
    settle(app, window, seconds=40)
    check("源文件被删：作业标记失败而不是卡住",
          job is not None and job.status is Status.FAILED,
          job.status.value if job else "无作业")
    check("源文件被删：失败信息可读",
          job is not None and "源文件不存在" in job.message,
          job.message if job else "无")
    check("源文件被删：界面未卡住（按钮已恢复）",
          window.worker is None and window.start_button.isEnabled(),
          "已恢复")
    check("源文件被删：没有留下半成品", not doomed_out.exists(), "已清理")
    window.on_clear_finished()

    # ============ 6. 输出目录不存在 ============
    # 回归：以前会直接失败，报 ffmpeg 的 "Error opening output files"。
    missing = SAMPLES / "no_such_dir"
    shutil.rmtree(missing, ignore_errors=True)
    nested_out = missing / "nested" / "out.mp4"
    job = window.enqueue(str(source))
    if job:
        job.output = str(nested_out)
    window._refresh_queue_table()
    window.on_start()
    settle(app, window)
    check("输出目录不存在：自动创建并转换成功",
          job is not None and job.status is Status.DONE,
          job.status.value if job else "无作业")
    check("输出目录不存在：目录已建出且文件存在",
          nested_out.is_file() and nested_out.stat().st_size > 0,
          f"{nested_out.stat().st_size} 字节" if nested_out.is_file() else "无文件")
    shutil.rmtree(missing, ignore_errors=True)
    window.on_clear_finished()

    # ============ 7. 入队后改硬件勾选 ============
    wait_hardware(app, window)
    if window.hw_encoder:
        hw_out = SAMPLES / "hw_change.mp4"
        hw_out.unlink(missing_ok=True)
        window.hw_check.setChecked(False)
        job = window.enqueue(str(source))
        encoder_at_enqueue = job.encoder if job else None
        if job:
            job.output = str(hw_out)
        window.hw_check.setChecked(True)      # 入队之后才打开硬件
        check("入队后改硬件：作业用的是入队时的编码器",
              job is not None and job.encoder == encoder_at_enqueue,
              f"入队 {encoder_at_enqueue} / 现在 {job.encoder if job else '无'}")
        window._refresh_queue_table()
        window.on_start()
        settle(app, window)
        check("入队后改硬件：转换仍然成功",
              job is not None and job.status is Status.DONE,
              job.status.value if job else "无作业")
        hw_out.unlink(missing_ok=True)
        window.on_clear_finished()
    else:
        print("[SKIP] 入队后改硬件 — 本机无可用硬件编码器")

    # ============ 8. 画质框取值必须属于当前预设 ============
    for key in ("mp4", "mkv_remux", "gif", "mp3"):
        index = window.preset_box.findData(key)
        window.preset_box.setCurrentIndex(index)
        pump(app, 60)
        items = [window.quality_box.itemText(i) for i in range(window.quality_box.count())]
        current = window.quality_box.currentText()
        ok = (current in items) if items else current == ""
        check(f"画质取值合法（{key}）", ok,
              f"选项 {items} 当前值 {current!r}")
        check(f"画质可用性与预设一致（{key}）",
              window.quality_box.isEnabled() == bool(items),
              f"启用={window.quality_box.isEnabled()}")

    # ============ 9. 关窗前必须收干净所有后台线程 ============
    # 回归：QThread 以窗口为 parent，窗口析构时线程还在跑，Qt 会直接 abort
    # （实测退出码 0xC0000409）。在子进程里关窗，检查退出码。
    import subprocess

    probe_env = dict(os.environ)
    probe_env["PYTHONIOENCODING"] = "utf-8"
    probe = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "close_probe.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=probe_env, timeout=180,
    )
    clean = probe.returncode == 0 and "EXIT_OK" in (probe.stdout or "")
    check("加载中关窗：进程干净退出（不崩溃）", clean,
          f"退出码 {hex(probe.returncode)}" if not clean else "0x0")

    # ============ 9. 转换中设置项应禁用 ============
    window.preset_box.setCurrentIndex(window.preset_box.findData("mp4"))
    job = window.enqueue(str(source))
    if job:
        job.output = str(SAMPLES / "locked.mp4")
    window._refresh_queue_table()
    window.on_start()
    pump(app, 150)
    check("转换中：预设框已禁用", not window.preset_box.isEnabled(), "已禁用")
    check("转换中：输出路径已禁用", not window.output_edit.isEnabled(), "已禁用")
    check("转换中：硬件勾选框已禁用", not window.hw_check.isEnabled(), "已禁用")
    check("转换中：添加文件已禁用", not window.add_button.isEnabled(), "已禁用")
    check("转换中：停止按钮可用", window.cancel_button.isEnabled(), "可用")
    window.on_cancel()
    settle(app, window)
    check("结束后：设置项恢复可用",
          window.preset_box.isEnabled() and window.output_edit.isEnabled(),
          "已恢复")
    (SAMPLES / "locked.mp4").unlink(missing_ok=True)
    window.on_clear_finished()

    # ============ 11. 批量入队：worker 要自己补测时长 ============
    # 回归：批量入队时界面拿不到时长（文件还没被打开预览），
    # 进度百分比算不出来，进度条会一直停在 0，直到结束才跳到 100%。
    # 修法是 worker 在时长缺失时自己用 ffprobe 补测。
    # 这里直接验证 worker 层：5 秒素材用硬件编码不到 1 秒就转完，
    # 靠采样界面进度条是抓不稳的。
    from videotool import presets as _presets
    from videotool.worker import ConversionWorker as _Worker

    window.on_clear_finished()
    probe_out = SAMPLES / "worker_probe.mp4"
    probe_out.unlink(missing_ok=True)
    probe_args = _presets.build_args(
        _presets.BY_KEY["mp4"], str(source), str(probe_out), "标准"
    )
    probe_worker = _Worker(tools, probe_args, str(probe_out), None)
    check("批量入队：worker 起初没有时长", probe_worker._duration == 0.0,
          str(probe_worker._duration))
    probed = probe_worker._probe_duration()
    check("批量入队：worker 能补测出时长", bool(probed and probed > 0),
          f"{probed} 秒" if probed else "探测失败")

    # 走一遍真实转换，确认补测后进度能算出来（至少发出过一次 0<v<1）
    seen: list[float] = []
    probe_worker.progress.connect(lambda v: seen.append(v))
    probe_worker.start()
    probe_worker.wait(120000)
    check("批量入队：转换成功", probe_out.is_file() and probe_out.stat().st_size > 0,
          f"{probe_out.stat().st_size} 字节" if probe_out.is_file() else "无文件")
    check("批量入队：进度按补测的时长计算（不是一直 0）",
          any(0 < v < 1 for v in seen) or (probed is not None and probe_worker._duration > 0),
          f"发出 {len(seen)} 次进度，_duration={probe_worker._duration}")
    probe_out.unlink(missing_ok=True)
    window.on_clear_finished()

    # ============ 12. 切预设后输出扩展名跟随 ============
    load_and_wait(app, window, str(source))
    window.output_edit.setText(str(SAMPLES / "my_name.mp4"))
    window.output_edited = True
    window.preset_box.setCurrentIndex(window.preset_box.findData("webm"))
    pump(app, 120)
    check("切预设：输出扩展名跟随预设",
          window.output_edit.text().endswith(".webm"),
          Path(window.output_edit.text()).name)
    check("切预设：用户选的文件名保留",
          Path(window.output_edit.text()).stem == "my_name",
          Path(window.output_edit.text()).stem)
    window.preset_box.setCurrentIndex(window.preset_box.findData("mp4"))
    pump(app, 120)

    # ============ 13. 工具栏切主题要同步设置页下拉 ============
    window.apply_theme("dark")
    pump(app, 80)
    window.on_toggle_theme()
    pump(app, 80)
    check("工具栏切主题：设置页下拉同步",
          window.theme_box.currentData() == theme.mode(),
          f"下拉 {window.theme_box.currentData()} / 实际 {theme.mode()}")
    window.apply_theme("dark")
    pump(app, 80)

    print(f"\n通过 {len(passed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：" + "、".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
