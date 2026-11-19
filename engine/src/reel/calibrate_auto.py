"""Automatic gate calibration (ADR-0033 §1): known-good pro finals + known-bad injected defects.

- Known-good: the gates that can judge a finished file on its own (frozen, black) run on the
  professional finals of the gold set. Every failure is a FALSE ALARM. (Caption gates need our
  separate overlay layer, which a pro final does not have: they are calibrated on known-bad only.)
- Known-bad: copies of one of our real renders, each with ONE injected defect at a different spot
  per trial. The gate meant to catch that defect must fail; every pass is a MISS.
- Promotion rule: a gate may go from warn to block with 0 false alarms on the pro finals and
  ≥ 9/10 catches of its own defect. The report recommends; config.QA_GATES stays the owner's switch.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

from reel import config, qa, tools
from reel import timebase as tb
from reel.schemas.timeline import Timeline
from reel.workspace import atomic_write_json

PROMOTE_MAX_FALSE_ALARMS = 0
SPEC_GATES = {"loudness", "frame_count"}
PROMOTE_MIN_CATCH = 0.9
EXCERPT_S = 20.0

# defect → the gate that must catch it
DEFECTS = {
    "black_stretch": "black",
    "frozen_stretch": "frozen",
    "loudness_low": "loudness",
    "captions_over_face": "caption_over_face",
    "captions_in_ui_zone": "safe_zone",
    "captions_see_through": "caption_contrast",
    "captions_wrong_colour": "caption_contrast",
}


def _stub(fps: Fraction, frames: int, w: int = 1080, h: int = 1920) -> Timeline:
    return Timeline(fps=f"{fps.numerator}/{fps.denominator}", width=w, height=h, duration_f=frames, assets={}, video=[], audio=[])


def _file_tl(path: Path) -> Timeline:
    st = tools.ffprobe_json(path, ["-select_streams", "v:0"])["streams"][0]
    fps = Fraction(st.get("avg_frame_rate") or st["r_frame_rate"]).limit_denominator(1001)
    return _stub(fps, len(tools.ffprobe_frame_times(path)), int(st["width"]), int(st["height"]))


# ------------------------------------------------------------------ known-good


def known_good(gold_root: Path) -> list[dict]:
    rows = []
    for final in sorted(gold_root.glob("*/final.mp4")):
        tl = _file_tl(final)
        results = qa.frozen_and_black(tl, final, [])
        rows.append({"reel": final.parent.name, "failed": [r.gate for r in results if not r.ok],
                     "detail": {r.gate: r.detail for r in results}})
    return rows


# ------------------------------------------------------------------ known-bad: file-level defects


def _ff(args: list[str]) -> None:
    tools.ffmpeg(["-y", "-hide_banner", "-loglevel", "error", *args])


def _excerpt(final: Path, out: Path, seconds: float = EXCERPT_S) -> Path:
    _ff(["-i", str(final), "-t", f"{seconds}", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-c:a", "aac", str(out)])
    return out


def inject_black(src: Path, out: Path, at_s: float, dur_s: float = 0.6) -> None:
    _ff(["-i", str(src), "-vf", f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,{at_s:.3f},{at_s + dur_s:.3f})'",
         "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-c:a", "copy", str(out)])


def inject_freeze(src: Path, out: Path, at_s: float, fps: Fraction, dur_s: float = qa.FROZEN_S + 0.8) -> None:
    n = int(dur_s * fps) + 1
    _ff(["-i", str(src), "-filter_complex",
         f"[0:v]split[a][b];[b]trim=start={at_s:.3f}:end={at_s + 0.2:.3f},setpts=PTS-STARTPTS,trim=end_frame=1,"
         f"loop=loop={n}:size=1,setpts=N/({fps.numerator}/{fps.denominator})/TB+{at_s:.3f}/TB[f];"
         f"[a][f]overlay=eof_action=pass:enable='between(t,{at_s:.3f},{at_s + dur_s:.3f})'[v]",
         "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-c:a", "copy", str(out)])


def inject_gain(src: Path, out: Path, gain_db: float) -> None:
    _ff(["-i", str(src), "-c:v", "copy", "-af", f"volume={gain_db}dB", "-c:a", "aac", "-b:a", "256k", str(out)])


# ------------------------------------------------------------------ known-bad: caption defects on extracted frames


def shift_rows(rgba: np.ndarray, dy: int) -> np.ndarray:
    """Move the overlay picture by dy rows (negative = up); vacated rows are transparent."""
    out = np.zeros_like(rgba)
    if dy < 0:
        out[:dy] = rgba[-dy:]
    elif dy > 0:
        out[dy:] = rgba[:-dy]
    else:
        out[:] = rgba
    return out


def fade(rgba: np.ndarray, k: float) -> np.ndarray:
    out = rgba.copy()
    out[..., 3] = (out[..., 3].astype(float) * k).astype(rgba.dtype)
    return out


def recolour(rgba: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """Text drawn in the colour of the picture behind it (the classic 'white on a white wall')."""
    out = rgba.copy()
    a = out[..., 3] > 0
    if a.any():
        out[..., :3][a] = np.median(bg.reshape(-1, 3), axis=0).astype(rgba.dtype)
    return out


def _caption_trial(tl: Timeline, ov: dict, bg: dict, faces: list[dict], safe: dict, defect: str, trial: int) -> list[qa.GateResult]:
    h = next(iter(ov.values())).shape[0]
    scale = h / tl.height  # sample rows per output px
    pages = sorted(ov)
    if defect == "captions_over_face":
        # move each page's caption onto that page's face (a different spot inside the face per trial)
        mutated = {}
        jitter = (trial % 5 - 2) / 10  # −0.2 … +0.2 face heights
        for f, o in ov.items():
            span = next((sp for sp in faces if sp["start_f"] <= f < sp["end_f"] and sp.get("box")), None)
            rows = np.nonzero(o[..., 3].max(axis=1) > 128)[0]
            if span is None or rows.size == 0:
                mutated[f] = shift_rows(o, -int(560 * scale))
                continue
            b = span["box"]
            target = (b["y"] + b["h"] * (0.5 + jitter)) * h
            mutated[f] = shift_rows(o, int(round(target - (rows.min() + rows.max()) / 2)))
    elif defect == "captions_in_ui_zone":
        dy = int((330 + 25 * trial) * scale)
        mutated = {f: shift_rows(o, dy) for f, o in ov.items()}
    elif defect == "captions_see_through":
        mutated = {f: fade(o, 0.12 + 0.03 * (trial % 5)) for f, o in ov.items()}
    else:  # captions_wrong_colour, on a different third of the pages per trial
        chosen = set(pages[trial % 3::3])
        mutated = {f: (recolour(o, bg[f]) if f in chosen and f in bg else o) for f, o in ov.items()}
    return qa.caption_pixels_from(tl, mutated, bg, faces, safe, [])


# ------------------------------------------------------------------ run


def known_bad(ws_root: Path, trials: int = 10, work: Path | None = None) -> dict[str, list[dict]]:
    tl = Timeline.model_validate_json((ws_root / "timeline" / "timeline.json").read_text())
    fps = tb.parse_rate(tl.fps)
    final, base, ov_path = ws_root / "render" / "final.mp4", ws_root / "render" / "base.mov", ws_root / "render" / "overlay.mov"
    props = json.loads((ws_root / "render" / "overlay.props.json").read_text())
    faces, safe = props.get("faces", []), props.get("safe", {"top": 220, "bottom": 420, "left": 60, "right": 130})
    out: dict[str, list[dict]] = {d: [] for d in DEFECTS}
    tmp = Path(tempfile.mkdtemp(prefix="reel_calib_", dir=work))
    try:
        # clean baselines: a defect only counts if the clean input passes the same gate
        excerpt = _excerpt(final, tmp / "excerpt.mp4")
        ex_tl = _file_tl(excerpt)
        clean_fb = {r.gate: r.ok for r in qa.frozen_and_black(ex_tl, excerpt, [])}
        clean_loud = {r.gate: r.ok for r in qa.frame_and_loudness(tl, final)}
        frames = qa.page_frames(tl)
        ov = qa.frames_at(ov_path, frames, alpha=True)
        bg = qa.frames_at(base, frames)
        clean_cap = {r.gate: set(r.at) for r in qa.caption_pixels_from(tl, ov, bg, faces, safe, [])}  # pages already failing
        span = max(1.0, EXCERPT_S - qa.FROZEN_S - 2.0)
        for n in range(trials):
            at = 0.5 + span * n / max(1, trials - 1)
            # black
            p = tmp / f"black_{n}.mp4"
            inject_black(excerpt, p, at)
            r = {x.gate: x for x in qa.frozen_and_black(ex_tl, p, [])}
            out["black_stretch"].append({"at_s": round(at, 2), "caught": not r["black"].ok, "valid": clean_fb.get("black", True)})
            p.unlink(missing_ok=True)
            # frozen
            p = tmp / f"frozen_{n}.mp4"
            inject_freeze(excerpt, p, at, fps)
            r = {x.gate: x for x in qa.frozen_and_black(ex_tl, p, [])}
            out["frozen_stretch"].append({"at_s": round(at, 2), "caught": not r["frozen"].ok, "valid": clean_fb.get("frozen", True)})
            p.unlink(missing_ok=True)
            # loudness: −3 … −12 dB (well outside the ±1 LU tolerance)
            gain = -(3.0 + n)
            p = tmp / f"quiet_{n}.mp4"
            inject_gain(final, p, gain)
            r = {x.gate: x for x in qa.frame_and_loudness(_file_tl(p), p)}
            out["loudness_low"].append({"gain_db": gain, "caught": not r["loudness"].ok, "valid": clean_loud.get("loudness", True)})
            p.unlink(missing_ok=True)
            # captions
            for defect in ("captions_over_face", "captions_in_ui_zone", "captions_see_through", "captions_wrong_colour"):
                gate = DEFECTS[defect]
                r = {x.gate: x for x in _caption_trial(tl, ov, bg, faces, safe, defect, n)}
                # our own render already fails a few pages: a catch must be NEW failing pages, on pages that were clean
                already = clean_cap.get(gate, set())
                new = set(r[gate].at) - already
                out[defect].append({"trial": n, "caught": bool(new), "valid": len(already) < len(frames), "new_pages": len(new),
                                    "baseline_pages": len(already), "detail": r[gate].detail})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def report(good: list[dict], bad: dict[str, list[dict]]) -> dict:
    gates: dict[str, dict] = {}
    for row in good:
        for g in ("frozen", "black"):
            d = gates.setdefault(g, {"false_alarms": 0, "known_good": 0})
            d["known_good"] += 1
            d["false_alarms"] += g in row["failed"]
    for defect, trials in bad.items():
        g = DEFECTS[defect]
        valid = [t for t in trials if t["valid"]]
        d = gates.setdefault(g, {"false_alarms": None, "known_good": 0})
        d.setdefault("defects", {})[defect] = {"caught": sum(t["caught"] for t in valid), "trials": len(valid),
                                               "invalid_baseline": len(trials) - len(valid)}
    for g, d in gates.items():
        rates = [v["caught"] / v["trials"] for v in d.get("defects", {}).values() if v["trials"]]
        d["catch_rate"] = round(min(rates), 3) if rates else None
        d["mode_now"] = config.QA_GATES.get(g, "warn")
        fa_ok = d["false_alarms"] is not None and d["false_alarms"] <= PROMOTE_MAX_FALSE_ALARMS and d["known_good"] > 0
        d["promote_to_block"] = bool(fa_ok and d["catch_rate"] is not None and d["catch_rate"] >= PROMOTE_MIN_CATCH)
        if g in SPEC_GATES:
            d["note"] = "delivery-spec gate (a measured requirement, not a judgement): blocks by definition"
            d["promote_to_block"] = d["mode_now"] == "block"
        elif d["false_alarms"] is None:
            d["note"] = "no known-good check possible (pro finals have burned-in captions); promotion waits for pro-editor labels (ADR-0033 §2)"
    return {"rule": f"block when false alarms ≤ {PROMOTE_MAX_FALSE_ALARMS} on the pro finals and catch rate ≥ {PROMOTE_MIN_CATCH:.0%}",
            "known_good_reels": len(good), "gates": gates, "known_good": good}


def run(projects_root: Path, gold_root: Path, project: str, trials: int, out_dir: Path) -> dict:
    t0 = time.time()
    good = known_good(gold_root)
    bad = known_bad(projects_root / project, trials)
    rep = report(good, bad) | {"project": project, "trials": trials, "seconds": round(time.time() - t0, 1), "defect_trials": bad}
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_dir / f"auto_{time.strftime('%Y%m%d_%H%M%S')}.json", rep)
    atomic_write_json(out_dir / "auto_latest.json", rep)
    return rep


DEFAULT_OUT = config.REPO_ROOT / "eval" / "calibration"
