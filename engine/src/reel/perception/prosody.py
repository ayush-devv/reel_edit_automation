"""Audio energy curve and per-segment delivery stats (inputs to selects, ADR-0016)."""

from __future__ import annotations

import numpy as np

from reel.perception.audio import ANALYSIS_RATE
from reel.schemas.perception import SegmentTable, WordTable

HOP_US = 100_000


def rms_db(pcm: np.ndarray, rate: int = ANALYSIS_RATE, hop_us: int = HOP_US) -> list[float]:
    """RMS level per hop in dBFS (floor −90)."""
    hop = int(rate * hop_us / 1e6)
    if pcm.size == 0 or hop <= 0:
        return []
    n = pcm.size // hop
    frames = pcm[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return [round(float(v), 1) for v in np.maximum(20 * np.log10(np.maximum(rms, 1e-9)), -90.0)]


def segment_stats(words: WordTable, segments: SegmentTable, energy_db: dict[str, list[float]], hop_us: int = HOP_US) -> list[dict]:
    by = words.by_index()
    out = []
    for s in segments.segments:
        ws = [by[i] for i in range(s.word_start, s.word_end + 1)]
        span = max(1, s.end_us - s.start_us)
        spoken = sum(w.end_us - w.start_us for w in ws)
        curve = energy_db.get(s.clip, [])
        a, b = s.start_us // hop_us, max(s.start_us // hop_us + 1, s.end_us // hop_us)
        level = curve[a:b]
        voiced = [v for v in level if v > -50]
        out.append({
            "seg_id": s.seg_id,
            "clip": s.clip,
            "words": len(ws),
            "words_per_s": round(len(ws) / (span / 1e6), 2),
            "pause_ratio": round(max(0.0, 1 - spoken / span), 3),
            "loudness_db": round(float(np.mean(voiced)), 1) if voiced else None,
            "loudness_range_db": round(float(np.percentile(voiced, 90) - np.percentile(voiced, 10)), 1) if len(voiced) > 3 else None,
            "asr_conf": round(float(np.mean([w.prob for w in ws])), 3),
            "fillers": sum(1 for w in ws if w.filler or w.candidate_filler),
            "suspect_words": [w.i for w in ws if w.suspect],
            "low_conf_words": [w.i for w in ws if w.low_conf],
            "proof_words": [w.i for w in ws if w.vocab_suspect],
        })
    return out
