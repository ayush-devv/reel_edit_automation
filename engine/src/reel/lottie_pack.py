"""Our own starter pack of Lottie animations (owned, no licence questions), written as plain Lottie JSON.

White strokes/fills, so `reel.lottie.load_for_render` can recolour them to the brand accent. 30 fps, 512 px canvas
(the underline is wide). `reel assets fetch` writes them to assets/lottie/procedural/ and indexes them.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

FR = 30
WHITE = [1, 1, 1, 1]
EASE_OUT = {"o": {"x": [0.2], "y": [0]}, "i": {"x": [0.1], "y": [1]}}
EASE_IO = {"o": {"x": [0.4], "y": [0]}, "i": {"x": [0.2], "y": [1]}}


def static(v):
    return {"a": 0, "k": v}


def anim(*keys, ease=EASE_OUT):
    """keys: (frame, value) pairs; the last key has no easing."""
    out = []
    for n, (t, v) in enumerate(keys):
        k = {"t": t, "s": v if isinstance(v, list) else [v]}
        if n < len(keys) - 1:
            k.update(ease)
        out.append(k)
    return {"a": 1, "k": out}


def tr(p=(0, 0), s=100, r=0, o=100):
    return {"ty": "tr", "p": static(list(p)), "a": static([0, 0]), "s": s if isinstance(s, dict) else static([s, s]),
            "r": r if isinstance(r, dict) else static(r), "o": o if isinstance(o, dict) else static(o), "sk": static(0), "sa": static(0)}


def path(points, closed=False, tangents=None):
    n = len(points)
    zero = [[0, 0]] * n
    ins, outs = (tangents or (zero, zero))
    return {"ty": "sh", "ks": static({"i": ins, "o": outs, "v": [list(p) for p in points], "c": closed})}


def stroke(w=26):
    return {"ty": "st", "c": static(WHITE), "o": static(100), "w": static(w), "lc": 2, "lj": 2, "ml": 4}


def fill():
    return {"ty": "fl", "c": static(WHITE), "o": static(100), "r": 1}


def trim(start=None, end=None):
    return {"ty": "tm", "s": start or static(0), "e": end or static(100), "o": static(0), "m": 1}


def group(items, name="g", transform=None):
    return {"ty": "gr", "nm": name, "it": [*items, transform or tr()]}


def layer(shapes, op, *, p=(256, 256), s=None, o=None, r=None, ind=1, name="shape"):
    ks = {"o": o or static(100), "r": r or static(0), "p": static([*p, 0]), "a": static([0, 0, 0]), "s": s or static([100, 100, 100])}
    return {"ddd": 0, "ind": ind, "ty": 4, "nm": name, "sr": 1, "ks": ks, "ao": 0, "shapes": shapes, "ip": 0, "op": op, "st": 0, "bm": 0}


def comp(name, layers, op, w=512, h=512):
    return {"v": "5.7.4", "fr": FR, "ip": 0, "op": op, "w": w, "h": h, "nm": name, "ddd": 0, "assets": [], "layers": layers}


def pop(t0=0, peak=115, settle=100):
    return anim((t0, [0, 0, 100]), (t0 + 8, [peak, peak, 100]), (t0 + 14, [settle, settle, 100]))


# ------------------------------------------------------------------ the pack


def check_draw():
    op = 45
    ring = group([{"ty": "el", "p": static([0, 0]), "s": static([360, 360])}, stroke(24), trim(end=anim((0, 0), (14, 100)))], "ring")
    tick = group([path([(-90, 0), (-25, 62), (100, -70)]), stroke(30), trim(end=anim((10, 0), (24, 100)))], "tick")
    return comp("check_draw", [layer([ring, tick], op, s=pop())], op)


def arrow_bounce():
    op = 48
    shaft = path([(0, -150), (0, 120)])
    head = path([(-80, 40), (0, 125), (80, 40)])
    body = group([shaft, head, stroke(30), trim(end=anim((0, 0), (10, 100)))], "arrow")
    y = anim((10, [256, 236, 0]), (20, [256, 270, 0]), (30, [256, 236, 0]), (40, [256, 270, 0]), (48, [256, 256, 0]), ease=EASE_IO)
    lay = layer([body], op)
    lay["ks"]["p"] = y
    return comp("arrow_bounce", [lay], op)


def pulse_ring():
    op = 36
    layers = []
    for n, t0 in enumerate((0, 8, 16)):
        ring = group([{"ty": "el", "p": static([0, 0]), "s": static([300, 300])}, stroke(22)], "ring")
        layers.append(layer([ring], op, ind=n + 1, s=anim((t0, [20, 20, 100]), (t0 + 20, [150, 150, 100])),
                            o=anim((t0, 100), (t0 + 12, 100), (t0 + 20, 0)), name=f"ring{n}"))
    return comp("pulse_ring", layers, op)


def sparkle_burst():
    op = 30
    rays = []
    for n in range(8):
        a = n * math.pi / 4
        rays.append(group([path([(0, -70), (0, -200)]), stroke(20),
                           trim(start=anim((6, 0), (20, 100)), end=anim((0, 0), (12, 100)))], f"ray{n}", tr(r=math.degrees(a))))
    star = group([{"ty": "sr", "sy": 1, "d": 1, "pt": static(4), "p": static([0, 0]), "r": static(0), "ir": static(18), "is": static(0),
                   "or": static(60), "os": static(0)}, fill()], "star")
    return comp("sparkle_burst", [layer([star], op, ind=1, s=anim((0, [0, 0, 100]), (8, [120, 120, 100]), (24, [0, 0, 100])), name="star"),
                                  layer(rays, op, ind=2, name="rays")], op)


def underline_swipe():
    op = 30
    k = 0.35
    pts = [(-230, 10), (0, -12), (230, 6)]
    tangents = ([[0, 0], [-230 * k, 0], [-60, -10]], [[60, -10], [230 * k, 0], [0, 0]])
    line = group([path(pts, tangents=tangents), stroke(22), trim(end=anim((0, 0), (12, 100)))], "swipe")
    return comp("underline_swipe", [layer([line], op, p=(256, 80))], op, w=512, h=160)


def heart_pop():
    op = 30
    # Sharp tip at the bottom and a cusp at the top: zero tangents there; round lobes elsewhere.
    v = [(0, 105), (-120, -10), (-62, -100), (0, -62), (62, -100), (120, -10)]
    ins = [[0, 0], [0, 55], [-40, 0], [0, 0], [-25, 0], [0, -50]]
    outs = [[0, 0], [0, -50], [25, 0], [0, 0], [40, 0], [0, 55]]
    heart = group([path(v, closed=True, tangents=(ins, outs)), fill()], "heart")
    return comp("heart_pop", [layer([heart], op, s=pop(peak=125))], op)


PACK = {
    "check_draw": (check_draw, "a ring and a check mark draw themselves, then settle", ["check", "done", "yes", "correct", "tick"]),
    "arrow_bounce": (arrow_bounce, "an arrow draws itself and bounces, pointing down", ["arrow", "point", "look", "down", "here"]),
    "pulse_ring": (pulse_ring, "three rings pulse outward and fade", ["pulse", "ring", "attention", "ping", "focus"]),
    "sparkle_burst": (sparkle_burst, "a four-point star flashes with rays bursting outward", ["sparkle", "burst", "wow", "highlight", "magic"]),
    "underline_swipe": (underline_swipe, "a hand-drawn underline swipes across (wide)", ["underline", "emphasis", "swipe", "stroke"]),
    "heart_pop": (heart_pop, "a heart pops in with an overshoot", ["heart", "love", "like", "favourite"]),
}


def build_all(folder: Path) -> dict[str, dict]:
    """Write every animation; returns per-file metadata for `reel.lottie.index_folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    meta = {}
    for name, (make, desc, tags) in PACK.items():
        (folder / f"{name}.json").write_text(json.dumps(make(), separators=(",", ":")))
        meta[name] = {"description": desc, "tags": tags, "recolour": True}
    return meta
