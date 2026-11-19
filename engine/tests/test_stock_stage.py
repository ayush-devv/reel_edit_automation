"""Edit-time stock b-roll (the `stock` stage): Claude writes searches from the talk, Pexels fills the project's pool.

No network: the Claude caller and the Pexels fetch are fakes.
"""

from __future__ import annotations

import json

import pytest

from reel import stock
from reel.claude_call import CallResult
from reel.runner import StageContext
from reel.stages import edit
from reel.workspace import Workspace


def _result(data: dict) -> CallResult:
    return CallResult(data=data, session_id="s", num_turns=1, cost_usd=0.001, usage={}, duration_s=0.0)


def _video(i: int, dur: int = 8) -> dict:
    return {"id": i, "duration": dur, "url": f"https://pexels.com/v/{i}", "user": {"name": f"A{i}"},
            "video_files": [{"link": f"https://x/{i}.mp4", "width": 1080, "height": 1920}]}


def _fetch(per_query: dict[str, list[int]], fail: set[str] = frozenset()):
    calls = []

    def fetch(url, key):
        calls.append(url)
        if "api.pexels.com" in url:
            q = next((q for q in per_query if q.replace(" ", "+") in url), None)
            if q in fail:
                raise OSError("network down")
            return json.dumps({"videos": [_video(i) for i in per_query.get(q, [])]}).encode()
        return b"MP4DATA"

    return fetch, calls


def test_no_key_skips_without_calling_anyone(tmp_path, monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    caller_calls = []
    out = stock.fetch_for_project(tmp_path, tmp_path / "clips", lambda *a, **k: caller_calls.append(1))
    assert out["status"] == "skipped" and "Pexels" in out["reason"] and not caller_calls and not (tmp_path / "clips").exists()


def test_queries_fill_the_pool_with_caps_dedupe_and_licence(tmp_path):
    queries = [{"query": "sugar cubes falling", "moment": "8 teaspoons"}, {"query": "orange juice pouring", "moment": "the juice"},
               {"query": "brain scan", "moment": "dementia"}, {"query": "kitchen scale", "moment": "weighing"}]
    fetch, _ = _fetch({"sugar cubes falling": [1, 2, 3], "orange juice pouring": [2, 4, 5], "brain scan": [6, 7], "kitchen scale": [8]})
    out = stock.fetch_for_project(tmp_path, tmp_path / "clips", lambda *a, **k: _result({"queries": queries}), key="k", fetch=fetch)
    assert out["status"] == "ok" and len(out["clips"]) == stock.MAX_CLIPS  # 2 per query, 6 total
    assert out["clips"][:4] == ["pexels_1.mp4", "pexels_2.mp4", "pexels_4.mp4", "pexels_5.mp4"]  # clip 2 is not taken twice
    side = json.loads((tmp_path / "clips" / "pexels_1.json").read_text())
    assert side["source"] == "Pexels" and side["query"] == "sugar cubes falling"


def test_failures_never_stop_the_edit(tmp_path):
    def broken_caller(*a, **k):
        raise RuntimeError("claude unavailable")

    assert stock.fetch_for_project(tmp_path, tmp_path / "c", broken_caller, key="k")["status"] == "failed"
    queries = [{"query": "sugar cubes", "moment": ""}, {"query": "juice glass", "moment": ""}]
    fetch, _ = _fetch({"sugar cubes": [1], "juice glass": [2]}, fail={"sugar cubes"})
    out = stock.fetch_for_project(tmp_path, tmp_path / "c", lambda *a, **k: _result({"queries": queries}), key="k", fetch=fetch)
    assert out["status"] == "ok" and out["clips"] == ["pexels_2.mp4"] and out["errors"][0].startswith("sugar cubes")
    fetch, _ = _fetch({})
    out = stock.fetch_for_project(tmp_path, tmp_path / "e", lambda *a, **k: _result({"queries": queries}), key="k", fetch=fetch)
    assert out["status"] == "empty" and out["clips"] == []


def test_stage_is_off_by_default_and_hashes_inputs_not_results(tmp_path, monkeypatch):
    ws = Workspace.create(tmp_path / "p")
    (ws.root / "tables").mkdir(parents=True, exist_ok=True)
    (ws.root / "tables" / "summary.md").write_text("A talk about sugar in juice.")
    off = StageContext(ws=ws, options={})
    assert edit.STOCK.input_hash(off) == "off" and edit.STOCK.run(off) == {"status": "off"} and edit.STOCK.outputs(off) == []

    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    on = StageContext(ws=ws, options={"stock": True})
    no_key = edit.STOCK.input_hash(on)
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    with_key = edit.STOCK.input_hash(on)
    assert no_key != with_key  # adding a key later lets a rerun fetch
    (ws.root / "stock" / "clips").mkdir(parents=True)
    (ws.root / "stock" / "clips" / "pexels_9.mp4").write_bytes(b"x")  # results already on disk …
    assert edit.STOCK.input_hash(on) == with_key  # … do not change the hash: a rerun never searches again
    (ws.root / "tables" / "summary.md").write_text("A different talk.")
    assert edit.STOCK.input_hash(on) != with_key


def test_stage_writes_status_and_broll_indexes_both_folders(tmp_path, monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    ws = Workspace.create(tmp_path / "p")
    client = tmp_path / "client"
    client.mkdir()
    (client / "own.mp4").write_bytes(b"x")
    calls = {}
    monkeypatch.setattr(stock, "fetch_for_project", lambda root, out, caller, **kw: (out.mkdir(parents=True, exist_ok=True),
                                                                                    (out / "pexels_1.mp4").write_bytes(b"x"),
                                                                                    {"status": "ok", "queries": [], "clips": ["pexels_1.mp4"], "errors": []})[-1])
    ctx = StageContext(ws=ws, options={"stock": True, "broll": str(client)})
    assert edit.STOCK.run(ctx) == {"status": "ok", "clips": 1}
    assert json.loads((ws.root / "stock" / "status.json").read_text())["clips"] == ["pexels_1.mp4"]
    from reel import broll

    monkeypatch.setattr(broll, "index", lambda w, folders, fps, caller: calls.setdefault("folders", folders) and {"clips": 2})
    monkeypatch.setattr(edit.project, "project_fps", lambda w: 25)
    edit.BROLL.run(ctx)
    assert [f.name for f in calls["folders"]] == ["client", "clips"]
    assert edit.BROLL.outputs(StageContext(ws=ws, options={})) == []


@pytest.mark.parametrize("flag", [True, False])
def test_run_args_carry_the_stock_switch(tmp_path, flag):
    from reel.studio.app import _run_args

    args = _run_args(tmp_path, {"input": "/x", "stock": flag})
    assert ("--stock" in args) is flag
