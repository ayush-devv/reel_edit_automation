import json
import os

import pytest

from reel.runner import Stage, run_pipeline
from reel.workspace import LockedError, Workspace, atomic_write_json


def _stage(name, calls, fail=False):
    def run(ctx):
        calls.append(name)
        if fail:
            raise RuntimeError("boom")
        atomic_write_json(ctx.ws.path("log", f"{name}.json"), {"v": ctx.options.get("v")})
        return {"n": len(calls)}

    return Stage(
        name=name,
        input_hash=lambda ctx: str(ctx.options.get("v")),
        outputs=lambda ctx: [ctx.ws.path("log", f"{name}.json")],
        run=run,
    )


def test_idempotent_and_resume(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    calls = []
    stages = [_stage("a", calls), _stage("b", calls)]
    run_pipeline(ws, stages, options={"v": 1})
    assert calls == ["a", "b"]
    run_pipeline(ws, stages, options={"v": 1})
    assert calls == ["a", "b"]  # nothing re-ran
    run_pipeline(ws, stages, options={"v": 2})
    assert calls == ["a", "b", "a", "b"]  # input change re-runs


def _reader(name, upstream, calls):
    """A stage whose input hash is the content of the upstream stage's output."""
    def run(ctx):
        calls.append(name)
        atomic_write_json(ctx.ws.path("log", f"{name}.json"), json.loads(ctx.ws.path("log", f"{upstream}.json").read_text()))
        return {}

    return Stage(name=name, input_hash=lambda ctx: ctx.ws.path("log", f"{upstream}.json").read_text(),
                 outputs=lambda ctx: [ctx.ws.path("log", f"{name}.json")], run=run)


def test_downstream_reruns_only_when_its_inputs_change(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    calls = []
    stages = [_stage("a", calls), _reader("b", "a", calls)]
    run_pipeline(ws, stages, options={"v": 1})
    ws.path("log", "a.json").unlink()  # a re-runs and writes the same output → b is still up to date
    run_pipeline(ws, stages, options={"v": 1})
    assert calls == ["a", "b", "a"]
    run_pipeline(ws, stages, options={"v": 2})  # a's output changes → b follows
    assert calls == ["a", "b", "a", "a", "b"]


def test_failure_recorded_then_resume(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    calls = []
    with pytest.raises(RuntimeError):
        run_pipeline(ws, [_stage("a", calls), _stage("b", calls, fail=True)], options={"v": 1})
    state = json.loads(ws.state_file.read_text())
    assert state["stages"]["a"]["status"] == "done"
    assert state["stages"]["b"]["status"] == "failed"
    assert not ws.lock_file.exists()  # lock released after failure
    run_pipeline(ws, [_stage("a", calls), _stage("b", calls)], options={"v": 1})
    assert calls == ["a", "b", "b"]  # a skipped, b resumed


def test_lock_blocks_concurrent_run(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    with ws.lock():
        with pytest.raises(LockedError):
            with ws.lock():
                pass


def test_stale_lock_taken_over(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    import socket

    ws.lock_file.write_text(json.dumps({"pid": 999_999_9, "host": socket.gethostname()}))
    with ws.lock():
        assert json.loads(ws.lock_file.read_text())["pid"] == os.getpid()


def test_force_reruns(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    calls = []
    stages = [_stage("a", calls), _stage("b", calls)]
    run_pipeline(ws, stages, options={"v": 1})
    run_pipeline(ws, stages, options={"v": 1}, force={"b"})
    assert calls == ["a", "b", "b"]
