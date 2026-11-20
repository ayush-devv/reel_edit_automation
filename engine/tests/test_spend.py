"""4.1 cost guard: quotes, approval bound to the request, never buying the same thing twice, month to date, the cap."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from reel import spend

from test_studio import env, make_project  # noqa: F401 — the env fixture


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("REEL_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "cfg" / "paid_ledger.jsonl"


PAID = {"paid": True, "price": {"usd": 0.30, "per": "1k_chars"}}


def test_quotes_follow_the_declared_price():
    assert spend.quote(PAID, chars=2000) == 0.6
    assert spend.quote({"price": {"usd": 0.05, "per": "second"}}, seconds=30) == 1.5
    assert spend.quote({"price": {"usd": 2, "per": "call"}}) == 2.0
    with pytest.raises(ValueError):
        spend.quote({"price": {"usd": 1, "per": "minute"}})


def test_a_paid_call_needs_an_approval_for_that_exact_request_and_is_never_bought_twice(tmp_path):
    runs = []

    def run_for(out: Path):
        def run():
            runs.append(out.name)
            out.write_bytes(b"AUDIO")
        return run

    assert spend.paid_call("free", {}, {"t": "x"}, tmp_path / "f.wav", run_for(tmp_path / "f.wav")) == "free" and runs == ["f.wav"]
    out = tmp_path / "a.wav"
    with pytest.raises(spend.ApprovalNeeded) as e:
        spend.paid_call("tts", PAID, {"text": "hello"}, out, run_for(out), chars=1000)
    assert e.value.quote_usd == 0.3 and runs == ["f.wav"]  # nothing ran
    with pytest.raises(spend.ApprovalNeeded):  # asking again doesn't record a second quote
        spend.paid_call("tts", PAID, {"text": "hello"}, out, run_for(out), chars=1000)
    assert [p["hash"] for p in spend.pending()] == [e.value.request_hash]
    other = spend.request_hash("tts", {"text": "goodbye"})
    with pytest.raises(KeyError):
        spend.approve(other)  # no quote for it
    spend.approve(e.value.request_hash)
    assert spend.pending() == []
    assert spend.paid_call("tts", PAID, {"text": "hello"}, out, run_for(out), chars=1000) == "bought" and runs[-1] == "a.wav"
    again = tmp_path / "b.wav"
    assert spend.paid_call("tts", PAID, {"text": "hello"}, again, run_for(again), chars=1000) == "reused"
    assert again.read_bytes() == b"AUDIO" and runs.count("b.wav") == 0  # the identical request is not bought again
    with pytest.raises(spend.ApprovalNeeded):  # a different request needs its own approval
        spend.paid_call("tts", PAID, {"text": "goodbye"}, tmp_path / "c.wav", run_for(tmp_path / "c.wav"), chars=1000)
    assert spend.paid_this_month() == 0.3


def _log(ws: Path, usd: float, when: float):
    (ws / "log").mkdir(parents=True, exist_ok=True)
    with (ws / "log" / "runs.jsonl").open("a") as f:
        f.write(json.dumps({"time": when, "label": "story", "exit": 0, "session_id": f"s{when}", "cost_usd": usd, "cost_cum_usd": usd}) + "\n")


def test_month_to_date_counts_this_month_only(tmp_path):
    root = tmp_path / "projects"
    now = time.time()
    _log(root / "p1", 1.25, now)
    last_month = datetime(datetime.now().year - 1, 12, 15).timestamp()  # surely an earlier month
    _log(root / "p1", 9.0, last_month)
    m = spend.month_to_date(root, now)
    assert m["claude_usd"] == 1.25 and m["total_usd"] == 1.25
    st = spend.status(root, 1.0, now)
    assert st["over_cap"] is True and st["cap_usd"] == 1.0
    assert spend.status(root, 0, now)["over_cap"] is False and spend.status(root, 0, now)["cap_usd"] is None


def test_the_studio_asks_before_a_new_run_past_the_cap(env):  # noqa: F811
    c = env["c"]
    ws = make_project(env["root"])
    _log(ws, 5.0, time.time())
    assert c.get("/api/spend").json()["cap_usd"] is None
    s = c.get("/api/settings").json()
    assert s["monthly_cap_usd"] == 0.0
    assert c.put("/api/settings", json={"max_jobs": s["max_jobs"], "monthly_cap_usd": 4.0}).json()["monthly_cap_usd"] == 4.0
    st = c.get("/api/spend").json()
    assert st["over_cap"] is True and st["month"]["claude_usd"] == 5.0
    r = c.post("/api/projects", data={"name": "x"}, files=[("files[]", ("a.mp4", b"\0" * 10, "video/mp4"))])
    assert r.status_code == 409 and r.json()["over_cap"] is True and "spend anyway" in r.json()["hint"]
    r = c.post("/api/projects", data={"name": "x", "spend_anyway": "1"}, files=[("files[]", ("a.mp4", b"\0" * 10, "video/mp4"))])
    assert r.status_code == 201
    assert c.post("/api/projects/p1/revise", json={"request": "faster"}).status_code == 409
    assert c.post("/api/projects/p1/revise", json={"request": "faster", "spend_anyway": True}).status_code == 200
    c.put("/api/settings", json={"max_jobs": s["max_jobs"], "monthly_cap_usd": 0})  # 0 = no cap
    assert c.get("/api/spend").json()["over_cap"] is False


def test_the_studio_approves_a_pending_quote(env, tmp_path):  # noqa: F811
    c = env["c"]
    out = tmp_path / "x.wav"
    with pytest.raises(spend.ApprovalNeeded) as e:
        spend.paid_call("sfx", PAID, {"prompt": "dhol"}, out, lambda: None, chars=100)
    assert [p["hash"] for p in c.get("/api/spend").json()["pending"]] == [e.value.request_hash]
    assert c.post("/api/spend/approve/nothex").status_code == 400
    assert c.post("/api/spend/approve/" + "0" * 24).status_code == 404
    assert c.post(f"/api/spend/approve/{e.value.request_hash}").status_code == 200
    assert c.get("/api/spend").json()["pending"] == []


def test_a_paid_voice_stops_the_dub_until_approved(tmp_path):
    from reel import dub

    spec = {"paid": True, "price": {"usd": 0.3, "per": "1k_chars"}, "cmd": ["true"], "id": "paid-voice"}
    with pytest.raises(spend.ApprovalNeeded):
        dub.synthesize(spec, [{"text": "नमस्ते", "lang": "hi", "out": str(tmp_path / "L01.wav")}], tmp_path)
    assert spend.pending()[0]["generator"] == "paid-voice"
