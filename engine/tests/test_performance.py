"""4.4: post-performance readings (typed in today), hold rate, and a per-client report labelled as correlation."""

from __future__ import annotations

import json

import pytest

from reel import performance
from reel.workspace import Workspace

from test_studio import _w, env, make_project  # noqa: F401 — the env fixture


def test_readings_are_checked_and_kept(tmp_path):
    ws = Workspace(make_project(tmp_path))
    with pytest.raises(performance.PerformanceError):
        performance.record(ws, {})
    with pytest.raises(performance.PerformanceError):
        performance.record(ws, {"skip_rate": 140})
    with pytest.raises(performance.PerformanceError):
        performance.record(ws, {"views": "lots"})
    with pytest.raises(performance.PerformanceError):
        performance.record(ws, {"views": 10}, post_url="http://instagram.com/p/x")
    performance.record(ws, {"views": 1200, "avg_watch_s": 1.8, "skip_rate": 31}, post_url="https://www.instagram.com/reel/abc/", platform="instagram")
    performance.record(ws, {"views": 5400})
    d = performance.load(ws)
    assert d["post_url"].endswith("/abc/") and d["platform"] == "instagram" and len(d["readings"]) == 2
    assert performance.latest(ws)["views"] == 5400 and performance.latest(ws)["source"] == "manual"
    assert performance.hold_rate({"avg_watch_s": 1.8}, 2.4) == 0.75 and performance.hold_rate({}, 2.4) is None


def _reel(root, pid, *, cuts, hook, watch):
    ws = make_project(root, pid)
    _w(ws / "qa" / "pace.json", {"ours": {"cuts_per_min": cuts}})
    fin = json.loads((ws / "plan" / "finish.json").read_text())
    fin["hook_title"] = {"text": "Big claim", "style": hook, "reason": "r"}
    _w(ws / "plan" / "finish.json", fin)
    performance.record(Workspace(ws), {"views": 1000, "avg_watch_s": watch})
    return ws


def test_the_client_report_needs_three_reels_and_says_it_is_correlation(tmp_path):
    root = tmp_path / "projects"
    _reel(root, "a1", cuts=30, hook="card", watch=2.2)
    _reel(root, "a2", cuts=28, hook="card", watch=2.0)
    r = performance.client_report(root, "Acme")
    assert r["what_worked"] == [] and r["needs"] == 1 and "not proof" in r["caveat"]
    _reel(root, "a3", cuts=12, hook="kinetic", watch=0.8)
    _reel(root, "a4", cuts=10, hook="kinetic", watch=0.7)
    r = performance.client_report(root, "Acme")
    assert r["with_watch_time"] == 4 and [x["project"] for x in r["rows"]][:2] == ["a1", "a2"]
    assert any("more cuts per minute" in w for w in r["what_worked"])
    assert any("hook title “card”" in w for w in r["what_worked"])
    assert performance.client_report(root, "Someone Else")["reels"] == 0


def test_the_studio_takes_readings_and_shows_the_report(env):  # noqa: F811
    c = env["c"]
    make_project(env["root"])
    assert c.post("/api/projects/p1/performance", json={}).status_code == 400
    r = c.post("/api/projects/p1/performance", json={"views": 900, "avg_watch_s": 1.2, "skip_rate": 40, "platform": "instagram",
                                                       "post_url": "https://www.instagram.com/reel/xyz/"})
    assert r.status_code == 200 and r.json()["hold_rate"] == 0.5 and r.json()["readings"][-1]["views"] == 900
    assert c.get("/api/clients/Acme").json()["performance"]["reels"] == 1


def test_performance_stays_out_of_the_editor_and_the_fingerprints():
    """A handful of posts must not steer edits or re-buy paid passes."""
    from pathlib import Path

    import reel

    src = Path(reel.__file__).parent
    for f in ("decide.py", "client_memory.py", "stages/edit.py", "verdict.py", "qa.py"):
        assert "performance" not in (src / f).read_text(), f
