"""Audio finishing (build step 7A): voice chain, room tone, delivery loudness (ADR-0017).

- Voice chain per reel: high-pass → de-click → denoise (tracking, floor from the measured room
  tone) → de-ess → gentle compression. De-reverb: no adequate ffmpeg filter (recorded gap).
- Room tone: the quietest ≥ 0.5 s non-speech stretch of each clip, looped under that clip's
  segments, so cut joins never jump between noise floors or drop to silence.
- Delivery loudness: two-pass `loudnorm` to −14 LUFS integrated, ≤ −1.5 dBTP, measured again on
  the encoded file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from reel import config, tools

TARGET_I = -14.0
TARGET_TP = -1.5
TARGET_LRA = 11.0
LUFS_TOLERANCE = 1.0
SILENT_LUFS = -60.0  # below this a track is treated as silence (nothing to normalise)
ROOM_TONE_MIN_US = 500_000
ROOM_TONE_MARGIN_US = 60_000  # keep clear of speech edges (breaths, tails)
ROOM_TONE_GAIN_DB = -3.0  # sits just under the voice track's own floor


def room_tone_region(pcm: np.ndarray, rate: int, speech_us: list[list[int]], *, min_us: int = ROOM_TONE_MIN_US) -> tuple[int, int, float] | None:
    """Quietest non-speech stretch ≥ min_us: (start_us, end_us, rms_dBFS), or None."""
    dur_us = int(pcm.size * 1e6 / rate)
    gaps, cursor = [], 0
    for s, e in sorted(speech_us):
        if s > cursor:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < dur_us:
        gaps.append((cursor, dur_us))
    best = None
    for s, e in gaps:
        s2, e2 = s + ROOM_TONE_MARGIN_US, e - ROOM_TONE_MARGIN_US
        if e2 - s2 < min_us:
            continue
        seg = pcm[int(s2 * rate / 1e6):int(e2 * rate / 1e6)]
        rms = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2))) if seg.size else 0.0
        db = 20 * np.log10(max(rms, 1e-9))
        if best is None or db < best[2]:
            best = (s2, e2, round(db, 1))
    return best


def voice_chain(noise_floor_db: float | None) -> str:
    nf = -50.0 if noise_floor_db is None else min(-20.0, max(-80.0, noise_floor_db))
    return (f"highpass=f=80,adeclick,afftdn=nf={nf:.0f}:tn=1,deesser=i=0.4,"
            "acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=2")


def room_tone_chain(noise_floor_db: float | None) -> str:
    nf = -50.0 if noise_floor_db is None else min(-20.0, max(-80.0, noise_floor_db))
    return f"highpass=f=80,afftdn=nf={nf:.0f}:tn=1,volume={ROOM_TONE_GAIN_DB}dB"


_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


def measure(path: Path, stream: str = "0:a:0") -> dict:
    """EBU R128 measurement (loudnorm first pass): input_i, input_tp, input_lra, input_thresh, target_offset."""
    proc = tools.run([config.ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(path), "-map", stream,
                      "-af", f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json", "-f", "null", "-"])
    m = _JSON.search(proc.stderr.decode(errors="replace"))
    if not m:
        raise tools.ToolError(["loudnorm"], 0, "no loudnorm measurement in ffmpeg output")
    return {k: float(v) for k, v in json.loads(m.group(0)).items() if k != "normalization_type"}


def loudnorm_filter(measured: dict) -> str:
    """Second pass (linear when possible); silence passes through untouched."""
    if measured["input_i"] <= SILENT_LUFS:
        return "anull"
    return (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:measured_I={measured['input_i']}:"
            f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
            f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true,"
            f"aresample={config.AUDIO_RATE}")


def check_delivery(measured: dict) -> list[str]:
    if measured["input_i"] <= SILENT_LUFS:
        return []
    problems = []
    if abs(measured["input_i"] - TARGET_I) > LUFS_TOLERANCE:
        problems.append(f"integrated loudness {measured['input_i']:.1f} LUFS (target {TARGET_I} ± {LUFS_TOLERANCE})")
    if measured["input_tp"] > TARGET_TP + 0.5:
        problems.append(f"true peak {measured['input_tp']:.1f} dBTP (max {TARGET_TP})")
    return problems
