"""Checks that a mezzanine honours the single-clock contract (ADR-0015)."""

from __future__ import annotations

import re
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np

from reel import config, tools
from reel.probe import SourceProbe, probe
from reel.timebase import frames_for_duration, parse_rate

MAX_AV_OFFSET_MS = 20.0


def count_frames(path: Path) -> int:
    proc = tools.run(
        [config.ffprobe_path(), "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
        timeout=600,
    )
    return int((proc.stdout or b"0").decode().strip().rstrip(",") or 0)


def flash_time(path: Path, min_jump: float = 60.0) -> float | None:
    """Time (s) of the brightest frame if it stands out from the median luma (sync probe)."""
    proc = tools.run(
        [config.ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-an", "-f", "null", "-"],
        timeout=600,
    )
    times, values = [], []
    pts = None
    for line in (proc.stdout or b"").decode().splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            pts = float(m.group(1))
            continue
        m = re.search(r"YAVG=([\d.]+)", line)
        if m and pts is not None:
            times.append(pts)
            values.append(float(m.group(1)))
    if not values:
        return None
    arr = np.array(values)
    above = np.flatnonzero(arr - float(np.median(arr)) >= min_jump)
    return times[int(above[0])] if above.size else None  # flash onset


def beep_time(path: Path, rate: int = config.AUDIO_RATE) -> float | None:
    """Onset (s) of the first loud audio event (sync probe)."""
    proc = subprocess.run(
        [str(config.ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600, check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
    if pcm.size == 0:
        return None
    peak = float(np.abs(pcm).max())
    if peak < 1000:  # silence
        return None
    idx = np.flatnonzero(np.abs(pcm) > 0.3 * peak)
    return float(idx[0]) / rate if idx.size else None


def av_offset_ms(path: Path) -> float | None:
    """Audio onset minus flash time, in ms; None if the clip has no probe."""
    f, b = flash_time(path), beep_time(path)
    if f is None or b is None:
        return None
    return (b - f) * 1000.0


def check_mezzanine(src: SourceProbe, out: Path, fps: Fraction, *, expect_probe: bool = False) -> dict:
    """Return {'ok': bool, 'checks': {...}, 'failures': [...]}."""
    p = probe(out)
    failures: list[str] = []
    c: dict = {}
    v = p.video
    if v is None:
        return {"ok": False, "checks": {}, "failures": ["no video stream in mezzanine"]}

    c["codec"] = v.codec
    if v.codec != "prores":
        failures.append(f"codec {v.codec} != prores")
    c["pix_fmt"] = v.pix_fmt
    if v.pix_fmt != "yuv422p10le":
        failures.append(f"pix_fmt {v.pix_fmt} != yuv422p10le")
    rate = parse_rate(v.r_frame_rate)
    c["fps"] = v.r_frame_rate
    if rate != fps:
        failures.append(f"fps {v.r_frame_rate} != {fps}")
    c["vfr"] = v.is_vfr
    if v.is_vfr:
        failures.append("mezzanine is VFR")
    c["rotation"] = v.rotation
    if v.rotation != 0:
        failures.append(f"rotation metadata {v.rotation} left in mezzanine")
    c["size"] = [v.width, v.height]
    if v.width % 2 or v.height % 2:
        failures.append("odd dimensions")
    sv = src.video
    assert sv is not None
    expected_portrait = sv.display_height >= sv.display_width
    if (v.height >= v.width) != expected_portrait:
        failures.append(f"orientation changed: source display {sv.display_width}x{sv.display_height}, mezz {v.width}x{v.height}")
    c["color"] = [v.color_primaries, v.color_transfer, v.color_space, v.color_range]
    if (v.color_primaries, v.color_transfer, v.color_space) != ("bt709", "bt709", "bt709"):
        failures.append(f"colour tags {c['color']} != bt709")
    if v.hdr:
        failures.append("mezzanine still HDR")

    frames = count_frames(out)
    expected = frames_for_duration(Fraction(src.duration_s).limit_denominator(100_000), fps)
    c["frames"] = frames
    c["frames_expected"] = expected
    if abs(frames - expected) > 1:
        failures.append(f"frame count {frames} vs expected {expected} (±1)")

    a = p.audio
    c["audio"] = None if a is None else [a.codec, a.sample_rate, a.channels]
    if a is None or (a.codec, a.sample_rate, a.channels) != ("pcm_s16le", config.AUDIO_RATE, config.AUDIO_CHANNELS):
        failures.append(f"audio {c['audio']} != pcm_s16le/48000/2")

    off = av_offset_ms(out)
    c["av_offset_ms"] = None if off is None else round(off, 2)
    if off is not None and abs(off) > MAX_AV_OFFSET_MS:
        failures.append(f"A/V offset {off:.1f} ms > {MAX_AV_OFFSET_MS} ms")
    if expect_probe and off is None:
        failures.append("sync probe (flash + beep) not detected")

    return {"ok": not failures, "checks": c, "failures": failures}
