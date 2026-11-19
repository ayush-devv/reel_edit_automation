"""Music structure for the bed (roadmap G1.4): real beats and downbeats, and where the track drops.

- Beats/downbeats: Beat This! (CPJKU, MIT code and weights, `pip install beat-this==1.1.0`, checkpoint `final0`), run
  with `dbn=False` so madmom (non-commercial models) is never needed. Missing package or checkpoint → librosa beats with
  "every 4th beat" downbeats, as before.
- The drop: plain DSP (no model, so no model-licence question): RMS energy before vs after each downbeat; the downbeat
  with the largest sustained rise, if it rises enough, is the drop. compile.music_offset_us lands it right after the hook.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

log = logging.getLogger(__name__)
CHECKPOINT = "final0"
DROP_WINDOW_S = 4.0  # energy compared over 4 s before and after a downbeat
DROP_MIN_RISE_DB = 6.0  # set conservatively: the library's borderline 4.5–5.5 dB rises are left out (not listened to yet)
DROP_MIN_LEVEL_DB = -30.0  # the after-window must be loud in absolute terms (not a rise from silence to quiet)


CHECKPOINT_SHA256 = "8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331"  # final0, fetched 2026-11-20


@lru_cache(maxsize=1)
def _model():
    import hashlib
    from pathlib import Path

    import torch
    from beat_this.inference import Audio2Beats  # optional dependency: the `music` extra

    model = Audio2Beats(checkpoint_path=CHECKPOINT, device="cpu", dbn=False)  # downloads once into the torch.hub cache
    ck = Path(torch.hub.get_dir()) / "checkpoints" / f"beat_this-{CHECKPOINT}.ckpt"
    if not ck.is_file() or hashlib.sha256(ck.read_bytes()).hexdigest() != CHECKPOINT_SHA256:
        raise RuntimeError(f"Beat This! checkpoint {ck} is missing or not the pinned file")
    return model


def tracker_name() -> str:
    try:
        from importlib.metadata import version

        return f"beat_this {version('beat-this')} {CHECKPOINT}"
    except Exception:  # noqa: BLE001
        return "librosa"


def beats(y: np.ndarray, rate: int) -> tuple[float, list[int], list[int], str]:
    """(bpm, beat times ms, downbeat times ms, tracker). Beat This! when installed, else librosa."""
    try:
        b, d = _model()(np.ascontiguousarray(y, dtype=np.float32), rate)
        beat_ms = [int(round(float(t) * 1000)) for t in b]
        down_ms = [int(round(float(t) * 1000)) for t in d]
        if len(beat_ms) >= 2:
            bpm = round(60_000 / float(np.median(np.diff(beat_ms))), 1)
            return bpm, beat_ms, down_ms, tracker_name()
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 — a tracker failure falls back, never stops indexing
        log.warning("beat_this failed (%s); using librosa beats", exc)
    from reel.library import librosa_beats

    bpm, beat_ms, down_ms = librosa_beats(y, rate)
    return bpm, beat_ms, down_ms, "librosa"


def rms_db(y: np.ndarray, rate: int, hop_s: float = 0.1) -> np.ndarray:
    hop = max(1, int(rate * hop_s))
    n = y.size // hop
    if n == 0:
        return np.array([-120.0])
    frames = y[: n * hop].astype(np.float64).reshape(n, hop)
    return 20 * np.log10(np.maximum(np.sqrt((frames ** 2).mean(axis=1)), 1e-6))


def find_drop(y: np.ndarray, rate: int, downbeats_ms: list[int], hop_s: float = 0.1) -> dict | None:
    """The downbeat after which the track gets clearly louder and stays there: {drop_ms, rise_db} or None."""
    env = rms_db(y, rate, hop_s)
    w = int(DROP_WINDOW_S / hop_s)
    best = None
    for d in downbeats_ms:
        k = int(round(d / 1000 / hop_s))
        if k - w < 0 or k + w > env.size:
            continue
        before, after = float(np.mean(env[k - w:k])), float(np.mean(env[k:k + w]))
        rise = after - before
        if rise >= DROP_MIN_RISE_DB and after >= DROP_MIN_LEVEL_DB and (best is None or rise > best["rise_db"]):
            best = {"drop_ms": int(d), "rise_db": round(rise, 1)}
    return best
