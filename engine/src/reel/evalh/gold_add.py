"""`reel gold add` (roadmap 3b.5): add one gold pair (raw footage + the pro's finished reel) in two minutes.

The acceptance rule for `reel improve` already checks each language subset (evalh/acceptance.py), but with 6 English
pairs the Hindi/Hinglish subset never exists. This makes adding a pair one command, and refuses a final that wasn't
cut from that raw: its speech-loudness envelope must line up with some stretch of the raw's.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import numpy as np
import yaml

from reel.evalh import harness

ENV_HZ = 20  # loudness envelope rate
PROBE_S = 30.0  # how much of the final is matched against the raw
WINDOW_S = 1.5  # piece length: shorter than a pro's typical shot
# Margin above chance, measured on the 6 gold pairs (2026-11-20): own raw +0.047 … +0.205 (5 of 6 above +0.13),
# another pair's raw −0.002 … +0.046. The two overlap, so this is a guard against an obviously wrong pair, not proof:
# below MIN_MATCH is refused (--no-check overrides); below WEAK_MATCH is accepted with a warning to look again.
MIN_MATCH = 0.03
WEAK_MATCH = 0.08
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}


class GoldError(ValueError):
    pass


def envelope(path: Path) -> np.ndarray:
    from reel.perception.audio import ANALYSIS_RATE, read_pcm

    pcm = read_pcm(path).astype(np.float32)
    hop = ANALYSIS_RATE // ENV_HZ
    n = len(pcm) // hop
    return np.sqrt((pcm[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12) if n else np.zeros(0, np.float32)


def _window_best(q: np.ndarray, w: np.ndarray) -> float:
    q = (q - q.mean()) / (q.std() + 1e-9)
    return float((w @ q).max() / len(q))


def best_match(final_env: np.ndarray, raw_env: np.ndarray, probe_s: float = PROBE_S) -> float:
    """How well the final's speech lines up with this raw: a pro reel jump-cuts every 1–2 s, so each WINDOW_S piece of
    the final's first `probe_s` is matched on its own against any stretch of the raw; the score is their median."""
    n = int(WINDOW_S * ENV_HZ)
    pieces = [final_env[i:i + n] for i in range(0, min(len(final_env), int(probe_s * ENV_HZ)) - n + 1, n)]
    pieces = [p for p in pieces if p.std() > 1e-6]
    if len(pieces) < 2 or len(raw_env) < n:
        return 0.0
    win = np.lib.stride_tricks.sliding_window_view(raw_env, n)
    w = (win - win.mean(axis=1, keepdims=True)) / (win.std(axis=1, keepdims=True) + 1e-9)
    return float(np.median([_window_best(p, w) for p in pieces]))


def match_margin(final_env: np.ndarray, raw_env: np.ndarray) -> float:
    """best_match above chance: the same match against the raw played backwards (same loudness statistics, no true
    alignment). Short pieces fit somewhere in a long raw by luck (≈ 0.71 on the gold set), so the margin is what counts."""
    return best_match(final_env, raw_env) - best_match(final_env, raw_env[::-1].copy())


def add_pair(raw: Path, final: Path, *, language: str, split: str = "tuning", genre: str | None = None, channel: str | None = None,
             pair_id: str | None = None, gold_dir: Path | None = None, check=True) -> dict:
    gold_dir = gold_dir or harness.GOLD_DIR
    if language not in ("en", "hi", "hinglish"):
        raise GoldError("language must be en, hi or hinglish")
    if split not in ("tuning", "holdout"):
        raise GoldError("split must be tuning or holdout")
    raws = [raw] if raw.is_file() else sorted(p for p in raw.iterdir() if p.suffix.lower() in VIDEO_EXT) if raw.is_dir() else []
    if not raws:
        raise GoldError(f"no raw video at {raw}")
    if not final.is_file():
        raise GoldError(f"no final reel at {final}")
    if check:
        fe = envelope(final)
        score = round(max(match_margin(fe, envelope(r)) for r in raws), 3)
        if score < MIN_MATCH:
            raise GoldError(f"the final doesn't line up with this raw footage (match {score:.2f} above chance, need {MIN_MATCH}): "
                            "is it the right pair?")
    else:
        score = None
    pid = pair_id or re.sub(r"[^a-z0-9_-]+", "-", final.stem.casefold()).strip("-")[:60] or f"pair-{int(time.time())}"
    d = gold_dir / pid
    if d.exists():
        raise GoldError(f"a gold pair {pid!r} already exists")
    (d / "raw").mkdir(parents=True)
    for r in raws:
        shutil.copy2(r, d / "raw" / r.name)
    shutil.copy2(final, d / "final.mp4")
    from reel.probe import probe

    dur = probe(d / "final.mp4").duration_s
    brief = {"project": pid, "language": language, "target_length_s": [round(dur * 0.8, 1), round(dur * 1.2, 1)],
             "notes": "Cut a vertical short-form reel from this footage, like the pro final."}
    if genre:
        brief["genre_hint"] = genre
    (d / "brief.json").write_text(json.dumps(brief, indent=1, ensure_ascii=False))
    (d / "source.json").write_text(json.dumps({"channel": channel, "added": time.time(), "match": score}, indent=1))
    manifest = harness.init_manifest()
    if split == "holdout":  # existing assignments are kept by init_manifest; set this new pair's split explicitly
        for r in manifest["reels"]:
            if r["id"] == pid:
                r["split"] = "holdout"
        harness.MANIFEST.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    counts = {"pairs": len(manifest["reels"]), "hindi_hinglish": sum(r.get("language") in ("hi", "hinglish") for r in manifest["reels"])}
    weak = score is not None and score < WEAK_MATCH
    return {"id": pid, "match": score, "duration_s": round(dur, 1), **counts,
            **({"warning": f"weak audio match ({score:+.3f}): watch the final next to the raw to be sure they belong together"} if weak else {})}
