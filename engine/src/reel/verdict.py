"""QA stage: gates + fresh-context Reviewer + sendable/hold verdict (ADR-0021).

`sendable` only when no blocking gate fails, every unsure caption word is confirmed, and the
Reviewer reports no blocker/major issue. Otherwise `hold(reasons)`. The verdict also carries the
revision request the fix loop may send to the Editor (fixable blocking gates, and Reviewer
issues once the Reviewer is calibrated — config.REVIEWER_TRUSTED).
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

from reel import claude_call, config, cuts, decide, project, qa, sheets
from reel import brief as brief_mod
from reel import timebase as tb
from reel.schemas.plan import FinishPlan, StoryPlan
from reel.schemas.review import FixTarget, Review, Severity
from reel.schemas.timeline import Timeline
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

REVIEWER_PERSONA = Path(__file__).parent / "personas" / "reviewer.md"
REVIEW_EFFORT = "medium"
SHEET_EVERY_S = 1.0
REVIEW_PROMPT = ("Review this finished reel. Read qa/review_input.md first, then look at every contact sheet and cut strip it lists. "
                 "Return your review.")


def confirmed_words(ws: Workspace) -> dict:
    p = ws.path("qa", "proof_confirmed.json")
    return json.loads(p.read_text()) if p.exists() else {}


def _faces_props(ws: Workspace) -> tuple[list[dict], dict]:
    props = json.loads(ws.path("render", "overlay.props.json").read_text())
    return props.get("faces", []), props.get("safe", {"top": 220, "bottom": 420, "left": 60, "right": 130})


def run_gates(ws: Workspace, tl: Timeline, story: StoryPlan, brief: brief_mod.Brief | None) -> list[qa.GateResult]:
    words = project.word_table(ws).by_index()
    kept_text = " ".join(words[i].text for it in story.items for i in range(it.word_start, it.word_end + 1))
    faces, safe = _faces_props(ws)
    flashes = [(f.at_f - f.frames // 2 - 1, f.at_f + f.frames // 2 + 1) for f in tl.flashes]
    dips = [(t.at_f - t.frames, t.at_f + t.frames) for t in tl.transitions if t.type.value in ("dip_to_black", "dip_to_white")]
    proof = json.loads(ws.path("qa", "proof_list.json").read_text()) if ws.path("qa", "proof_list.json").exists() else []
    final, base, ov = ws.path("render", "final.mp4"), ws.path("render", "base.mov"), ws.path("render", "overlay.mov")
    fin_file = ws.path("plan", "finish.json")
    fin = FinishPlan.model_validate_json(fin_file.read_text()) if fin_file.exists() else None
    results = [*qa.frame_and_loudness(tl, final), qa.proof_words(proof, confirmed_words(ws)), qa.brief_compliance(tl, kept_text, brief),
               qa.numbers_match(fin, story, project.word_table(ws)),
               qa.broll_repeat(fin, project.indexes(ws).broll),
               qa.dead_air(tl), qa.reading_speed(tl), qa.face_cut(tl, faces), *qa.caption_pixels(tl, base, ov, faces, safe, flashes),
               *qa.frozen_and_black(tl, final, dips)]
    return qa.apply_modes(results)


def cut_checks(ws: Workspace, tl: Timeline) -> tuple[list[qa.GateResult], list[str]]:
    """Cut-point self-check (reel.cuts): gates + the strips the Reviewer looks at."""
    gates, report = cuts.check(ws, tl, project.word_table(ws), project.edges(ws))
    return qa.apply_modes(gates), report["review_strips"]


def pace_numbers(ws: Workspace, tl: Timeline, options: dict) -> dict:
    """Pace of our render and of the reference reel, measured the same way (qa.measure_pace), plus the exact
    timeline counts. A measurement that fails is recorded as such: it never passes silently."""
    out: dict = {"timeline": qa.timeline_changes(tl), "speech_share": qa.speech_share(tl)}
    try:
        out["ours"] = qa.measure_pace(ws.path("render", "final.mp4"))
        ref = options.get("reference")
        out["reference"] = qa.measure_pace(Path(ref)) if ref and Path(ref).exists() else None
    except Exception as exc:  # noqa: BLE001 — scenedetect missing or an unreadable file: report, don't crash QA
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def pace_results(pace: dict) -> list[qa.GateResult]:
    if "ours" not in pace:
        why = f"not measured ({pace.get('error', 'unknown error')})"
        return qa.apply_modes([qa.GateResult("pace", False, detail=why), qa.GateResult("static_stretch", False, detail=why)])
    return qa.apply_modes(qa.pace_gates(pace["ours"], pace.get("reference")))


def client_style_results(ws: Workspace, cuts_per_min: float | None) -> list[qa.GateResult]:
    """3a.2: does this reel look like the ones this client approved? Warns on two or more departures."""
    from reel import client_memory

    p = client_memory.profile(ws)
    fp = ws.path("plan", "finish.json")
    if not p or not fp.exists():
        return qa.apply_modes([qa.GateResult("client_style_drift", True, detail="no approved reels for this client yet")])
    d = client_memory.drift(p, json.loads(fp.read_text()), cuts_per_min)
    return qa.apply_modes([qa.GateResult("client_style_drift", len(d) < 2, detail="; ".join(d) or f"consistent with {p['reels']} approved reel(s)",
                                         fixable=True, fix_hint="Match the client's usual captions, look and pace unless the brief asks for a change.",
                                         measured={"departures": d, "profile_reels": p["reels"]})])


def pace_lines(pace: dict | None, gates: list[qa.GateResult]) -> list[str]:
    if not pace:
        return []
    lines = ["", "## Pace (measured on the final render; judge pacing, story and shot choice, not only defects)", ""]
    ours, ref, t = pace.get("ours"), pace.get("reference"), pace["timeline"]
    if ours:
        lines.append(f"- Scene cuts: {ours['cuts_per_min']} per minute; longest stretch with no cut {ours['longest_static_s']} s"
                     + (f" (reference reel: {ref['cuts_per_min']} per minute, longest {ref['longest_static_s']} s)" if ref else ""))
    lines.append(f"- Timeline picture changes: {t['cuts']} cuts, {t['punch_ins']} punch-in changes, {t['pip_changes']} picture-in-picture "
                 f"in/outs = {t['changes_per_min']} per minute; longest unchanged {t['longest_unchanged_s']} s")
    lufs = next((g.measured.get("lufs") for g in gates if g.gate == "loudness" and g.measured.get("lufs") is not None), None)
    if lufs is not None:
        lines.append(f"- Integrated loudness {lufs:.1f} LUFS")
    lines.append(f"- Speech on screen {int(pace['speech_share'] * 100)} % of the reel; silent {100 - int(pace['speech_share'] * 100)} %")
    return lines


def review_input(ws: Workspace, tl: Timeline, story: StoryPlan, brief, gates: list[qa.GateResult], sheet_paths: list[Path],
                 cut_strips: list[str] | None = None, pace: dict | None = None) -> str:
    fps = tb.parse_rate(tl.fps)
    hook = next((h for h in story.hook_options if h.id == story.hook), None)
    lines = ["# Review input", "", "## Brief", "", json.dumps(brief.model_dump(exclude_none=True), ensure_ascii=False, indent=1) if brief else "No brief.", "",
             "## What the Editor intended", "", f"- Genre: {story.genre}", f"- Summary: {story.summary}",
             f"- Hook: {hook.reason if hook else '?'}", *[f"- {it.id} ({it.beat}): {it.reason}" for it in story.items], "",
             "## Read-back (output timecodes)", "", ws.path("plan", "story_readback.txt").read_text().strip(), "",
             "## On-screen text", ""]
    lines += [f"- title {qa.tc(t.start_f, fps)}–{qa.tc(t.end_f, fps)}: “{t.text}”" for t in tl.titles] or ["- no title"]
    if tl.captions:
        lines.append(f"- captions: family {tl.captions.family}, {len(tl.captions.pages)} pages, timing {tl.captions.timing}")
        lines += [f"  - {qa.tc(p.start_f, fps)} " + " ".join(("*" + w.text + "*") if w.emph else w.text for w in p.words) for p in tl.captions.pages]
    lines += ["", f"## Look: {tl.grade.look} at {tl.grade.strength}", "", "## Automatic QA", "", "| gate | result | mode | detail |", "|---|---|---|---|"]
    lines += [f"| {g.gate} | {'pass' if g.ok else 'FAIL'} | {g.mode} | {g.detail} {(' at ' + ', '.join(g.at[:6])) if g.at else ''} |" for g in gates]
    lines += pace_lines(pace, gates)
    lines += ["", "## Contact sheets of the final render (one frame per second, labelled with the timecode)", ""]
    lines += [f"- {p.relative_to(ws.root)}" for p in sheet_paths]
    if cut_strips:
        lines += ["", "## Cut strips (timeline view: 10 frames from 1.5 s before to 1.5 s after the cut over the audio waveform; "
                  "red line = the cut; the header names any automatic finding). First and last 2 s, then the most suspicious cuts", ""]
        lines += [f"- {s}" for s in cut_strips]
    return "\n".join(lines) + "\n"


def final_sheets(ws: Workspace, tl: Timeline) -> list[Path]:
    fps = tb.parse_rate(tl.fps)
    dur = float(Fraction(tl.duration_f) / fps)
    stamps = [(t, f"{int(t // 60)}:{t % 60:04.1f}") for t in [k * SHEET_EVERY_S + 0.25 for k in range(int(dur / SHEET_EVERY_S) + 1)] if t < dur]
    for old in ws.path("qa", "sheets").glob("*.png") if ws.path("qa", "sheets").exists() else []:
        old.unlink()
    return sheets.make_sheets(ws.path("render", "final.mp4"), stamps, ws.path("qa", "sheets", "final"))


def decide_verdict(gates: list[qa.GateResult], review: Review | None) -> dict:
    reasons, requests = [], []
    for g in gates:
        if g.blocking:
            reasons.append(f"{g.gate}: {g.detail}")
            if g.fixable:
                requests.append(f"- [{g.gate}] {g.detail}{(' at ' + ', '.join(g.at[:6])) if g.at else ''}. Fix: {g.fix_hint}")
    if review:
        for i in review.issues:
            if i.severity in (Severity.blocker, Severity.major):
                reasons.append(f"reviewer {i.severity.value} ({i.category.value}) at {i.at or 'whole reel'}: {i.problem}")
                if config.REVIEWER_TRUSTED and i.fix_target != FixTarget.owner:
                    requests.append(f"- [reviewer {i.id}, {i.fix_target.value}] at {i.at or 'whole reel'}: {i.problem} Fix: {i.fix}")
        if not review.sendable and not any(i.severity in (Severity.blocker, Severity.major) for i in review.issues):
            reasons.append(f"reviewer: not sendable — {review.summary}")
    warnings = [f"{g.gate}: {g.detail}" for g in gates if not g.ok and not g.blocking]
    status = "hold" if reasons else "sendable"
    request = ("Quality check before delivery found these problems. Fix all of them in one revision, changing nothing else:\n"
               + "\n".join(requests)) if requests else ""
    return {"status": status, "reasons": reasons, "warnings": warnings, "fix_request": request}


def verdict_md(v: dict, gates: list[qa.GateResult], review: Review | None, proof_open: list[dict]) -> str:
    head = "✅ SENDABLE" if v["status"] == "sendable" else "⏸ HOLD"
    lines = [f"# {head}", ""]
    if v["reasons"]:
        lines += ["## Why it is on hold", "", *[f"- {r}" for r in v["reasons"]], ""]
    if proof_open:
        lines += ["## Proof list — confirm or correct these caption words (~30 s)", "",
                  *[f"- `{p['i']}` at {p['at']}: “{p['text']}”" + (f" → suggestion “{p['suggestion']}”" if p.get("suggestion") else "") + f" ({p['why']})" for p in proof_open],
                  "", "`reel proof --project <p> --ok <i> --fix <i>=<text>` then `reel run` (re-renders captions only).", ""]
    if v["warnings"]:
        lines += ["## Warnings (gates not yet calibrated — not blocking)", "", *[f"- {w}" for w in v["warnings"]], ""]
    if review:
        lines += ["## Reviewer", "", review.summary, "", *[f"- **{i.severity.value}** {i.category.value} at {i.at or '—'}: {i.problem} → {i.fix}" for i in review.issues]]
        lines += ["", "Strengths: " + "; ".join(review.strengths), ""]
    lines += ["## Gates", "", "| gate | | mode | detail |", "|---|---|---|---|"]
    lines += [f"| {g.gate} | {'✓' if g.ok else '✗'} | {g.mode} | {g.detail} |" for g in gates]
    return "\n".join(lines) + "\n"


def recompute(ws: Workspace) -> dict | None:
    """Re-decide the verdict from the stored gate results and review with today's gate modes: switching a gate between
    warn and block (Quality lab, C3) needs no new measurement and no Reviewer call. None when QA never ran."""
    gp, rp = ws.path("qa", "gates.json"), ws.path("qa", "review.json")
    if not gp.exists():
        return None
    gates = qa.apply_modes([qa.GateResult(**g) for g in json.loads(gp.read_text())])
    review = Review.model_validate_json(rp.read_text()) if rp.exists() else None
    v = decide_verdict(gates, review)
    proof_open = next((g.measured.get("open", []) for g in gates if g.gate == "proof_words"), [])
    atomic_write_json(gp, [g.as_dict() for g in gates])
    atomic_write_json(ws.path("qa", "verdict.json"), v | {"proof_open": proof_open})
    atomic_write_bytes(ws.path("qa", "verdict.md"), verdict_md(v, gates, review, proof_open).encode())
    return v


def run(ws: Workspace, options: dict, caller=claude_call.call) -> dict:
    tl = Timeline.model_validate_json(ws.path("timeline", "timeline.json").read_text())
    story = project.load_json_model(StoryPlan, ws.path("plan", "story.json"))
    brief = brief_mod.load_brief(options.get("brief"))
    gates = run_gates(ws, tl, story, brief)
    cut_gates, strips = cut_checks(ws, tl)
    gates += cut_gates
    pace = pace_numbers(ws, tl, options)
    gates += pace_results(pace)
    gates += client_style_results(ws, (pace.get("ours") or {}).get("cuts_per_min"))
    atomic_write_json(ws.path("qa", "pace.json"), pace)
    sheet_paths = final_sheets(ws, tl)
    atomic_write_bytes(ws.path("qa", "review_input.md"), review_input(ws, tl, story, brief, gates, sheet_paths, strips, pace).encode())
    review = None
    if not options.get("skip_review"):
        d = decide.decide(caller, ws, label="review", prompt=REVIEW_PROMPT, model=Review, persona=REVIEWER_PERSONA,
                          effort=REVIEW_EFFORT, check=lambda r: [])
        review = d.plan
        atomic_write_json(ws.path("qa", "review.json"), review.model_dump(mode="json"))
    v = decide_verdict(gates, review)
    proof_open = next((g.measured.get("open", []) for g in gates if g.gate == "proof_words"), [])
    atomic_write_json(ws.path("qa", "gates.json"), [g.as_dict() for g in gates])
    atomic_write_json(ws.path("qa", "verdict.json"), v | {"proof_open": proof_open})
    atomic_write_bytes(ws.path("qa", "verdict.md"), verdict_md(v, gates, review, proof_open).encode())
    return {"verdict": v["status"], "reasons": len(v["reasons"]), "warnings": len(v["warnings"]),
            "reviewer_issues": len(review.issues) if review else None}
