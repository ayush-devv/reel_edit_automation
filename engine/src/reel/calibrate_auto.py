"""Automatic gate calibration (ADR-0033 §1): known-good pro finals + known-bad injected defects.

- Known-good: the gates that can judge a finished file on its own (frozen, black) run on the
  professional finals of the gold set. Every failure is a FALSE ALARM. (Caption gates need our
  separate overlay layer, which a pro final does not have: they are calibrated on known-bad only.)
- Known-bad: copies of one of our real renders, each with ONE injected defect at a different spot
  per trial. The gate meant to catch that defect must fail; every pass is a MISS.
- A trial counts as caught only if the gate flags at least half of the pages the defect actually changed
  (recall ≥ 0.5 over mutated pages that were clean at baseline), not merely one page anywhere.
- Promotion rule: a gate may go from warn to block with 0 false alarms on ≥ 30 known-good pro finals and
  ≥ 9/10 catches of its own defect. With fewer known-good reels "0 false alarms" says little: 0/6 still allows
  a ~39 % false-alarm rate at 95 % confidence, so gates stay `warn` until the known-good set is large enough.
  The report recommends; config.QA_GATES stays the owner's switch.
"""

from __future__ import annotations

import json
import math
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
PROMOTE_MIN_KNOWN_GOOD = 30  # 0/30 false alarms bounds the false-alarm rate below ~10 % (95 %); 0/6 only below ~39 %
SPEC_GATES = {"loudness", "frame_count"}
PROMOTE_MIN_CATCH = 0.9
MIN_RECALL = 0.5  # a caption trial is caught when the gate flags ≥ half of the pages the defect changed
EXCERPT_S = 20.0
EDGE_S = qa.HEAD_TAIL_S + 0.1  # injections stay clear of the head/tail fade exemption
BLACK_S = 0.6
FREEZE_S = qa.FROZEN_S + 0.8

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


def fa_upper_95(false_alarms: int, n: int) -> float | None:
    """One-sided 95 % (Clopper-Pearson) upper bound on the false-alarm rate after `false_alarms` in `n` known-good reels."""
    if n <= 0:
        return None
    if false_alarms >= n:
        return 1.0

    def cdf(p: float) -> float:
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(false_alarms + 1))

    lo, hi = 0.0, 1.0
    for _ in range(60):  # cdf falls as p rises: find p where P(X ≤ k) = 0.05
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) > 0.05 else (lo, mid)
    return hi


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
    """Text drawn in the colour of the picture right behind it (the classic 'white on a white wall'): the median
    of the background inside the caption's bounding box, around the text."""
    out = rgba.copy()
    a = out[..., 3] > 0
    if a.any():
        ys, xs = np.nonzero(a)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        local = bg[y0:y1, x0:x1][~a[y0:y1, x0:x1]]
        src = local if local.size else bg[y0:y1, x0:x1].reshape(-1, 3)
        out[..., :3][a] = np.median(src.reshape(-1, 3), axis=0).astype(rgba.dtype)
    return out


def mutate_captions(tl: Timeline, ov: dict, bg: dict, faces: list[dict], safe: dict, defect: str, trial: int) -> tuple[dict, set[int]]:
    """Inject one caption defect → (mutated overlay samples, frames whose caption the defect actually changed in a way
    its gate can see). Titles, graphics and PiPs are stripped first (qa.caption_layer), so only captions move; frames
    the gates cannot judge (full-screen card, flash) are left as they are."""
    h = next(iter(ov.values())).shape[0]
    scale = h / tl.height  # sample rows per output px
    caps = {f: qa.caption_layer(tl, f, o, faces, safe) for f, o in ov.items()}
    visible = {f for f, c in caps.items() if c is not None and (c[..., 3] > 128).any()}
    mutated = {f: (c if c is not None else ov[f]) for f, c in caps.items()}
    changed: set[int] = set()
    if defect == "captions_over_face":
        # move each page's caption onto that page's face (a different spot inside the face per trial)
        jitter = (trial % 5 - 2) / 10  # −0.2 … +0.2 face heights
        for f in visible:
            o = mutated[f]
            span = next((sp for sp in faces if sp["start_f"] <= f < sp["end_f"] and sp.get("box")), None)
            rows = np.nonzero(o[..., 3].max(axis=1) > 128)[0]
            if span is None:
                mutated[f] = shift_rows(o, -int(560 * scale))  # no face to land on: cannot count for this gate
                continue
            b = span["box"]
            target = (b["y"] + b["h"] * (0.5 + jitter)) * h
            mutated[f] = shift_rows(o, int(round(target - (rows.min() + rows.max()) / 2)))
            changed.add(f)
    elif defect == "captions_in_ui_zone":
        dy = int((330 + 25 * trial) * scale)
        for f in visible:
            mutated[f] = shift_rows(mutated[f], dy)
        changed = set(visible)
    elif defect == "captions_see_through":
        for f in visible:
            mutated[f] = fade(mutated[f], 0.12 + 0.03 * (trial % 5))
        full = {f for f, op in qa.page_samples(tl) if op >= 0.999}  # a page sampled mid-fade is never called see-through
        changed = visible & full
    else:  # captions_wrong_colour, on a different third of the pages per trial
        chosen = set(sorted(ov)[trial % 3::3]) & visible & set(bg)
        for f in chosen:
            mutated[f] = recolour(mutated[f], bg[f])
        changed = chosen
    return mutated, changed


def _caption_trial(tl: Timeline, ov: dict, bg: dict, faces: list[dict], safe: dict, defect: str, trial: int) -> list[qa.GateResult]:
    return qa.caption_pixels_from(tl, mutate_captions(tl, ov, bg, faces, safe, defect, trial)[0], bg, faces, safe, [])


def caption_recall(gate: qa.GateResult, baseline_failing: set[str], changed_tcs: set[str]) -> tuple[float | None, int, int]:
    """(recall, newly failing mutated pages, eligible pages): eligible = pages the defect changed that passed at
    baseline and that the gate judged. None when no page is eligible (the trial cannot measure anything)."""
    eligible = changed_tcs - baseline_failing - set(gate.measured.get("skipped", []))
    new = (set(gate.at) - baseline_failing) & eligible
    return (len(new) / len(eligible) if eligible else None), len(new), len(eligible)


def injection_times(dur_s: float, trials: int) -> list[float]:
    """Start times for the black/freeze injections, spread over the excerpt's real length: every injection starts after
    the head fade window and ends (freeze: FREEZE_S long) before the tail window. [] when the excerpt is too short."""
    lo, hi = EDGE_S, dur_s - EDGE_S - max(FREEZE_S, BLACK_S)
    if hi < lo or trials <= 0:
        return []
    return [round(lo + (hi - lo) * n / max(1, trials - 1), 3) for n in range(trials)]


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
        ex_dur = float(Fraction(ex_tl.duration_f) / tb.parse_rate(ex_tl.fps))
        times = injection_times(ex_dur, trials)
        for n in range(trials):
            at = times[n] if times else None
            for defect, gate, inject in (("black_stretch", "black", inject_black),
                                         ("frozen_stretch", "frozen", lambda s, d, t: inject_freeze(s, d, t, fps))):
                if at is None:  # excerpt too short to hold the injection clear of the head/tail fades
                    out[defect].append({"at_s": None, "caught": False, "valid": False, "excerpt_s": round(ex_dur, 2)})
                    continue
                p = tmp / f"{gate}_{n}.mp4"
                inject(excerpt, p, at)
                r = {x.gate: x for x in qa.frozen_and_black(ex_tl, p, [])}
                out[defect].append({"at_s": round(at, 2), "caught": not r[gate].ok, "valid": clean_fb.get(gate, True)})
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
                mutated, changed = mutate_captions(tl, ov, bg, faces, safe, defect, n)
                r = {x.gate: x for x in qa.caption_pixels_from(tl, mutated, bg, faces, safe, [])}
                # our own render already fails a few pages: a catch must be NEW failing pages among the pages the defect
                # changed that were clean, and at least MIN_RECALL of them
                already = clean_cap.get(gate, set())
                recall, new, eligible = caption_recall(r[gate], already, {qa.tc(f, fps) for f in changed})
                out[defect].append({"trial": n, "caught": recall is not None and recall >= MIN_RECALL, "valid": recall is not None,
                                    "recall": None if recall is None else round(recall, 3), "new_pages": new, "eligible_pages": eligible,
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
        row = {"caught": sum(t["caught"] for t in valid), "trials": len(valid), "invalid_baseline": len(trials) - len(valid)}
        recalls = [t["recall"] for t in valid if t.get("recall") is not None]
        if recalls:
            row["mean_recall"] = round(sum(recalls) / len(recalls), 3)
        d.setdefault("defects", {})[defect] = row
    for g, d in gates.items():
        rates = [v["caught"] / v["trials"] for v in d.get("defects", {}).values() if v["trials"]]
        d["catch_rate"] = round(min(rates), 3) if rates else None
        d["mode_now"] = config.QA_GATES.get(g, "warn")
        n_good, fa = d["known_good"], d["false_alarms"]
        if fa is not None and n_good:
            d["fa_upper_95"] = round(fa_upper_95(fa, n_good), 3)
        waiting = []
        if fa is None or not n_good:
            waiting.append("no known-good check")
        else:
            if fa > PROMOTE_MAX_FALSE_ALARMS:
                waiting.append(f"{fa} false alarm(s) on {n_good} known-good reels")
            if n_good < PROMOTE_MIN_KNOWN_GOOD:
                waiting.append(f"only {n_good}/{PROMOTE_MIN_KNOWN_GOOD} known-good reels")
        if d["catch_rate"] is None or d["catch_rate"] < PROMOTE_MIN_CATCH:
            waiting.append(f"catch rate {d['catch_rate']} < {PROMOTE_MIN_CATCH}")
        d["promote_to_block"] = not waiting
        if waiting:
            d["waiting_for"] = waiting
        if g in SPEC_GATES:
            d["note"] = "delivery-spec gate (a measured requirement, not a judgement): blocks by definition"
            d["promote_to_block"] = d["mode_now"] == "block"
            d.pop("waiting_for", None)
        elif fa is None:
            d["note"] = "no known-good check possible (pro finals have burned-in captions); promotion waits for pro-editor labels (ADR-0033 §2)"
    n = len(good)
    ub = fa_upper_95(0, n)
    stats = (f"0 false alarms on {n} known-good reels still allows a false-alarm rate up to {ub:.0%} at 95 % confidence "
             f"(Clopper-Pearson; {PROMOTE_MIN_KNOWN_GOOD} reels bring that to {fa_upper_95(0, PROMOTE_MIN_KNOWN_GOOD):.0%}), so no measured gate "
             f"is promoted before {PROMOTE_MIN_KNOWN_GOOD} known-good reels. Catch rates come from defects injected into ONE of our renders, "
             f"so they say how well a gate sees that defect, not how often real reels have it.") if n else "no known-good reels"
    return {"rule": (f"block when false alarms ≤ {PROMOTE_MAX_FALSE_ALARMS} on ≥ {PROMOTE_MIN_KNOWN_GOOD} known-good pro finals and catch rate "
                     f"≥ {PROMOTE_MIN_CATCH:.0%} (a caption trial is caught when recall ≥ {MIN_RECALL:.0%} of the pages it changed)"),
            "rule_params": {"max_false_alarms": PROMOTE_MAX_FALSE_ALARMS, "min_known_good": PROMOTE_MIN_KNOWN_GOOD,
                            "min_catch": PROMOTE_MIN_CATCH, "min_recall": MIN_RECALL},
            "statistics": stats, "known_good_reels": n, "gates": gates, "known_good": good}


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
