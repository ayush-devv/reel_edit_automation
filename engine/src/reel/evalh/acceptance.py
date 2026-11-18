"""Change-acceptance rule for the self-improvement loop (ADR-0030 §3). Pure functions.

Runs are per reel: {reel_id: [{"primary": float|None, "families": {fam: 0–1}, "vetoes": [...],
"language": "en"|"hi"|"hinglish"|None}, ...]}. A change is accepted only if every check holds.
"""

from __future__ import annotations

import itertools
import random
import statistics

TOLERANCE_POINTS = {"story": -2.0, "captions": -1.0, "style": -3.0, "reviewer": -3.0, "soft_gates": 0.0}
MAX_REEL_DROP = 8.0
P_MAX = 0.10
DELTA_FLOOR = 2.0


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def reel_means(runs: dict[str, list[dict]]) -> dict[str, float | None]:
    return {r: _mean([x.get("primary") for x in rs]) for r, rs in runs.items()}


def noise_sd(baseline: dict[str, list[dict]]) -> float:
    """SD of baseline-vs-baseline differences (first run vs second run of each reel)."""
    d = [rs[0]["primary"] - rs[1]["primary"] for rs in baseline.values()
         if len(rs) >= 2 and rs[0].get("primary") is not None and rs[1].get("primary") is not None]
    return statistics.stdev(d) if len(d) >= 2 else 0.0


def delta_min(baseline: dict[str, list[dict]]) -> float:
    n = max(1, len(baseline))
    return max(DELTA_FLOOR, 2 * noise_sd(baseline) / n ** 0.5)


def permutation_p(gains: list[float], *, exact_up_to: int = 16, samples: int = 20000, seed: int = 0) -> float:
    """One-sided paired sign-flip test: P(mean of randomly signed gains ≥ observed mean)."""
    if not gains:
        return 1.0
    obs = statistics.mean(gains)
    if len(gains) <= exact_up_to:
        flips = list(itertools.product((1, -1), repeat=len(gains)))
    else:
        rng = random.Random(seed)
        flips = [[rng.choice((1, -1)) for _ in gains] for _ in range(samples)]
    hits = sum(1 for f in flips if statistics.mean(g * s for g, s in zip(gains, f)) >= obs - 1e-12)
    return hits / len(flips)


def family_change_points(baseline: dict, candidate: dict) -> dict[str, float]:
    out = {}
    fams = {f for rs in list(baseline.values()) + list(candidate.values()) for x in rs for f in (x.get("families") or {})}
    for fam in fams:
        diffs = []
        for r in baseline:
            b = _mean([x["families"].get(fam) for x in baseline[r] if x.get("families")])
            c = _mean([x["families"].get(fam) for x in candidate.get(r, []) if x.get("families")])
            if b is not None and c is not None:
                diffs.append((c - b) * 100)
        if diffs:
            out[fam] = round(statistics.mean(diffs), 2)
    return out


def decide(baseline: dict[str, list[dict]], candidate: dict[str, list[dict]]) -> dict:
    reasons = []
    # 1. no new veto
    new_vetoes = [r for r in candidate if any(x.get("vetoes") for x in candidate[r]) and not any(x.get("vetoes") for x in baseline.get(r, []))]
    if new_vetoes:
        reasons.append(f"new veto on {new_vetoes}")
    bm, cm = reel_means(baseline), reel_means(candidate)
    paired = [(r, bm[r], cm.get(r)) for r in bm if bm[r] is not None and cm.get(r) is not None]
    gains = [c - b for _, b, c in paired]
    mean_gain = statistics.mean(gains) if gains else 0.0
    dmin = delta_min(baseline)
    # 2. effect size
    if mean_gain < dmin:
        reasons.append(f"mean gain {mean_gain:+.2f} < δ_min {dmin:.2f}")
    # 3. significance
    p = permutation_p(gains)
    if p > P_MAX:
        reasons.append(f"permutation p {p:.3f} > {P_MAX}")
    # 4. family tolerances
    fam = family_change_points(baseline, candidate)
    for f, tol in TOLERANCE_POINTS.items():
        if f in fam and fam[f] < tol:
            reasons.append(f"{f} {fam[f]:+.2f} below tolerance {tol:+.1f}")
    # 5. no reel collapses
    drops = [(r, round(c - b, 2)) for r, b, c in paired if c - b < -MAX_REEL_DROP]
    if drops:
        reasons.append(f"reel(s) dropped > {MAX_REEL_DROP}: {drops}")
    # 6. language subsets each non-negative
    lang = {}
    for r, b, c in paired:
        lg = next((x.get("language") for x in baseline[r] if x.get("language")), None) or "en"
        lang.setdefault("hinglish" if lg in ("hi", "hinglish") else "en", []).append(c - b)
    for lg, gs in lang.items():
        if statistics.mean(gs) < 0:
            reasons.append(f"{lg} subset {statistics.mean(gs):+.2f} < 0")
    return {"accepted": not reasons, "reasons": reasons, "mean_gain": round(mean_gain, 2), "delta_min": round(dmin, 2),
            "p": round(p, 4), "families": fam, "n_reels": len(paired), "per_language": {k: round(statistics.mean(v), 2) for k, v in lang.items()}}
