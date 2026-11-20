"""3a.1 story check-in: questions built by code, answers applied and re-validated, the Studio flow."""

from __future__ import annotations

import json

import pytest

from reel import checkin, decide
from reel.claude_call import CallResult
from reel.schemas.perception import Word, WordTable
from reel.workspace import Workspace, atomic_write_json

from test_studio import env  # noqa: F401 — the env fixture

# four segments of 20 words (10 s each); s003 is a retake of s002 and the engine's suggested one
TEXT = {0: "Most people save what is left", 1: "Here is the long story about my first job and the salary",
        2: "Save first then spend", 3: "Save first then spend"}


def _words() -> WordTable:
    out = []
    for s in range(4):
        base = TEXT[s].split()
        for k in range(20):
            i = s * 20 + k
            out.append(Word(i=i, clip="c01", text=base[k % len(base)] + ("." if k == 19 else ""), start_us=i * 500_000, end_us=i * 500_000 + 400_000))
    return WordTable(language="en", words=out)


def _row(s):
    return {"seg_id": f"s{s:03d}", "clip": "c01", "t0": s * 10.0, "t1": s * 10.0 + 9.9, "words": [s * 20, s * 20 + 19], "text": TEXT[s],
            "take": {"group": "T01", "take": s - 1, "of": 2, "suggested_rank": 2 if s == 2 else 1} if s in (2, 3) else None}


def _item(iid, s, beat):
    w = _words().by_index()
    return {"id": iid, "clip": "c01", "word_start": s * 20, "word_end": s * 20 + 19, "first_word": w[s * 20].text, "last_word": w[s * 20 + 19].text,
            "beat": beat, "reason": "r"}


STORY = {"genre": "genre.tutorial", "summary": "save first", "hook": "h1", "knowledge_used": [],
         "hook_options": [{"id": "h1", "item": "k01", "rank": 1, "reason": "a claim"}, {"id": "h2", "item": "k03", "rank": 2, "reason": "the payoff"}],
         "items": [_item("k01", 0, "hook"), _item("k02", 1, "setup"), _item("k03", 2, "payoff")]}


@pytest.fixture
def ws(tmp_path):
    w = Workspace.create(tmp_path / "p1")
    atomic_write_json(w.path("source", "manifest.json"), {"project_fps": "30/1", "clips": [{"id": "c01", "probe": {"duration_s": 40.0}}]})
    atomic_write_json(w.path("perception", "words.json"), _words().model_dump(mode="json"))
    atomic_write_json(w.path("tables", "segments.json"), {"segments": [_row(s) for s in range(4)]})
    atomic_write_json(w.path("tables", "takes.json"), {"groups": [{"group": "T01", "members": [
        {"seg_id": "s002", "take": 1, "suggested_rank": 2}, {"seg_id": "s003", "take": 2, "suggested_rank": 1}]}]})
    atomic_write_json(w.path("plan", "story.json"), STORY)
    atomic_write_json(w.path("plan", "sessions.json"), {"story": "st-1"})
    atomic_write_json(w.path("run_options.json"), {"input": "/x", "language": "en"})
    return w


def test_questions_come_from_hook_options_takes_and_long_lines(ws):
    meta = checkin.build(ws, decide.load_inputs(ws))
    c = checkin.load(ws)
    kinds = [q["kind"] for q in c["questions"]]
    assert meta["questions"] == 3 and kinds == ["hook", "take", "drop"]
    assert c["status"] == "open" and c["hook"]["item"] == "k01" and len(c["lines"]) == 3 and c["total_s"] > 29
    assert c["left_out"][0]["seg_id"] == "s003"
    take = c["questions"][1]
    assert take["item"] == "k03" and take["segment"] == "s003" and "take 2 of 2" in take["text"]


def test_must_keep_line_left_out_is_a_warning(ws, tmp_path):
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"project": "p1", "must_keep_lines": ["save first then spend", "my grandmother's rule"]}))
    checkin.build(ws, decide.load_inputs(ws, str(brief)))
    assert checkin.load(ws)["warnings"] == ["The brief's must-keep line “my grandmother's rule” isn't in the story."]


def test_answers_change_only_the_story_and_approve(ws):
    inp = decide.load_inputs(ws)
    checkin.build(ws, inp)
    res = checkin.answer(ws, inp, ["q1", "q2"])
    story = json.loads(ws.path("plan", "story.json").read_text())
    assert [it["id"] for it in story["items"]] == ["k03", "k01", "k02"] and story["hook"] == "h2"  # the payoff now opens
    k03 = story["items"][0]
    assert (k03["word_start"], k03["word_end"]) == (60, 79)  # the suggested take
    assert res == {"applied": ["hook", "take"], "calls": 0}
    assert checkin.load(ws)["status"] == "approved" and "TOTAL" in ws.path("plan", "story_readback.txt").read_text()
    assert not ws.path("plan", "finish.json").exists()
    with pytest.raises(checkin.CheckinError, match="no open"):
        checkin.answer(ws, inp, [])


def test_dropping_a_line_and_a_note(ws):
    inp = decide.load_inputs(ws)
    checkin.build(ws, inp)
    revised = dict(STORY, items=[_item("k01", 0, "hook"), _item("k03", 2, "payoff")])
    calls = []

    def fake(prompt, schema, **kw):
        calls.append((prompt, kw))
        return CallResult(data=revised, session_id="st-2", num_turns=1, cost_usd=0.01, usage={}, duration_s=0.0)

    res = checkin.answer(ws, inp, ["q3"], note="end on the payoff", caller=fake)
    assert res["applied"] == ["drop", "note"] and res["calls"] == 1
    assert calls[0][1]["resume"] == "st-1" and "end on the payoff" in calls[0][0]
    assert [it["id"] for it in json.loads(ws.path("plan", "story.json").read_text())["items"]] == ["k01", "k03"]


def test_stale_or_unknown_answers_are_refused(ws):
    inp = decide.load_inputs(ws)
    checkin.build(ws, inp)
    with pytest.raises(checkin.CheckinError, match="unknown"):
        checkin.answer(ws, inp, ["q9"])
    ws.path("plan", "story.json").write_text(json.dumps(dict(STORY, summary="changed")))
    with pytest.raises(checkin.CheckinError, match="changed"):
        checkin.answer(ws, inp, ["q1"])


def test_the_run_stops_after_the_story_pass():
    from reel.stages import CLIP_PIPELINE, EDIT_PIPELINE, edit

    names = [s.name for s in edit.checkin_pipeline(EDIT_PIPELINE)]
    assert names[-2:] == ["story", "checkin"] and "finish" not in names and "ingest" in names
    assert [s.name for s in edit.checkin_pipeline(CLIP_PIPELINE)][0] == "stock"


def test_studio_checkin_flow(env, ws):  # noqa: F811
    import shutil

    root = env["root"] / "p1"
    shutil.copytree(ws.root, root)
    (root / "studio.json").write_text(json.dumps({"name": "Save first", "created": 1795000000.0}))
    w = Workspace(root)
    checkin.build(w, decide.load_inputs(w))
    proj = next(p for p in env["c"].get("/api/projects").json() if p["id"] == "p1")
    assert proj["status"] == "awaiting_story" and "check the story" in proj["needs_attention"]
    c = env["c"].get("/api/projects/p1/checkin").json()
    assert len(c["questions"]) == 3
    assert env["c"].post("/api/projects/p1/checkin", json={"yes": ["q7"]}).status_code == 400
    r = env["c"].post("/api/projects/p1/checkin", json={"yes": ["q1"], "note": "shorter"})
    assert r.status_code == 200, r.text
    job, _p = env["launcher"].procs[-1]
    a = job.argv
    assert a[a.index("checkin") + 1:a.index("checkin") + 3] == ["--project", str(root)] and "--approve" in a and "--continue" in a
    assert a[a.index("--yes") + 1] == "q1" and a[a.index("--note") + 1] == "shorter"
    assert env["c"].get("/api/projects/nope/checkin").status_code == 404
