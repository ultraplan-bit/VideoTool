"""转换预设：把"用户想干什么"翻译成 ffmpeg 参数。

界面上不让用户填裸参数，只选预设 + 少量可调项。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Preset:
    key: str
    label: str            # 界面显示名
    suffix: str           # 输出扩展名
    summary: str          # 一句话说明
    vcodec: str | None    # None 表示不带视频
    acodec: str | None
    extra: tuple[str, ...] = ()          # 固定附加参数
    audio_only: bool = False
    needs_video: bool = True             # 输入必须是视频
    quality_choices: tuple[str, ...] = ()  # 可选的画质档位
    default_quality: str = ""
    # 能否用硬件编码器替换。只有走 H.264 的预设可以：
    # WebM 容器不接受 H.264（只支持 VP8/VP9/AV1），GIF 和音频预设不编码视频，
    # MKV 换壳是流拷贝。给这些预设套 h264_nvenc 会直接报错。
    hardware_ok: bool = False


# 画质档位 → CRF（数字越小越清晰、文件越大）
CRF = {"高质量": "18", "标准": "23", "小体积": "28"}

PRESETS: tuple[Preset, ...] = (
    Preset(
        key="mp4",
        label="MP4（H.264 + AAC）",
        suffix=".mp4",
        summary="兼容性最好，手机、网页、播放器通吃",
        vcodec="libx264",
        acodec="aac",
        extra=("-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"),
        quality_choices=("高质量", "标准", "小体积"),
        default_quality="标准",
        hardware_ok=True,
    ),
    Preset(
        key="mkv_remux",
        label="MKV（不重编码，只换壳）",
        suffix=".mkv",
        summary="几秒完成，画质零损失，适合改封装格式",
        vcodec="copy",
        acodec="copy",
    ),
    Preset(
        key="webm",
        label="WebM（VP9 + Opus）",
        suffix=".webm",
        summary="网页友好，同画质体积更小",
        vcodec="libvpx-vp9",
        acodec="libopus",
        extra=("-b:v", "0", "-row-mt", "1"),
        quality_choices=("高质量", "标准", "小体积"),
        default_quality="标准",
    ),
    Preset(
        key="gif",
        label="GIF 动图",
        suffix=".gif",
        summary="取前 5 秒生成动图，适合做表情包或预览",
        vcodec=None,
        acodec=None,
        extra=("-t", "5", "-vf", "fps=12,scale=480:-2:flags=lanczos", "-loop", "0"),
        needs_video=True,
    ),
    Preset(
        key="mp3",
        label="MP3 音频",
        suffix=".mp3",
        summary="只抽出声音，转成通用 MP3",
        vcodec=None,
        acodec="libmp3lame",
        extra=("-q:a", "2"),
        audio_only=True,
    ),
    Preset(
        key="m4a",
        label="M4A 音频",
        suffix=".m4a",
        summary="只抽出声音，转成 Apple 系常用格式",
        vcodec=None,
        acodec="aac",
        extra=("-b:a", "192k"),
        audio_only=True,
    ),
)

BY_KEY = {p.key: p for p in PRESETS}


# 硬件编码器的画质参数与软件不同：
# NVENC 用 -cq（恒定质量）而不是 -crf，-preset 取值也是 p1~p7 而不是 medium。
# 所以硬件模式下的参数要单独拼，不能直接套用软件编码的那一套。
HW_CQ = {"高质量": "23", "标准": "27", "小体积": "32"}
HW_PRESET = {"h264_nvenc": "p5", "h264_qsv": "medium", "h264_amf": "balanced", "h264_mf": ""}
# 这些编码器不支持 -pix_fmt yuv420p 之外的选项时会被忽略，yuv420p 是安全的通用值


def build_args(
    preset: Preset,
    src: str,
    dst: str,
    quality: str = "",
    encoder: str | None = None,
) -> list[str]:
    """拼出 ffmpeg 参数。

    encoder 传入硬件编码器名时，走硬件参数（-cq 等）；
    否则按预设的软件编码器拼参数。
    """
    # 预设不支持硬件编码时直接忽略，避免拼出非法组合（如 H.264 塞进 WebM）
    if not preset.hardware_ok:
        encoder = None
    hardware = bool(encoder and encoder.startswith(("h264_nvenc", "h264_qsv",
                                                    "h264_amf", "h264_mf")))
    args: list[str] = ["-hide_banner", "-y", "-i", src]

    if preset.vcodec and preset.vcodec != "copy":
        args += ["-c:v", encoder or preset.vcodec]
        if hardware:
            if quality:
                args += ["-cq", HW_CQ.get(quality, "27")]
            hw_preset = HW_PRESET.get(encoder or "", "")
            if hw_preset:
                args += ["-preset", hw_preset]
            # 硬件编码器统一用 yuv420p，兼容性最好
            args += ["-pix_fmt", "yuv420p"]
        else:
            if preset.key == "webm" and quality:
                args += ["-crf", CRF.get(quality, "32")]
            elif preset.key == "mp4" and quality:
                args += ["-crf", CRF.get(quality, "23")]
    elif preset.vcodec == "copy":
        args += ["-c:v", "copy"]

    if preset.acodec:
        args += ["-c:a", preset.acodec]
    if preset.audio_only:
        args += ["-vn"]

    if hardware:
        # 硬件模式下要丢掉预设里的软件专用参数：
        # -preset medium 是 libx264 的档位，nvenc 不认；-pix_fmt 上面已按硬件要求加过。
        extra = _drop_options(preset.extra, "-preset", "-pix_fmt")
    else:
        extra = list(preset.extra)
    args += extra

    args += ["-progress", "pipe:1", "-nostats", dst]
    return args


def _drop_options(options: tuple[str, ...], *flags: str) -> list[str]:
    """从参数列表里去掉指定选项及其取值。

    ffmpeg 的选项是「-flag value」成对出现，所以去掉 -preset 时要连它后面的
    medium 一起丢掉，否则 medium 会被当成输入文件名。
    """
    kept: list[str] = []
    skip_next = False
    for item in options:
        if skip_next:
            skip_next = False
            continue
        if item in flags:
            skip_next = True
            continue
        kept.append(item)
    return kept

