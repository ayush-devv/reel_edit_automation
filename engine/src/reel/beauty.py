"""Beauty pass, opt-in (roadmap 3c.1): gently smoother skin on the speaker's face, never "filtered".

Off unless the brief (`beauty: true`) or the brand kit (`beauty: "light"`) turns it on. Applied to the rendered base
(render/base.mov), so it follows every cut, punch-in and crop exactly as the viewer sees them:
1. face boxes from the MediaPipe Face Landmarker (already used by the cover stage) on frames sampled at SAMPLE_FPS;
2. a feathered elliptical skin matte, interpolated between samples, written as a small grey video;
3. ffmpeg: a capped edge-preserving `bilateral` blur plus a very small brightness lift, blended in only inside the matte.
A measured check (`beauty_strength` QA gate) compares face-region detail before and after and warns past MAX_DETAIL_LOSS,
so "never reads as filtered" is measured, not promised. There is no age detection: the UI says not to use it on minors.
"""

from __future__ import annotations

import functools
import json
import subprocess
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

from reel import config
from reel.workspace import atomic_write_json, tmp_path_for

SAMPLE_FPS = 6
MASK_W = 270  # matte resolution (scaled up to the frame, then feathered)
LIGHT = {"sigmaS": 5, "sigmaR": 0.06, "brightness": 0.01}  # toned down after looking at real frames (2026-11-20)
MAX_DETAIL_LOSS = 0.35  # warn when the face loses more than this share of its fine detail (Laplacian variance)
CHECK_FRAMES = 8


def mode(brief, brand) -> str:
    """'light' or 'off'. The brief can turn it on for one reel; the brand kit for every reel of a client."""
    if brief is not None and getattr(brief, "beauty", False):
        return "light"
    if brand is not None and getattr(brand, "beauty", "off") == "light":
        return "light"
    return "off"


@functools.lru_cache(maxsize=4)
def _grid(w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return yy, xx


def _soft_ellipse(xx, yy, cx, cy, rx, ry, edge: float = 0.5) -> np.ndarray:
    d = ((xx - cx) / max(rx, 1.0)) ** 2 + ((yy - cy) / max(ry, 1.0)) ** 2
    return np.clip((1.0 + edge / 2 - d) / edge, 0.0, 1.0)


# Where the eyes and the mouth sit in a Face Landmarker box (forehead top → chin), as fractions of the box. Checked on
# the _real_doac_v2 frames (2026-11-20): smoothing them read as "filtered", so they are carved out of the skin matte.
EYES = (0.42, 0.80, 0.13)  # centre y, width, height
MOUTH = (0.79, 0.42, 0.13)


def ellipse(box: dict, w: int, h: int) -> np.ndarray:
    """A feathered skin matte inside a normalised face box: the face ellipse (inset so hair and background stay
    sharp) minus the eye band and the mouth, which must stay crisp."""
    yy, xx = _grid(w, h)
    bx, by, bw, bh = box["x"] * w, box["y"] * h, box["w"] * w, box["h"] * h
    skin = _soft_ellipse(xx, yy, bx + bw / 2, by + bh * 0.55, bw * 0.42, bh * 0.48)
    eyes = _soft_ellipse(xx, yy, bx + bw / 2, by + bh * EYES[0], bw * EYES[1] / 2, bh * EYES[2] / 2, edge=0.8)
    mouth = _soft_ellipse(xx, yy, bx + bw / 2, by + bh * MOUTH[0], bw * MOUTH[1] / 2, bh * MOUTH[2] / 2, edge=0.8)
    return skin * (1 - eyes) * (1 - mouth)


def boxes_per_frame(samples: dict[int, dict | None], total: int) -> list[dict | None]:
    """Linear interpolation between sampled boxes; None where no face is near (no smoothing there)."""
    keys = sorted(f for f, b in samples.items() if b)
    out: list[dict | None] = [None] * total
    if not keys:
        return out
    for f in range(total):
        prev = max((k for k in keys if k <= f), default=None)
        nxt = min((k for k in keys if k >= f), default=None)
        if prev is None or nxt is None:
            k = prev if prev is not None else nxt
            out[f] = samples[k] if abs(k - f) <= SAMPLE_FPS else None
            continue
        if nxt - prev > 3 * (1 + SAMPLE_FPS):  # a long gap with no face sampled: the face may have left the frame
            out[f] = samples[prev] if f - prev <= SAMPLE_FPS else (samples[nxt] if nxt - f <= SAMPLE_FPS else None)
            continue
        t = 0.0 if nxt == prev else (f - prev) / (nxt - prev)
        a, b = samples[prev]["box"], samples[nxt]["box"]
        out[f] = {"box": {k: a[k] + (b[k] - a[k]) * t for k in ("x", "y", "w", "h")}}
    return out


def filter_graph(strength: dict = LIGHT) -> str:
    return (f"[0:v]split[a][b];[b]bilateral=sigmaS={strength['sigmaS']}:sigmaR={strength['sigmaR']},eq=brightness={strength['brightness']}[s];"
            f"[1:v]format=gray,gblur=sigma=4[m0];[m0][a]scale2ref=flags=bilinear[m][a2];[s][m]alphamerge[sm];[a2][sm]overlay=format=auto[v]")


def _write_mask(boxes: list[dict | None], w: int, h: int, fps: Fraction, out: Path) -> None:
    proc = subprocess.Popen([str(config.ffmpeg_path()), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                             "-r", f"{fps.numerator}/{fps.denominator}", "-i", "-", "-c:v", "ffv1", str(out)], stdin=subprocess.PIPE)
    blank = np.zeros((h, w), np.uint8).tobytes()
    try:
        for b in boxes:
            proc.stdin.write((ellipse(b["box"], w, h) * 255).astype(np.uint8).tobytes() if b else blank)
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("beauty matte encode failed")


def detail(frames: dict[int, np.ndarray], boxes: list[dict | None]) -> float | None:
    from reel.cover import laplacian_var

    vals = []
    for f, rgb in frames.items():
        b = boxes[f] if f < len(boxes) else None
        if not b:
            continue
        h, w = rgb.shape[:2]
        x0, y0 = int(b["box"]["x"] * w), int(b["box"]["y"] * h)
        x1, y1 = int((b["box"]["x"] + b["box"]["w"]) * w), int((b["box"]["y"] + b["box"]["h"]) * h)
        crop = rgb[max(0, y0):y1, max(0, x0):x1].mean(axis=2) if rgb.ndim == 3 else rgb
        if crop.size > 100:
            vals.append(laplacian_var(crop))
    return float(np.mean(vals)) if vals else None


def apply(base: Path, total_frames: int, fps: Fraction, *, detect=None, sample=None) -> dict:
    """Smooth the face in base.mov in place. Returns what was done and the measured detail loss."""
    from reel import qa
    from reel.cover import detect_faces
    from reel.render import encode_args

    detect = detect or detect_faces
    sample = sample or (lambda path, frames: qa.frames_at(path, frames, width=MASK_W))
    t0 = time.time()
    step = max(1, round(float(fps) / SAMPLE_FPS))
    picks = list(range(0, total_frames, step))
    frames = sample(base, picks)
    found = detect(frames)
    boxes = boxes_per_frame(found, total_frames)
    if not any(boxes):
        return {"applied": False, "why": "no face found", "seconds": round(time.time() - t0, 1)}
    h_w = next(iter(frames.values())).shape[:2]
    mask = base.with_name("beauty_mask.mkv")
    _write_mask(boxes, MASK_W, int(round(MASK_W * h_w[0] / h_w[1] / 2) * 2), fps, mask)
    tmp = tmp_path_for(base)
    subprocess.run([str(config.ffmpeg_path()), "-v", "error", "-y", "-i", str(base), "-i", str(mask), "-filter_complex", filter_graph(),
                    "-map", "[v]", "-map", "0:a?", *encode_args(tmp)], check=True)
    check = picks[:: max(1, len(picks) // CHECK_FRAMES)][:CHECK_FRAMES]
    before = detail(sample(base, check), boxes)
    after = detail(sample(tmp, check), boxes)
    tmp.replace(base)
    loss = round(1 - after / before, 3) if before and after is not None else None
    meta = {"applied": True, "mode": "light", "faces_sampled": sum(1 for b in found.values() if b), "detail_loss": loss,
            "seconds": round(time.time() - t0, 1)}
    atomic_write_json(base.with_name("beauty.json"), meta)
    return meta


def gate_result(render_dir: Path):
    """QA `beauty_strength`: warn when the face lost too much detail (it would read as filtered)."""
    from reel import qa

    f = render_dir / "beauty.json"
    if not f.exists():
        return qa.GateResult("beauty_strength", True, detail="beauty pass off")
    m = json.loads(f.read_text())
    if not m.get("applied"):
        return qa.GateResult("beauty_strength", True, detail=f"beauty pass on, not applied: {m.get('why', '')}")
    loss = m.get("detail_loss")
    if loss is None:
        return qa.GateResult("beauty_strength", False, detail="beauty pass applied, detail loss not measured")
    return qa.GateResult("beauty_strength", loss <= MAX_DETAIL_LOSS, detail=f"face detail −{loss:.0%} (limit {MAX_DETAIL_LOSS:.0%})",
                         fix_hint="Turn the beauty pass off for this reel, or ask for it to be lighter.", measured=m)
