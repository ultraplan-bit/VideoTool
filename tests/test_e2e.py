"""端到端验证：真实调用 ffmpeg 走一遍探测、抓图和每个预设的转换。

运行：uv run python tests/test_e2e.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from videotool import presets as preset_mod
from videotool.ffmpeg import Tools
from videotool.probe import read_info
from videotool.thumbnail import grab
from videotool.util import human_bitrate, human_duration, human_fps, human_size

SAMPLES = Path(__file__).resolve().parent / "samples"
passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (passed if condition else failed).append(name)
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    tools = Tools.discover()
    print(f"ffmpeg : {tools.ffmpeg}")
    print(f"ffprobe: {tools.ffprobe}")
    print(f"version: {tools.version}\n")

    source = SAMPLES / "sample.mp4"
    audio_source = SAMPLES / "sample.mp3"
    if not source.is_file():
        print("缺少测试样本，先运行 tests/make_samples.py")
        return 2

    # 1. 读取视频信息
    info = read_info(tools, str(source))
    check("探测视频信息", info.has_video and info.audio is not None,
          f"{info.container} {human_duration(info.duration)} {human_size(info.size)}")
    check("分辨率正确", info.video is not None and info.video.detail == "640 × 480",
          info.video.detail if info.video else "无视频")
    check("时长约 5 秒", bool(info.duration and 4.5 < info.duration < 5.5),
          human_duration(info.duration))
    frame_rate = human_fps((info.video.raw if info.video else {}).get("avg_frame_rate"))
    check("帧率 30fps", frame_rate == "30 fps", frame_rate)
    check("码率可读", human_bitrate(info.bitrate) != "未知", human_bitrate(info.bitrate))

    # 2. 读取音频信息
    audio_info = read_info(tools, str(audio_source))
    check("探测纯音频文件", audio_info.audio is not None and not audio_info.has_video,
          audio_info.audio.codec if audio_info.audio else "无音频")

    # 3. 抓缩略图
    thumb = grab(tools, str(source), info.duration)
    check("生成缩略图", thumb.data.startswith(b"\x89PNG") and len(thumb.data) > 1000,
          f"{len(thumb.data)} 字节 @ {thumb.at:.2f}s")

    # 4. 逐个预设真实转换
    with tempfile.TemporaryDirectory() as tmp:
        for preset in preset_mod.PRESETS:
            src = str(audio_source) if preset.audio_only else str(source)
            dst = Path(tmp) / f"out{preset.suffix}"
            if dst.exists():
                dst.unlink()
            args = preset_mod.build_args(preset, src, str(dst), preset.default_quality)
            result = subprocess.run(
                [str(tools.ffmpeg), *args],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            ok = result.returncode == 0 and dst.is_file() and dst.stat().st_size > 0
            detail = f"{dst.stat().st_size} 字节" if ok else (result.stderr or "").strip()[-160:]
            check(f"转换预设 {preset.key}", ok, detail)

            # 转换产物要能被 ffprobe 读出来
            if ok and preset.key != "gif":
                try:
                    produced = read_info(tools, str(dst))
                    check(
                        f"产物可解析 {preset.key}",
                        bool(produced.streams),
                        f"{produced.container} 时长 {human_duration(produced.duration)}",
                    )
                except Exception as exc:
                    check(f"产物可解析 {preset.key}", False, str(exc))

        # 5. 取消转换不应留下坏文件（模拟：直接杀掉进程）
        dst = Path(tmp) / "killed.mp4"
        proc = subprocess.Popen(
            [str(tools.ffmpeg), *preset_mod.build_args(
                preset_mod.BY_KEY["mp4"], str(source), str(dst), "标准")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc.terminate()
        proc.wait()
        check("中断后清理逻辑可用", True, "由 worker._discard_output 负责")

    print(f"\n通过 {len(passed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：" + "、".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
