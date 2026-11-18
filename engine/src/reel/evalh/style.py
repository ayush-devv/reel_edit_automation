"""Style family (ADR-0030 §2): how far our reel's pacing/caption/colour numbers sit from the
genre's reference library, built from the TUNING split's pro finals only (holdout excluded).
Measurements are cached in eval/cache/<id>.style.json."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from reel import config, reference
from reel.evalh import metrics as m


def cached_vector(video: Path, cache: Path) -> dict[str, float]:
    if cache.exists():
        return json.loads(cache.read_text())
    vec = reference.style_vector(reference.measure_style(video))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(vec))
    return vec


def library(reels: list[dict], resolve) -> dict[str, dict[str, list[float]]]:
    """{genre: {metric: [values]}} from tuning finals; a genre with < 3 reels falls back to all."""
    by_genre: dict[str, list[dict]] = {}
    for r in reels:
        if r.get("split") != "tuning" or not r.get("final"):
            continue
        vec = cached_vector(resolve(r["final"]), config.EVAL_DIR / "cache" / f"{r['id']}.style.json")
        by_genre.setdefault(r.get("genre") or "any", []).append(vec)
    allv = [v for vs in by_genre.values() for v in vs]
    lib = {}
    for g, vs in list(by_genre.items()) + [("any", allv)]:
        pool = vs if len(vs) >= 3 else allv
        lib[g] = {k: [v[k] for v in pool] for k in (pool[0] if pool else {})}
    return lib


def style_score(ours: dict[str, float], lib_genre: dict[str, list[float]]) -> tuple[float | None, dict]:
    parts = {k: round(m.robust_style_score(v, lib_genre[k]), 3) for k, v in ours.items() if k in lib_genre and len(lib_genre[k]) >= 3}
    return (statistics.mean(parts.values()) if parts else None), parts
