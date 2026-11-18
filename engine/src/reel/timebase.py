"""Exact time arithmetic shared by compiler, ffmpeg graph builder and Remotion timing (ADR-0015).

All conversions use Fraction. Rounding happens once, at the boundary where an integer
(frame index or audio sample) is required, and always on cumulative positions so that
per-segment rounding never accumulates into drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from reel import config

US = 1_000_000


def parse_rate(text: str) -> Fraction:
    """Parse an ffprobe rate like '30000/1001' or '25' into a Fraction (0 if unknown)."""
    if not text or text in ("0/0", "N/A"):
        return Fraction(0)
    if "/" in text:
        num, den = text.split("/", 1)
        den_i = int(den)
        return Fraction(int(num), den_i) if den_i else Fraction(0)
    return Fraction(text)


def snap_fps(fps: Fraction) -> Fraction:
    """Snap a measured/nominal rate to the nearest standard project rate, capped at 60."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    if fps > config.MAX_PROJECT_FPS * Fraction(105, 100):
        # 120/240 fps phone footage: keep 60 (2x / 4x decimation is clean).
        return Fraction(60)
    return min(config.STANDARD_FPS, key=lambda s: abs(s - fps))


def frames_for_duration(duration_s: Fraction, fps: Fraction) -> int:
    """Number of whole frames that fit a duration at fps (round half up)."""
    return int((duration_s * fps) + Fraction(1, 2))


def frame_to_us(frame: int, fps: Fraction) -> int:
    """Start time of a frame in microseconds (exact, rounded to nearest µs)."""
    return int(Fraction(frame) / fps * US + Fraction(1, 2))


def us_to_frame(us: int, fps: Fraction, *, mode: str = "nearest") -> int:
    """Frame index containing/nearest to a microsecond time."""
    exact = Fraction(us, US) * fps
    if mode == "floor":
        return exact.numerator // exact.denominator
    if mode == "ceil":
        return -((-exact.numerator) // exact.denominator)
    return int(exact + Fraction(1, 2))


def frame_to_sample(frame: int, fps: Fraction, rate: int = config.AUDIO_RATE) -> int:
    """Audio sample index at the start of a frame. Exact for cumulative positions."""
    return int(Fraction(frame) * rate / fps + Fraction(1, 2))


def us_to_sample(us: int, rate: int = config.AUDIO_RATE) -> int:
    return int(Fraction(us) * rate / 1_000_000 + Fraction(1, 2))


def samples_per_frame(fps: Fraction, rate: int = config.AUDIO_RATE) -> Fraction:
    return Fraction(rate) / fps


@dataclass(frozen=True)
class Segment:
    """A run of output frames taken from a source range."""

    out_start: int  # first output frame
    out_frames: int  # number of output frames

    @property
    def out_end(self) -> int:
        return self.out_start + self.out_frames


def layout_segments(frame_counts: Iterable[int]) -> list[Segment]:
    """Place segments back to back on the output frame grid."""
    segs, cursor = [], 0
    for n in frame_counts:
        if n <= 0:
            raise ValueError("segment must have at least one frame")
        segs.append(Segment(cursor, n))
        cursor += n
    return segs


def audio_bounds(segments: Iterable[Segment], fps: Fraction, rate: int = config.AUDIO_RATE) -> list[tuple[int, int]]:
    """Sample-accurate [start, end) per segment from cumulative frame positions.

    Because each boundary is computed from the absolute frame index, the sum of segment
    lengths equals the total exactly — no drift however many cuts there are.
    """
    return [(frame_to_sample(s.out_start, fps, rate), frame_to_sample(s.out_end, fps, rate)) for s in segments]
