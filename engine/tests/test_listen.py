"""G2.5: the free-model listening test: licence refusal, blind pairs, votes, the adopt rule, the Studio routes."""

from __future__ import annotations

import json

import pytest

from reel import licences, listen

from test_studio import env  # noqa: F401 — the env fixture


def _fake_runner(cmd, prompt, out):
    out.write_bytes(b"RIFF" + prompt["id"].encode())


@pytest.fixture
def root(tmp_path, monkeypatch):
    lib = tmp_path / "lib.wav"
    lib.write_bytes(b"RIFFlibrary")
    monkeypatch.setattr(listen, "_library_pick", lambda kind, match: lib)
    monkeypatch.setattr(listen, "ROOT", tmp_path / "listening")
    return tmp_path / "listening"


GENS = {
    "acestep": {"set": "music", "licence_id": "mit", "cmd": ["gen", "{prompt}", "{out}"], "commit": "abc"},
    "mystery": {"set": "music", "licence_id": "no-such-licence", "cmd": ["gen"]},
    "sfxgen": {"set": "sfx", "licence_id": "mit", "cmd": ["gen"]},
}


def test_generators_without_a_licence_row_are_refused(root):
    m = listen.prepare("music", root, gens=GENS, runner=_fake_runner)
    assert m["generators"]["acestep"]["status"] == "ok" and m["generators"]["acestep"]["commit"] == "abc"
    assert m["generators"]["mystery"]["status"] == "refused" and "no row" in m["generators"]["mystery"]["why"]
    assert "sfxgen" not in m["generators"]  # another set
    models = {o["model"] for o in m["outputs"]}
    assert models == {"library", "acestep"} and len(m["outputs"]) == 2 * len(listen.PROMPTS["music"])


def test_a_blocked_licence_is_refused():
    reg = licences.load_registry()
    blocked = next(lid for lid, lic in reg.licences.items() if lic.blocked)
    with pytest.raises(listen.ListenError, match="not usable"):
        listen.check_licence("x", {"licence_id": blocked}, reg)


def test_pairs_are_blind_and_votes_decide(root):
    listen.prepare("music", root, gens=GENS, runner=_fake_runner)
    shown = listen.blind("music", root)
    assert len(shown) == len(listen.PROMPTS["music"])
    assert not any(name in json.dumps(x) for x in shown for name in ("acestep", "library"))  # nothing on the page gives the model away
    assert all(set(x) == {"id", "prompt", "A", "B", "done"} for x in shown)
    key = {x["id"]: x for x in json.loads((root / "music" / "pairs.json").read_text())}
    for x in shown:  # the owner prefers the generator every time and finds it usable
        gen_side = "A" if key[x["id"]]["A"]["model"] == "acestep" else "B"
        listen.vote("music", x["id"], gen_side, usable_a=True, usable_b=gen_side == "B", root=root)
    s = listen.summary("music", root)
    assert s["models"]["acestep"]["decision"] == "adopt" and s["models"]["acestep"]["win_rate"] == 1.0
    assert s["models"]["library"]["decision"] == "reference"
    assert all(x["done"] for x in listen.blind("music", root))
    with pytest.raises(listen.ListenError):
        listen.vote("music", "nope", "A", True, True, root=root)
    with pytest.raises(listen.ListenError):
        listen.vote("music", shown[0]["id"], "C", True, True, root=root)


def test_a_model_that_loses_or_is_unusable_is_not_adopted(root):
    listen.prepare("music", root, gens=GENS, runner=_fake_runner)
    key = json.loads((root / "music" / "pairs.json").read_text())
    for x in key:
        lib_side = "A" if x["A"]["model"] == "library" else "B"
        listen.vote("music", x["id"], "tie", usable_a=lib_side == "A", usable_b=lib_side == "B", root=root)
    s = listen.summary("music", root)
    assert s["models"]["acestep"]["decision"] == "not yet" and s["models"]["acestep"]["usable_rate"] == 0.0


def test_listening_routes(env, root):  # noqa: F811
    listen.prepare("music", root, gens=GENS, runner=_fake_runner)
    r = env["c"].get("/api/listening/music").json()
    assert len(r["pairs"]) == 4 and r["summary"]["votes"] == 0
    pair = r["pairs"][0]
    assert env["c"].post("/api/listening/music/vote", json={"pair": pair["id"], "choice": "tie", "usable_a": True}).status_code == 204
    assert env["c"].post("/api/listening/music/vote", json={"pair": "x", "choice": "A"}).status_code == 400
    media = env["c"].get(f"/api/listening/music/media/{pair['A']}")
    assert media.status_code == 200 and media.content.startswith(b"RIFF")
    from fastapi.testclient import TestClient

    bare = TestClient(env["app"])  # an <audio> tag cannot send a header: the token rides in the query
    assert bare.get(f"/api/listening/music/media/{pair['A']}?token={env['token']}").content.startswith(b"RIFF")
    assert bare.get(f"/api/listening/music/media/{pair['A']}").status_code == 401
    assert bare.get(f"/api/listening/music?token={env['token']}").status_code == 401  # only the media files take a query token
    assert env["c"].get("/api/listening/music/media/../../etc/passwd").status_code == 404
    assert env["c"].get("/api/listening/sfx/media/" + pair["A"]).status_code == 404  # another set's folder
    assert env["c"].post("/api/listening/music/prepare").status_code == 200
    assert env["c"].get("/api/listening/drums").status_code == 400
