"""Reference-style imitation (build step 10f): measure a finished reel the client likes and give
the Editor a concrete style profile to match (pacing, captions, colour), plus contact sheets.

No Claude call here — measurements only; the Editor reads `context/reference_style.md`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from reel import sheets
from reel.perception import visual
from reel.perception.audio import read_frames
from reel.probe import probe
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

OCR_FPS = 2.0


def colour_stats(frames: np.ndarray) -> dict:
    x = frames.reshape(-1, 3).astype(np.float64) / 255.0
    lum = x @ np.array([0.2126, 0.7152, 0.0722])
    mx, mn = x.max(axis=1), x.min(axis=1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    return {"mean_luma": round(float(lum.mean()), 3), "contrast": round(float(lum.std()), 3), "saturation": round(float(sat.mean()), 3),
            "warmth": round(float((x[:, 0] - x[:, 2]).mean()), 3), "black_level": round(float(np.percentile(lum, 2)), 3)}


def suggest_look(c: dict) -> tuple[str, float]:
    """Nearest of reel.color.LOOKS by simple, explainable rules."""
    if c["black_level"] > 0.08 and c["saturation"] < 0.35:
        return "film", 0.6
    if c["contrast"] > 0.26 and c["saturation"] > 0.45:
        return "punchy", 0.5
    if c["warmth"] > 0.06:
        return "warm", 0.5
    if c["warmth"] < -0.03:
        return "cool", 0.5
    return "clean", 0.4


def caption_stats(items: list[dict], samples: int, frame_hw: tuple[int, int], frames: np.ndarray) -> dict:
    """On-screen text that behaves like captions (letters, ≤ 8 words, not a static logo)."""
    text = [it for it in items if sum(ch.isalpha() for ch in it["text"]) >= 2 and len(it["text"].split()) <= 8]
    by_t: dict[int, list[dict]] = {}
    for it in text:
        by_t.setdefault(it["t_us"], []).append(it)
    if not text:
        return {"on_screen_share": 0.0}
    letters = "".join(ch for it in text for ch in it["text"] if ch.isalpha())
    upper = sum(ch.isupper() for ch in letters) / max(1, len(letters))
    ys = [(it["box"][1] + it["box"][3]) / 2 for it in text]
    words = [len(it["text"].split()) for it in text]
    h, w = frame_hw
    light, boxed = [], []
    for it in text:  # text brightness vs its surroundings, and whether the block sits on a flat box
        k = min(int(it["t_us"] / 1e6 * OCR_FPS), len(frames) - 1)
        x0, y0, x1, y1 = (int(it["box"][0] * w), int(it["box"][1] * h), int(it["box"][2] * w), int(it["box"][3] * h))
        patch = frames[k, y0:y1, x0:x1].reshape(-1, 3).astype(float)
        if patch.size < 30:
            continue
        lum = patch @ np.array([0.2126, 0.7152, 0.0722])
        light.append(float(np.percentile(lum, 90) - np.median(lum)) > float(np.median(lum) - np.percentile(lum, 10)))
        boxed.append(float(np.percentile(lum, 25)) < 70 and float(np.std(lum[lum < np.percentile(lum, 50)])) < 12)
    return {"on_screen_share": round(len(by_t) / max(1, samples), 2), "words_per_block": round(float(np.median(words)), 1),
            "upper_share": round(upper, 2), "y_centre": round(float(np.median(ys)), 2),
            "light_text": bool(np.mean(light) > 0.5) if light else None, "boxed": bool(np.mean(boxed) > 0.5) if boxed else None}


def measure_style(video: Path) -> dict:
    """Pacing, caption and colour measurements of a finished reel (no files written)."""
    p = probe(video)
    dur = p.duration_s
    cuts = visual.scene_cuts(video)
    shots = len(cuts) + 1
    frames, h, w = read_frames(video, OCR_FPS, 360)
    ocr = visual.ocr(video, fps=OCR_FPS, width=360)
    prof = {"duration_s": round(dur, 1), "shots": shots, "avg_shot_s": round(dur / shots, 2), "cuts_per_min": round(len(cuts) / dur * 60, 1),
            "motion": round(float(np.mean(visual.motion_energy(video).get("values") or [0.0])), 2),
            "colour": colour_stats(frames[:: max(1, len(frames) // 24)]),
            "captions": caption_stats(ocr.get("items", []), len(frames), (h, w), frames)}
    prof["look"], prof["look_strength"] = suggest_look(prof["colour"])
    return prof


def style_vector(prof: dict) -> dict[str, float]:
    """The numbers the style family compares (ADR-0030: robust z vs the genre's reference library)."""
    cap, col = prof.get("captions", {}), prof.get("colour", {})
    return {"cuts_per_min": prof.get("cuts_per_min", 0.0), "motion": prof.get("motion", 0.0),
            "caption_share": cap.get("on_screen_share", 0.0), "words_per_block": cap.get("words_per_block", 0.0) or 0.0,
            "upper_share": cap.get("upper_share", 0.0) or 0.0, "contrast": col.get("contrast", 0.0), "saturation": col.get("saturation", 0.0)}


def analyse(ws: Workspace, ref: Path, *, asr_backend=None) -> dict:
    prof = measure_style(ref)
    dur = prof["duration_s"]
    if asr_backend is not None and probe(ref).audio is not None:
        from reel.perception.audio import extract_wav

        words, _lang = asr_backend.transcribe(extract_wav(ref, ws.path("reference", "ref.wav")), None, None)
        speech_s = sum(w.end_s - w.start_s for w in words)
        prof["speech"] = {"words": len(words), "words_per_s": round(len(words) / max(dur, 1e-6), 2),
                          "talk_share": round(speech_s / max(dur, 1e-6), 2)}
    stamps = [(t, f"ref {t:.1f}s") for t in np.arange(0.5, dur, max(1.0, dur / 24))]
    prof["sheets"] = [str(s.relative_to(ws.root)) for s in sheets.make_sheets(ref, stamps, ws.path("reference", "sheets", "ref"))]
    atomic_write_json(ws.path("reference", "style.json"), prof)
    atomic_write_bytes(ws.path("context", "reference_style.md"), style_md(prof).encode())
    return {k: prof[k] for k in ("duration_s", "cuts_per_min", "look")}


def style_md(p: dict) -> str:
    c, cap = p["colour"], p["captions"]
    lines = ["# Reference style — the client wants a reel like this one (match it unless the brand kit says otherwise)", "",
             f"- **Length** {p['duration_s']} s · **{p['shots']} shots**, one every {p['avg_shot_s']} s (**{p['cuts_per_min']} cuts/min**) — match the cut rhythm with cuts, punch-ins or b-roll.",
             f"- **Motion** energy {p['motion']} (0–255 mean frame difference)."]
    if "speech" in p:
        s = p["speech"]
        lines.append(f"- **Speech** {s['words_per_s']} words/s, talking {int(s['talk_share'] * 100)} % of the time — trim pauses to a similar density.")
    if cap.get("on_screen_share"):
        case = "UPPER CASE" if cap["upper_share"] > 0.7 else "sentence/title case"
        pos = "upper third" if cap["y_centre"] < 0.4 else "middle" if cap["y_centre"] < 0.62 else "lower part"
        lines.append(f"- **Captions** on screen {int(cap['on_screen_share'] * 100)} % of the time, ~{cap['words_per_block']} words per block, {case}, "
                     f"in the {pos} of the frame (y≈{cap['y_centre']}), {'light' if cap.get('light_text') else 'dark'} text"
                     f"{', on a box' if cap.get('boxed') else ''} — pick the closest caption family and tokens.")
    else:
        lines.append("- **Captions**: none burned in.")
    lines.append(f"- **Colour** brightness {c['mean_luma']}, contrast {c['contrast']}, saturation {c['saturation']}, warmth {c['warmth']:+} → nearest look "
                 f"`{p['look']}` at {p['look_strength']}.")
    lines += ["", "Contact sheets of the reference: " + ", ".join(p["sheets"]), ""]
    return "\n".join(lines)
