"""用 ffprobe 读取媒体信息。"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from .ffmpeg import Tools


@dataclass
class Stream:
    index: int
    kind: str            # video / audio / subtitle
    codec: str
    detail: str          # 分辨率或声道数等一句话描述
    bitrate: int | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class MediaInfo:
    path: str
    container: str
    duration: float | None
    size: int | None
    bitrate: int | None
    streams: list[Stream] = field(default_factory=list)

    @property
    def video(self) -> Stream | None:
        return next((s for s in self.streams if s.kind == "video"), None)

    @property
    def audio(self) -> Stream | None:
        return next((s for s in self.streams if s.kind == "audio"), None)

    @property
    def has_video(self) -> bool:
        return self.video is not None


def _to_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _to_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _describe_video(stream: dict) -> str:
    width, height = stream.get("width"), stream.get("height")
    if not width or not height:
        return "无画面尺寸"
    return f"{width} × {height}"


def _describe_audio(stream: dict) -> str:
    channels = stream.get("channels")
    rate = stream.get("sample_rate")
    parts = []
    if channels:
        parts.append(f"{channels} 声道")
    if rate:
        parts.append(f"{_to_int(rate) and int(rate) / 1000:g} kHz")
    return " / ".join(parts) or "音频"


def parse(raw: dict, path: str) -> MediaInfo:
    """把 ffprobe 的 JSON 结果转成 MediaInfo。"""
    fmt = raw.get("format") or {}
    streams: list[Stream] = []
    for item in raw.get("streams") or []:
        kind = item.get("codec_type") or "unknown"
        if kind == "video":
            detail = _describe_video(item)
        elif kind == "audio":
            detail = _describe_audio(item)
        elif kind == "subtitle":
            detail = (item.get("tags") or {}).get("language") or "字幕"
        else:
            detail = kind
        streams.append(
            Stream(
                index=int(item.get("index", len(streams))),
                kind=kind,
                codec=item.get("codec_name") or "未知",
                detail=detail,
                bitrate=_to_int(item.get("bit_rate")),
                raw=item,
            )
        )
    return MediaInfo(
        path=path,
        container=(fmt.get("format_name") or "未知").split(",")[0],
        duration=_to_float(fmt.get("duration")),
        size=_to_int(fmt.get("size")),
        bitrate=_to_int(fmt.get("bit_rate")),
        streams=streams,
    )


def read_info(tools: Tools, path: str, timeout: float = 30) -> MediaInfo:
    """读取媒体信息。文件损坏或格式不支持时抛 RuntimeError。"""
    result = tools.run(
        [
            "-v", "error",
            "-of", "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        timeout=timeout,
        use_probe=True,
    )
    if result.returncode != 0:
        message = (result.stderr or "").strip().splitlines()
        raise RuntimeError(message[-1] if message else "ffprobe 读取失败")
    try:
        raw = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"无法解析 ffprobe 输出：{exc}") from exc
    info = parse(raw, path)
    if not info.streams:
        raise RuntimeError("文件中没有可识别的流")
    return info
