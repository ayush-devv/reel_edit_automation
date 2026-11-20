"""Revision evals (roadmap 3b.3): did the revision do what the note asked, and nothing else?

Each case (eval/revisions/*.yaml) names a finished project, a client note, the expected change kind and, for a
local change, the output region it should land in. The harness runs `decide.revise` on a copy of the project, compiles
the result, and compares old vs new with the partial re-render diff (`rediff.changed_ranges`, G1.5) plus a timeline diff:
- **did_it**: something of the expected kind changed (inside the region when one is given);
- **collateral_s**: seconds of overlay change *outside* the region, plus base-picture changes outside it;
- **dont_break**: the plan still validates (no error) and no new validator warning appeared.
No render is spent: plans and props are compared. One Claude call per case.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from fractions import Fraction
from pathlib import Path

import yaml

from reel import config

CASES = config.EVAL_DIR / "revisions"
SCOREBOARD = config.EVAL_DIR / "revisions_scoreboard.jsonl"
SKIP_DIRS = {"render", "export", "versions", "log", "qa"}
KINDS = ("captions", "music", "cut", "look", "graphics")


def load_cases(folder: Path | None = None) -> list[dict]:
    folder = folder or CASES
    out = []
    for f in sorted(folder.glob("*.yaml")) if folder.exists() else []:
        c = yaml.safe_load(f.read_text()) or {}
        c.setdefault("id", f.stem)
        if c.get("expect", {}).get("kind") not in KINDS:
            raise ValueError(f"{f.name}: expect.kind must be one of {KINDS}")
        out.append(c)
    return out


def _link(src: str, dst: str) -> None:
    try:
        os.link(src, dst)  # plans are rewritten atomically (new inode), so the original project is never touched
    except OSError:
        shutil.copy2(src, dst)


def copy_project(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, copy_function=_link, ignore=lambda d, names: [n for n in names if Path(d) == src and n in SKIP_DIRS])
    return dst


def _props(ws, tl) -> dict:
    from reel import overlay

    def read(name):
        p = ws.path("perception", f"{name}.json")
        return json.loads(p.read_text()) if p.exists() else None

    return overlay.build_props(tl, ws.root, read("faces"), read("ocr"), read("scenes"), read("speakers"))


def _compile(ws, options, inp=None):
    """Compile the current plans. `inp` is reused across calls: loading it probes every mezzanine (minutes on a long
    source), and a revision changes only the plans, never the footage."""
    from reel import decide, project
    from reel.runner import StageContext
    from reel.schemas.plan import FinishPlan, StoryPlan
    from reel.stages.edit import compile_for

    ctx = StageContext(ws=ws, options=options)
    inp = inp or decide.load_inputs(ws, options.get("brief"), options.get("brand"))
    story = project.load_json_model(StoryPlan, ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ws.path("plan", "finish.json"))
    tl, _ = compile_for(ctx, inp, story, fin)
    return tl, inp, story, fin


def _video_changes(old, new) -> list[tuple[int, int]]:
    """Output frame spans whose picture source changed (cuts, punch-ins, speed): differing video clips."""
    key = lambda v: (v.at_f, v.dur_f, v.src_in_us, v.src_out_us, tuple((k.f, k.v) for k in v.scale), v.speed)  # noqa: E731
    from reel.rediff import _merge

    a, b = {key(v) for v in old.video}, {key(v) for v in new.video}
    return _merge([(v.at_f, v.at_f + v.dur_f) for v in [*old.video, *new.video] if key(v) in (a ^ b)])  # merged: no double count


def measure(old_tl, new_tl, old_props, new_props, expect: dict, warnings_before: int, warnings_after: int, errors_after: int) -> dict:
    from reel import rediff
    from reel import timebase as tb

    fps = tb.parse_rate(new_tl.fps)
    sec = lambda f: float(Fraction(f) / fps)  # noqa: E731
    overlay = rediff.changed_elements(old_props, new_props)  # what changed, not what a partial render would redo
    overlay = [(0, max(old_tl.duration_f, new_tl.duration_f))] if overlay is None else overlay  # a global overlay change
    video = _video_changes(old_tl, new_tl)
    music = [a.model_dump() for a in old_tl.audio if a.role == "music"] != [a.model_dump() for a in new_tl.audio if a.role == "music"]
    look = old_tl.grade != new_tl.grade
    region = expect.get("region_s")
    lo, hi = (region or [0, 1e9])

    def inside(span):
        return sec(span[1]) > lo and sec(span[0]) < hi

    def outside_s(spans):
        tot = 0.0
        for a, b in spans:
            s0, s1 = sec(a), sec(b)
            tot += max(0.0, min(s1, lo) - s0) + max(0.0, s1 - max(s0, hi)) if region else 0.0
        return tot

    kind = expect["kind"]
    if kind in ("captions", "graphics"):
        did = any(inside(r) for r in overlay)
    elif kind == "cut":
        did = any(inside(r) for r in video) or old_tl.duration_f != new_tl.duration_f
    elif kind == "music":
        did = music
    else:
        did = look
    collateral = outside_s(overlay) + (outside_s(video) if kind != "cut" or region else 0.0)
    if kind in ("music", "look") and not region:  # a global change: any picture/overlay change at all is collateral
        collateral = sum(sec(b) - sec(a) for a, b in overlay + video)
    return {"did_it": bool(did), "collateral_s": round(collateral, 2), "dont_break": errors_after == 0 and warnings_after <= warnings_before,
            "overlay_changed_s": round(sum(sec(b) - sec(a) for a, b in overlay), 2), "picture_changed_s": round(sum(sec(b) - sec(a) for a, b in video), 2),
            "music_changed": music, "look_changed": look}


def run_case(case: dict, work: Path, caller) -> dict:
    from reel import decide
    from reel.validate import errors, validate_finish
    from reel.workspace import Workspace

    src = (config.REPO_ROOT / case["project"]).resolve()
    ws = Workspace(copy_project(src, work / case["id"]))
    options = json.loads(ws.path("run_options.json").read_text()) if ws.path("run_options.json").exists() else {}
    # The baseline is the UNREVISED plans compiled with today's code, never the stored timeline: that one may come from
    # an older engine, and every code change since would count as the revision's collateral.
    old_tl, inp, story0, fin0 = _compile(ws, options)
    old_props = _props(ws, old_tl)
    w_before = len(validate_finish(fin0, story0, inp.words, inp.idx, inp.kids))
    res = decide.revise(inp, case["note"], caller)
    new_tl, inp, story1, fin1 = _compile(ws, options, inp)
    issues = validate_finish(fin1, story1, inp.words, inp.idx, inp.kids)
    m = measure(old_tl, new_tl, old_props, _props(ws, new_tl), case["expect"], w_before, len(issues) - len(errors(issues)), len(errors(issues)))
    return {"id": case["id"], "note": case["note"], "reply": res["reply"], "calls": res["calls"], "cost_usd": res["cost_usd"], **m}


def run_all(caller=None, *, cases: list[dict] | None = None, work_root: Path | None = None) -> dict:
    from reel import claude_call

    cases = load_cases() if cases is None else cases
    run_id = time.strftime("%Y%m%d-%H%M%S")
    work = work_root or (config.REPO_ROOT / "projects" / "_eval" / f"revisions-{run_id}")
    rows = []
    for c in cases:
        try:
            rows.append(run_case(c, work, caller or claude_call.call))
        except Exception as exc:  # noqa: BLE001 — a crash counts against the case, never stops the run
            rows.append({"id": c["id"], "note": c.get("note"), "error": f"{type(exc).__name__}: {exc}", "did_it": False, "dont_break": False})
    ok = [r for r in rows if "error" not in r]
    out = {"run_id": run_id, "time": time.time(), "cases": rows, "did_it": sum(r["did_it"] for r in rows), "n": len(rows),
           "dont_break": sum(r["dont_break"] for r in rows),
           "mean_collateral_s": round(sum(r["collateral_s"] for r in ok) / len(ok), 2) if ok else None}
    SCOREBOARD.parent.mkdir(parents=True, exist_ok=True)
    with SCOREBOARD.open("a") as f:
        f.write(json.dumps(out) + "\n")
    return out
