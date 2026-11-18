"""Per-shot reframing (found on real multi-camera podcast footage): one median face per clip
puts the speaker at the edge or shows the back of a head after every camera switch.

Each base clip is split at the source's scene cuts; every shot is centred on the median of its
largest face (4 fps samples), inheriting the previous shot's centre when no face is visible.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from fractions import Fraction

from reel import timebase as tb
from reel.schemas.timeline import VideoClip

DEFAULT_CENTRE = (0.5, 0.45)


@dataclass
class Shot:
    start_f: int  # clip-relative output frame where this shot starts
    centre: tuple[float, float]  # normalised source coords
    box: dict | None  # median largest-face box (normalised source coords)


def _largest(faces: list[dict]) -> dict | None:
    return max(faces, key=lambda b: b["w"] * b["h"]) if faces else None


def shots(c: VideoClip, fps: Fraction, cuts_us: list[int], samples: list[dict], fallback: tuple[float, float] = DEFAULT_CENTRE) -> list[Shot]:
    src0, src1 = c.src_in_us, c.src_out_us
    bounds = [src0] + [u for u in sorted(cuts_us) if src0 < u < src1] + [src1]
    out: list[Shot] = []
    prev = fallback
    for a, b in zip(bounds, bounds[1:]):
        boxes = [bx for s in samples if a <= s["t_us"] < b and (bx := _largest(s.get("faces") or []))]
        if boxes:
            box = {k: statistics.median(bx[k] for bx in boxes) for k in ("x", "y", "w", "h")}
            centre = (box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
        else:
            box, centre = None, prev
        start_f = round(tb.us_to_frame(a - src0, fps) / c.speed)
        if out and start_f <= out[-1].start_f:
            continue
        out.append(Shot(start_f=start_f, centre=centre, box=box))
        prev = centre
    return out or [Shot(0, fallback, None)]


def piecewise(values: list[float], starts: list[int], var: str = "n", fmt: str = "{:.0f}") -> str:
    """Step expression over clip-relative frames: value k from starts[k] until starts[k+1]."""
    expr = fmt.format(values[-1])
    for v, nxt in zip(reversed(values[:-1]), reversed(starts[1:])):
        expr = f"if(lt({var},{nxt}),{fmt.format(v)},{expr})"
    return expr
