"""ffprobe → typed description of a source clip (ADR-0015 inputs)."""

from __future__ import annotations

import statistics
from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel

from reel import tools
from reel.timebase import parse_rate

HDR_TRANSFERS = {"smpte2084": "pq", "arib-std-b67": "hlg"}


class VideoInfo(BaseModel):
    codec: str
    width: int
    height: int
    display_width: int  # after rotation
    display_height: int
    rotation: int  # degrees, normalised to 0/90/180/270 (clockwise display rotation)
    r_frame_rate: str
    avg_frame_rate: str
    nominal_fps: float
    is_vfr: bool
    frame_interval_cv: float | None  # coefficient of variation of frame intervals (sampled)
    pix_fmt: str | None
    bit_depth: int | None
    color_primaries: str | None
    color_transfer: str | None
    color_space: str | None
    color_range: str | None
    hdr: str | None  # "pq" | "hlg" | None
    sar: str | None
    start_s: float = 0.0  # stream start time (sections / phone files can start video and audio at different times)


class AudioInfo(BaseModel):
    codec: str
    sample_rate: int
    channels: int
    start_s: float = 0.0


def _start(stream: dict) -> float:
    try:
        return float(stream.get("start_time") or 0.0)
    except ValueError:
        return 0.0


class SourceProbe(BaseModel):
    path: str
    duration_s: float
    size_bytes: int
    container: str
    video: VideoInfo | None
    audio: AudioInfo | None

    @property
    def fps(self) -> Fraction:
        assert self.video is not None
        return Fraction(self.video.nominal_fps).limit_denominator(1001)


def _rotation(stream: dict) -> int:
    rot = 0
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            try:
                rot = int(round(float(sd["rotation"])))
            except (TypeError, ValueError):
                pass
    tags = stream.get("tags", {}) or {}
    if not rot and "rotate" in tags:
        rot = -int(tags["rotate"])  # legacy tag is clockwise; displaymatrix is counter-clockwise
    # ffprobe displaymatrix rotation is counter-clockwise in degrees; normalise to clockwise 0..270
    return (-rot) % 360


def _bit_depth(stream: dict) -> int | None:
    raw = stream.get("bits_per_raw_sample")
    if raw and str(raw).isdigit():
        return int(raw)
    pix = stream.get("pix_fmt") or ""
    for depth in (16, 12, 10):
        if f"p{depth}" in pix:
            return depth
    return 8 if pix else None


def _vfr_stats(path: Path, nominal: float) -> tuple[bool, float | None]:
    """Sample frame times; VFR if intervals vary materially."""
    try:
        times = tools.ffprobe_frame_times(path)
    except tools.ToolError:
        return False, None
    times = sorted(t for t in times if t >= 0)
    if len(times) < 3:
        return False, None
    intervals = [b - a for a, b in zip(times, times[1:]) if b > a]
    if len(intervals) < 2:
        return False, None
    mean = statistics.fmean(intervals)
    cv = statistics.pstdev(intervals) / mean if mean > 0 else 0.0
    expected = 1.0 / nominal if nominal > 0 else mean
    off_grid = sum(1 for d in intervals if abs(d - expected) > 0.25 * expected) / len(intervals)
    return (cv > 0.05 or off_grid > 0.02), round(cv, 4)


def probe(path: Path) -> SourceProbe:
    data = tools.ffprobe_json(path)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)

    video = None
    if v:
        r = parse_rate(v.get("r_frame_rate", ""))
        avg = parse_rate(v.get("avg_frame_rate", ""))
        nominal = float(avg or r)
        rotation = _rotation(v)
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        dw, dh = (h, w) if rotation in (90, 270) else (w, h)
        is_vfr, cv = _vfr_stats(path, nominal)
        transfer = v.get("color_transfer")
        video = VideoInfo(
            codec=v.get("codec_name", "?"),
            width=w,
            height=h,
            display_width=dw,
            display_height=dh,
            rotation=rotation,
            r_frame_rate=v.get("r_frame_rate", ""),
            avg_frame_rate=v.get("avg_frame_rate", ""),
            nominal_fps=round(nominal, 6),
            is_vfr=is_vfr,
            frame_interval_cv=cv,
            pix_fmt=v.get("pix_fmt"),
            bit_depth=_bit_depth(v),
            color_primaries=v.get("color_primaries"),
            color_transfer=transfer,
            color_space=v.get("color_space"),
            color_range=v.get("color_range"),
            hdr=HDR_TRANSFERS.get(transfer or ""),
            sar=v.get("sample_aspect_ratio"),
            start_s=_start(v),
        )
    audio = None
    if a:
        audio = AudioInfo(
            codec=a.get("codec_name", "?"),
            sample_rate=int(a.get("sample_rate", 0) or 0),
            channels=int(a.get("channels", 0) or 0),
            start_s=_start(a),
        )
    return SourceProbe(
        path=str(path),
        duration_s=float(fmt.get("duration", 0) or 0),
        size_bytes=int(fmt.get("size", 0) or 0),
        container=fmt.get("format_name", "?"),
        video=video,
        audio=audio,
    )
