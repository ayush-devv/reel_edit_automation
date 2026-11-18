"""Palette-adaptive caption tokens (build step 10c, ADR-0017 brand-first).

After compiling, sample the source pixels behind each caption page (caption band of the
mezzanine frame at the page's midpoint) and make the Editor's tokens legible on this footage:
  - fill colour below 4.5:1 against the band and no outline/box → add an outline (dark or light);
  - emphasis colour that blends into the band (< 3:1) → the most legible candidate from the
    footage palette + a few accents.
Keys the brand kit set are never changed. Every change is recorded with its reason.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np

from reel import qa
from reel import timebase as tb
from reel.schemas.timeline import Timeline

BAND = (0.45, 0.85)  # where captions can sit (below the chin, above the platform UI), share of frame height
CLASH_RATIO = 2.0  # a pixel this close in luminance contrast makes text over it vanish
MAX_CLASH = 0.10  # more than this share of the band → change the colour / add an outline
ACCENTS = ["#FFD400", "#00E5FF", "#FF3B6B", "#7CFF4F", "#FFFFFF", "#FF8A00"]


def _on(v: str | None) -> bool:
    return bool(v) and (v == "true" or v.startswith("#"))


def band_samples(tl: Timeline, root: Path, max_pages: int = 24) -> np.ndarray:
    """RGB pixels of the caption band behind sampled caption pages (from the mezzanine)."""
    fps = tb.parse_rate(tl.fps)
    clips = sorted((c for c in tl.video if c.id.startswith("v_")), key=lambda c: c.at_f)
    pages = tl.captions.pages if tl.captions else []
    step = max(1, len(pages) // max_pages)
    want: dict[str, list[int]] = {}
    for p in pages[::step]:
        mid = (p.start_f + p.end_f) // 2
        c = next((c for c in clips if c.at_f <= mid < c.at_f + c.dur_f), None)
        if c is None:
            continue
        src_f = tb.us_to_frame(c.src_in_us, fps) + int((mid - c.at_f) * c.speed)
        want.setdefault(c.asset, []).append(src_f)
    px = []
    for asset, frames in want.items():
        for img in qa.frames_at(root / tl.assets[asset].uri, frames, width=160).values():
            h = img.shape[0]
            px.append(img[int(BAND[0] * h):int(BAND[1] * h)].reshape(-1, 3))
    return np.concatenate(px) if px else np.zeros((0, 3), dtype=np.uint8)


def _lum_px(px: np.ndarray) -> np.ndarray:
    c = px.astype(np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722])


def clash_share(colour: str, lum: np.ndarray) -> float:
    """Share of band pixels against which `colour` falls below CLASH_RATIO contrast (local, not average:
    yellow text on the yellow part of a striped background vanishes even if the average is grey)."""
    lc = qa.luminance(qa.hex_rgb(colour)[:3])
    hi, lo = np.maximum(lum, lc), np.minimum(lum, lc)
    return float(((hi + 0.05) / (lo + 0.05) < CLASH_RATIO).mean())


def adapt(tl: Timeline, root: Path, palette: list[str], locked: set[str]) -> tuple[Timeline, list[str]]:
    if not tl.captions or not tl.captions.pages:
        return tl, []
    px = band_samples(tl, root)
    if px.size == 0:
        return tl, []
    lum = _lum_px(px)
    t = dict(tl.captions.tokens)
    changes = []
    base = t.get("base_color") or "#FFFFFF"
    fill_clash = clash_share(base, lum)
    if not _on(t.get("stroke")) and not _on(t.get("box")) and "stroke" not in locked:
        # captions over live video always get an outline unless they sit on a plate: real footage (white
        # sugar, bright windows) defeats any fill colour somewhere, and sampling can't see every frame
        outline = "#000000" if qa.luminance(qa.hex_rgb(base)[:3]) > 0.4 else "#FFFFFF"
        t["stroke"] = outline
        changes.append(f"no outline or plate (fill vanishes on {fill_clash:.0%} of sampled background) → outline {outline}")
    emph = t.get("emph_color")
    if emph and "emph_color" not in locked and clash_share(emph, lum) > MAX_CLASH:
        cands = [c for c in dict.fromkeys(palette + ACCENTS) if c.lower() != base.lower()]
        best = min(cands, key=lambda c: (clash_share(c, lum), c not in palette))
        if clash_share(best, lum) < clash_share(emph, lum):
            changes.append(f"emphasis {emph} vanishes on {clash_share(emph, lum):.0%} of the band → {best} ({clash_share(best, lum):.0%})")
            t["emph_color"] = best
    if not changes:
        return tl, []
    return tl.model_copy(update={"captions": tl.captions.model_copy(update={"tokens": t})}), changes
