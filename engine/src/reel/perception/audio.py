"""Decode mezzanine audio for analysis (16 kHz mono float32)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from reel import config

ANALYSIS_RATE = 16_000


def extract_wav(mezz: Path, out: Path) -> Path:
    """16 kHz mono WAV for ASR/VAD (cached next to perception outputs)."""
    if out.exists() and out.stat().st_mtime >= mezz.stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.tmp.wav")
    subprocess.run(
        [str(config.ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(mezz),
         "-vn", "-ac", "1", "-ar", str(ANALYSIS_RATE), "-c:a", "pcm_s16le", str(tmp)],
        check=True, capture_output=True,
    )
    tmp.replace(out)
    return out


def read_pcm(mezz: Path, rate: int = ANALYSIS_RATE) -> np.ndarray:
    """Mono float32 samples in [-1, 1]."""
    proc = subprocess.run(
        [str(config.ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(mezz),
         "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        check=True, capture_output=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def read_frames(mezz: Path, fps: float, width: int, *, gray: bool = False) -> tuple[np.ndarray, int, int]:
    """Decode frames at `fps`, scaled to `width` (even height). Returns (frames[N,H,W,C], H, W)."""
    vf = f"fps={fps},scale={width}:-2:flags=area"
    pix = "gray" if gray else "rgb24"
    probe = subprocess.run(
        [str(config.ffprobe_path()), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(mezz)], check=True, capture_output=True, text=True,
    ).stdout.strip().split(",")
    src_w, src_h = int(probe[0]), int(probe[1])
    h = int(round(src_h * width / src_w / 2)) * 2
    proc = subprocess.run(
        [str(config.ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(mezz),
         "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", pix, "-"],
        check=True, capture_output=True,
    )
    ch = 1 if gray else 3
    n = len(proc.stdout) // (width * h * ch)
    frames = np.frombuffer(proc.stdout[: n * width * h * ch], dtype=np.uint8).reshape(n, h, width, ch)
    return frames, h, width
