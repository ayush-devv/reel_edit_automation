"""Gold metrics and the primary score (ADR-0030 §2). Pure functions, no I/O."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# ---------------------------------------------------------------- story


def set_iou(a: Iterable[int], b: Iterable[int]) -> float:
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def hook_iou(pred_hook_words: Iterable[int], gold_hook_words: Iterable[int]) -> float:
    """Overlap of the opening segment's source word indices."""
    return set_iou(pred_hook_words, gold_hook_words)


def f1(pred: Iterable[int], gold: Iterable[int]) -> float:
    p, g = set(pred), set(gold)
    if not p and not g:
        return 1.0
    tp = len(p & g)
    if tp == 0:
        return 0.0
    precision, recall = tp / len(p), tp / len(g)
    return 2 * precision * recall / (precision + recall)


def kendall_tau(pred_order: Sequence[str], gold_order: Sequence[str]) -> float | None:
    """Kendall's tau-a over items present in both orders; None if fewer than 3 shared."""
    shared = [x for x in pred_order if x in set(gold_order)]
    if len(shared) < 3:
        return None
    gold_pos = {x: i for i, x in enumerate(gold_order)}
    seq = [gold_pos[x] for x in shared]
    n = len(seq)
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            if seq[i] < seq[j]:
                concordant += 1
            elif seq[i] > seq[j]:
                discordant += 1
    return (concordant - discordant) / (n * (n - 1) / 2)


def cut_rate_score(pred_cuts_per_min: float, gold_cuts_per_min: float) -> float:
    """1 at equal pace, falling to 0 at a 2x difference either way."""
    if pred_cuts_per_min <= 0 or gold_cuts_per_min <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(math.log2(pred_cuts_per_min / gold_cuts_per_min)))


def story_score(hook: float, word_f1: float, tau: float | None, cut_rate: float) -> float:
    """ADR-0030: .30 hook IoU + .35 word-keep F1 + .15 (tau+1)/2 + .20 cut-rate; tau dropped (re-weighted) if None."""
    parts = [(0.30, hook), (0.35, word_f1), (0.20, cut_rate)]
    if tau is not None:
        parts.append((0.15, (tau + 1) / 2))
    total_w = sum(w for w, _ in parts)
    return sum(w * s for w, s in parts) / total_w


# ---------------------------------------------------------------- captions


def word_error_rate(ref: Sequence[str], hyp: Sequence[str]) -> float:
    """Word-level Levenshtein distance / len(ref). Missing captions count as deletions."""
    ref = [w.lower() for w in ref]
    hyp = [w.lower() for w in hyp]
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def median_timing_error_ms(pairs: Iterable[tuple[float, float]]) -> float | None:
    """pairs = (predicted_onset_s, reference_onset_s) for matched words."""
    errs = [abs(p - r) * 1000 for p, r in pairs]
    return statistics.median(errs) if errs else None


def caption_score(wer: float, median_err_ms: float | None) -> float:
    """ADR-0030: .6 (1 - WER) + .4 (1 - median timing error / 150 ms)."""
    acc = max(0.0, 1.0 - wer)
    timing = 0.0 if median_err_ms is None else max(0.0, 1.0 - median_err_ms / 150.0)
    return 0.6 * acc + 0.4 * timing


# ---------------------------------------------------------------- style


def robust_style_score(value: float, ref_values: Sequence[float]) -> float:
    """1 inside the reference IQR, decaying with robust z beyond it (median/MAD)."""
    if len(ref_values) < 3:
        return 1.0
    vals = sorted(ref_values)
    q1, med, q3 = statistics.quantiles(vals, n=4)
    if q1 <= value <= q3:
        return 1.0
    mad = statistics.median([abs(v - med) for v in vals]) or 1e-9
    z = abs(value - med) / (1.4826 * mad)
    return max(0.0, 1.0 - (z - 0.6745) / 3.0)  # 0.6745 ≈ z at the quartiles


# ---------------------------------------------------------------- primary score

WEIGHTS = {"story": 0.40, "captions": 0.20, "style": 0.15, "soft_gates": 0.10, "reviewer": 0.15}


def reviewer_weight_factor(kappa: float | None) -> float:
    """0 until calibrated; .5 at kappa >= .4; 1 at kappa >= .6 (ADR-0030)."""
    if kappa is None or kappa < 0.4:
        return 0.0
    return 0.5 if kappa < 0.6 else 1.0


@dataclass
class ReelScore:
    families: dict[str, float] = field(default_factory=dict)  # each in [0, 1]
    vetoes: list[str] = field(default_factory=list)
    reviewer_kappa: float | None = None

    @property
    def primary(self) -> float | None:
        """0–100 over the families present; None when vetoed or nothing to score."""
        if self.vetoes:
            return None
        num = den = 0.0
        for fam, s in self.families.items():
            w = WEIGHTS[fam] * (reviewer_weight_factor(self.reviewer_kappa) if fam == "reviewer" else 1.0)
            if w <= 0:
                continue
            num += w * s
            den += w
        return None if den == 0 else round(100 * num / den, 2)
