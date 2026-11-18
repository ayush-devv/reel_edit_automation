"""Snap word edges to where speech is actually heard (ADR-0002).

Whisper places word starts late/early and often ends words before the last syllable decays.
For each word we look at short-time energy around its edges and move the edge to the onset
(or decay) of sound relative to the local noise floor — never crossing a neighbouring word.
Idea follows social-video-agent's acoustic edge refinement (Apache-2.0); implementation is ours.
"""

from __future__ import annotations

import numpy as np

from reel.perception.audio import ANALYSIS_RATE
from reel.schemas.perception import Word

HOP_S = 0.010  # 10 ms energy frames
SEARCH_US = 400_000
FLOOR_PCTL = 20
ABOVE_FLOOR_DB = 10.0
MIN_SILENCE_FRAMES = 3  # 30 ms of quiet ends a word


def energy_db(pcm: np.ndarray, rate: int = ANALYSIS_RATE) -> np.ndarray:
    hop = int(rate * HOP_S)
    n = pcm.size // hop
    if n == 0:
        return np.zeros(0)
    frames = pcm[: n * hop].reshape(n, hop)
    return 20 * np.log10(np.maximum(np.sqrt((frames ** 2).mean(axis=1)), 1e-9))


def _idx(us: int) -> int:
    return int(us / 1e6 / HOP_S)


def _us(i: int) -> int:
    return int(round(i * HOP_S * 1e6))


def snap_word_edges(words: list[Word], pcm: np.ndarray, rate: int = ANALYSIS_RATE) -> dict[int, tuple[int, int]]:
    """{word index: (heard_start_us, heard_end_us)} for words of one clip, in time order."""
    e = energy_db(pcm, rate)
    if e.size == 0:
        return {w.i: (w.start_us, w.end_us) for w in words}
    out: dict[int, tuple[int, int]] = {}
    for k, w in enumerate(words):
        lo_bound = words[k - 1].end_us if k > 0 else 0
        hi_bound = words[k + 1].start_us if k + 1 < len(words) else _us(e.size)
        a = max(_idx(max(lo_bound, w.start_us - SEARCH_US)), 0)
        b = min(_idx(min(hi_bound, w.end_us + SEARCH_US)) + 1, e.size)
        window = e[a:b]
        if window.size < 3:
            out[w.i] = (w.start_us, w.end_us)
            continue
        thr = np.percentile(window, FLOOR_PCTL) + ABOVE_FLOOR_DB
        if window.max() < thr:  # no clear sound: keep ASR edges
            out[w.i] = (w.start_us, w.end_us)
            continue
        loud = np.flatnonzero(window >= thr)
        # start: first loud frame at or after the search start, but not after the word's own end
        start_i = a + int(loud[0])
        # end: walk forward from the last loud frame inside [start, ASR end + search] until quiet for MIN_SILENCE_FRAMES
        end_i = a + int(loud[-1]) + 1
        for j in range(max(start_i, _idx(w.end_us)), b):
            if np.all(e[j:j + MIN_SILENCE_FRAMES] < thr):
                end_i = j
                break
        s_us = max(lo_bound, min(_us(start_i), w.end_us - 1))
        e_us = min(hi_bound, max(_us(end_i), s_us + 1))
        out[w.i] = (s_us, e_us)
    return out
