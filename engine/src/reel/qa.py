"""QA gates measured on the render (ADR-0006, ADR-0017, ADR-0021).

Every gate returns a GateResult with measurements and the offending timecodes. Its mode
(`block` | `warn`) comes from config.QA_GATES: measured gates start as `warn` until their
false-positive rate on owner-sendable renders is known (`reel calibrate`).
"""

from __future__ import annotations

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
MAX_CPS = 20.0
FACE_OVERLAP_MAX = 0.03  # share of the face box covered by overlay pixels
SAMPLE_W = 270  # analysis width (1080 / 4)


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


def page_frames(tl: Timeline) -> list[int]:
    return [(p.start_f + p.end_f) // 2 for p in (tl.captions.pages if tl.captions else [])]


def reading_speed(tl: Timeline) -> GateResult:
    fps = tb.parse_rate(tl.fps)
    bad, worst = [], 0.0
    for p in tl.captions.pages if tl.captions else []:
        chars = sum(len(w.text) for w in p.words) + max(0, len(p.words) - 1)
        cps = chars / max(float(Fraction(p.end_f - p.start_f) / fps), 1e-6)
        worst = max(worst, cps)
        if cps > MAX_CPS:
            bad.append(tc(p.start_f, fps))
    return GateResult("reading_speed", not bad, detail=f"max {worst:.1f} chars/s (limit {MAX_CPS:.0f})", at=bad, fixable=True,
                      fix_hint="Use a caption family with fewer words per page, or cut the fastest lines.", measured={"max_cps": round(worst, 1)})


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
    frames = page_frames(tl)
    t = tl.captions.tokens
    fill = hex_rgb(t.get("base_color") or t.get("speaker_a") or "#FFFFFF")[:3]
    on = lambda v: v == "true" or bool(re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", v or ""))  # noqa: E731
    stroke_rgb = hex_rgb(t["stroke"])[:3] if on(t.get("stroke")) and t["stroke"].startswith("#") else (0, 0, 0)
    stroke = on(t.get("stroke"))
    box_hex = t.get("box_color") or (t["box"] if (t.get("box") or "").startswith("#") else "#000000B3")
    box = hex_rgb(box_hex) if on(t.get("box")) else None
    low, over_face, out_safe, worst = [], [], [], 99.0
    for f in frames:
        o, b = ov.get(f), bg.get(f)
        if o is None or b is None:
            continue
        a = o[..., 3] / 255.0
        h, w = a.shape
        ys, xs = np.nonzero(a > FAINT_ALPHA)
        if ys.size == 0:
            if (a > 0.05).mean() > 0.002:  # a caption is drawn but nowhere opaque: see-through text
                low.append(tc(f, fps))
                worst = min(worst, 1.0)
            continue
        # background right behind the caption block (bbox, excluding text pixels)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        region = b[y0:y1, x0:x1][a[y0:y1, x0:x1] < 0.05]
        behind = region.reshape(-1, 3) if region.size else b[y0:y1, x0:x1].reshape(-1, 3)
        if box:
            behind = (np.asarray(box[:3]) * box[3] + behind.mean(axis=0) * (1 - box[3]))[None, :]
        solid = o[..., :3][a > 0.9].reshape(-1, 3).astype(float)
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
            if face_a.size and float((face_a > 0.5).mean()) > FACE_OVERLAP_MAX:
                over_face.append(tc(f, fps))
        # safe zone (px on the 1080x1920 grid, scaled to the sample)
        if not any(s <= f < e for s, e in flashes):
            k = w / tl.width
            if (y0 < safe["top"] * k or y1 > h - safe["bottom"] * k or x0 < safe["left"] * k or x1 > w - safe["right"] * k):
                out_safe.append(tc(f, fps))
    return [
        GateResult("caption_contrast", not low, detail=f"lowest {worst:.1f}:1 (min {MIN_CONTRAST}:1)", at=low, fixable=True,
                   fix_hint="Use a boxed or stroked caption style, or a fill colour that stands out from the footage.",
                   measured={"min_ratio": round(worst, 2)}),
        GateResult("caption_over_face", not over_face, detail=f"{len(over_face)} page(s) cover the face", at=over_face, fixable=True,
                   fix_hint="Move captions to a zone below the face (lower_third) or use fewer words per page."),
        GateResult("safe_zone", not out_safe, detail=f"{len(out_safe)} page(s) outside the safe zone", at=out_safe, fixable=True,
                   fix_hint="Shorter pages or a lower_middle zone."),
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
    fmt = lambda s: f"{int(s // 60)}:{s % 60:05.2f}"  # noqa: E731
    return [GateResult("frozen", not frozen, detail=f"{len(frozen)} freeze(s) > {FROZEN_S} s", at=[fmt(a) for a, _ in frozen], fixable=True,
                       fix_hint="Cut away or punch in during the frozen stretch."),
            GateResult("black", not blacks, detail=f"{len(blacks)} black stretch(es)", at=[fmt(a) for a, _ in blacks])]


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
