"""Cover frame / thumbnail (cap.export.cover_frame).

~40 candidate frames of the BASE render (render/base.mov: graded, framed, no captions) from the
first 60 % of the reel plus the Editor's highlight moments (hook item, emphasised words,
punch-ins). Each is scored

    score = face area (capped) × sharpness (Laplacian variance of the face, capped) × expression

with MediaPipe Face Landmarker blendshapes: eyes closed (eyeBlinkLeft/Right > 0.5) is rejected,
smile / raised brows / an open mouth are rewarded moderately; faces under 1 % of the frame count
as no face (frames without a face rank by sharpness only, far below any face). The top 5, at
least 4 % of the runtime apart, are kept. Writes render/cover/:

  cover.jpg        1080x1920: best frame + the hook title (≤ 6 words), big, outlined, on a dark
                   gradient, inside the 3:4 centre that the profile grid shows
  cover_clean.jpg  the same frame without text
  covers/cover_N.jpg  the top-5 candidates (clean)
  cover.json       the choice, every candidate's scores, font and model used

Model and font are pinned by URL + SHA-256 and cached in ~/.cache/reel.
"""

from __future__ import annotations

import hashlib
import io
import os
import ssl
import shutil
import tempfile
import urllib.request
import zipfile
from fractions import Fraction
from pathlib import Path

import numpy as np

from reel import qa, sheets, tools
from reel import timebase as tb
from reel.cuts import decode_frames
from reel.perception.visual import MODEL_DIR
from reel.schemas.perception import WordTable
from reel.schemas.plan import FinishPlan, StoryPlan
from reel.schemas.timeline import Timeline
from reel.workspace import atomic_write_json

LANDMARKER_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
LANDMARKER_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
INTER_URL = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"  # SIL OFL 1.1
INTER_ZIP_SHA256 = "9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e"
INTER_MEMBER = "extras/ttf/InterDisplay-ExtraBold.ttf"
INTER_SHA256 = "776d88313defcd42d33bc43bddcba6fc1e93ee3eaeca1c1ded2eacf2baec9d24"
FONT_DIR = Path(os.environ.get("REEL_FONT_DIR", MODEL_DIR.parent / "fonts"))
FALLBACK_FONTS = (*sheets.FONT_CANDIDATES, "/Library/Fonts/Arial Unicode.ttf")

N_CANDIDATES = 40
MAX_HIGHLIGHTS = 16
EARLY_SHARE = 0.60
ANALYSIS_W = 540
MIN_FACE = 0.01  # share of the frame
AREA_CAP = 0.20  # a bigger face is not a better cover
SHARP_CAP = 60.0  # Laplacian variance of the face (0–255 luma at ANALYSIS_W) that counts as fully
#                   sharp (in-focus faces measured 25–70 on a real podcast reel)
BLINK_MAX = 0.5
LOOK_DOWN_FROM = 0.3  # eyes on the table, not the viewer: up to −40 % expression from here to 0.7
NO_FACE = 0.02  # weight of a faceless frame (below any real face)
SPACING_SHARE = 0.04
TOP_K = 5
TITLE_WORDS = 6
OUT_W, OUT_H = 1080, 1920
GRID_TOP, GRID_BOTTOM = 240, 1680  # the profile grid shows the 3:4 centre (1080x1440)
TEXT_MAX_W = 940
TEXT_MAX_SIZE = 150


# ------------------------------------------------------------------ pinned downloads


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _tls() -> ssl.SSLContext:
    """The OS trust store when `truststore` is installed (GitHub's release-asset host does not verify
    against certifi's bundle alone), else $SSL_CERT_FILE / certifi / Python's default."""
    if not os.environ.get("SSL_CERT_FILE"):
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except ImportError:
            pass
    cafile = os.environ.get("SSL_CERT_FILE")
    if not cafile:
        try:  # python.org builds ship without a CA bundle
            import certifi

            cafile = certifi.where()
        except ImportError:
            cafile = None
    return ssl.create_default_context(cafile=cafile)


def _download(url: str, timeout: int = 120) -> bytes:
    ctx = _tls()
    with urllib.request.urlopen(url, context=ctx, timeout=timeout) as r:  # noqa: S310 — fixed https URL
        return r.read()


def _install(path: Path, data: bytes, sha: str) -> Path:
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        raise RuntimeError(f"checksum mismatch for {path.name}: {got} != pinned {sha}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def landmarker_model() -> Path:
    path = MODEL_DIR / "face_landmarker.task"
    if path.exists() and _sha256(path) == LANDMARKER_SHA256:
        return path
    return _install(path, _download(LANDMARKER_URL), LANDMARKER_SHA256)


def inter_font() -> Path:
    """Inter Display ExtraBold TTF (drawtext needs TTF/OTF; the renderer's fontsource copy is woff2)."""
    path = FONT_DIR / Path(INTER_MEMBER).name
    if path.exists() and _sha256(path) == INTER_SHA256:
        return path
    data = _download(INTER_URL)
    if hashlib.sha256(data).hexdigest() != INTER_ZIP_SHA256:
        raise RuntimeError("Inter release zip checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return _install(path, z.read(INTER_MEMBER), INTER_SHA256)


def _covers(font: str, text: str) -> bool:
    try:
        from fontTools.ttLib import TTFont

        cmap = TTFont(font, lazy=True).getBestCmap()
    except Exception:  # noqa: BLE001 — no fontTools / unreadable font: assume it covers
        return True
    return all(ord(ch) in cmap for ch in text if not ch.isspace())


def cover_font(text: str) -> tuple[str | None, str]:
    """(font file, note): pinned Inter, else the first system font that has every glyph."""
    notes = []
    try:
        inter = str(inter_font())
        if _covers(inter, text):
            return inter, "Inter Display ExtraBold (OFL, pinned)"
        notes.append("Inter lacks glyphs for the title")
    except Exception as exc:  # noqa: BLE001 — offline: fall back to a system font
        notes.append(f"Inter unavailable ({type(exc).__name__})")
    for f in FALLBACK_FONTS:
        if Path(f).exists() and _covers(f, text):
            return f, f"{Path(f).stem} (fallback: {'; '.join(notes)})"
    return None, f"ffmpeg default font (fallback: {'; '.join(notes)})"


# ------------------------------------------------------------------ candidates


def _blocked(tl: Timeline) -> list[tuple[int, int]]:
    """Frames that never make a cover: transitions and footage effects."""
    out = [(t.at_f - t.frames - 1, t.at_f + t.frames + 1) for t in tl.transitions]
    return out + [(e.start_f, e.end_f) for e in tl.effects]


def candidate_frames(tl: Timeline, story: StoryPlan, n: int = N_CANDIDATES) -> list[tuple[int, str]]:
    """Highlight moments first (hook item, emphasised words, punch-ins), the rest spread over the
    first 60 % of the reel. Returns sorted (frame, why)."""
    fps = tb.parse_rate(tl.fps)
    total = tl.duration_f
    blocked = _blocked(tl)
    ok = lambda f: 0 <= f < total and not any(a <= f <= b for a, b in blocked)  # noqa: E731
    sec = lambda s: int(round(s * float(fps)))  # noqa: E731
    picks: dict[int, str] = {}

    def add(f: int, why: str) -> None:
        if ok(f) and f not in picks and sum(1 for w in picks.values() if w != "early") < MAX_HIGHLIGHTS:
            picks[f] = why

    hook = next((h.item for h in story.hook_options if h.id == story.hook), None)
    for c in sorted((c for c in tl.video if c.id.startswith("v_") and c.src.item == hook), key=lambda c: c.at_f):
        for off in (0.3, 0.8, 1.4):
            if sec(off) < c.dur_f:
                add(c.at_f + sec(off), "hook")
    for p in tl.captions.pages if tl.captions else []:
        for w in p.words:
            if w.emph:
                add((w.start_f + w.end_f) // 2, f"emphasis “{w.text}”")
    for c in tl.video:
        for k in c.scale:
            if k.v > 1.0 and k.f < c.dur_f:
                add(c.at_f + min(k.f + sec(0.2), c.dur_f - 1), "punch-in")
    early = max(1, int(total * EARLY_SHARE))
    room = max(0, n - len(picks))
    for f in np.linspace(0, early - 1, room + 2)[1:-1] if room else []:
        f = int(round(f))
        if ok(f) and f not in picks:
            picks[f] = "early"
    if not picks and total:
        picks[0] = "first frame"
    return sorted(picks.items())


# ------------------------------------------------------------------ scoring


def detect_faces(frames: dict[int, np.ndarray]) -> dict[int, dict | None]:
    """Largest face per frame via MediaPipe Face Landmarker: normalised box from the landmarks +
    blendshape scores. Tests monkeypatch this."""
    import mediapipe as mp

    opts = mp.tasks.vision.FaceLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(landmarker_model())),
                                                 output_face_blendshapes=True, num_faces=3)
    out: dict[int, dict | None] = {}
    with mp.tasks.vision.FaceLandmarker.create_from_options(opts) as lm:
        for f, rgb in frames.items():
            res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
            best = None
            for k, marks in enumerate(res.face_landmarks or []):
                xs, ys = [p.x for p in marks], [p.y for p in marks]
                x0, y0 = max(0.0, min(xs)), max(0.0, min(ys))
                box = {"x": x0, "y": y0, "w": min(1.0, max(xs)) - x0, "h": min(1.0, max(ys)) - y0}
                blend = {c.category_name: float(c.score) for c in (res.face_blendshapes[k] if res.face_blendshapes else [])}
                if best is None or box["w"] * box["h"] > best["box"]["w"] * best["box"]["h"]:
                    best = {"box": box, "blend": blend}
            out[f] = best
    return out


def laplacian_var(gray: np.ndarray) -> float:
    g = gray.astype(np.float64)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]
    return float(lap.var())


def score_frame(rgb: np.ndarray, face: dict | None) -> dict:
    """Score one candidate (see module doc). `face` = {"box": {x,y,w,h} normalised, "blend": {...}}."""
    gray = rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    h, w = gray.shape
    area = face["box"]["w"] * face["box"]["h"] if face else 0.0
    if face and area >= MIN_FACE:
        b = face["box"]
        y0, y1 = int(max(0.0, b["y"]) * h), int(min(1.0, b["y"] + b["h"]) * h)
        x0, x1 = int(max(0.0, b["x"]) * w), int(min(1.0, b["x"] + b["w"]) * w)
        sharp_raw = laplacian_var(gray[y0:y1, x0:x1])
    else:
        sharp_raw = laplacian_var(gray[h // 4: 3 * h // 4, w // 8: 7 * w // 8])
        face, area = None, 0.0
    sharp = min(1.0, sharp_raw / SHARP_CAP)
    out = {"face_area": round(area, 4), "sharpness": round(sharp_raw, 1), "sharp": round(sharp, 3), "expression": 1.0,
           "blink": None, "rejected": None}
    if face is None:
        out["score"] = round(NO_FACE * sharp, 5)
        return out
    bl = face.get("blend") or {}
    blink = max(bl.get("eyeBlinkLeft", 0.0), bl.get("eyeBlinkRight", 0.0))
    smile = (bl.get("mouthSmileLeft", 0.0) + bl.get("mouthSmileRight", 0.0)) / 2
    brow = max(bl.get("browInnerUp", 0.0), (bl.get("browOuterUpLeft", 0.0) + bl.get("browOuterUpRight", 0.0)) / 2)
    jaw = min(bl.get("jawOpen", 0.0), 0.5) / 0.5
    look_down = (bl.get("eyeLookDownLeft", 0.0) + bl.get("eyeLookDownRight", 0.0)) / 2
    expr = (1.0 + 0.4 * smile + 0.2 * brow + 0.2 * jaw) * (1 - 0.4 * min(1.0, max(0.0, (look_down - LOOK_DOWN_FROM) / 0.4)))
    out |= {"blink": round(blink, 3), "look_down": round(look_down, 3), "expression": round(expr, 3),
            "box": {k: round(v, 4) for k, v in face["box"].items()}}
    if blink > BLINK_MAX:
        out |= {"rejected": "eyes closed", "score": 0.0}
        return out
    out["score"] = round(min(area, AREA_CAP) / AREA_CAP * sharp * expr, 5)
    return out


def pick(scored: list[dict], total: int, k: int = TOP_K, spacing: float = SPACING_SHARE) -> list[dict]:
    """Greedy best-first, keeping candidates ≥ spacing × runtime apart; rejected frames never win."""
    gap = max(1, int(round(total * spacing)))
    chosen: list[dict] = []
    for c in sorted((c for c in scored if not c["rejected"]), key=lambda c: (-c["score"], c["frame"])):
        if all(abs(c["frame"] - o["frame"]) >= gap for o in chosen):
            chosen.append(c)
        if len(chosen) == k:
            break
    return chosen


# ------------------------------------------------------------------ title


def title_text(finish: FinishPlan, story: StoryPlan, words: WordTable | None) -> str:
    """Hook title from the finish plan, else the hook line; at most 6 words."""
    text = finish.hook_title.text.strip()
    if not text and words is not None:
        item_id = next((h.item for h in story.hook_options if h.id == story.hook), None)
        it = next((i for i in story.items if i.id == item_id), story.items[0] if story.items else None)
        by = words.by_index()
        if it:
            text = " ".join(by[i].text for i in range(it.word_start, it.word_end + 1) if i in by and not by[i].filler)
    toks = text.split()[:TITLE_WORDS]
    if toks:
        toks[-1] = toks[-1].rstrip(",;:.")
    return " ".join(toks)


def _width(font: str | None, text: str, size: float) -> float:
    try:
        from fontTools.ttLib import TTFont

        f = TTFont(font, lazy=True)
        cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
        return sum(hmtx[cmap.get(ord(ch), ".notdef")][0] for ch in text) / upm * size
    except Exception:  # noqa: BLE001 — no fontTools / font: average bold glyph width
        return 0.62 * size * len(text)


def layout(text: str, font: str | None) -> tuple[list[str], int]:
    """Split into 1–3 lines and pick the split that allows the biggest font size."""
    words = text.split()
    best: tuple[list[str], int] = ([text], 40)
    for n in range(1, min(3, len(words)) + 1):
        for cuts in _splits(len(words), n):
            lines = [" ".join(words[a:b]) for a, b in zip((0, *cuts), (*cuts, len(words)))]
            widest = max(_width(font, ln, 100) for ln in lines) / 100
            size = int(min(TEXT_MAX_SIZE, TEXT_MAX_W / max(widest, 1e-6)))
            if size > best[1]:
                best = (lines, size)
    return best


def _splits(n: int, parts: int) -> list[tuple[int, ...]]:
    if parts == 1:
        return [()]
    out = []
    for k in range(1, n - parts + 2):
        out += [(k, *(k + c for c in rest)) for rest in _splits(n - k, parts - 1)]
    return out


# ------------------------------------------------------------------ rendering


def text_on_top(face_box: dict | None, top: tuple[int, int], bottom: tuple[int, int]) -> bool:
    """Put the title where it covers less of the face (output px rows); the bottom wins ties."""
    if not face_box:
        return False
    f0, f1 = face_box["y"] * OUT_H, (face_box["y"] + face_box["h"]) * OUT_H
    overlap = lambda a, b: max(0.0, min(b, f1) - max(a, f0))  # noqa: E731
    return overlap(*top) < overlap(*bottom)


def _esc(p: str) -> str:
    return sheets._escape(p).replace(",", "\\,")


def write_jpeg(rgb: np.ndarray, out: Path, *, text: str = "", font: str | None = None, face_box: dict | None = None) -> dict:
    """1080x1920 JPEG of `rgb`, optionally with the title (drawtext) on a dark gradient."""
    out.parent.mkdir(parents=True, exist_ok=True)
    h, w = rgb.shape[:2]
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "frame.rgb"
        raw.write_bytes(np.ascontiguousarray(rgb).tobytes())
        chain = f"[0:v]scale={OUT_W}:{OUT_H}:flags=lanczos,format=rgba[bg]"
        meta = {}
        if text:
            lines, size = layout(text, font)
            lh = int(size * 1.1)
            block = lh * len(lines)
            top_y, bottom_y = GRID_TOP + 60, GRID_BOTTOM - 80 - block
            on_top = text_on_top(face_box, (top_y, top_y + block), (bottom_y, bottom_y + block))
            if on_top:  # title in the upper part of the grid-safe area, clear of the face
                y0, grad_y, grad_h, alpha = top_y, 0, top_y + block + 260, "215*(1-Y/H)"
            else:
                y0 = bottom_y
                grad_y = y0 - 260
                grad_h, alpha = OUT_H - grad_y, "215*Y/H"
            ff = f":fontfile='{_esc(font)}'" if font else ""
            draws = []
            for k, line in enumerate(lines):
                tf = Path(td) / f"line{k}.txt"
                tf.write_text(line)
                draws.append(f"drawtext=textfile='{_esc(str(tf))}':expansion=none{ff}:fontsize={size}:fontcolor=white"
                             f":borderw={max(3, size // 14)}:bordercolor=black@0.9:shadowx=0:shadowy={max(2, size // 22)}:shadowcolor=black@0.55"
                             f":x=(w-text_w)/2:y={y0 + k * lh}")
            chain += (f";color=c=black:s={OUT_W}x{grad_h}:d=1,format=rgba,geq=r=0:g=0:b=0:a='{alpha}'[g]"
                      f";[bg][g]overlay=0:{grad_y}:format=auto,{','.join(draws)}")
            meta = {"lines": lines, "font_size": size, "text_top": y0, "text_bottom": y0 + block, "placement": "top" if on_top else "bottom"}
        tools.ffmpeg(["-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", str(raw), "-filter_complex", chain + ",format=yuvj420p" if text
                      else chain.replace("format=rgba[bg]", "format=yuvj420p"), "-frames:v", "1", "-q:v", "2", str(out)])
    return meta


# ------------------------------------------------------------------ stage


def build(ws, tl: Timeline, story: StoryPlan, finish: FinishPlan, words: WordTable | None, *, base: Path | None = None) -> dict:
    fps = tb.parse_rate(tl.fps)
    base = base or ws.path("render", "base.mov")
    out = ws.path("render", "cover")
    for old in [*out.glob("*.jpg"), *(out / "covers").glob("*.jpg")] if out.exists() else []:
        old.unlink()
    cands = candidate_frames(tl, story)
    small = decode_frames(base, {f for f, _ in cands}, ANALYSIS_W)
    try:
        faces, face_note = detect_faces(small), "MediaPipe Face Landmarker (float16 v1, pinned)"
    except Exception as exc:  # noqa: BLE001 — no mediapipe / offline: rank by sharpness only
        faces, face_note = {}, f"unavailable ({type(exc).__name__}: {exc}) — ranked by sharpness"
    scored = []
    for f, why in cands:
        if f in small:
            scored.append({"frame": f, "tc": qa.tc(f, fps), "why": why, **score_frame(small[f], faces.get(f))})
    top = pick(scored, tl.duration_f) or sorted(scored, key=lambda c: (-c["sharp"], c["frame"]))[:1]
    full = decode_frames(base, {c["frame"] for c in top}, OUT_W)
    title = title_text(finish, story, words)
    font, font_note = cover_font(title) if title else (None, "no title")
    for n, c in enumerate(top, 1):
        c["file"] = f"covers/cover_{n}.jpg"
        write_jpeg(full[c["frame"]], out / c["file"])
    if not top:
        raise ValueError("no usable cover candidates (frames could not be decoded)")
    best = top[0]
    write_jpeg(full[best["frame"]], out / "cover_clean.jpg")
    try:
        text_meta = write_jpeg(full[best["frame"]], out / "cover.jpg", text=title, font=font, face_box=best.get("box"))
    except tools.ToolError as exc:  # an ffmpeg build without drawtext (libfreetype): ship the clean frame, say why
        shutil.copyfile(out / "cover_clean.jpg", out / "cover.jpg")
        text_meta = {"skipped": f"title not drawn: ffmpeg cannot draw text ({str(exc).splitlines()[0][:120]})"}
        font_note = f"{font_note}; title skipped (no drawtext in this ffmpeg build)"
    report = {"frame": best["frame"], "tc": best["tc"], "t": round(float(Fraction(best["frame"]) / fps), 3), "score": best["score"],
              "title": title, "font": font_note, "text": text_meta, "faces": face_note, "top": top,
              "candidates": sorted(scored, key=lambda c: c["frame"]), "rules": {
                  "early_share": EARLY_SHARE, "min_face": MIN_FACE, "area_cap": AREA_CAP, "sharp_cap": SHARP_CAP, "blink_max": BLINK_MAX,
                  "spacing_share": SPACING_SHARE}}
    atomic_write_json(out / "cover.json", report)
    return {"frame": best["frame"], "tc": best["tc"], "score": best["score"], "title": title, "font": font_note, "faces": face_note,
            "candidates": len(scored), "top": [c["frame"] for c in top]}
