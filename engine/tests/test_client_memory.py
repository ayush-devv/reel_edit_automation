"""3a.2 per-client style memory: learned from approvals only, profile, packs, hashes, drift, Studio."""

from __future__ import annotations

import json

from reel import client_memory, decide
from reel.workspace import Workspace

from test_studio import env, make_project  # noqa: F401 — the env fixture


def _project(root, pid, *, family="bold_pop", look="clean", cuts=20.0, client="Acme"):
    ws = make_project(root, pid, verdict="sendable")
    fin = json.loads((ws / "plan" / "finish.json").read_text())
    fin["captions"]["family"], fin["grade"]["look"] = family, look
    (ws / "plan" / "finish.json").write_text(json.dumps(fin))
    (ws / "qa" / "pace.json").write_text(json.dumps({"ours": {"cuts_per_min": cuts}}))
    meta = json.loads((ws / "studio.json").read_text()) | {"client": client}
    (ws / "studio.json").write_text(json.dumps(meta))
    return Workspace(ws)


def test_profile_from_approved_reels_only(tmp_path):
    a = _project(tmp_path, "a", cuts=18)
    b = _project(tmp_path, "b", cuts=22, look="warm")
    c = _project(tmp_path, "c", cuts=20)
    for ws in (a, b, c):
        client_memory.learn(ws, "delivered")
    new = _project(tmp_path, "new")
    p = client_memory.profile(new)
    assert p["reels"] == 3 and p["caption_family"] == "bold_pop" and p["look"] == "clean" and p["cuts_per_min"] == 20
    assert (tmp_path / ".clients" / "acme.json").exists()
    assert client_memory.profile(a)["reels"] == 2  # its own approval is left out
    client_memory.forget(b)
    assert client_memory.profile(new)["reels"] == 2
    assert client_memory.profile(_project(tmp_path, "other", client="Zeta")) is None  # another client


def test_recurring_hand_settings_become_defaults(tmp_path):
    from reel import adjustments

    for pid in ("a", "b"):
        ws = _project(tmp_path, pid)
        adjustments.log(ws, "music_track", "none")
        client_memory.learn(ws, "owner_sendable")
    p = client_memory.profile(_project(tmp_path, "new"))
    assert p["recurring_settings"] == [{"kind": "music_track", "value": "none", "reels": 2}]
    md = client_memory.pack_md(p)
    assert "approved reels (2 so far)" in md and "music track → \"none\" by hand on 2 reels" in md


def test_drift_needs_two_departures():
    p = {"reels": 3, "caption_family": "bold_pop", "look": "clean", "cuts_per_min": 20}
    same = {"captions": {"family": "bold_pop"}, "grade": {"look": "clean"}}
    assert client_memory.drift(p, same, 21) == []
    two = client_memory.drift(p, {"captions": {"family": "minimal_calm"}, "grade": {"look": "warm"}}, 20)
    assert len(two) == 2 and "client usually bold_pop" in two[0]
    assert client_memory.drift({**p, "reels": 1}, {"captions": {"family": "x"}, "grade": {"look": "y"}}, 5) == []  # too little history


def test_packs_and_hashes_carry_the_profile_only_when_it_exists(tmp_path):
    from reel.runner import StageContext
    from reel.stages import edit

    new = _project(tmp_path, "new")
    (new.root / "source" / "manifest.json").write_text(json.dumps({"project_fps": "30/1", "clips": [{"id": "c01", "probe": {"duration_s": 3.0}}]}))
    ctx = StageContext(ws=new, options={})
    assert edit._client_key(ctx) == {}
    assert "approved reels" not in decide.story_pack(decide.load_inputs(new))
    for pid in ("a", "b"):
        client_memory.learn(_project(tmp_path, pid), "delivered")
    assert "client_style" in edit._client_key(ctx)
    assert "approved reels (2 so far)" in decide.story_pack(decide.load_inputs(new))


def test_studio_learns_on_delivery_and_label(env):  # noqa: F811
    _project(env["root"], "p1")
    _project(env["root"], "p2")
    assert env["c"].post("/api/projects/p1/delivered", json={"delivered": True}).status_code == 204
    assert env["c"].post("/api/projects/p2/label", json={"sendable": True, "reason": "good"}).status_code == 204
    r = env["c"].get("/api/clients/Acme").json()
    assert r["profile"]["reels"] == 2 and {x["id"] for x in r["reels"]} == {"p1", "p2"}
    assert env["c"].post("/api/projects/p2/label", json={"sendable": False, "reason": "no"}).status_code == 204
    assert env["c"].get("/api/clients/acme").json()["profile"]["reels"] == 1  # p2's approval withdrawn; p1 stays (delivered)
    assert env["c"].post("/api/projects/p1/label", json={"sendable": False, "reason": "meh"}).status_code == 204
    assert env["c"].get("/api/clients/acme").json()["profile"]["reels"] == 1  # still delivered: still counts
    assert env["c"].get("/api/clients/nobody").json()["profile"] is None
