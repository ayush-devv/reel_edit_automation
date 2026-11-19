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
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    caller_calls = []
    out = stock.fetch_for_project(tmp_path, tmp_path / "clips", lambda *a, **k: caller_calls.append(1))
    assert out["status"] == "skipped" and "Pixabay" in out["reason"] and not caller_calls and not (tmp_path / "clips").exists()


def _pixabay_hit(i: int, w: int = 1920, h: int = 1080, dur: int = 10) -> dict:
    return {"id": i, "duration": dur, "pageURL": f"https://pixabay.com/videos/{i}/", "user": f"U{i}",
            "videos": {"large": {"url": f"https://cdn.pixabay.com/{i}_large.mp4", "width": w, "height": h},
                       "medium": {"url": f"https://cdn.pixabay.com/{i}_medium.mp4", "width": w * 2 // 3, "height": h * 2 // 3},
                       "tiny": {"url": f"https://cdn.pixabay.com/{i}_tiny.mp4", "width": 640, "height": 360}}}


def test_pixabay_search_picks_the_sharpest_rendition_and_keeps_the_key_out_of_headers():
    seen = []

    def fetch(url, key):
        seen.append((url, key))
        return json.dumps({"hits": [_pixabay_hit(1), _pixabay_hit(2, dur=120), _pixabay_hit(3, w=1080, h=1920)]}).encode()

    res = stock.search_pixabay("sugar cubes", n=3, key="PK", fetch=fetch)
    assert [r["id"] for r in res] == [1, 3]  # the 2-minute clip is too long for a cutaway
    assert res[0]["url"].endswith("1_large.mp4") and res[1]["h"] == 1280  # sharpest landscape; the smallest portrait ≥ 1280 tall
    assert seen[0][1] == "" and "key=PK" in seen[0][0] and "video_type=film" in seen[0][0]


def test_pixabay_fills_in_when_pexels_has_nothing(tmp_path):
    calls = []

    def fetch(url, key):
        calls.append((url.split("?")[0], key))
        if "api.pexels.com" in url:
            return json.dumps({"videos": []}).encode()
        if "pixabay.com/api" in url:
            return json.dumps({"hits": [_pixabay_hit(7), _pixabay_hit(8)]}).encode()
        return b"MP4DATA"

    out = stock.fetch_for_project(tmp_path, tmp_path / "c", lambda *a, **k: _result({"queries": [{"query": "brain scan", "moment": ""}]}),
                                  keys={"pexels": "XK", "pixabay": "PK"}, fetch=fetch)
    assert out["providers"] == ["pexels", "pixabay"] and out["clips"] == ["pixabay_7.mp4", "pixabay_8.mp4"]
    side = json.loads((tmp_path / "c" / "pixabay_7.json").read_text())
    assert side["source"] == "Pixabay" and "Pixabay Content License" in side["license"]
    # provenance for the licence manifest: licence row, page, bytes, when
    assert side["licence_id"] == "pixabay-content" and side["source_url"] == "https://pixabay.com/videos/7/"
    assert len(side["sha256"]) == 64 and side["downloaded_at"].startswith("20")
    assert all(k == "" for u, k in calls if "pexels" not in u)  # the Pexels key never goes to Pixabay or a CDN


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
    assert out["status"] == "ok" and out["clips"] == ["pexels_2.mp4"] and out["errors"][0].startswith("pexels · sugar cubes")
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
