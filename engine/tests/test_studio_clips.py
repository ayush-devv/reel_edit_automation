"""G2.2 Clip Factory in Reel Studio: the board, making reels, the source and reel-project statuses."""

from __future__ import annotations

import json

from reel import mine
from reel.studio import costs
from reel.workspace import Workspace, atomic_write_json

from test_clipfactory import N_SEGS, FakeClaude, _cand, _faces, _segments, _seg_range, _words
from test_studio import env, make_project  # noqa: F401 — the env fixture


def _source(root):
    w = Workspace.create(root / "podcast")
    atomic_write_json(w.path("source", "manifest.json"), {"project_fps": "30/1", "clips": [{"id": "c01", "probe": {
        "duration_s": 600.0, "video": {"display_width": 1920, "display_height": 1080}}}]})
    atomic_write_json(w.path("perception", "words.json"), _words().model_dump(mode="json"))
    atomic_write_json(w.path("perception", "segments.json"), _segments().model_dump(mode="json"))
    atomic_write_json(w.path("perception", "faces.json"), _faces())
    w.path("mezz").mkdir(parents=True, exist_ok=True)  # no movie: spawning then skips the contact sheets
    w.path("tables").mkdir(parents=True, exist_ok=True)
    w.path("tables", "script.md").write_text("# Script\n" + "\n".join(f"[s{n:03d} …] text" for n in range(N_SEGS)) + "\n")
    w.path("tables", "summary.md").write_text("# Footage summary\n")
    atomic_write_json(w.path("run_options.json"), {"input": "/x/podcast.mp4", "language": "en", "brief": None, "mine": True})
    atomic_write_json(w.path("studio.json"), {"name": "Podcast ep 4", "client": "Acme", "kind": "source"})
    stages = {n: {"status": "done", "input_hash": "x", "outputs": ["o"], "meta": {}, "finished": 1795000100.0}
              for n in ("ingest", "mezzanine", "perception", "tables", "mine")}
    atomic_write_json(w.path("state.json"), {"schema": 1, "stages": stages})
    mine.mine_pass(w, {}, FakeClaude({"candidates": [_cand("c01", [_seg_range(2, 4)]), _cand("c02", [_seg_range(20, 22)], family="story")]}))
    return w


def test_board_lists_candidates_with_the_engines_score(env):
    _source(env["root"])
    proj = next(p for p in env["c"].get("/api/projects").json() if p["id"] == "podcast")
    assert proj["status"] == "source" and proj["kind"] == "source" and "pick the reels to make" in proj["needs_attention"]
    detail = env["c"].get("/api/projects/podcast").json()
    assert [s["name"] for s in detail["stages"]] == ["ingest", "mezzanine", "perception", "tables", "mine"]
    board = env["c"].get("/api/projects/podcast/clips").json()
    assert board["score_label"] == "Editor's estimate" and len(board["candidates"]) == 2
    c01 = next(c for c in board["candidates"] if c["id"] == "c01")
    assert c01["status"] == "selected" and c01["excerpt"].startswith("w60") and c01["project"] is None
    assert board["estimate_per_reel"] is None  # fewer than 3 past edits: no guess


def test_making_reels_spawns_projects_and_queues_their_edits(env):
    _source(env["root"])
    r = env["c"].post("/api/projects/podcast/clips/make", json={"ids": ["c01"], "run": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["made"] == ["podcast__c01"] and len(body["jobs"]) == 1
    job, _p = env["launcher"].procs[-1]
    assert job.argv[-3:] == ["run", "--project", str(env["root"] / "podcast__c01")]
    child = env["c"].get("/api/projects/podcast__c01").json()
    assert child["kind"] == "clip" and child["parent"] == "podcast" and child["name"] == "title c01"
    assert all(s["status"] == "skipped" for s in child["stages"] if s["name"] in ("ingest", "mezzanine", "perception", "tables"))
    env["launcher"].finish("run")
    board = env["c"].get("/api/projects/podcast/clips").json()
    assert next(c for c in board["candidates"] if c["id"] == "c01")["project"]["id"] == "podcast__c01"
    picks = (env["root"] / "podcast" / "mine" / "picks.jsonl").read_text().splitlines()
    assert json.loads(picks[-1])["picked"] == ["c01"]
    assert "pick the reels to make" not in next(p for p in env["c"].get("/api/projects").json() if p["id"] == "podcast")["needs_attention"]


def test_bad_ids_and_unmined_projects_are_refused(env):
    _source(env["root"])
    assert env["c"].post("/api/projects/podcast/clips/make", json={"ids": ["c99"], "run": False}).status_code == 400
    make_project(env["root"], "plain")
    assert env["c"].get("/api/projects/plain/clips").status_code == 404


def test_a_reel_project_can_be_retried_without_an_input(env):
    _source(env["root"])
    env["c"].post("/api/projects/podcast/clips/make", json={"ids": ["c02"], "run": False})
    r = env["c"].post("/api/projects/podcast__c02/retry", json={})
    assert r.status_code == 200, r.text
    job, _p = env["launcher"].procs[-1]
    assert job.argv[-3:] == ["run", "--project", str(env["root"] / "podcast__c02")]


def test_cost_estimate_needs_three_past_edits(tmp_path):
    root = tmp_path / "projects"
    for n in range(3):
        log = root / f"p{n}" / "log" / "runs.jsonl"
        log.parent.mkdir(parents=True)
        log.write_text("\n".join(json.dumps(r) for r in [
            {"time": 1, "label": "story", "cost_usd": 0.10 + n / 100, "session_id": f"a{n}"},
            {"time": 2, "label": "story_readback", "cost_usd": 0.15 + n / 100, "session_id": f"b{n}", "resume": f"a{n}"},
            {"time": 3, "label": "finish", "cost_usd": 0.20, "session_id": f"c{n}"},
            {"time": 4, "label": "finish:fix1", "cost_cum_usd": 0.25, "session_id": f"d{n}", "resume": f"c{n}"},
        ]) + "\n")
    est = costs.per_reel_estimate(root)
    assert est["from_edits"] == 3 and est["low_usd"] == round(0.11 + 0.05 + 0.25, 3)  # story, readback delta, finish + fix delta
