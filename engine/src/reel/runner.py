"""`reel run` state machine (ADR-0020).

Each stage declares how to compute its input hash, which outputs prove it is done, and how
to run. A stage is skipped only when its stored input hash matches and every output exists
and passes the stage's own validation. State lives in state.json, written atomically.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from reel.workspace import Workspace, atomic_write_json

log = logging.getLogger(__name__)


@dataclass
class StageContext:
    ws: Workspace
    options: dict = field(default_factory=dict)

    def state(self) -> dict:
        return load_state(self.ws)


@dataclass(frozen=True)
class Stage:
    name: str
    input_hash: Callable[[StageContext], str]
    outputs: Callable[[StageContext], list[Path]]
    run: Callable[[StageContext], dict]  # returns stage metadata to store
    validate: Callable[[StageContext], bool] = lambda ctx: True


def load_state(ws: Workspace) -> dict:
    if ws.state_file.exists():
        return json.loads(ws.state_file.read_text())
    return {"schema": 1, "stages": {}}


def save_state(ws: Workspace, state: dict) -> None:
    atomic_write_json(ws.state_file, state)


def _is_done(ctx: StageContext, stage: Stage, entry: dict, input_hash: str) -> bool:
    if entry.get("status") != "done" or entry.get("input_hash") != input_hash:
        return False
    if not all(p.exists() for p in stage.outputs(ctx)):
        return False
    try:
        return bool(stage.validate(ctx))
    except Exception:  # validation failure means redo
        log.exception("validation of %s failed", stage.name)
        return False


def run_pipeline(ws: Workspace, stages: list[Stage], *, options: dict | None = None, force: set[str] | None = None) -> dict:
    """Run stages in order under the workspace lock. Returns the final state."""
    force = force or set()
    ctx = StageContext(ws=ws, options=options or {})
    with ws.lock():
        state = load_state(ws)
        for stage in stages:
            entry = state["stages"].get(stage.name, {})
            # computed after upstream stages ran: every input hash covers the upstream outputs it
            # reads, so a stage re-runs exactly when its own inputs changed (a caption-only change
            # re-renders the overlay, never the base)
            ih = stage.input_hash(ctx)
            if stage.name not in force and _is_done(ctx, stage, entry, ih):
                log.info("skip %s (up to date)", stage.name)
                continue
            log.info("run %s", stage.name)
            state["stages"][stage.name] = {"status": "running", "input_hash": ih, "started": time.time()}
            save_state(ws, state)
            try:
                meta = stage.run(ctx) or {}
                if not all(p.exists() for p in stage.outputs(ctx)):
                    missing = [str(p) for p in stage.outputs(ctx) if not p.exists()]
                    raise RuntimeError(f"{stage.name} finished without outputs: {missing}")
                if not stage.validate(ctx):
                    raise RuntimeError(f"{stage.name} outputs failed validation")
            except Exception as exc:
                state["stages"][stage.name] = {
                    "status": "failed",
                    "input_hash": ih,
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace": traceback.format_exc(limit=5),
                    "finished": time.time(),
                }
                save_state(ws, state)
                raise
            state["stages"][stage.name] = {
                "status": "done",
                "input_hash": ih,
                "outputs": [str(p.relative_to(ws.root)) for p in stage.outputs(ctx)],
                "meta": meta,
                "finished": time.time(),
            }
            save_state(ws, state)
        return state
