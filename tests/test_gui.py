"""界面测试：离屏启动窗口，走完整交互流程，并输出截图。

覆盖：加载、信息展示、缩略图、页面切换、批量队列真实转换、取消清理。
运行：uv run python tests/test_gui.py
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
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressBar  # noqa: E402

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


def dismiss_dialogs() -> None:
    """离屏测试里模态对话框没人点，定时关掉，否则测试会挂住。"""
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, QMessageBox) and widget.isVisible():
            widget.close()


def wait_for(signal, timeout_ms: int = 60000) -> bool:
    """等信号触发一次，超时返回 False。"""
    loop = QEventLoop()
    state = {"fired": False}

    def on_signal(*_args) -> None:
        state["fired"] = True
        loop.quit()

    closer = QTimer()
    closer.timeout.connect(dismiss_dialogs)
    closer.start(200)
    signal.connect(on_signal)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    closer.stop()
    signal.disconnect(on_signal)
    return state["fired"]


def pump(app, ms: int = 300) -> None:
    """跑一会儿事件循环，让界面和后台线程都推进。

    期间要持续关闭模态对话框：队列跑完会弹"全部完成"提示，
    离屏环境没人点确认，不关掉就会一直挂在这里。
    """
    loop = QEventLoop()
    closer = QTimer()
    closer.timeout.connect(dismiss_dialogs)
    closer.start(200)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    closer.stop()
    app.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(theme.stylesheet())
    tools = Tools.discover()
    window = MainWindow(tools)
    window.quiet = True   # 关掉完成提示框，避免离屏环境下模态阻塞
    window.show()
    app.processEvents()
    check("窗口创建", window.isVisible())

    # ---------- 加载 ----------
    window.load(str(SAMPLES / "sample.mp4"))
    loader = window.loader
    loaded = wait_for(loader.loaded, 60000) if loader else False
    check("加载视频并读出信息", loaded and window.info is not None,
          window.info.container if window.info else "无")
    pixmap = window.preview.pixmap()
    check("缩略图已显示", bool(pixmap) and not pixmap.isNull(),
          f"{pixmap.width()}x{pixmap.height()}" if pixmap else "无")
    check("信息面板已填充",
          window.info_rows["video"].value.text() != "—"
          and window.info_rows["streams"].value.text() != "—",
          window.info_rows["streams"].value.text())
    check("指标卡已填充",
          window.metric_duration.value_label.text() != "—"
          and window.metric_size.value_label.text() != "—",
          f"{window.metric_duration.value_label.text()} / "
          f"{window.metric_size.value_label.text()}")

    # 源文件是 .mp4、默认预设也是 .mp4，默认输出名必须不同，否则会覆盖原文件
    default_output = Path(window.output_edit.text())
    check("默认输出路径不与源文件同名",
          default_output.name != "sample.mp4" and default_output.suffix == ".mp4",
          default_output.name)
    check("开始按钮已启用", window.start_button.isEnabled())

    # ---------- 页面切换 ----------
    for index, title in enumerate(["转换", "队列", "设置", "关于"]):
        window._switch_page(index)
        app.processEvents()
        ok = window.pages.currentIndex() == index and window.page_title.text() == title
        check(f"切换到「{title}」页", ok, window.page_title.text())
    check("设置页显示 ffmpeg 路径",
          "ffmpeg" in window.ffmpeg_rows["ffmpeg"].value.text().lower(),
          window.ffmpeg_rows["ffmpeg"].value.text()[-38:])
    window._switch_page(0)

    # ---------- 多文件拖拽：首个进预览，其余进队列 ----------
    # 默认预设是 MP4（需要视频轨），所以用两个视频文件；
    # 纯音频会被 enqueue 按"预设需要视频轨"拒绝，这本身也是预期行为。
    second = SAMPLES / "sample2.mp4"
    shutil.copyfile(SAMPLES / "sample.mp4", second)

    window.on_clear_finished()
    before = len(window.queue.jobs)
    window.accept_files([
        str(SAMPLES / "sample.mp4"),
        str(second),
        str(SAMPLES / "not_here.mp4"),      # 不存在的路径应被跳过
    ])
    check("多文件拖入后其余进队列", len(window.queue.jobs) == before + 1,
          f"队列 {before} → {len(window.queue.jobs)}")
    queued = window.queue.jobs[-1] if window.queue.jobs else None
    check("队列里是第二个文件", queued is not None and queued.name == "sample2.mp4",
          queued.name if queued else "无")
    check("不存在的路径被跳过",
          all("not_here" not in j.name for j in window.queue.jobs), "已跳过")
    multi_loader = window.loader
    if multi_loader:
        wait_for(multi_loader.loaded, 60000)
    check("预览显示的是第一个文件",
          window.info is not None and Path(window.info.path).name == "sample.mp4",
          Path(window.info.path).name if window.info else "无")

    # 纯音频在需要视频轨的预设下应被拒绝
    rejected = window.enqueue(str(SAMPLES / "sample.mp3"))
    check("需要视频轨的预设会拒绝纯音频", rejected is None,
          "已拒绝" if rejected is None else f"意外入队 {rejected.name}")

    # 彻底清空队列：on_clear_finished 只清已结束的作业，
    # 这里留下的待处理作业会让后续批量测试的行数和状态断言全部错位。
    window.queue.jobs.clear()
    window._refresh_queue_table()
    second.unlink(missing_ok=True)
    check("多文件测试后队列已复位", len(window.queue.jobs) == 0,
          f"{len(window.queue.jobs)} 项残留")
    window._switch_page(0)

    # ---------- 批量队列真实转换 ----------
    out1 = SAMPLES / "batch_a.mp4"
    out2 = SAMPLES / "batch_b.mkv"
    for path in (out1, out2):
        path.unlink(missing_ok=True)

    window._switch_page(1)
    job1 = window.enqueue(str(SAMPLES / "sample.mp4"))
    check("作业 1 入队", job1 is not None, job1.name if job1 else "无")
    if job1:
        job1.output = str(out1)

    # 第二个作业换 MKV 换壳预设，验证不同预设混跑
    window.preset_box.setCurrentIndex(1)
    job2 = window.enqueue(str(SAMPLES / "sample.mp4"))
    check("作业 2 入队（MKV 预设）", job2 is not None, job2.preset_label if job2 else "无")
    if job2:
        job2.output = str(out2)
    window._refresh_queue_table()
    check("队列表格行数正确", window.queue_table.rowCount() == 2,
          f"{window.queue_table.rowCount()} 行")

    progress_values: list[int] = []
    window.on_start()
    check("批量转换已启动", window.worker is not None)

    deadline, elapsed = 180.0, 0.0
    while elapsed < deadline:
        pump(app, 250)
        elapsed += 0.25
        widget = window.queue_table.cellWidget(0, COL_PROGRESS)
        if isinstance(widget, QProgressBar):
            progress_values.append(widget.value())
        if window.worker is None and all(j.status.is_final for j in window.queue.jobs):
            break

    check("队列全部结束", all(j.status.is_final for j in window.queue.jobs),
          "、".join(f"{j.name}:{j.status.value}" for j in window.queue.jobs))
    check("作业 1 转换成功", job1 is not None and job1.status is Status.DONE,
          job1.message if job1 else "")
    check("作业 2 转换成功", job2 is not None and job2.status is Status.DONE,
          job2.message if job2 else "")
    check("输出文件都已生成",
          out1.is_file() and out1.stat().st_size > 0
          and out2.is_file() and out2.stat().st_size > 0,
          f"{out1.stat().st_size if out1.is_file() else 0} / "
          f"{out2.stat().st_size if out2.is_file() else 0} 字节")
    check("进度条有更新", any(v > 0 for v in progress_values),
          f"{len(progress_values)} 次采样")
    status_item = window.queue_table.item(0, COL_STATUS)
    check("状态列显示完成",
          status_item is not None and status_item.text() == Status.DONE.value,
          status_item.text() if status_item else "无")

    # ---------- 截图（此时队列有结果，界面信息最完整） ----------
    window._switch_page(1)
    pump(app, 400)
    check("队列页截图", window.grab().save(str(ROOT / "tests" / "v2_queue_done.png")),
          "tests/v2_queue_done.png")
    window._switch_page(0)
    pump(app, 400)
    check("转换页截图", window.grab().save(str(ROOT / "tests" / "v2_convert.png")),
          "tests/v2_convert.png")

    # ---------- 改设置后重来一遍 ----------
    # 回归：第一轮转换结束后队列里留着已完成的记录，若 on_start 按「队列是否为空」
    # 判断，用户改了设置再点开始就会被告知「任务都已结束」，没法重来。
    rerun_out = SAMPLES / "rerun.mp4"
    rerun_out.unlink(missing_ok=True)

    window.on_clear_finished()
    window.load(str(SAMPLES / "sample.mp4"))
    rerun_loader = window.loader
    if rerun_loader:
        wait_for(rerun_loader.loaded, 60000)
    window.preset_box.setCurrentIndex(0)
    window.output_edit.setText(str(rerun_out))
    window.output_edited = True

    window.on_start()
    first_worker = window.worker
    done_first = wait_for(first_worker.succeeded, 120000) if first_worker else False
    check("改设置重来：第一轮转换完成", done_first, str(rerun_out))
    check("第一轮后队列里有已完成作业",
          any(j.status is Status.DONE for j in window.queue.jobs),
          "、".join(j.status.value for j in window.queue.jobs))

    # 不清空队列，改画质后再点开始 —— 这正是用户报的场景
    window.quality_box.setCurrentText("小体积")
    window.on_start()
    check("改设置后能重新开始（不报任务已结束）", window.worker is not None,
          "已启动" if window.worker else "没有启动")
    second_worker = window.worker
    if second_worker:
        done_second = wait_for(second_worker.succeeded, 120000)
        check("改设置重来：第二轮转换完成", done_second, "完成")
    else:
        check("改设置重来：第二轮转换完成", False, "未启动")

    done_count = len([j for j in window.queue.jobs if j.status is Status.DONE])
    check("两轮都留下已完成作业", done_count >= 2, f"{done_count} 个已完成")
    check("第二轮输出文件存在", rerun_out.is_file() and rerun_out.stat().st_size > 0,
          f"{rerun_out.stat().st_size} 字节" if rerun_out.is_file() else "无文件")
    # 覆盖确认：_existing_outputs 挑出输出已存在的作业（不弹框，可单独验证）
    from videotool.jobs import Job

    existing_file = SAMPLES / "exists_check.mp4"
    existing_file.write_bytes(b"x")
    fake_jobs = [
        Job(source="a.mp4", preset_key="mp4", preset_label="MP4",
            quality="标准", output=str(existing_file)),
        Job(source="b.mp4", preset_key="mp4", preset_label="MP4",
            quality="标准", output=str(SAMPLES / "definitely_missing.mp4")),
    ]
    hits = window._existing_outputs(fake_jobs)
    check("_existing_outputs 只挑出已存在的",
          len(hits) == 1 and hits[0].source == "a.mp4",
          f"{len(hits)} 个命中")
    existing_file.unlink(missing_ok=True)
    check("文件删掉后不再算已存在",
          not window._existing_outputs(fake_jobs[:1]), "已忽略")

    rerun_out.unlink(missing_ok=True)
    window.on_clear_finished()

    # ---------- 清空已结束 ----------
    window.on_clear_finished()
    check("清空已结束后队列为空", window.queue_table.rowCount() == 0,
          f"{window.queue_table.rowCount()} 行")

    # ---------- 取消流程 ----------
    window._switch_page(1)
    job3 = window.enqueue(str(SAMPLES / "sample.mp4"))
    check("取消测试作业入队", job3 is not None, job3.name if job3 else "无")
    if job3:
        cancelled_path = SAMPLES / "cancelled.mp4"
        cancelled_path.unlink(missing_ok=True)
        job3.output = str(cancelled_path)
        window._refresh_queue_table()
        window.on_start()
        pump(app, 120)
        window.on_cancel()
        deadline, elapsed = 60.0, 0.0
        while elapsed < deadline and window.worker is not None:
            pump(app, 250)
            elapsed += 0.25
        # 5 秒素材转得快，取消可能来不及生效。
        # 检验不变量：要么干净完成、要么不留半成品文件。
        if job3.status is Status.DONE:
            check("取消测试（转换太快已正常完成）", cancelled_path.is_file(), "已完成")
        else:
            check("取消后不留半成品文件", not cancelled_path.exists(), job3.status.value)
        cancelled_path.unlink(missing_ok=True)

    for path in (out1, out2):
        path.unlink(missing_ok=True)

    print(f"\n通过 {len(passed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：" + "、".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
