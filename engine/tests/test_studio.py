"""Reel Studio API (docs/product/studio-api.md): FastAPI TestClient against a fake workspace in tmp_path.

Job execution is mocked: the launcher returns fake processes the test finishes by hand.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reel.studio import costs
from reel.studio.app import create_app
from reel.studio.jobs import JobManager
from reel.studio.settings import Settings

WORDS = ["How", "much", "sugar", "is", "in", "here"]


class FakeProc:
    pid = None

    def __init__(self):
        self.done = threading.Event()
        self.rc = 0

    def wait(self):
        self.done.wait(30)
        return self.rc

    def finish(self, rc=0):
        self.rc = rc
        self.done.set()

    def terminate(self):
        self.finish(-15)

    kill = terminate


class Launcher:
    def __init__(self):
        self.procs: list[tuple] = []

    def __call__(self, job, logf):
        p = FakeProc()
        self.procs.append((job, p))
        return p

    def finish(self, kind=None, rc=0):
        job, p = next((j, p) for j, p in self.procs if not p.done.is_set() and (kind is None or j.kind == kind))
        p.finish(rc)
        for _ in range(200):  # the waiter thread flips the status
            if job.status != "running":
                return job
            time.sleep(0.01)
        raise AssertionError("job did not finish")


def _w(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj))


def make_project(root: Path, pid: str = "p1", *, verdict: str = "hold", runs: list[dict] | None = None) -> Path:
    ws = root / pid
    _w(ws / "studio.json", {"name": f"Project {pid}", "created": 1795000000.0, "client": "Acme", "footage_s": 60})
    stages = {n: {"status": "done", "input_hash": "x", "outputs": ["o"], "meta": {}, "finished": 1795000100.0 + i}
              for i, n in enumerate(["ingest", "mezzanine", "perception", "tables", "story", "finish", "compile", "render",
                                     "overlay", "composite", "qa", "package", "variants"])}
    for opt in ("broll", "reference"):
        stages[opt] = {"status": "done", "input_hash": "none", "outputs": [], "meta": {}, "finished": 1795000100.0}
    stages["composite"]["meta"] = {"video_s": 12.5}
    _w(ws / "state.json", {"schema": 1, "stages": stages})
    _w(ws / "run_options.json", {"input": str(ws / "source" / "raw"), "brief": None, "brand": None, "skip_review": True})
    _w(ws / "source" / "manifest.json", {"clips": [{"id": "c01"}], "project_fps": "30/1"})
    _w(ws / "perception" / "words.json", {"language": "en", "words": [
        {"i": i, "clip": "c01", "text": t, "start_us": i * 400_000, "end_us": i * 400_000 + 300_000} for i, t in enumerate(WORDS)]})
    _w(ws / "plan" / "story.json", {
        "genre": "genre.podcast_clip", "summary": "sugar", "hook": "h1", "knowledge_used": ["tech.hook.question_or_claim"],
        "hook_options": [{"id": "h1", "item": "k01", "rank": 1, "reason": "a question hook"}],
        "items": [{"id": "k01", "clip": "c01", "word_start": 0, "word_end": 2, "first_word": "How", "last_word": "sugar", "beat": "hook", "reason": "opens on the question"},
                  {"id": "k02", "clip": "c01", "word_start": 3, "word_end": 5, "first_word": "is", "last_word": "here", "beat": "point", "reason": "the answer"}]})
    _w(ws / "plan" / "finish.json", {
        "hook_title": {"text": "", "style": "card", "reason": "none needed"},
        "grade": {"look": "clean", "strength": 0.4, "reason": "neutral"},
        "punch_ins": [{"id": "p01", "item": "k02", "at_word": 4, "scale": 1.2, "ramp_frames": 0, "ease": "hold", "reason": "emphasis"}],
        "speeds": [], "transitions": [], "sfx": [], "broll": [], "knowledge_used": [],
        "captions": {"family": "bold_pop", "tokens": [{"key": "emph_color", "value": "#FFD400"}], "emphasis_words": [2], "script": "latin", "reason": "energy"},
        "music": {"track": "none", "gain_db": -18, "duck_db": 12, "reason": "speech only"}})
    clip = {"asset": "c01", "src_in_us": 0}
    _w(ws / "timeline" / "timeline.json", {  # a valid Timeline written without its defaults, like older engine versions
        "fps": "30/1", "width": 1080, "height": 1920, "duration_f": 72,
        "assets": {"c01": {"id": "c01", "kind": "video", "uri": "source/c01.mp4"}},
        "video": [{"id": "v_k01", **clip, "at_f": 0, "dur_f": 36, "src_out_us": 1_200_000, "src": {"item": "k01", "words": [0, 2]}},
                  {"id": "v_k02", **clip, "at_f": 36, "dur_f": 36, "src_out_us": 2_400_000, "scale": [{"f": 0, "v": 1.0}, {"f": 6, "v": 1.2}],
                   "src": {"item": "k02", "words": [3, 5]}}],
        "audio": [{"id": "a_k01", **clip, "at_f": 0, "dur_f": 36, "role": "voice", "src": {"item": "k01", "words": [0, 2]}}],
        "grade": {"look": "clean", "strength": 0.4}})
    _w(ws / "qa" / "verdict.json", {"status": verdict, "reasons": ["proof_words: 1 unconfirmed"] if verdict == "hold" else [], "warnings": [],
                                    "fix_request": "", "proof_open": [{"i": 2, "text": "sugar", "suggestion": None, "at": "0:00.80", "frame": 24, "why": "low confidence"}]
                                    if verdict == "hold" else []})
    _w(ws / "qa" / "gates.json", [{"gate": "loudness", "ok": True, "mode": "block", "detail": "-14 LUFS", "measured": {}},
                                   {"gate": "reading_speed", "ok": False, "mode": "warn", "detail": "fast", "measured": {}}])
    _w(ws / "qa" / "review.json", {"summary": "fine", "sendable": True, "strengths": [], "issues": [
        {"id": "R1", "at": "0:01", "category": "captions", "severity": "minor", "problem": "small", "fix": "bigger", "fix_target": "finish"}]})
    (ws / "render").mkdir(parents=True, exist_ok=True)
    (ws / "render" / "final.mp4").write_bytes(bytes(range(256)) * 40)
    _w(ws / "export" / "package" / "README.md", "# pkg")
    _w(ws / "log" / "runs.jsonl", "\n".join(json.dumps(r) for r in (runs or [])) + "\n")
    return ws


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    launcher = Launcher()
    s = Settings(projects_root=root, brands_root=tmp_path / "brands", token_file=tmp_path / "cfg" / "studio_token",
                 web_dist=tmp_path / "dist", eval_manifest=tmp_path / "eval" / "manifest.yaml", scoreboard=tmp_path / "eval" / "sb.jsonl",
                 improve_log=tmp_path / "eval" / "improve.jsonl", calibration_report=tmp_path / "eval" / "calibration.json",
                 prefs_file=tmp_path / "cfg" / "studio_settings.json", python="python", doctor=lambda: {"ok": True, "items": []},
                 start_scheduler=False, poll_s=0.05, sse_max_s=1.5)
    app = create_app(s, launcher=launcher)
    client = TestClient(app)
    client.headers["X-Reel-Token"] = app.state.token
    return {"root": root, "s": s, "app": app, "c": client, "launcher": launcher, "token": app.state.token}


# ------------------------------------------------------------------ auth


def test_token_required_and_file_is_private(env):
    make_project(env["root"])
    bare = TestClient(env["app"])
    assert bare.get("/api/projects").status_code == 401
    assert bare.get("/api/projects", headers={"X-Reel-Token": "0" * 64}).status_code == 401
    assert bare.get(f"/api/projects?token={env['token']}").status_code == 401  # query token only for SSE / media / zip
    assert bare.get(f"/api/projects/p1/media/render/final.mp4?token={env['token']}").status_code == 200
    assert bare.get("/api/projects", headers={"X-Reel-Token": env["token"]}).status_code == 200
    assert (env["s"].token_file.stat().st_mode & 0o777) == 0o600
    assert bare.get("/").status_code == 200  # the web app itself is public; its API calls carry the token


# ------------------------------------------------------------------ read side


def test_project_list_and_detail(env):
    make_project(env["root"], "p1", verdict="hold")
    make_project(env["root"], "p2", verdict="sendable")
    (env["root"] / ".trash").mkdir()
    (env["root"] / "loose.log").write_text("x")
    (env["root"] / "not_a_project").mkdir()
    lst = env["c"].get("/api/projects").json()
    assert [p["id"] for p in lst] == ["p1", "p2"]  # hold before sendable (attention first)
    p1 = lst[0]
    assert p1["status"] == "hold" and p1["verdict"] == "hold" and p1["name"] == "Project p1"
    assert p1["duration_s"] == 12.5 and p1["progress"] == 1.0 and "1 proof word" in p1["needs_attention"]

    d = env["c"].get("/api/projects/p1").json()
    st = {x["name"]: x["status"] for x in d["stages"]}
    assert st["broll"] == "skipped" and st["reference"] == "skipped" and st["render"] == "done"
    kinds = {x["kind"] for x in d["decisions"]}
    assert {"story", "finish", "review", "qa"} <= kinds
    hook = next(x for x in d["decisions"] if x["title"].startswith("Hook"))
    assert "How much sugar" in hook["title"] and hook["detail"] == "a question hook"
    gates = {g["name"]: g["status"] for g in d["verdict_detail"]["gates"]}
    assert gates == {"loudness": "pass", "reading_speed": "warn"}
    assert d["proof"][0]["i"] == 2 and d["review"]["issues"][0]["text"] == "small"
    assert d["media"]["final"] == "render/final.mp4"

    tl = env["c"].get("/api/projects/p1/timeline").json()
    assert tl["story"]["k01"] == {"beat": "hook", "text": "How much sugar", "words": [[0, "How"], [1, "much"], [2, "sugar"]]}
    assert tl["timeline"]["effects"] == [] and tl["timeline"]["grade"]["grain"] == 0.0  # defaults filled in
    r = tl["reasons"]  # keyed like the layer blocks: plan item, punch-in clip, dialogue clip, singletons
    assert r["k01"].startswith("opens on the question") and "Hook: a question hook" in r["k01"]
    assert r["v_k02"] == "Punch-in: emphasis" and r["a_k01"] == "opens on the question" and r["grade"] == "neutral"
    assert tl["adjust"]["caption_family"] == "bold_pop" and tl["adjust"]["caption_tokens"] == {"emph_color": "#FFD400"}
    assert tl["adjust"]["punch_ins"] == 1 and tl["adjust"]["max_pause_ms"] is None
    assert d["versions"] == [{"n": 1, "created": d["versions"][0]["created"], "label": "Original edit", "reply": "", "cost_usd": None,
                              "final": "render/final.mp4"}]  # virtual until the first change
    assert d["eta_s"] is None and d["delivered_at"] is None
    assert env["c"].get("/api/projects/nope").status_code == 404
    assert env["c"].get("/api/projects/.trash").status_code == 404


def test_interrupted_stage_is_not_running(env):
    ws = make_project(env["root"])
    state = json.loads((ws / "state.json").read_text())
    state["stages"]["render"] = {"status": "running", "input_hash": "x", "started": 1.0}
    _w(ws / "state.json", state)
    _w(ws / "run.lock", {"pid": 999_999_9, "host": "x"})
    d = env["c"].get("/api/projects/p1").json()
    assert d["status"] == "failed" and d["stage"] == "render"
    assert next(s for s in d["stages"] if s["name"] == "render")["error"].startswith("Interrupted")


# ------------------------------------------------------------------ media


def test_media_whitelist_traversal_and_range(env):
    ws = make_project(env["root"])
    (env["root"] / "secret.txt").write_text("nope")
    c = env["c"]
    assert c.get("/api/projects/p1/media/render/final.mp4").status_code == 200
    r = c.get("/api/projects/p1/media/render/final.mp4", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206 and r.headers["content-range"] == "bytes 10-19/10240" and r.content == bytes(range(10, 20))
    for bad in ("state.json", "plan/story.json", "render/../state.json", "render/%2e%2e/state.json", "%2e%2e/secret.txt",
                "render/..%2f..%2fsecret.txt", "render//final.mp4", "render/missing.mp4", "/etc/passwd"):
        assert c.get(f"/api/projects/p1/media/{bad}").status_code == 404, bad
    (ws / "render" / "escape.mp4").symlink_to(env["root"] / "secret.txt")
    assert c.get("/api/projects/p1/media/render/escape.mp4").status_code == 404


def test_package_zip(env):
    make_project(env["root"])
    r = env["c"].get(f"/api/projects/p1/package.zip?token={env['token']}")
    assert r.status_code == 200 and r.content[:2] == b"PK"


# ------------------------------------------------------------------ adjust (validated by the engine's validator)


def test_adjust_validation_422_then_applies(env):
    ws = make_project(env["root"])
    c = env["c"]
    r = c.post("/api/projects/p1/adjust", json={"kind": "look_strength", "value": 1.5})
    assert r.status_code == 422 and r.json()["issues"][0]["code"] == "out_of_range"
    r = c.post("/api/projects/p1/adjust", json={"kind": "caption_family", "value": "no_such_family"})
    assert r.status_code == 422 and r.json()["issues"][0]["code"] == "unknown_family"
    r = c.post("/api/projects/p1/adjust", json={"kind": "max_pause_ms", "value": 50})
    assert r.status_code == 422 and r.json()["issues"][0]["path"] == "max_pause_ms"
    assert c.post("/api/projects/p1/adjust", json={"kind": "look_strength", "value": "loud"}).status_code == 400
    assert c.post("/api/projects/p1/adjust", json={"kind": "colour", "value": 1}).status_code == 400
    assert json.loads((ws / "plan" / "finish.json").read_text())["grade"]["strength"] == 0.4  # nothing written on refusal

    # switching family drops the old family's tokens instead of failing on them
    r = c.post("/api/projects/p1/adjust", json={"kind": "caption_family", "value": "clean_phrase"})
    assert r.status_code == 200, r.text
    assert r.json()["job"]["kind"] == "adjust"
    fin = json.loads((ws / "plan" / "finish.json").read_text())
    assert fin["captions"]["family"] == "clean_phrase" and fin["captions"]["tokens"] == [{"key": "emph_color", "value": "#FFD400"}]
    job, _ = env["launcher"].procs[-1]
    assert job.argv[3:] == ["rerun", "--project", str(ws), "--from", "compile"]
    assert c.post("/api/projects/p1/adjust", json={"kind": "look", "value": "warm"}).status_code == 409  # one job per project
    env["launcher"].finish()
    vs = c.get("/api/projects/p1/versions").json()
    assert [v["label"] for v in vs] == ["Original edit", "Manual"] and vs[1]["final"] == "versions/2/final.mp4"
    assert vs[1]["reply"] == "caption family → clean_phrase · QA after the change: Hold, 1 reason(s): proof_words"  # 3b.4
    assert (ws / "versions" / "1" / "plan" / "finish.json").exists()
    assert c.post("/api/projects/p1/adjust", json={"kind": "punch_ins_off", "value": True}).status_code == 200
    assert json.loads((ws / "plan" / "finish.json").read_text())["punch_ins"] == []


def test_proof_maps_ok_and_fix(env):
    ws = make_project(env["root"])
    c = env["c"]
    assert c.post("/api/projects/p1/proof", json={"words": [{"i": 99, "text": "x"}]}).status_code == 400
    assert c.post("/api/projects/p1/proof", json={"words": [{"i": 2, "text": "Shugar"}]}).status_code == 200
    assert json.loads((ws / "qa" / "proof_confirmed.json").read_text()) == {"2": {"ok": True, "text": "Shugar"}}


# ------------------------------------------------------------------ jobs: limit, FIFO, 409, memory guard


def test_queue_limit_fifo_and_conflict(env):
    for i in range(4):
        make_project(env["root"], f"q{i}")
    c = env["c"]
    jobs = [c.post(f"/api/projects/q{i}/retry", json={}).json()["job"] for i in range(4)]
    assert [j["status"] for j in jobs] == ["running", "running", "running", "queued"]
    r = c.post("/api/projects/q0/retry", json={"stage": "render"})
    assert r.status_code == 409 and r.json()["detail"]["project"] == "q0"
    listed = c.get("/api/jobs").json()
    assert len(listed["running"]) == 3 and [j["project"] for j in listed["queued"]] == ["q3"]
    assert json.loads(env["s"].queue_file.read_text())["jobs"][-1]["project"] == "q3"  # persisted
    assert c.get("/api/projects/q3").json()["status"] == "queued"
    env["launcher"].finish()
    assert c.get("/api/jobs").json()["queued"] == [] and c.get("/api/projects/q3").json()["status"] == "running"
    job, _ = env["launcher"].procs[0]
    assert job.argv[3:6] == ["run", str(env["root"] / "q0" / "source" / "raw"), "--project"] and "--skip-review" in job.argv
    assert c.post("/api/projects/q3/cancel").status_code == 204
    assert c.post("/api/projects/q1/retry", json={"stage": "bogus"}).status_code == 400


def test_memory_guard_and_restart(tmp_path):
    s = Settings(projects_root=tmp_path, memory_budget_gb=5.0, start_scheduler=False)
    launcher = Launcher()
    m = JobManager(s, launcher=launcher)
    a = m.submit("a", "run", ["x"], cwd=tmp_path, log=tmp_path / "a.log", est_gb=4.0)
    b = m.submit("b", "run", ["x"], cwd=tmp_path, log=tmp_path / "b.log", est_gb=3.0)
    c = m.submit("c", "run", ["x"], cwd=tmp_path, log=tmp_path / "c.log", est_gb=0.5)
    assert (a.status, b.status, c.status) == ("running", "queued", "queued")  # FIFO: c waits behind b
    big = JobManager(Settings(projects_root=tmp_path / "solo", memory_budget_gb=1.0, start_scheduler=False), launcher=Launcher())
    assert big.submit("x", "run", ["x"], cwd=tmp_path, log=tmp_path / "x.log", est_gb=8.0).status == "running"  # alone: never deadlocks
    launcher.finish()
    assert (b.status, c.status) == ("running", "running")
    # queued jobs survive a restart
    m2 = JobManager(Settings(projects_root=tmp_path / "r", start_scheduler=False, max_jobs=0), launcher=Launcher())
    m2.submit("z", "run", ["x"], cwd=tmp_path, log=tmp_path / "z.log", est_gb=1.0)
    m3 = JobManager(Settings(projects_root=tmp_path / "r", start_scheduler=False), launcher=Launcher())
    assert [j.project for j in m3.queued()] == ["z"]


def test_toolchain_missing_is_503(env):
    make_project(env["root"])
    app = create_app(Settings(**{**env["s"].__dict__, "doctor": lambda: {"ok": False, "items": [{"name": "pinned ffmpeg", "ok": False, "detail": "x"}]}}),
                     launcher=Launcher())
    c = TestClient(app, headers={"X-Reel-Token": app.state.token})
    r = c.post("/api/projects/p1/retry", json={})
    assert r.status_code == 503 and r.json()["detail"] == ["pinned ffmpeg"]
    before = (env["root"] / "p1" / "plan" / "finish.json").read_text()
    assert c.post("/api/projects/p1/adjust", json={"kind": "look", "value": "warm"}).status_code == 503
    assert (env["root"] / "p1" / "plan" / "finish.json").read_text() == before  # refused before anything is written
    h = c.get("/api/health").json()
    assert h["engine"] == "ok" and h["toolchain_ok"] is False and h["jobs"]["limit"] == 3


def test_terminal_run_lock_is_409(env):
    import os

    ws = make_project(env["root"])
    _w(ws / "run.lock", {"pid": os.getpid(), "host": "here"})
    before = (ws / "plan" / "finish.json").read_text()
    r = env["c"].post("/api/projects/p1/adjust", json={"kind": "look", "value": "warm"})
    assert r.status_code == 409 and r.json()["detail"]["kind"] == "external"
    assert (ws / "plan" / "finish.json").read_text() == before


def test_web_app_spa_fallback(env):
    dist = env["s"].web_dist
    _w(dist / "index.html", "<!doctype html><div id=root></div>")
    _w(dist / "assets" / "a.js", "console.log(1)")
    (dist.parent / "outside.txt").write_text("secret")
    bare = TestClient(env["app"])
    assert "id=root" in bare.get("/").text and "id=root" in bare.get("/projects/p1/review").text
    assert bare.get("/assets/a.js").text == "console.log(1)"
    for bad in ("/..%2foutside.txt", "/assets/..%2f..%2foutside.txt"):
        assert "secret" not in bare.get(bad).text
    assert bare.get("/api/nope", headers={"X-Reel-Token": env["token"]}).status_code == 404


# ------------------------------------------------------------------ SSE


def test_sse_snapshot_then_stage_event(env):
    ws = make_project(env["root"])

    def later():
        time.sleep(0.4)
        state = json.loads((ws / "state.json").read_text())
        state["stages"]["qa"] = {"status": "failed", "input_hash": "x", "error": "RuntimeError: boom", "finished": time.time()}
        _w(ws / "state.json", state)

    threading.Thread(target=later).start()
    r = env["c"].get(f"/api/projects/p1/events?token={env['token']}", headers={"X-Reel-Token": ""})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [(b.split("event: ")[1].split("\n")[0], json.loads(b.split("data: ", 1)[1])) for b in r.text.split("\n\n") if "event: " in b]
    assert events[0][0] == "snapshot" and events[0][1]["id"] == "p1"
    stage = next(d for e, d in events if e == "stage")
    assert stage["name"] == "qa" and stage["status"] == "failed" and "boom" in stage["error"]


# ------------------------------------------------------------------ costs


def test_cost_deltas_over_resumed_sessions(tmp_path):
    rows = [  # legacy rows: cost_usd is the running session total; newer rows: cost_cum_usd + delta cost_usd
        {"time": 1, "label": "story", "session_id": "s1", "resume": None, "cost_usd": 0.18},
        {"time": 2, "label": "story:fix1", "session_id": "s1", "resume": "s1", "cost_usd": 0.22},
        {"time": 3, "label": "finish", "session_id": "s2", "resume": None, "cost_usd": 0.16},
        {"time": 4, "label": "revision", "session_id": "s2", "resume": "s2", "cost_usd": 0.33},
        {"time": 5, "label": "story", "session_id": "s3", "resume": None, "cost_usd": 0.55, "cost_cum_usd": 0.55},
        {"time": 6, "label": "story_readback", "session_id": "s3", "resume": "s3", "cost_usd": 0.21, "cost_cum_usd": 0.76},
        {"time": 7, "label": "review", "session_id": "s4", "resume": None, "cost_usd": None},
    ]
    make_project(tmp_path, "a", runs=rows)
    got = [c["cost_usd"] for c in costs.calls(tmp_path / "a" / "log" / "runs.jsonl")]
    assert got == pytest.approx([0.18, 0.04, 0.16, 0.17, 0.55, 0.21, 0.0])
    assert costs.project_total(tmp_path / "a" / "log" / "runs.jsonl") == pytest.approx(1.31)
    summ = costs.summary(tmp_path, days=30, now=86400 * 10)
    assert summ["total_usd"] == pytest.approx(1.31) and summ["by_project"] == [{"id": "a", "usd": pytest.approx(1.31)}]
    assert costs.summary(tmp_path, days=1, now=86400 * 10)["total_usd"] == 0


# ------------------------------------------------------------------ lab, brands, label, CLI pieces


def test_release_lock_refuses_holdout(env):
    reels = [{"id": f"r{i}", "split": "holdout" if i < 2 else "tuning", "language": "en"} for i in range(5)]
    _w(env["s"].eval_manifest, json.dumps({"reels": reels}))
    c = env["c"]
    lab = c.get("/api/lab").json()
    assert lab["release_locked"] is True and lab["gold"] == {**lab["gold"], "pairs": 5, "holdout": 2, "tuning": 3}
    r = c.post("/api/lab/eval", json={"release": True})
    assert r.status_code == 409 and "locked" in r.json()["error"]
    r = c.post("/api/lab/eval", json={})
    assert r.status_code == 200 and env["launcher"].procs[-1][0].argv[3:] == ["eval", "--set", "tuning"]
    assert c.post("/api/lab/calibrate").status_code == 409  # one lab job at a time
    assert c.post("/api/lab/nope").status_code == 400


def test_brands_crud_and_label(env):
    c = env["c"]
    made = c.post("/api/brands", json={"brand": {"client": "Dear Ma", "colors": {"accent": "#FF3399"}}}).json()
    assert made["id"] == "dear-ma" and made["brand"]["colors"]["accent"] == "#FF3399" and made["brand"]["caption_tokens"] == {}
    assert c.post("/api/brands", json={"id": "dear-ma", "brand": {"client": "Dear Ma"}}).status_code == 409
    assert c.post("/api/brands", json={"brand": {"client": "X", "bogus": 1}}).status_code == 400
    assert c.post("/api/brands", json={"client": "X"}).status_code == 400  # the Brand goes inside {id?, brand}
    assert c.put("/api/brands/dear-ma", json={"client": "Dear Ma", "look": "warm"}).json()["brand"]["look"] == "warm"
    assert c.get("/api/brands/dear-ma").json()["brand"]["look"] == "warm"
    assert [b["id"] for b in c.get("/api/brands").json()] == ["dear-ma"]
    assert c.get("/api/brands/..%2fx").status_code == 404
    ws = make_project(env["root"])
    assert c.post("/api/projects/p1/label", json={"sendable": False, "reason": "captions"}).status_code == 204
    assert json.loads((ws / "qa" / "owner_label.json").read_text()) == {"sendable": False, "note": "captions"}


def test_upload_rejects_non_video_and_queues_run(env):
    c = env["c"]
    r = c.post("/api/projects", data={"name": "Client A"}, files=[("files[]", ("a.mp4", b"\0" * 10, "video/mp4")),
                                                                   ("files[]", ("brief.pdf", b"%PDF", "application/pdf"))])
    assert r.status_code == 400 and "brief.pdf" in r.json()["error"]
    r = c.post("/api/projects", data={"name": "Client A", "brief": json.dumps({"language": "hinglish", "client": "Acme"})},
               files=[("files[]", ("a.mp4", b"\0" * 10, "video/mp4"))])
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    ws = env["root"] / pid
    assert (ws / "source" / "raw" / "a.mp4").exists() and json.loads((ws / "brief.json").read_text())["language"] == "hinglish"
    assert r.json()["job"]["kind"] == "run" and c.get(f"/api/projects/{pid}").json()["name"] == "Client A"
    assert c.post("/api/projects", data={"name": "B", "brief": "{not json"}, files=[("files[]", ("a.mp4", b"\0", "video/mp4"))]).status_code == 400


def test_delete_moves_to_trash(env):
    make_project(env["root"])
    assert env["c"].delete("/api/projects/p1").status_code == 204
    assert not (env["root"] / "p1").exists() and len(list((env["root"] / ".trash").iterdir())) == 1


def test_cli_rerun_and_revise_args(tmp_path, monkeypatch):
    from reel import cli, runner
    from reel.stages import edit

    seen = {}

    def fake_run_pipeline(ws, stages, *, options=None, force=None):
        seen.update(names=[s.name for s in stages], force=force, options=options)
        return {"stages": {}}

    monkeypatch.setattr(runner, "run_pipeline", fake_run_pipeline)
    ws = make_project(tmp_path, "p")
    _w(ws / "run_options.json", {"input": "x", "deliverables": ["square"]})
    state = json.loads((ws / "state.json").read_text())
    state["stages"]["finish"]["input_hash"] = "stale"  # e.g. story.json changed by a manual adjustment
    _w(ws / "state.json", state)
    assert cli.main(["rerun", "--project", str(ws), "--from", "package"]) == 0
    assert seen["names"] == ["package", "variants"] and seen["force"] == {"package"}
    fresh = edit.FINISH.input_hash(runner.StageContext(ws=runner.Workspace(ws), options=seen["options"]))
    assert json.loads((ws / "state.json").read_text())["stages"]["finish"]["input_hash"] == fresh  # a later `reel run` keeps the plans
    assert not (ws / "run.lock").exists()
    ctx = runner.StageContext(ws=None, options={"deliverables": ["square", "nope"]})
    assert edit._deliverables(ctx) == ["square"]
    got = []
    monkeypatch.setattr(cli, "_cmd_revise", lambda args: got.append(args.request) or 0)
    cli.main(["revise", "--project", "p", "--", "-make the hook faster"])
    assert got == ["-make the hook faster"]


# ------------------------------------------------------------------ unified contract: package, delivered, settings, lab, libraries


def test_rename_and_set_client_without_touching_the_brief(env):
    ws = make_project(env["root"])
    c = env["c"]
    assert c.patch("/api/projects/p1", json={"name": "  Juice myth  ", "client": "Globex"}).status_code == 204
    p = c.get("/api/projects/p1").json()
    assert p["name"] == "Juice myth" and p["client"] == "Globex"
    assert c.patch("/api/projects/p1", json={"client": ""}).status_code == 204
    assert c.get("/api/projects/p1").json()["client"] is None
    assert c.patch("/api/projects/p1", json={"name": ""}).status_code in (400, 422)
    assert json.loads((ws / "run_options.json").read_text())["brief"] is None  # the Editor's inputs are unchanged
    from reel import project as project_mod
    from reel.workspace import Workspace

    c.patch("/api/projects/p1", json={"client": "Globex"})
    assert project_mod.studio_client(Workspace(ws)) == "Globex"  # the licence gate's fallback client


def test_templates_live_on_the_engine(env):
    c = env["c"]
    assert c.get("/api/templates").json() == {}
    saved = c.put("/api/templates", json={"templates": {"Acme reels": {"client": "Acme", "purpose": "promo"}}}).json()
    assert saved == {"Acme reels": {"client": "Acme", "purpose": "promo"}} and c.get("/api/templates").json() == saved
    f = env["s"].prefs_file.parent / "templates.json"
    assert (f.stat().st_mode & 0o777) == 0o600
    assert c.put("/api/templates", json={"templates": {" ": {}}}).status_code == 400


def test_starter_packs_run_as_a_library_job(env):
    r = env["c"].post("/api/library/starter-packs")
    assert r.status_code == 200 and r.json()["job"]["project"] == "_library"
    assert env["launcher"].procs[-1][0].argv[3:] == ["assets", "fetch"]


def test_plain_verdict_and_eta(env):
    ws = make_project(env["root"])
    v = env["c"].get("/api/projects/p1").json()["verdict_detail"]
    assert v["plain"] == [{"gate": "reading_speed", "status": "warn", "title": "Reading speed",
                           "sentence": "Captions go by faster than people can read in one stretch.", "at": [], "detail": "fast"}]
    from reel.studio import projects as pr

    for k in range(3):  # three finished projects, every stage 0.5 s per footage second (60 s footage → 30 s)
        other = make_project(env["root"], f"q{k}")
        st = json.loads((other / "state.json").read_text())
        for e in st["stages"].values():
            e["started"] = e["finished"] - 30
        _w(other / "state.json", st)
    stl = [{"name": "render", "status": "running", "started": 1000.0}, {"name": "overlay", "status": "pending"}]
    assert pr.eta_s(ws, stl, now=1010.0) == 20 + 30  # render: 30 − 10 s spent; overlay: 30
    assert pr.eta_s(ws, [{"name": "never_seen", "status": "pending"}]) is None  # < 3 samples: unknown, not a guess


def test_a_long_recording_is_used_where_it_is(env, tmp_path):
    """No upload, no copy: the recording on this Mac is the run's input (the 4 GB browser cap doesn't apply)."""
    c = env["c"]
    rec = tmp_path / "talk.mp4"
    rec.write_bytes(b"\0" * 10)
    (tmp_path / "notes.txt").write_text("x")
    for bad in ("https://example.com/talk.mp4", str(tmp_path / "nope.mp4"), str(tmp_path / "notes.txt"), str(tmp_path)):
        assert c.post("/api/projects", data={"name": "x", "source_path": bad}).status_code == 400, bad
    both = c.post("/api/projects", data={"name": "x", "source_path": str(rec)}, files=[("files[]", ("a.mp4", b"\0", "video/mp4"))])
    assert both.status_code == 400
    assert c.post("/api/projects", data={"name": "x"}).status_code == 400  # neither
    r = c.post("/api/projects", data={"name": "Talk", "source_path": str(rec), "mode": "long"})
    assert r.status_code == 201, r.text
    ws = env["root"] / r.json()["id"]
    assert not list((ws / "source" / "raw").iterdir())  # nothing copied
    argv = env["launcher"].procs[-1][0].argv
    assert str(rec.resolve()) in argv and "--mine" in argv and "--no-story-checkin" not in argv
    from reel.studio import projects as projects_mod

    assert projects_mod.studio_meta(ws)["source_path"] == str(rec.resolve())


def test_an_upload_too_big_is_refused_before_it_is_read(env):
    from reel.studio import app as app_mod

    app2 = app_mod.create_app(Settings(**{**env["s"].__dict__, "max_upload_bytes": 100}), launcher=env["launcher"])
    c2 = TestClient(app2, headers={"X-Reel-Token": env["token"]})
    r = c2.post("/api/projects", data={"name": "x"}, files=[("files[]", ("a.mp4", b"\0" * 1000, "video/mp4"))])
    assert r.status_code == 413 and "on this Mac" in r.text


def test_create_project_checks_the_broll_folder(env, tmp_path):
    files = {"files": ("a.mp4", b"x" * 10, "video/mp4")}
    r = env["c"].post("/api/projects", data={"name": "x", "broll_folder": str(tmp_path / "nope")}, files=files)
    assert r.status_code in (400, 503) and ("b-roll" in r.text or "toolchain" in r.text.lower())


def test_hook_preview_waits_for_the_pick_then_renders(env):
    ws = make_project(env["root"])
    (ws / "qa" / "verdict.json").unlink()  # a --preview-first run: no render, no verdict yet
    _w(ws / "export" / "preview" / "preview.json", {"frames": 90, "chosen": None, "options": {
        "A": {"caption_family": "bold_pop", "look": "clean", "file": "export/preview/hook_A.mp4", "plan": {}},
        "B": {"caption_family": "clean_phrase", "look": "warm", "file": "export/preview/hook_B.mp4", "plan": {"look": "warm"}}}})
    c = env["c"]
    p = c.get("/api/projects/p1").json()
    assert p["status"] == "awaiting_choice" and "pick the hook look (A/B)" in p["needs_attention"] and p["preview"]["options"]["B"]["look"] == "warm"
    assert c.post("/api/projects/p1/preview/choose", json={"option": "Z"}).status_code == 400  # the Studio maps validation errors to 400
    r = c.post("/api/projects/p1/preview/choose", json={"option": "B"})
    assert r.status_code == 200 and "--preview-first" not in env["launcher"].procs[-1][0].argv
    assert json.loads((ws / "plan" / "finish.json").read_text())["grade"]["look"] == "warm"
    assert c.get("/api/projects/p1").json()["preview"]["chosen"] == "B"


def test_post_copy_route_serves_only_the_credited_version(env):
    ws = make_project(env["root"])
    c = env["c"]
    _w(ws / "plan" / "copy.json", json.dumps({"status": "failed", "reason": "claude unavailable"}))
    r = c.get("/api/projects/p1/copy")
    assert r.status_code == 404 and "claude unavailable" in r.text
    _w(ws / "export" / "package" / "copy.json", json.dumps({"ig_caption": "Hook\n\n#a\n\nCredit", "status": "ok"}))
    assert c.get("/api/projects/p1/copy").json()["ig_caption"].endswith("Credit")


def test_package_listing_and_delivered(env):
    ws = make_project(env["root"])
    _w(ws / "export" / "package" / "reel.mp4", "x" * 10)
    _w(ws / "export" / "package" / "timeline.fcpxml", "<fcpxml/>")
    _w(ws / "export" / "package" / "captions.srt", "1")
    _w(ws / "export" / "package" / "stems" / "dialogue.wav", "ab")
    _w(ws / "export" / "package" / "stems" / "music.wav", "cd")
    _w(ws / "export" / "variants" / "reel_square.mp4", "sq")
    _w(ws / "export" / "review" / "review.mp4", "rv")
    (ws / "cover.jpg").write_bytes(b"jpg")
    c = env["c"]
    pkg = c.get("/api/projects/p1/package").json()
    by = {f["kind"]: f for f in pkg["files"]}
    assert by["final"] == {"path": "export/package/reel.mp4", "label": "Final reel · 9:16 · 1080×1920", "kind": "final", "bytes": 10, "thumb": "cover.jpg"}
    assert by["variant"]["label"].startswith("Square") and by["review_copy"]["path"] == "export/review/review.mp4"
    assert by["stems"] == {"path": "export/package/stems/", "label": "Audio stems · dialogue, music, effects", "kind": "stems", "bytes": 4, "thumb": None}
    assert {f["kind"] for f in pkg["files"]} >= {"timeline", "captions", "other"} and pkg["warnings"] == []
    for f in pkg["files"]:  # every file (not folder) is servable as media
        if not f["path"].endswith("/"):
            assert c.get(f"/api/projects/p1/media/{f['path']}").status_code == 200, f["path"]

    assert c.post("/api/projects/p1/delivered").status_code == 204  # no body: marks delivered
    s = c.get("/api/projects").json()[0]
    assert s["delivered_at"] and "delivered" not in s
    make_project(env["root"], "p2", verdict="sendable")
    assert [p["id"] for p in c.get("/api/projects").json()] == ["p2", "p1"]  # delivered sorts last
    assert c.post("/api/projects/p1/delivered", json={"delivered": False}).status_code == 204
    assert c.get("/api/projects/p1").json()["delivered_at"] is None


def test_settings_persist_private_and_feed_the_queue(env):
    c, s = env["c"], env["s"]
    got = c.get("/api/settings").json()
    assert got == {"max_jobs": 3, "projects_dir": str(env["root"]), "default_brief": {}, "default_deliverables": [], "pexels_key_set": False,
                   "pixabay_key_set": False, "monthly_cap_usd": 0.0}
    new = {**got, "max_jobs": 1, "default_brief": {"language": "hinglish", "platform": "platform.tiktok"}, "default_deliverables": ["square"],
           "pexels_key": "sekret-key", "pixabay_key": "pix-sekret"}
    r = c.put("/api/settings", json=new)
    assert r.status_code == 200 and r.json()["pexels_key_set"] is True and r.json()["pixabay_key_set"] is True
    assert "pexels_key" not in r.json() and "pixabay_key" not in r.json()
    assert "sekret" not in c.get("/api/settings").text and c.get("/api/health").json()["jobs"]["limit"] == 1
    assert (s.prefs_file.stat().st_mode & 0o777) == 0o600 and json.loads(s.prefs_file.read_text())["pexels_key"] == "sekret-key"
    assert s.job_env["PEXELS_API_KEY"] == "sekret-key" and s.job_env["PIXABAY_API_KEY"] == "pix-sekret"  # reach the jobs, never the queue file
    assert c.put("/api/settings", json={**new, "pexels_key": ""}).json()["pexels_key_set"] is True  # blank keeps the key
    for bad in ({**new, "max_jobs": 4}, {**new, "projects_dir": "/elsewhere"}, {**new, "default_brief": {"bogus": 1}},
                {**new, "default_deliverables": ["vertical"]}):
        assert c.put("/api/settings", json=bad).status_code == 400, bad
    # max_jobs drives the queue
    for i in range(2):
        make_project(env["root"], f"m{i}")
    assert [c.post(f"/api/projects/m{i}/retry", json={}).json()["job"]["status"] for i in range(2)] == ["running", "queued"]
    c.put("/api/settings", json={**new, "max_jobs": 2})
    assert len(c.get("/api/jobs").json()["running"]) == 2
    # a restart reads the saved preferences
    app2 = create_app(Settings(**{**s.__dict__, "max_jobs": 3, "job_env": {}}), launcher=Launcher())
    assert app2.state.settings.max_jobs == 2 and app2.state.settings.job_env["PEXELS_API_KEY"] == "sekret-key"


def test_lab_shape(env):
    s = env["s"]
    _w(s.eval_manifest, json.dumps({"reels": [{"id": "a", "split": "tuning", "language": "en", "channel": "@x"},
                                               {"id": "b", "split": "holdout", "language": "hinglish"}]}))
    _w(s.scoreboard, "\n".join(json.dumps(r) for r in [
        {"run_id": "r1", "time": 1795000000.0, "split": "tuning", "mean_primary": 61.5, "vetoed": 0,
         "reels": [{"id": "a", "primary": 61.5, "families": {"story": 0.5, "captions": 0.7}, "vetoes": []}]},
        {"run_id": "r2", "time": 1795000100.0, "split": "tuning", "mean_primary": None, "reels": []}]))
    _w(s.improve_log, "\n".join(json.dumps(r) for r in [
        {"round": 0, "diagnosis": "d", "changes": [{"kind": "edit", "node_id": "tech.x"}], "outcome": "accepted", "decision": {"mean_gain": 2.0, "reasons": []}},
        {"round": 1, "diagnosis": "nothing", "changes": [], "problems": ["bad node"], "outcome": "invalid proposal"}]))
    _w(s.calibration_report, {"rule": "r", "gates": {"black": {"false_alarms": 2, "known_good": 6, "catch_rate": 1.0, "mode_now": "warn",
                                                               "promote_to_block": False}}})
    lab = env["c"].get("/api/lab").json()
    assert lab["gold"] == {"pairs": 2, "tuning": 1, "holdout": 1, "hinglish": 1}
    assert lab["gold_pairs"][0] == {"id": "a", "split": "tuning", "language": "en", "source": "@x"}
    assert lab["runs"] == [{"id": "r1", "at": lab["runs"][0]["at"], "split": "tuning", "primary": 0.615, "families": {"story": 0.5, "captions": 0.7},
                            "vetoed": 0, "reels": [{"id": "a", "primary": 0.615, "verdict": None, "vetoes": []}]}]  # null scores dropped
    assert lab["improve_history"][0] | {"at": None} == {"at": None, "round": 0, "change": "edit tech.x", "outcome": "accepted", "gain": 0.02, "reason": None}
    assert lab["improve_history"][1]["outcome"] == "invalid" and lab["improve_history"][1]["reason"] == "bad node"
    cal = lab["calibration"]
    assert cal["agreement"] is None and cal["n_labels"] == 0 and cal["trusted"] is False
    assert cal["gates"] == [{"name": "black", "mode": "warn", "false_alarm_rate": 0.333, "catch_rate": 1.0, "promote_to_block": False}]
    assert lab["release_locked"] is True and lab["lock_reason"].startswith("Release check locked")
    r = env["c"].post("/api/lab/improve", json={"budget": 7})
    assert r.status_code == 200 and env["launcher"].procs[-1][0].argv[3:6] == ["improve", "--budget", "7"]


def test_library_media_and_query_token(env, monkeypatch, tmp_path):
    from reel import assets

    wav = tmp_path / "pop.wav"
    wav.write_bytes(b"RIFF....")
    monkeypatch.setattr(assets, "load", lambda *a, **k: assets.Indexes(sfx={"pop_1": {"id": "pop_1", "file": str(wav), "category": "pop"}},
                                                                        music={}, broll={}, caption_families={}))
    bare = TestClient(env["app"])
    assert bare.get(f"/api/libraries/sfx/pop_1/media?token={env['token']}").content == b"RIFF...."
    assert bare.get("/api/libraries/sfx/pop_1/media").status_code == 401
    assert env["c"].get("/api/libraries/sfx/nope/media").status_code == 404
    assert env["c"].get("/api/libraries/fonts/pop_1/media").status_code == 400
    lib = env["c"].get("/api/libraries").json()
    assert lib["sfx"][0]["id"] == "pop_1" and lib["unreadable"] == []


def test_job_versions_reply_cost_and_sse_snapshot_after_done(env):
    ws = make_project(env["root"])
    c = env["c"]
    r = c.post("/api/projects/p1/revise", json={"request": "make the hook faster"})
    assert r.status_code == 200 and r.json()["job"]["kind"] == "revise" and r.json()["job"]["status"] == "running"
    job_id = r.json()["job"]["id"]
    _w(ws / "plan" / "history" / "001_request.json", {"request": "make the hook faster", "reply": "Trimmed the opening breath."})
    with open(ws / "log" / "runs.jsonl", "a") as f:
        f.write(json.dumps({"time": time.time() + 1, "label": "revision", "session_id": "z", "cost_usd": 0.09, "cost_cum_usd": 0.09, "exit": 0}) + "\n")

    def later():
        time.sleep(0.3)
        env["launcher"].finish("revise")

    threading.Thread(target=later).start()
    r = c.get(f"/api/projects/p1/events?token={env['token']}", headers={"X-Reel-Token": ""})
    events = [(b.split("event: ")[1].split("\n")[0], json.loads(b.split("data: ", 1)[1])) for b in r.text.split("\n\n") if "event: " in b]
    names = [e for e, _ in events]
    job_ev = next(d for e, d in events if e == "job" and d["status"] == "done")
    assert job_ev["id"] == job_id
    measured = "Trimmed the opening breath. · QA after the change: Hold, 1 reason(s): proof_words"  # 3b.4: the claim next to the measured verdict
    assert next(d for e, d in events if e == "revision") == {"reply": measured, "request": "make the hook faster", "version": 2}
    assert names.index("done") < len(names) - 1 and names[names.index("done") + 1] == "snapshot"
    snap = events[names.index("done") + 1][1]
    assert [v["label"] for v in snap["versions"]] == ["Original edit", "Revision: “make the hook faster”"]
    assert snap["versions"][1]["reply"] == measured and snap["versions"][1]["cost_usd"] == pytest.approx(0.09)
    # proof fixes become versions too; restoring the current version is refused
    assert c.post("/api/projects/p1/proof", json={"words": [{"i": 2, "text": "sugar"}]}).status_code == 200
    env["launcher"].finish("proof")
    vs = c.get("/api/projects/p1/versions").json()
    assert vs[-1]["label"] == "Caption fix" and vs[-1]["reply"].startswith("Caption words: “sugar” confirmed · QA after the change:")
    assert c.post(f"/api/projects/p1/versions/{vs[-1]['n']}/restore").status_code == 400
    assert c.post("/api/projects/p1/versions/1/restore").status_code == 200


def test_decision_costs_and_reviewer_summary(env):
    rows = [{"time": 1, "label": "story", "session_id": "s1", "cost_usd": 0.5, "cost_cum_usd": 0.5, "exit": 0},
            {"time": 2, "label": "finish", "session_id": "s2", "cost_usd": 0.25, "cost_cum_usd": 0.25, "exit": 0},
            {"time": 3, "label": "review", "session_id": "s3", "cost_usd": 0.125, "cost_cum_usd": 0.125, "exit": 0}]
    make_project(env["root"], runs=rows)
    d = env["c"].get("/api/projects/p1").json()
    cost = {x["title"]: x.get("cost_usd") for x in d["decisions"]}
    assert cost["Captions: bold_pop"] == 0.25 and cost["Reviewer: sendable"] == 0.125
    assert next(x for x in d["decisions"] if x["title"].startswith("Hook"))["cost_usd"] == 0.5
    assert all("cost_usd" not in x for x in d["decisions"] if x["title"].startswith("Keep"))


def test_cost_days_cover_the_whole_window(tmp_path):
    make_project(tmp_path, "a", runs=[{"time": 86400 * 9.5, "label": "story", "cost_usd": 0.2}])
    days = costs.summary(tmp_path, days=3, now=86400 * 10)["by_day"]
    assert len(days) == 3 and days[-1]["date"] == time.strftime("%Y-%m-%d", time.localtime(86400 * 10)) and sum(d["usd"] for d in days) == pytest.approx(0.2)


def test_underscore_project_ids_are_projects_not_job_slots(env):
    make_project(env["root"], "_real")  # e.g. projects/_real_doac
    c = env["c"]
    assert c.post("/api/projects/_real/adjust", json={"kind": "look", "value": "warm"}).status_code == 200
    env["launcher"].finish("adjust")
    assert [v["label"] for v in c.get("/api/projects/_real/versions").json()] == ["Original edit", "Manual"]


# ------------------------------------------------------------------ review links (client page without the token)


def test_review_link_lifecycle_and_isolation(env, monkeypatch):
    from reel.studio import review_links

    made = []
    monkeypatch.setattr(review_links, "_transcode", lambda src, dst: (made.append(src), dst.write_bytes(b"MP4DATA")))
    ws = make_project(env["root"])
    ws2 = make_project(env["root"], "p2")
    (ws2 / "render" / "final.mp4").unlink()
    c, bare = env["c"], TestClient(env["app"])
    assert c.post("/api/projects/p2/review-links", json={"hours": 24}).status_code == 409  # no render to make a copy from
    assert c.get("/api/projects/p2/review-links").json()["ready"] is False
    assert bare.post("/api/projects/p1/review-links", json={"hours": 24}).status_code == 401  # owner side needs the token
    link = c.post("/api/projects/p1/review-links", json={"hours": 24}).json()
    assert made == [ws / "render" / "final.mp4"] and (ws / "export" / "review" / "review.mp4").read_bytes() == b"MP4DATA"
    assert link["state"] == "active" and link["path"].startswith("/r/") and len(link["id"]) >= 24

    page = bare.get(link["path"])  # the client needs no token
    assert page.status_code == 200 and "Project p1" in page.text and "Send notes" in page.text
    assert "default-src 'none'" in page.headers["content-security-policy"] and page.headers["x-robots-tag"].startswith("noindex")
    assert "Project p2" not in page.text
    assert bare.get(link["path"] + "/video").content == b"MP4DATA"

    r = bare.post(link["path"] + "/notes", data={"name": " Priya ", "text": "0:12 faster\nlove it"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == link["path"] + "?sent=1"
    assert bare.post(link["path"] + "/notes", data={"text": "   "}).status_code == 400
    assert bare.post(link["path"] + "/notes", data={"text": "x" * 5000}).status_code == 400
    got = c.get("/api/projects/p1/review-links").json()
    assert got["ready"] and [n["text"] for n in got["notes"]] == ["0:12 faster\nlove it"] and got["notes"][0]["name"] == "Priya"
    assert got["links"][0]["notes"] == 1
    assert c.get("/api/projects/p2/review-links").json()["links"] == []  # links belong to one project

    for bad in ("/r/short", "/r/" + "A" * 30, link["path"] + "x"):
        assert bare.get(bad).status_code in (404, 410), bad
    assert bare.get("/r/../api/projects").status_code == 401  # a link never opens the token-protected API
    assert c.delete(f"/api/projects/p2/review-links/{link['id']}").status_code == 404  # another project's link
    assert c.delete(f"/api/projects/p1/review-links/{link['id']}").status_code == 204
    assert bare.get(link["path"]).status_code == 410 and bare.get(link["path"] + "/video").status_code == 410
    assert bare.post(link["path"] + "/notes", data={"text": "late"}).status_code == 410

    expiring = c.post("/api/projects/p1/review-links", json={"hours": 1}).json()
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 7200)
    assert bare.get(expiring["path"]).status_code == 410
    monkeypatch.setattr(time, "time", real_time)
    assert c.post("/api/projects/p1/review-links", json={"hours": 0}).status_code == 400


def test_review_link_before_the_render_shows_the_checkin_and_the_hook(env, monkeypatch):
    """3a.1 + G1.6 on the client page: the client only suggests (recorded, stamped); the owner applies in the Studio."""
    from reel.studio import review_links

    made = []
    monkeypatch.setattr(review_links, "_transcode", lambda src, dst: (made.append(src.name), dst.write_bytes(b"SMALL")))
    ws = make_project(env["root"], "p2")
    (ws / "render" / "final.mp4").unlink()
    c, bare = env["c"], TestClient(env["app"])
    ci = {"status": "open", "story_fp": "fp1", "summary": "s", "total_s": 21.0, "questions": [
        {"id": "q1", "kind": "drop", "text": "Drop this 9 s line: <b>bold</b>?", "why": "engine take score"}],
        "lines": [{"id": "k1", "seconds": 3.2, "text": "Hook <script>x</script>"}, {"id": "k2", "seconds": 9.0, "text": "Long line"}]}
    (ws / "plan").mkdir(exist_ok=True)
    (ws / "plan" / "checkin.json").write_text(json.dumps(ci))
    pv_dir = ws / "export" / "preview"
    pv_dir.mkdir(parents=True)
    for o in "AB":
        (pv_dir / f"hook_{o}.mp4").write_bytes(b"FULLQUALITY")
    pv = {"frames": 90, "options": {"A": {"file": "export/preview/hook_A.mp4"}, "B": {"file": "export/preview/hook_B.mp4"}}, "chosen": None}
    (pv_dir / "preview.json").write_text(json.dumps(pv))

    assert c.get("/api/projects/p2/review-links").json()["ready"] is True
    link = c.post("/api/projects/p2/review-links", json={"hours": 24}).json()
    assert sorted(made) == ["hook_A.mp4", "hook_B.mp4"]  # watermarked copies; the full-quality previews are never served
    page = bare.get(link["path"]).text
    assert "Check the story" in page and "Pick the look" in page and "Send notes" not in page
    assert "<script>x" not in page and "&lt;script&gt;" in page and "&lt;b&gt;" in page and "engine take score" not in page
    assert bare.get(link["path"] + "/video").status_code == 410
    assert bare.get(link["path"] + "/hook/A").content == b"SMALL"
    assert bare.get(link["path"] + "/hook/C").status_code in (400, 404, 422)
    assert bare.post(link["path"] + "/notes", data={"text": "hi"}).status_code == 400  # no reel to note yet

    r = bare.post(link["path"] + "/checkin", data={"yes": ["q1"], "note": "end on the result", "name": "Priya"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("?sent=checkin")
    assert bare.post(link["path"] + "/checkin", data={"yes": ["q9"]}).status_code == 400  # not a question on this check-in
    assert bare.post(link["path"] + "/hook", data={"option": "B"}, follow_redirects=False).status_code == 303
    assert bare.post(link["path"] + "/hook", data={"option": "Z"}).status_code == 400
    got = c.get("/api/projects/p2/review-links").json()["choices"]
    assert got["checkin"]["yes"] == ["q1"] and got["checkin"]["note"] == "end on the result" and got["hook"]["option"] == "B"

    ci["story_fp"] = "fp2"  # the story changed: the old answers are not offered for the new questions
    (ws / "plan" / "checkin.json").write_text(json.dumps(ci))
    assert c.get("/api/projects/p2/review-links").json()["choices"]["checkin"] is None
    ci["status"] = "answered"
    (ws / "plan" / "checkin.json").write_text(json.dumps(ci))
    pv["chosen"] = "A"
    (pv_dir / "preview.json").write_text(json.dumps(pv))
    assert bare.post(link["path"] + "/checkin", data={"yes": []}).status_code == 400  # settled
    assert bare.get(link["path"] + "/hook/A").status_code == 410
    assert "in progress" in bare.get(link["path"]).text  # nothing open, nothing rendered: not "expired"
