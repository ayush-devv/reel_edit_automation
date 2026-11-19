"""Active speaker detection on multi-person shots (adapted from openshorts `active_speaker.py`, MIT).

Only stretches where faces.json sees two or more faces are analysed (single-face footage costs
nothing). Each stretch is cut at the source's scene cuts into pieces (one camera shot each).

Per piece:
1. tracks = faces.json boxes grouped by position (BlazeFace, 4 fps);
2. each track's face region is cropped from 12 fps frames and run through the MediaPipe Face
   Landmarker (VIDEO mode, blendshapes). Cropping per face instead of landmarking the whole frame
   keeps small faces in wide shots detectable (the landmarker's own detector misses faces under
   ~8 % of the frame width). A track with no landmarks (the back of a head in an over-the-shoulder
   shot) is dropped: it can never be attributed;
3. per 0.4 s window: mouth activity = mean |Δ jawOpen| + a small open-mouth level term,
   normalised by the piece's peak (p95) activity;
4. a window is speech only if its audio RMS is ≥ 0.18 × the piece's peak AND a word or VAD
   speech region overlaps it; a speech window goes to the face leading the other by ≥ 0.15
   (normalised) and above an absolute jitter floor, else it is "uncertain" (both talking,
   laughter, nobody visibly talking);
5. hysteresis: a new speaker (or "uncertain") is confirmed after 3 consecutive speech windows
   (~1.2 s); silent windows hold the current speaker. The analysis is offline, so a confirmed
   switch is placed at the START of its run, then snapped to a word gap (never mid-word).

Output per clip (perception/speakers.json): tracks, speaker segments [{start_us, end_us, track}]
(track null = uncertain speech → the framing keeps the whole frame), per-word labels.
"""

from __future__ import annotations

import hashlib
import os
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

import numpy as np

from reel import config
from reel.perception.visual import MODEL_DIR

LANDMARKER_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                  "face_landmarker/float16/1/face_landmarker.task")
LANDMARKER_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

ASD_FPS = 12.0
DECODE_WIDTH = 1280  # frames are decoded at this width (or the source width) before the per-face crops
WINDOW_US = 400_000
AUDIO_GATE = 0.18  # window RMS ≥ this share of the piece's peak RMS (linear) → loud enough to be speech
MARGIN = 0.15  # normalised lead the speaker needs over the next face
ABS_FLOOR = 0.007  # raw activity (|Δ jawOpen| per frame) under this is jitter, never a speaker
SCALE_FLOOR = 0.02  # normalisation never divides by less (two still faces don't blow jitter up to 1.0)
LEVEL_W = 0.2  # weight of the open-mouth level term in the activity
HOLD = 3  # consecutive speech windows to confirm a switch (~1.2 s)
MIN_PIECE_US = 1_000_000  # shorter multi-face stretches are ignored
TRACK_DIST = 0.12  # max centre distance (normalised) to keep a face on the same track
MIN_TRACK_PRESENCE = 0.4  # a track must be seen in this share of the piece's face samples
MIN_LANDMARK_SHARE = 0.4  # … and get landmarks in this share of the piece's frames
SWITCH_LEAD_US = 100_000  # a switch inside a pause sits this long before the next word
UNCERTAIN = "uncertain"


# ------------------------------------------------------------------ model


def landmarker_model() -> Path:
    """face_landmarker.task, downloaded once and checked against the pinned SHA-256."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / "face_landmarker.task"
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == LANDMARKER_SHA256:
        return path
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    with urllib.request.urlopen(LANDMARKER_URL, context=ctx, timeout=60) as r:  # noqa: S310 — fixed https URL
        data = r.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != LANDMARKER_SHA256:
        raise RuntimeError(f"face_landmarker.task checksum mismatch: {digest}")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


# ------------------------------------------------------------------ stretches and tracks (pure)


def multi_face_pieces(samples: list[dict], cuts_us: list[int], *, bridge_us: int = 2_000_000,
                      min_us: int = MIN_PIECE_US) -> list[tuple[int, int]]:
    """Stretches where ≥ 2 faces are seen (short gaps bridged), split at scene cuts."""
    if not samples:
        return []
    dt = int(np.median(np.diff([s["t_us"] for s in samples]))) if len(samples) > 1 else 250_000
    runs: list[list[int]] = []
    for s in samples:
        if len(s.get("faces") or []) < 2:
            continue
        t = s["t_us"]
        if runs and t - runs[-1][1] <= bridge_us:
            runs[-1][1] = t + dt
        else:
            runs.append([t, t + dt])
    pieces = []
    for a, b in runs:
        bounds = [a] + [c for c in sorted(cuts_us) if a < c < b] + [b]
        pieces += [(x, y) for x, y in zip(bounds, bounds[1:]) if y - x >= min_us]
    return pieces


def _centre(b: dict) -> tuple[float, float]:
    return b["x"] + b["w"] / 2, b["y"] + b["h"] / 2


def face_tracks(samples: list[dict], a: int, b: int) -> list[dict]:
    """Faces in [a, b) grouped by position: [{"box": median box, "boxes": [(t_us, box)]}], left to right."""
    window = [s for s in samples if a <= s["t_us"] < b]
    tracks: list[dict] = []
    for s in window:
        used: set[int] = set()
        for f in sorted(s.get("faces") or [], key=lambda f: -f["w"] * f["h"]):
            cx, cy = _centre(f)
            best, dist = None, TRACK_DIST
            for k, tr in enumerate(tracks):
                d = float(np.hypot(cx - tr["c"][0], cy - tr["c"][1]))
                if k not in used and d < dist:
                    best, dist = k, d
            if best is None:
                tracks.append({"c": (cx, cy), "boxes": []})
                best = len(tracks) - 1
            used.add(best)
            tracks[best]["boxes"].append((s["t_us"], f))
            tracks[best]["c"] = (cx, cy)
    n = max(1, len(window))
    out = []
    for tr in tracks:
        if len(tr["boxes"]) < MIN_TRACK_PRESENCE * n:
            continue
        box = {k: round(float(np.median([f[k] for _, f in tr["boxes"]])), 4) for k in ("x", "y", "w", "h")}
        out.append({"box": box, "boxes": tr["boxes"]})
    return sorted(out, key=lambda t: t["box"]["x"])


def crop_region(boxes: list[dict], src_w: int, src_h: int, pad: float = 0.6) -> tuple[int, int, int, int]:
    """Pixel region (x, y, w, h) holding every box of a track, padded by `pad` × the median face size."""
    fw = float(np.median([f["w"] for f in boxes])) * src_w
    fh = float(np.median([f["h"] for f in boxes])) * src_h
    x0 = min(f["x"] for f in boxes) * src_w - pad * fw
    x1 = max(f["x"] + f["w"] for f in boxes) * src_w + pad * fw
    y0 = min(f["y"] for f in boxes) * src_h - pad * fh
    y1 = max(f["y"] + f["h"] for f in boxes) * src_h + pad * fh
    side = max(x1 - x0, y1 - y0)  # square-ish: the landmarker's detector expects a face-shaped input
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x0, x1 = max(0, int(cx - side / 2)), min(src_w, int(cx + side / 2))
    y0, y1 = max(0, int(cy - side / 2)), min(src_h, int(cy + side / 2))
    return x0, y0, max(2, x1 - x0), max(2, y1 - y0)


# ------------------------------------------------------------------ attribution (pure)


def window_activity(series: list[tuple[int, float, float]], a: int, b: int) -> float | None:
    """Mouth activity of one face in [a, b) from (t_us, jawOpen, mouthClose) samples; None = face not seen."""
    pts = [(j, c) for t, j, c in series if a <= t < b]
    if not pts:
        return None
    jaw = np.array([p[0] for p in pts])
    motion = float(np.abs(np.diff(jaw)).mean()) if len(jaw) > 1 else 0.0
    level = float(np.clip(jaw - np.array([p[1] for p in pts]), 0, None).mean())
    return motion + LEVEL_W * level


def attribute(activity: list[dict], speech: list[bool], *, margin: float = MARGIN, floor: float = ABS_FLOOR) -> list:
    """Per window: the leading track id, UNCERTAIN (speech, no clear leader) or None (no speech).

    `activity[w]` = {track: raw activity (None = not seen)}; normalised by the piece's p95 activity."""
    vals = [v for row in activity for v in row.values() if v is not None]
    scale = max(float(np.percentile(vals, 95)) if vals else 0.0, SCALE_FLOOR)
    out = []
    for row, sp in zip(activity, speech):
        if not sp:
            out.append(None)
            continue
        ranked = sorted(((v, k) for k, v in row.items() if v is not None), reverse=True)
        if len(ranked) < 2 and len(row) >= 2:
            ranked.append((0.0, None))  # the other face not seen this window: compare with "silent"
        if len(ranked) < 2:
            out.append(UNCERTAIN)
            continue
        (top, who), (nxt, _) = ranked[0], ranked[1]
        lead = min(1.0, top / scale) - min(1.0, nxt / scale)
        out.append(who if top >= floor and lead >= margin else UNCERTAIN)
    return out


def smooth(labels: list, hold: int = HOLD) -> list:
    """Hysteresis: a new label holds after `hold` consecutive speech windows and is backdated to the
    start of that run; silent windows (None) keep the current label and neither count nor reset a run.
    Before the first confirmed label: silent windows take it (the piece opens on its first speaker),
    unconfirmed speech is UNCERTAIN (someone else may have been talking)."""
    out: list = [None] * len(labels)
    cur, cand, run_start, count = None, None, 0, 0
    for i, lab in enumerate(labels):
        if lab is None or lab == cur:
            if lab is not None:
                cand, count = None, 0
            out[i] = cur
            continue
        if lab == cand:
            count += 1
        else:
            cand, count, run_start = lab, 1, i
        if count >= hold:
            cur, cand, count = lab, None, 0
            for j in range(run_start, i + 1):
                out[j] = cur
        else:
            out[i] = cur
    first = next((k for k, s in enumerate(out) if s is not None), None)
    if first is None:
        return [UNCERTAIN if lab is not None else None for lab in labels]
    return [(out[first] if labels[k] is None else UNCERTAIN) if k < first else out[k] for k in range(len(out))]


def speech_windows(a: int, b: int, rms_db: list[float] | None, hop_us: int, words: list[tuple[int, int]] | None,
                   speech: list[tuple[int, int]] | None, gate: float = AUDIO_GATE) -> list[bool]:
    """Per 0.4 s window of [a, b): loud enough (≥ gate × piece peak RMS) and overlapping a word or VAD speech."""
    starts = list(range(a, b, WINDOW_US))
    if rms_db:
        lin = 10 ** (np.asarray(rms_db, dtype=float) / 20)
        rms = []
        for s in starts:
            k0, k1 = s // hop_us, max(s // hop_us + 1, min(b, s + WINDOW_US) // hop_us)
            seg = lin[k0:k1]
            rms.append(float(np.sqrt((seg ** 2).mean())) if seg.size else 0.0)
        peak = max(rms) if rms else 0.0
        loud = [peak > 0 and r >= gate * peak for r in rms]
    else:
        loud = [True] * len(starts)
    spans = [*(words or []), *(speech or [])]
    if words is None and speech is None:
        voiced = [True] * len(starts)
    else:
        voiced = [any(x < min(b, s + WINDOW_US) and y > s for x, y in spans) for s in starts]
    return [lo and vo for lo, vo in zip(loud, voiced)]


def snap(t: int, words: list[tuple[int, int]], lo: int, hi: int) -> int:
    """Move a switch time out of any word, to just before the next word inside the pause; within [lo, hi]."""
    for s, e in words:
        if s < t < e:
            t = s if t - s <= e - t else e
            break
    prev_e = max((e for s, e in words if e <= t), default=None)
    next_s = min((s for s, e in words if s >= t), default=None)
    if prev_e is not None and next_s is not None and next_s - prev_e > 0:
        t = max(prev_e, next_s - min(SWITCH_LEAD_US, (next_s - prev_e) // 2))
    return min(max(t, lo), hi)


def segments(states: list, a: int, b: int, words: list[tuple[int, int]]) -> list[dict]:
    """Window states → [{start_us, end_us, track}] over [a, b) (track None = uncertain), switches snapped."""
    out: list[dict] = []
    for i, st in enumerate(states):
        if st is None:
            continue
        t = a + i * WINDOW_US
        track = None if st == UNCERTAIN else st
        if out and out[-1]["track"] == track:
            continue
        if out:
            t = snap(t, words, out[-1]["start_us"] + 1, b - 1)
            out[-1]["end_us"] = t
        out.append({"start_us": a if not out else t, "end_us": b, "track": track})
    return [s for s in out if s["end_us"] > s["start_us"]]


# ------------------------------------------------------------------ model run


def _decode(mezz: Path, a: int, b: int, width: int, src_w: int, src_h: int) -> np.ndarray:
    w = min(width, src_w) // 2 * 2
    h = int(round(src_h * w / src_w / 2)) * 2
    proc = subprocess.run(
        [str(config.ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{a / 1e6:.6f}", "-t", f"{(b - a) / 1e6:.6f}",
         "-i", str(mezz), "-vf", f"fps={ASD_FPS},scale={w}:{h}:flags=area", "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True)
    n = len(proc.stdout) // (w * h * 3)
    return np.frombuffer(proc.stdout[: n * w * h * 3], dtype=np.uint8).reshape(n, h, w, 3)


def mouth_series(frames: np.ndarray, t0_us: int, region: tuple[int, int, int, int],
                 face: dict | None = None) -> list[tuple[int, float, float]]:
    """(t_us, jawOpen, mouthClose) for the face inside `region` of each frame (frames without a face skipped).
    `face` (normalised box the track's faces stayed in): a landmarked face centred outside it is someone else's
    (a padded crop around the back of a head can reach the other person's face) and is ignored."""
    import mediapipe as mp

    x, y, w, h = region
    fh, fw = frames.shape[1:3] if len(frames) else (1, 1)
    opts = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(landmarker_model())),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_faces=1, output_face_blendshapes=True,
        min_face_detection_confidence=0.4, min_face_presence_confidence=0.4, min_tracking_confidence=0.4)
    out = []
    with mp.tasks.vision.FaceLandmarker.create_from_options(opts) as lm:  # fresh per (piece, face): no state across cuts
        for k, fr in enumerate(frames):
            t = t0_us + int(round(k / ASD_FPS * 1e6))
            res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(fr[y:y + h, x:x + w])),
                                      int(t // 1000))
            if res.face_blendshapes:
                if face is not None:
                    lms = res.face_landmarks[0]
                    cx = (x + w * float(np.mean([p.x for p in lms]))) / fw
                    cy = (y + h * float(np.mean([p.y for p in lms]))) / fh
                    if not (face["x"] <= cx <= face["x"] + face["w"] and face["y"] <= cy <= face["y"] + face["h"]):
                        continue
                bs = {c.category_name: c.score for c in res.face_blendshapes[0]}
                out.append((t, round(float(bs.get("jawOpen", 0.0)), 4), round(float(bs.get("mouthClose", 0.0)), 4)))
    return out


def analyse_clip(mezz: Path, faces: dict, cuts_us: list[int], words: list[tuple[int, int, int]] | None = None,
                 rms_db: list[float] | None = None, hop_us: int = 100_000, speech: list[tuple[int, int]] | None = None,
                 src_size: tuple[int, int] | None = None, pieces: list[tuple[int, int]] | None = None) -> dict:
    """speakers.json entry for one clip. `words` = (index, start_us, end_us); `pieces` overrides the
    multi-face stretches (tests). No multi-face stretch → empty result, no model loaded."""
    samples = faces.get("samples") or []
    pieces = multi_face_pieces(samples, cuts_us) if pieces is None else pieces
    result: dict = {"fps": ASD_FPS, "tracks": [], "segments": [], "words": {}, "pieces": [list(p) for p in pieces]}
    if not pieces:
        return result
    if src_size is None:
        from reel.render import source_size

        src_size = source_size(mezz)
    src_w, src_h = src_size
    spans = [(s, e) for _, s, e in (words or [])]
    t0, frames_n, next_id = time.time(), 0, 0
    for a, b in pieces:
        tracks = face_tracks(samples, a, b)
        if len(tracks) < 2:
            continue
        frames = _decode(mezz, a, b, DECODE_WIDTH, src_w, src_h)
        frames_n += len(frames)
        fh, fw = frames.shape[1:3] if len(frames) else (src_h, src_w)
        live = []
        for tr in tracks:
            bxs = [f for _, f in tr["boxes"]]
            x0, y0 = min(f["x"] for f in bxs), min(f["y"] for f in bxs)
            union = {"x": x0, "y": y0, "w": max(f["x"] + f["w"] for f in bxs) - x0, "h": max(f["y"] + f["h"] for f in bxs) - y0}
            series = mouth_series(frames, a, crop_region(bxs, fw, fh), union)
            if len(series) >= MIN_LANDMARK_SHARE * max(1, len(frames)):
                live.append((next_id, tr, series))
                result["tracks"].append({"id": next_id, "box": tr["box"], "start_us": a, "end_us": b})
                next_id += 1
        if len(live) < 2:
            continue  # one visible face (the other is the back of a head): nothing to compare
        starts = list(range(a, b, WINDOW_US))
        activity = [{tid: window_activity(series, s, min(b, s + WINDOW_US)) for tid, _, series in live} for s in starts]
        gate = speech_windows(a, b, rms_db, hop_us, spans if words is not None else None, speech)
        states = smooth(attribute(activity, gate))
        result["segments"] += segments(states, a, b, spans)
    for i, s, e in words or []:
        mid = (s + e) // 2
        seg = next((g for g in result["segments"] if g["start_us"] <= mid < g["end_us"]), None)
        if seg is not None:
            result["words"][str(i)] = seg["track"]
    result["frames"] = frames_n
    result["landmark_s"] = round(time.time() - t0, 2)
    return result


# ------------------------------------------------------------------ lookups


def speaker_at(speakers: dict | None, clip: str, t_us: int) -> int | None:
    """Track id of the active speaker in `clip` at source time `t_us` (None = unknown / uncertain /
    single-face footage). For J/L cuts and per-word speaker labels."""
    for seg in ((speakers or {}).get(clip) or {}).get("segments") or []:
        if seg["start_us"] <= t_us < seg["end_us"]:
            return seg["track"]
    return None
