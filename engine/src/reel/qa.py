"""QA gates measured on the render (ADR-0006, ADR-0017, ADR-0021).

Every gate returns a GateResult with measurements and the offending timecodes. Its mode
(`block` | `warn`) comes from config.QA_GATES: measured gates start as `warn` until their
false-positive rate on owner-sendable renders is known (`reel calibrate`).
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np

from reel import config, mix
from reel import timebase as tb
from reel.brief import Brief
from reel.schemas.timeline import Timeline
from reel.validate import norm

DEAD_AIR_S = 1.5
FROZEN_S = 3.0
MIN_CONTRAST = 4.5
MAX_CPS = 20.0  # sustained over READ_WINDOW_S, not per page
READ_WINDOW_S = 3.0
FACE_OVERLAP_MAX = 0.03  # share of the face box covered by overlay pixels
SAMPLE_W = 270  # analysis width (1080 / 4)
HEAD_TAIL_S = 0.5  # black entirely inside the first/last 0.5 s is a designed fade-in/out, not a defect
FULLSCREEN_GRAPHICS = {"text_card"}  # Graphics.tsx FULLSCREEN (cta_card style=card is treated as full-screen too)


@dataclass
class GateResult:
    gate: str
    ok: bool
    mode: str = "warn"
    detail: str = ""
    at: list[str] = field(default_factory=list)  # timecodes of failures
    fixable: bool = False  # can the Editor fix it with a revision?
    fix_hint: str = ""
    measured: dict = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return not self.ok and self.mode == "block"

    def as_dict(self) -> dict:
        return asdict(self)


def tc(frame: int, fps: Fraction) -> str:
    t = float(Fraction(frame) / fps)
    return f"{int(t // 60)}:{t % 60:05.2f}"


# ------------------------------------------------------------------ pixels


FRAMES_PER_CALL = 40  # ffmpeg's expression parser fails (ENOMEM) beyond ~100 select terms


def frames_at(path: Path, frames: list[int], *, width: int = SAMPLE_W, alpha: bool = False) -> dict[int, np.ndarray]:
    """Decode exactly these frame numbers (scaled to `width`) → {frame: HxWxC uint8}. Chunked: long
    reels have hundreds of caption pages and one huge select expression breaks ffmpeg."""
    if not frames:
        return {}
    wanted = sorted(set(frames))
    pix = "rgba" if alpha else "rgb24"
    probe = subprocess.run([str(config.ffprobe_path()), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], check=True, capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    height = int(round(h * width / w / 2) * 2)
    ch = 4 if alpha else 3
    out: dict[int, np.ndarray] = {}
    for k in range(0, len(wanted), FRAMES_PER_CALL):
        chunk = wanted[k:k + FRAMES_PER_CALL]
        sel = "+".join(f"eq(n\\,{f})" for f in chunk)
        raw = subprocess.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(path), "-vf", f"select='{sel}',scale={width}:{height}:flags=area",
                              "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", pix, "-"], check=True, capture_output=True).stdout
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width, ch)
        out.update(zip(chunk, arr))
    return out


def _lin(c: np.ndarray) -> np.ndarray:
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(rgb) -> float:
    r, g, b = _lin(np.asarray(rgb, dtype=np.float64).reshape(-1, 3)).mean(axis=0)
    return float(0.2126 * r + 0.7152 * g + 0.0722 * b)


def contrast_ratio(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hex_rgb(h: str) -> tuple[int, int, int, float]:
    h = h.lstrip("#")
    r, g, b = (int(h[k:k + 2], 16) for k in (0, 2, 4))
    a = int(h[6:8], 16) / 255 if len(h) >= 8 else 1.0
    return r, g, b, a


# ------------------------------------------------------------------ gates on the timeline


def _js_round(x: float) -> int:
    """JavaScript Math.round (halves round up; Python's round() rounds halves to even)."""
    return int(math.floor(x + 0.5))


def _num(v: str | None, d: float) -> float:
    try:
        return float(v) if v is not None else d
    except ValueError:
        return d


def skip_windows(tl: Timeline) -> list[tuple[int, int]]:
    """Half-open frame windows where the overlay cannot be judged as captions at all: full-screen
    graphics (text_card, cta_card style=card) and white flashes (±1 frame), mirroring Overlay.tsx/Graphics.tsx."""
    out = [(g.start_f, g.end_f) for g in tl.graphics if g.kind in FULLSCREEN_GRAPHICS or (g.kind == "cta_card" and g.style == "card")]
    out += [(f.at_f - f.frames // 2 - 1, f.at_f + f.frames // 2 + 2) for f in tl.flashes]
    return out


def page_samples(tl: Timeline) -> list[tuple[int, float]]:
    """(frame to sample, modelled caption opacity at that frame) per caption page.

    Mirrors Overlay.tsx: `fade` (and phrase timing) fades the page in over animF frames, `slide_fade` fades the page
    and each word in over animF, and a page not followed back-to-back fades out over its last 3 frames. The midpoint is
    kept when it is fully opaque and judgeable; otherwise the fully opaque frame nearest to it, otherwise the frame of
    peak opacity (a very short page may never reach full opacity: the gate then does not call it see-through).
    Frames inside skip_windows are avoided when the page has any other frame."""
    if not tl.captions:
        return []
    fps = float(tb.parse_rate(tl.fps))
    t = tl.captions.tokens
    anim = "fade" if tl.captions.timing == "phrase" else t.get("anim")
    anim_f = max(1, _js_round(_num(t.get("anim_ms"), 150) / 1000 * fps))
    skips = skip_windows(tl)
    pages = tl.captions.pages
    clamp = lambda x: min(1.0, max(0.0, x))  # noqa: E731
    out = []
    for p in pages:
        nxt = next((q for q in pages if q.start_f >= p.end_f), None)
        back_to_back = nxt is not None and nxt.start_f - p.end_f <= 1
        first_word = min((w.start_f for w in p.words), default=p.start_f)

        def opacity(f: int, p=p, back_to_back=back_to_back, first_word=first_word) -> float:
            k = 1.0
            if anim in ("fade", "slide_fade"):
                k = clamp((f - p.start_f) / anim_f)
            if anim == "slide_fade":  # the most visible word: the first one
                k *= clamp((f - first_word) / anim_f)
            if not back_to_back:
                k *= clamp((p.end_f - f) / 3)
            return k

        mid = (p.start_f + p.end_f) // 2
        frames = list(range(p.start_f, max(p.start_f + 1, p.end_f)))
        free = [f for f in frames if not any(s <= f < e for s, e in skips)] or frames
        full = [f for f in free if opacity(f) >= 0.999]
        if full:
            best = min(full, key=lambda f: (abs(f - mid), f))
        else:
            best = max(free, key=lambda f: (opacity(f), f))  # ties: the latest frame
        out.append((best, opacity(best)))
    return out


def page_frames(tl: Timeline) -> list[int]:
    return [f for f, _ in page_samples(tl)]


def reading_speed(tl: Timeline) -> GateResult:
    """Sustained reading rate: characters shown per second over a sliding READ_WINDOW_S window of output time.

    A page's own chars ÷ duration is no measure for word-synced 1–3-word pages: they follow speech, and a 0.3 s page of
    one word is not "unreadable". What a viewer cannot follow is more text over a few seconds than they can read, so
    each page counts in a window by the share of its duration that lies inside it. Limit: MAX_CPS (20 chars/s, the
    common adult subtitle ceiling; normal speech of ~3 words/s shows ~15–18)."""
    fps = tb.parse_rate(tl.fps)
    pages = [(p.start_f, p.end_f, sum(len(w.text) for w in p.words) + max(0, len(p.words) - 1))
             for p in (tl.captions.pages if tl.captions else []) if p.end_f > p.start_f]
    if not pages:
        return GateResult("reading_speed", True, detail="no captions", measured={"max_cps": 0.0})
    win = _js_round(READ_WINDOW_S * float(fps))
    win = max(1, min(win, tl.duration_f) if tl.duration_f > 0 else win)  # a reel shorter than the window: the whole reel
    last = max(0, max(tl.duration_f, max(e for _, e, _ in pages)) - win)
    # the shown-characters curve is piecewise linear in the window start: its maxima sit where a window edge meets a page edge
    starts = sorted({min(last, max(0, x)) for s, e, _ in pages for x in (s, e - win)})

    def rate(t0: int) -> float:
        shown = sum(c * max(0, min(e, t0 + win) - max(s, t0)) / (e - s) for s, e, c in pages)
        return shown / float(Fraction(win) / fps)

    rates = [(rate(t), t) for t in starts]
    worst, worst_t = max(rates, key=lambda x: (x[0], -x[1]))
    runs: list[list[tuple[float, int]]] = []  # chains of overlapping failing windows = one dense stretch each
    for r, t in rates:
        if r > MAX_CPS:
            if runs and t < runs[-1][-1][1] + win:
                runs[-1].append((r, t))
            else:
                runs.append([(r, t)])
    bad = [tc(max(run, key=lambda x: (x[0], -x[1]))[1], fps) for run in runs]  # each stretch at its densest window
    page_max = max(c / max(float(Fraction(e - s) / fps), 1e-6) for s, e, c in pages)
    secs = float(Fraction(win) / fps)
    return GateResult("reading_speed", not bad, detail=f"max {worst:.1f} chars/s over {secs:.1f} s at {tc(worst_t, fps)} (limit {MAX_CPS:.0f})",
                      at=bad, fixable=True, fix_hint="Cut or shorten the lines in the densest stretch, or slow the cut there.",
                      measured={"max_cps": round(worst, 1), "worst_at": tc(worst_t, fps), "window_s": round(secs, 2),
                                "max_page_cps": round(page_max, 1)})


def dead_air(tl: Timeline) -> GateResult:
    """Gaps between kept words on the output timeline (captions hold the non-filler words)."""
    fps = tb.parse_rate(tl.fps)
    words = sorted((w.start_f, w.end_f) for p in (tl.captions.pages if tl.captions else []) for w in p.words)
    gaps = []
    edges = [(0, 0)] + words + [(tl.duration_f, tl.duration_f)]
    for (_s0, e0), (s1, _e1) in zip(edges, edges[1:]):
        if float(Fraction(s1 - e0) / fps) > DEAD_AIR_S:
            gaps.append(tc(e0, fps))
    return GateResult("dead_air", not gaps, detail=f"{len(gaps)} gap(s) > {DEAD_AIR_S} s without speech", at=gaps, fixable=True,
                      fix_hint="Tighten the cut around these pauses or cover them with b-roll/music.")


def brief_compliance(tl: Timeline, kept_text: str, brief: Brief | None) -> GateResult:
    if not brief:
        return GateResult("brief", True, mode="block", detail="no brief")
    kept = norm(" ".join(kept_text.split()))
    kept_tokens = kept_text.lower().split()
    problems = []

    def present(line: str, need: float) -> bool:
        toks = [norm(t) for t in line.split() if norm(t)]
        if not toks:
            return True
        kt = {norm(t) for t in kept_tokens}
        return sum(t in kt for t in toks) / len(toks) >= need

    for line in brief.must_keep_lines:
        if not present(line, 0.8):
            problems.append(f"must-keep line missing: “{line}”")
    for claim in brief.banned_claims:
        if norm(claim) and norm(claim) in kept:
            problems.append(f"banned claim present: “{claim}”")
    if brief.cta and not present(brief.cta, 0.6):
        problems.append(f"CTA missing: “{brief.cta}”")
    return GateResult("brief", not problems, mode="block", detail="; ".join(problems) or "must-keep, banned claims, CTA ok",
                      fixable=bool(problems), fix_hint="Keep every must-keep line and the CTA; remove banned claims.")


def numbers_match(fin, story, words) -> GateResult:
    """Safety net for the plan-time check: on-screen numbers that disagree with the speech (or nobody says)."""
    from reel.validate import number_checks

    if fin is None:
        return GateResult("numbers", True, detail="no finish plan")
    found = number_checks(fin, story, words)
    return GateResult("numbers", not found, detail="; ".join(f"{p}: “{s}” ({st}) — {', '.join(d)}" for p, s, st, d in found)
                      or "on-screen numbers match the speech", fixable=bool(found),
                      fix_hint="Show the number the speaker says, or drop it.", measured={"checks": [list(f[:3]) for f in found]})


def proof_words(proof: list[dict], confirmed: dict) -> GateResult:
    open_ = [p for p in proof if str(p["i"]) not in confirmed]
    return GateResult("proof_words", not open_, mode="block",
                      detail=(f"{len(open_)} unconfirmed caption word(s): " + ", ".join(f"{p['at']} “{p['text']}” ({p['why']})" for p in open_)) if open_ else "all caption words confirmed",
                      at=[p["at"] for p in open_], measured={"open": open_})


def face_cut(tl: Timeline, faces_props: list[dict]) -> GateResult:
    """Median face box per clip, grown by the clip's largest punch-in around the face centre."""
    fps = tb.parse_rate(tl.fps)
    bad = []
    clips = [c for c in tl.video if c.id.startswith("v_")]
    for span in faces_props:
        box = span.get("box")
        c = next((c for c in clips if c.at_f <= span["start_f"] < c.at_f + c.dur_f), None)
        if not box or c is None:
            continue
        s = max([k.v for k in c.scale] + [1.0])
        cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
        x0, x1 = cx - box["w"] * s / 2, cx + box["w"] * s / 2
        y0, y1 = cy - box["h"] * s / 2, cy + box["h"] * s / 2
        if min(x0, y0) < -0.05 * box["w"] or max(x1, y1) > 1 + 0.05 * box["w"]:
            bad.append(tc(span["start_f"], fps))
    return GateResult("face_cut", not bad, detail=f"{len(bad)} clip(s) crop the face", at=bad, fixable=True,
                      fix_hint="Reduce the punch-in scale on these clips.")


# ------------------------------------------------------------------ gates on pixels


# The overlay also carries hook titles, motion graphics, PiP b-roll cards and flashes. Caption gates must judge
# captions only, so each sampled frame gets a mask of where those other elements can be, rebuilt from the timeline
# with the placements of renderer/src/Overlay.tsx + Graphics.tsx (output px, padded for springs, shadows, wraps).
# Captions themselves live in a band ~0.45H – (H − safe.bottom); no mask covers the bottom UI zone full-width, so a
# caption drifting there (or onto a face outside these regions) is still caught.

MASK_PAD = 30
CAPTION_TOP = 0.58  # Graphics.tsx captionTop: graphics are placed above this share of the height


def _span_at(faces: list[dict], f: int) -> dict | None:
    return next((s for s in faces if s["start_f"] <= f < s["end_f"]), None)


def _clear_of(top: float, h: float, boxes: list[dict], H: float, direction: int, min_top: float, max_bottom: float,
              x0: float = -math.inf, x1: float = math.inf, W: float = 1) -> float:
    """Overlay.tsx clearOf: move a block off the text boxes it overlaps."""
    t = top
    for _ in range(4):
        hit = next((b for b in boxes if t < (b["y"] + b["h"]) * H and b["y"] * H < t + h and x0 < (b["x"] + b["w"]) * W and b["x"] * W < x1), None)
        if not hit:
            break
        t = (hit["y"] + hit["h"]) * H + 24 if direction > 0 else hit["y"] * H - h - 24
    return min(max(t, min_top), max_bottom - h)


def _place_clear(top: float, h: float, face: dict | None, tl: Timeline, safe: dict) -> float:
    """Graphics.tsx placeClear: keep a block off the face and above the caption band."""
    H = tl.height
    min_top, max_top = safe["top"], CAPTION_TOP * H - h - 16
    t = min(max(top, min_top), max_top)
    if not face:
        return t
    fy0, fy1 = face["y"] * H - 24, (face["y"] + face["h"]) * H + 24
    if t + h <= fy0 or t >= fy1:
        return t
    if fy0 - h >= min_top:
        return fy0 - h
    if fy1 <= max_top:
        return fy1
    return max(min_top, max_top)


def _graphic_rects(g, tl: Timeline, faces: list[dict], safe: dict) -> list[tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) output-px regions a live graphic can paint (Graphics.tsx placements, padded)."""
    W, H, P = tl.width, tl.height, MASK_PAD
    st, sl, sr = safe["top"], safe["left"], safe["right"]
    safe_w = W - sl - sr
    face = (_span_at(faces, g.start_f) or {}).get("box")
    k = g.kind
    if k == "progress_bar":
        return [(0, 0, W, 40)]
    if k == "logo_watermark":  # 140×120 box near the top corner (older renders: 60 px higher)
        x0 = W - sr - 140 if g.position != "top_left" else sl
        return [(x0 - 20, st - 80, x0 + 160, st + 150)]
    if k == "emoji_pop":
        if not g.uri:
            return []
        size, left, top = 170, W - sr - 200, st + 60
        if g.position == "upper_left":
            left = sl + 30
        if g.position == "beside_face" and face:
            right = (face["x"] + face["w"]) * W
            left = right + size * 0.2 if right + size * 0.2 + size <= W - sr else face["x"] * W - size * 1.2
            top = max(st, face["y"] * H - size * 0.3)
        else:
            top = _place_clear(top, size, face, tl, safe)
        left = min(max(left, sl), W - sr - size)
        top = min(max(top, st), CAPTION_TOP * H - size)
        return [(left - 60, top - 60, left + size + 60, top + size + 60)]  # float ±12, back-out overshoot, shadow
    if k == "keyword_card":
        words = g.text.split()
        size = _js_round(min(124, (safe_w - 40) / (max(1, len(g.text)) * 0.68 + len(words) * 0.24 + 0.6)))
        top = _place_clear(0.46 * H if g.position == "center" else st + 90, size * 1.25, face, tl, safe)
        return [(0, top - 40 - P, W, top + size * 1.05 * 1.6 + P)]  # words rise from 60 % below, exit 40 px up
    if k == "lower_third":
        role = len(re.split(r"\s+[·|—–-]\s+", g.text)) > 1
        top = _place_clear(st + 40, 130 if role else 90, face, tl, safe)
        return [(sl + 20 - P, top - P, W - sr + P, top + 160 + P)]
    if k == "counter":
        pre, _, post = g.text.partition("{n}")
        chars = len(pre) + len(post) + len(str(int(abs(g.value))))  # fewest characters → the largest size it can take
        size = _js_round(min(150, (safe_w - 20) / max(1, chars * 0.66)))
        top = _place_clear(0.46 * H if g.position == "center" else st + 80, size * 1.2, face, tl, safe)
        return [(0, top - 0.15 * size - P, W, top + size * 1.35 + P)]  # pops 0.6 → ~1.1× around its centre
    if k == "cta_card":  # style=card counts as full-screen (skip_windows); the pill slams in from 2.2× around its centre
        hc = 58 * 1.2 * 2 + 36
        c = st + 60 + hc / 2
        return [(0, c - 2.2 * hc / 2 - P, W, c + 2.2 * hc / 2 + P)]
    if k == "callout":
        cx, cy, rx, ry = g.x * W, g.y * H, 150.0, 150.0
        if g.position == "face" and face:
            cx, cy = (face["x"] + face["w"] / 2) * W, (face["y"] + face["h"] / 2) * H
            rx, ry = face["w"] * W / 2 * 1.35, face["h"] * H / 2 * 1.3
        elif g.position == "face":
            cx, cy = W / 2, 0.35 * H
        if g.style in ("circle", "box"):
            xs, ys = (cx - rx, cx + rx), (cy - ry, cy + ry)
        elif g.style == "underline":
            xs, ys = (cx - rx, cx + rx), (cy + ry - 6, cy + ry + 18)
        else:  # arrow from upper-right towards the point (the curve stays inside its control hull)
            sx, sy = min(W - sr - 20, cx + 260), max(st + 40, cy - 300)
            ex, ey = cx + 40, cy - 40
            xs, ys = (min(sx, ex) - 46, max(sx, (sx + ex) / 2 + 60, ex)), (min(sy, ey) - 46, max(sy, ey) + 46)
        rects = [(xs[0] - 40, ys[0] - 40, xs[1] + 40, ys[1] + 40)]  # stroke 11, drop shadow, −3° tilt
        if g.text:
            label_top = min(cy + ry + 30, CAPTION_TOP * H - 70)
            lw = len(g.text) * 48 * 0.62 + 36
            rects.append((W / 2 - lw / 2 - P, label_top - 10, W / 2 + lw / 2 + P, label_top + 80))
        return rects
    return []  # text_card / cta card: skip_windows; unknown kinds are not drawn (Graphics.tsx KINDS)


def non_caption_mask(tl: Timeline, f: int, shape: tuple[int, int], faces: list[dict], safe: dict) -> np.ndarray | None:
    """Boolean mask (sample resolution) of overlay pixels at frame f that are not captions, or None when the frame
    cannot be judged as captions at all (full-screen card, flash)."""
    if any(s <= f < e for s, e in skip_windows(tl)):
        return None
    h, w = shape
    kx, ky = w / tl.width, h / tl.height
    m = np.zeros((h, w), dtype=bool)

    def rect(x0: float, y0: float, x1: float, y1: float) -> None:
        r0, r1 = max(0, math.floor(y0 * ky)), min(h, math.ceil(y1 * ky))
        c0, c1 = max(0, math.floor(x0 * kx)), min(w, math.ceil(x1 * kx))
        if r0 < r1 and c0 < c1:
            m[r0:r1, c0:c1] = True

    W, H, P = tl.width, tl.height, MASK_PAD
    title = next((t for t in tl.titles if t.layer != "behind" and t.start_f <= f < t.end_f), None)
    if title:  # Overlay.tsx Titles (front layer): a 70 px card near the top, pushed off on-screen text, never below 0.5H
        max_w = W - safe["left"] - safe["right"]
        lines = math.ceil(len(title.text) * 70 * 0.54 / (max_w - 60))
        th = lines * 70 * 1.12 + 36
        top = _clear_of(safe["top"] + 70, th, (_span_at(faces, title.start_f) or {}).get("text") or [], H, +1, safe["top"], 0.5 * H)
        rect(safe["left"] - P, top - P, W - safe["right"] + P, top + th + P)
    for g in tl.graphics:
        if g.start_f <= f < g.end_f:
            for r in _graphic_rects(g, tl, faces, safe):
                rect(*r)
    for pip in tl.pips:  # Overlay.tsx PipCard: 0.42W × 4:3 card in a corner; 5 px border, 18/50 px drop shadow
        if pip.start_f <= f < pip.end_f:
            pw = _js_round(W * 0.42)
            ph = _js_round(pw * 4 / 3)
            left = safe["left"] + 20 if pip.corner.endswith("left") else W - safe["right"] - pw - 20
            top = H - safe["bottom"] - ph - 20 if pip.corner.startswith("bottom") else safe["top"] + 40
            rect(left - 40, top - 40, left + pw + 40, top + ph + 80)
    return m


def caption_layer(tl: Timeline, f: int, rgba: np.ndarray, faces: list[dict], safe: dict) -> np.ndarray | None:
    """Copy of an overlay sample with every non-caption pixel made transparent; None if the frame is not judgeable."""
    m = non_caption_mask(tl, f, rgba.shape[:2], faces, safe)
    if m is None:
        return None
    out = rgba.copy()
    out[..., 3][m] = 0
    return out


def caption_pixels(tl: Timeline, base: Path, overlay: Path, faces_props: list[dict], safe: dict, flashes: list[tuple[int, int]]) -> list[GateResult]:
    """Contrast, caption-over-face and safe-zone from the overlay alpha and the base pixels behind it."""
    frames = page_frames(tl)
    if not frames:
        return [GateResult(g, True, detail="no captions") for g in ("caption_contrast", "caption_over_face", "safe_zone")]
    return caption_pixels_from(tl, frames_at(overlay, frames, alpha=True), frames_at(base, frames), faces_props, safe, flashes)


FAINT_ALPHA = 0.5  # caption pixels that never reach this opacity are see-through


def caption_pixels_from(tl: Timeline, ov: dict, bg: dict, faces_props: list[dict], safe: dict, flashes: list[tuple[int, int]]) -> list[GateResult]:
    """`ov` / `bg`: frame → RGBA overlay / RGB base samples (from frames_at). Contrast uses the fill colour the
    overlay actually rendered (not only the tokens), so a caption drawn too faint or in the wrong colour is caught."""
    fps = tb.parse_rate(tl.fps)
    t = tl.captions.tokens
    fill = hex_rgb(t.get("base_color") or t.get("speaker_a") or "#FFFFFF")[:3]
    on = lambda v: v == "true" or bool(re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", v or ""))  # noqa: E731
    stroke_rgb = hex_rgb(t["stroke"])[:3] if on(t.get("stroke")) and t["stroke"].startswith("#") else (0, 0, 0)
    stroke = on(t.get("stroke"))
    box_hex = t.get("box_color") or (t["box"] if (t.get("box") or "").startswith("#") else "#000000B3")
    box = hex_rgb(box_hex) if on(t.get("box")) else None
    low, over_face, out_safe, skipped, partial, worst = [], [], [], [], [], 99.0
    for f, op in page_samples(tl):
        o, b = ov.get(f), bg.get(f)
        if o is None or b is None:
            continue
        a_all = o[..., 3] / 255.0  # every overlay pixel: only to keep drawn pixels out of the background sample
        h, w = a_all.shape
        mask = non_caption_mask(tl, f, (h, w), faces_props, safe)
        if mask is None or any(s <= f < e for s, e in flashes) or op < 0.2:  # full-screen card, flash, page never visible
            skipped.append(tc(f, fps))
            continue
        a = np.where(mask, 0.0, a_all)  # caption pixels only
        if op < 0.999:
            partial.append(tc(f, fps))  # a page too short to reach full opacity: judged at its peak, never "see-through"
        thr = FAINT_ALPHA * min(1.0, op)
        ys, xs = np.nonzero(a > thr)
        if ys.size == 0:
            if op >= 0.999 and (a > 0.05).mean() > 0.002:  # a caption is drawn but nowhere opaque: see-through text
                low.append(tc(f, fps))
                worst = min(worst, 1.0)
            continue
        # background right behind the caption block (bbox, excluding anything drawn)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        region = b[y0:y1, x0:x1][a_all[y0:y1, x0:x1] < 0.05]
        behind = region.reshape(-1, 3) if region.size else b[y0:y1, x0:x1].reshape(-1, 3)
        if box:
            behind = (np.asarray(box[:3]) * box[3] + behind.mean(axis=0) * (1 - box[3]))[None, :]
        solid = o[..., :3][a > 0.9 * min(1.0, op)].reshape(-1, 3).astype(float)
        if solid.shape[0] >= 20:
            # legibility of what was actually rendered: the text's brightest and darkest parts (fill and outline)
            # against the background, or against each other (an outline carries text on any background)
            lum = solid @ np.array([0.2126, 0.7152, 0.0722])
            lo, hi = solid[lum <= np.percentile(lum, 10)].mean(axis=0), solid[lum >= np.percentile(lum, 90)].mean(axis=0)
            ratio = max(contrast_ratio(hi, behind), contrast_ratio(lo, behind), contrast_ratio(hi, lo) if stroke else 0.0)
        else:  # too few opaque pixels to measure: fall back to what the style tokens promise
            ratio = contrast_ratio(fill, behind)
            if stroke:
                ratio = max(ratio, contrast_ratio(fill, stroke_rgb))
        worst = min(worst, ratio)
        if ratio < MIN_CONTRAST:
            low.append(tc(f, fps))
        # caption over face
        span = next((s for s in faces_props if s["start_f"] <= f < s["end_f"]), None)
        fb = (span or {}).get("box")
        if fb:
            fy0, fy1 = int(fb["y"] * h), int((fb["y"] + fb["h"]) * h)
            fx0, fx1 = int(fb["x"] * w), int((fb["x"] + fb["w"]) * w)
            face_a = a[max(0, fy0):fy1, max(0, fx0):fx1]
            if face_a.size and float((face_a > thr).mean()) > FACE_OVERLAP_MAX:
                over_face.append(tc(f, fps))
        # safe zone (px on the 1080x1920 grid, scaled to the sample)
        k = w / tl.width
        if (y0 < safe["top"] * k or y1 > h - safe["bottom"] * k or x0 < safe["left"] * k or x1 > w - safe["right"] * k):
            out_safe.append(tc(f, fps))
    note = f"; {len(skipped)} page(s) not judged (full-screen card or flash)" if skipped else ""
    meas = {"skipped": skipped, "partial_opacity": partial}
    return [
        GateResult("caption_contrast", not low, detail=f"lowest {worst:.1f}:1 (min {MIN_CONTRAST}:1){note}", at=low, fixable=True,
                   fix_hint="Use a boxed or stroked caption style, or a fill colour that stands out from the footage.",
                   measured={"min_ratio": round(worst, 2), **meas}),
        GateResult("caption_over_face", not over_face, detail=f"{len(over_face)} page(s) cover the face{note}", at=over_face, fixable=True,
                   fix_hint="Move captions to a zone below the face (lower_third) or use fewer words per page.", measured=dict(meas)),
        GateResult("safe_zone", not out_safe, detail=f"{len(out_safe)} page(s) outside the safe zone{note}", at=out_safe, fixable=True,
                   fix_hint="Shorter pages or a lower_middle zone.", measured=dict(meas)),
    ]


_BLACK = re.compile(r"black_start:([\d.]+) black_end:([\d.]+)")


def frozen_and_black(tl: Timeline, final: Path, dips: list[tuple[int, int]]) -> list[GateResult]:
    fps = tb.parse_rate(tl.fps)
    proc = subprocess.run([str(config.ffmpeg_path()), "-hide_banner", "-nostdin", "-i", str(final), "-map", "0:v",
                           "-vf", f"freezedetect=n=-60dB:d={FROZEN_S},blackdetect=d=0.1:pix_th=0.10", "-f", "null", "-"],
                          capture_output=True, text=True)
    log = proc.stderr
    frozen = [(float(a), float(b)) for a, b in re.findall(r"freeze_start: ([\d.]+)[\s\S]*?freeze_end: ([\d.]+)", log)]
    starts = re.findall(r"freeze_start: ([\d.]+)", log)
    if len(starts) > len(frozen):  # freeze running to the end has no freeze_end line
        frozen.append((float(starts[-1]), float(Fraction(tl.duration_f) / fps)))
    blacks = [(float(a), float(b)) for a, b in _BLACK.findall(log)]
    dip_s = [(float(Fraction(s) / fps) - 0.05, float(Fraction(e) / fps) + 0.05) for s, e in dips]
    blacks = [(a, b) for a, b in blacks if not any(ds <= a and b <= de for ds, de in dip_s)]
    # a black stretch entirely inside the first/last HEAD_TAIL_S is a designed fade-in/out (one frame of tolerance)
    dur_s, tol = float(Fraction(tl.duration_f) / fps), float(1 / fps)
    edge = [(a, b) for a, b in blacks if b <= HEAD_TAIL_S + tol or a >= dur_s - HEAD_TAIL_S - tol]
    blacks = [x for x in blacks if x not in edge]
    fmt = lambda s: f"{int(s // 60)}:{s % 60:05.2f}"  # noqa: E731
    return [GateResult("frozen", not frozen, detail=f"{len(frozen)} freeze(s) > {FROZEN_S} s", at=[fmt(a) for a, _ in frozen], fixable=True,
                       fix_hint="Cut away or punch in during the frozen stretch."),
            GateResult("black", not blacks, detail=f"{len(blacks)} black stretch(es)" + (f"; {len(edge)} head/tail fade(s) exempt" if edge else ""),
                       at=[fmt(a) for a, _ in blacks], measured={"edge_fades": len(edge)})]


def frame_and_loudness(tl: Timeline, final: Path) -> list[GateResult]:
    from reel.tools import ffprobe_frame_times

    frames = len(ffprobe_frame_times(final))
    m = mix.measure(final)
    problems = mix.check_delivery(m)
    return [GateResult("frame_count", frames == tl.duration_f, mode="block", detail=f"{frames}/{tl.duration_f} frames"),
            GateResult("loudness", not problems, mode="block", detail="; ".join(problems) or f"{m['input_i']:.1f} LUFS, {m['input_tp']:.1f} dBTP",
                       measured={"lufs": m["input_i"], "true_peak": m["input_tp"]})]


def apply_modes(results: list[GateResult]) -> list[GateResult]:
    for r in results:
        r.mode = config.QA_GATES.get(r.gate, r.mode)
    return results
