"""3b.2: ours vs pro judged in both orders (a flip is a tie), and the owner's blind picks that calibrate it."""

from __future__ import annotations

import json

import pytest

from reel.claude_call import CallResult
from reel.evalh import pairwise as pw

from test_studio import env  # noqa: F401 — the env fixture


class Judge:
    """Answers per order: `answers[ours_side]` is what it says when ours is on that side."""

    def __init__(self, a, b):
        self.answers = {"pairwise_A": a, "pairwise_B": b}
        self.calls = []

    def __call__(self, prompt, schema, *, label="", **kw):
        self.calls.append(label)
        return CallResult(data={"better": self.answers[label], "reasons": "r"}, session_id="s", num_turns=1, cost_usd=0.0, usage={}, duration_s=0.0)


@pytest.fixture
def no_media(monkeypatch):
    monkeypatch.setattr(pw, "_prepare", lambda ws, ours, pro, side: None)


@pytest.mark.parametrize("a, b, result, consistent", [
    ("A", "B", "win", True),    # ours chosen in both orders
    ("B", "A", "loss", True),   # the pro chosen in both orders
    ("A", "A", "tie", False),   # always "A": position bias → tie
    ("same", "same", "tie", True),
])
def test_both_orders_and_flips_are_ties(tmp_path, no_media, a, b, result, consistent):
    judge = Judge(a, b)
    r = pw.judge(tmp_path / "ours.mp4", tmp_path / "pro.mp4", tmp_path / "w", judge)
    assert r["result"] == result and r["consistent"] == consistent and judge.calls == ["pairwise_A", "pairwise_B"]


def test_tally_and_owner_agreement(tmp_path):
    rows = [{"run_id": "r1", "reels": [{"id": "x", "pairwise": {"result": "win"}}, {"id": "y", "pairwise": {"result": "tie"}},
                                       {"id": "z", "pairwise": {"result": "loss"}}]}]
    assert pw.tally(rows[0]["reels"]) == {"win": 1, "tie": 1, "loss": 1}
    log = tmp_path / "owner.jsonl"
    for reel, ours_wins in (("x", True), ("y", False), ("z", False)):
        ours = pw.side_of_ours("r1", reel)
        other = "B" if ours == "A" else "A"
        pw.record_owner("r1", reel, ours if ours_wins else other, log)
    agreement = pw.owner_agreement(rows, log)
    assert agreement == {"n": 3, "agree": 2, "rate": 0.667}  # y: judge tie, owner chose the pro
    with pytest.raises(ValueError):
        pw.record_owner("r1", "x", "C", log)


def test_owner_picks_through_the_studio(env, tmp_path):  # noqa: F811
    ours, pro = tmp_path / "ours.mp4", tmp_path / "pro.mp4"
    ours.write_bytes(b"OURS")
    pro.write_bytes(b"PRO")
    env["s"].scoreboard.parent.mkdir(parents=True, exist_ok=True)
    env["s"].pairwise_log = tmp_path / "owner.jsonl"
    env["s"].scoreboard.write_text(json.dumps({"run_id": "r1", "mean_primary": 70, "pairwise": {"win": 1, "tie": 0, "loss": 0},
                                               "reels": [{"id": "x", "pairwise": {"result": "win"}, "files": {"ours": str(ours), "pro": str(pro)}}]}) + "\n")
    lab = env["c"].get("/api/lab").json()["pairwise"]
    assert lab["last"] == {"win": 1, "tie": 0, "loss": 0} and lab["pending"] == [{"run": "r1", "reel": "x"}]
    side = pw.side_of_ours("r1", "x")
    assert env["c"].get(f"/api/lab/pairwise/r1/x/{side}").content == b"OURS"
    assert env["c"].post("/api/lab/pairwise/vote", json={"run": "r1", "reel": "x", "choice": side}).status_code == 204
    lab = env["c"].get("/api/lab").json()["pairwise"]
    assert lab["pending"] == [] and lab["agreement"] == {"n": 1, "agree": 1, "rate": 1.0}
    assert env["c"].post("/api/lab/pairwise/vote", json={"run": "r9", "reel": "x", "choice": "A"}).status_code == 404
