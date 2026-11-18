"""Voice activity (Silero VAD 6, MIT, ONNX) and non-lexical filler spans.

Whisper usually drops "umm/uh"; Silero still hears them. Speech that no transcribed word
covers for ≥ 150 ms becomes a cuttable filler span (ADR-0007).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from reel.perception.audio import ANALYSIS_RATE
from reel.schemas.perception import Word

MIN_FILLER_US = 150_000


@lru_cache(maxsize=1)
def _model():
    from silero_vad import load_silero_vad

    return load_silero_vad(onnx=True)


def speech_regions(pcm: np.ndarray, rate: int = ANALYSIS_RATE) -> list[tuple[int, int]]:
    """Speech regions as (start_us, end_us)."""
    import torch
    from silero_vad import get_speech_timestamps

    if pcm.size == 0:
        return []
    ts = get_speech_timestamps(torch.from_numpy(np.ascontiguousarray(pcm)), _model(), sampling_rate=rate,
                               min_silence_duration_ms=120, speech_pad_ms=30)
    return [(int(t["start"] * 1e6 / rate), int(t["end"] * 1e6 / rate)) for t in ts]


def filler_spans(regions: list[tuple[int, int]], words: list[Word], min_us: int = MIN_FILLER_US) -> list[tuple[int, int]]:
    """Parts of speech regions not covered by any word, at least `min_us` long."""
    covered = sorted((w.start_us, w.end_us) for w in words)
    spans = []
    for rs, re_ in regions:
        cursor = rs
        for ws, we in covered:
            if we <= cursor or ws >= re_:
                continue
            if ws - cursor >= min_us:
                spans.append((cursor, ws))
            cursor = max(cursor, we)
        if re_ - cursor >= min_us:
            spans.append((cursor, re_))
    return spans


def analyse(wav_pcm: np.ndarray, words: list[Word]) -> dict:
    regions = speech_regions(wav_pcm)
    return {
        "speech": [list(r) for r in regions],
        # Candidates, not certainties: Whisper ends words early, so breaths/tails also appear here.
        # The compiler/Claude decide; audio-edge snapping (step 4) refines them.
        "filler_candidates": [list(s) for s in filler_spans(regions, words)],
        "speech_ratio": round(sum(e - s for s, e in regions) / max(1, int(wav_pcm.size * 1e6 / ANALYSIS_RATE)), 4),
    }
