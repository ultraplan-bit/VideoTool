"""硬件编码测试。

本机没有可用显卡时自动跳过（其他机器上跑也应该是通过而不是失败）。
运行：uv run python tests/test_hardware.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videotool import presets as preset_mod  # noqa: E402
from videotool.ffmpeg import Tools, detect_hardware_encoder  # noqa: E402

SAMPLES = ROOT / "tests" / "samples"
passed: list[str] = []
failed: list[str] = []
skipped: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    skipped.append(name)
    print(f"[SKIP] {name} — {why}")


def run(tools: Tools, args: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        [str(tools.ffmpeg), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    tail = (result.stderr or "").strip().splitlines()
    return result.returncode == 0, tail[-1] if tail else ""


def main() -> int:
    tools = Tools.discover()
    source = SAMPLES / "sample.mp4"
    if not source.is_file():
        print("缺少测试样本，先运行 tests/make_samples.py")
        return 2

    # ---------- 参数拼装（不依赖显卡，任何机器都能验） ----------
    print("=== 参数拼装 ===")
    mp4 = preset_mod.BY_KEY["mp4"]
    hw_args = preset_mod.build_args(mp4, "in.mp4", "out.mp4", "标准", "h264_nvenc")
    check("MP4 预设接受硬件编码器", "h264_nvenc" in hw_args,
          " ".join(hw_args))
    check("硬件模式用 -cq 而非 -crf", "-cq" in hw_args and "-crf" not in hw_args,
          f"cq={hw_args[hw_args.index('-cq') + 1] if '-cq' in hw_args else '无'}")
    check("硬件模式用 p 档 preset", "-preset" in hw_args
          and hw_args[hw_args.index("-preset") + 1].startswith("p"),
          hw_args[hw_args.index("-preset") + 1] if "-preset" in hw_args else "无")
    check("软件专用参数已剔除",
          "-preset" in hw_args and hw_args[hw_args.index("-preset") + 1] != "medium",
          "没有残留 libx264 的 medium 档")
    check("pix_fmt 未重复", hw_args.count("-pix_fmt") == 1,
          f"{hw_args.count('-pix_fmt')} 次")

    # 不支持硬件编码的预设必须忽略传入的编码器，
    # 否则会拼出 H.264 塞进 WebM 这种非法组合
    for key in ("webm", "gif", "mkv_remux", "mp3"):
        preset = preset_mod.BY_KEY[key]
        args = preset_mod.build_args(preset, "in.mp4", f"out{preset.suffix}", "标准", "h264_nvenc")
        check(f"{key} 预设忽略硬件编码器", "h264_nvenc" not in args,
              args[args.index("-c:v") + 1] if "-c:v" in args else "不编码视频")

    # ---------- 真实转换（依赖显卡） ----------
    print("")
    print("=== 真实转换 ===")
    encoder = detect_hardware_encoder(tools)
    if encoder is None:
        skip("硬件编码真实转换", "本机未检测到可用硬件编码器")
        skip("硬件编码速度对比", "同上")
    else:
        name, label = encoder
        print(f"检测到：{label}（{name}）")
        with tempfile.TemporaryDirectory() as tmp:
            # 软件 vs 硬件，比速度
            times: dict[str, float] = {}
            for tag, enc in (("软件", None), ("硬件", name)):
                dst = Path(tmp) / f"{tag}.mp4"
                args = preset_mod.build_args(mp4, str(source), str(dst), "标准", enc)
                start = time.time()
                ok, error = run(tools, args)
                elapsed = time.time() - start
                size = dst.stat().st_size if dst.is_file() else 0
                check(f"{tag}编码转换成功", ok and size > 0,
                      f"{elapsed:.2f}s，{size} 字节" + (f"，{error}" if not ok else ""))
                if ok:
                    times[tag] = elapsed

            if len(times) == 2 and times["软件"] > 0:
                speedup = times["软件"] / max(times["硬件"], 0.001)
                # 5 秒素材太短，硬件启动开销占比大，这里只做记录不做断言
                print(f"      速度对比：软件 {times['软件']:.2f}s，"
                      f"硬件 {times['硬件']:.2f}s（{speedup:.1f}x）")

            # 硬件编码的产物必须能被 ffprobe 正常解析
            if "硬件" in times:
                from videotool.probe import read_info

                info = read_info(tools, str(Path(tmp) / "硬件.mp4"))
                check("硬件产物可被解析",
                      info.has_video and info.video is not None,
                      f"{info.video.codec} {info.video.detail}" if info.video else "无视频")
                check("硬件产物编码器是 h264",
                      info.video is not None and info.video.codec == "h264",
                      info.video.codec if info.video else "无")

    print("")
    tail = f"通过 {len(passed)} 项，失败 {len(failed)} 项"
    if skipped:
        tail += f"，跳过 {len(skipped)} 项"
    print(tail)
    if failed:
        print("失败项：" + "、".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
