"""`reel run` with the bounded fix loop (ADR-0021): render → QA → (revise → re-render → QA) ≤ N times.

Only the verdict's `fix_request` is sent to the Editor (fixable blocking gates; Reviewer issues
once the Reviewer is calibrated). Anything else ends the run with `hold(reasons)`.
"""

from __future__ import annotations

import json

from reel import claude_call, config, decide
from reel.runner import StageContext, load_state, run_pipeline, save_state
from reel.workspace import Workspace


def apply_revision(ws: Workspace, options: dict, request: str, caller=claude_call.call) -> dict:
    """Resume the Editor's finish session with a revision; the revised plans become the finish stage's output."""
    from reel.stages import edit

    with ws.lock():
        res = decide.revise(decide.load_inputs(ws, options.get("brief"), options.get("brand")), request, caller)
        state = load_state(ws)
        ctx = StageContext(ws=ws, options=options)
        state["stages"]["finish"] = {**state["stages"].get("finish", {}), "status": "done", "input_hash": edit.FINISH.input_hash(ctx),
                                     "meta": {"revision": res}}
        save_state(ws, state)
    return res


def run(ws: Workspace, stages, options: dict, *, force: set[str] | None = None, caller=None, max_loops: int | None = None) -> dict:
    caller = caller or options.get("claude_call") or claude_call.call
    opts = {**options, "claude_call": caller}
    max_loops = config.MAX_FIX_LOOPS if max_loops is None else max_loops
    history = []
    state = run_pipeline(ws, stages, options=opts, force=force)
    for loop in range(max_loops + 1):
        vfile = ws.path("qa", "verdict.json")
        if not vfile.exists():
            break
        v = json.loads(vfile.read_text())
        history.append({"loop": loop, "status": v["status"], "reasons": v["reasons"]})
        if v["status"] == "sendable" or not v.get("fix_request") or loop == max_loops:
            break
        res = apply_revision(ws, opts, v["fix_request"], caller)
        history[-1]["revision"] = res.get("reply")
        state = run_pipeline(ws, stages, options=opts)
    return {"state": state, "loops": history}
