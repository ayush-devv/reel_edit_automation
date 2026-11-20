"""G2.4: story-line edits (C4), gate switches (C3), bake-off in the lab (C5), the launcher (E1), kept adjustments."""

from __future__ import annotations

import json
import plistlib

import pytest

from reel import adjustments, config, story_edit
from reel.schemas.plan import FinishPlan, StoryPlan
from reel.studio import server
from reel.workspace import Workspace

from test_studio import env, make_project  # noqa: F401 — the env fixture


def _plans(ws):
    return (StoryPlan.model_validate_json((ws / "plan" / "story.json").read_text()),
            FinishPlan.model_validate_json((ws / "plan" / "finish.json").read_text()))


# ------------------------------------------------------------------ C4 story-line edits


def test_dropping_a_line_drops_what_was_attached_to_it(tmp_path):
    ws = make_project(tmp_path)
    story, fin = _plans(ws)
    fin = fin.model_copy(update={"graphics": [
        {"id": "g1", "kind": "progress_bar", "item": "k01", "from_word": 0, "to_word": 0, "text": "", "emoji": "", "value": 0, "style": "",
         "position": "", "x": -1, "y": -1, "reason": "r"},
        {"id": "g2", "kind": "keyword_card", "item": "k01", "from_word": 1, "to_word": 2, "text": "sugar", "emoji": "", "value": 0, "style": "",
         "position": "", "x": -1, "y": -1, "reason": "r"}]})
    fin = FinishPlan.model_validate(fin.model_dump())
    new_story, new_fin, meta = story_edit.reorder(story, fin, ["k02"])
    assert [it.id for it in new_story.items] == ["k02"] and meta["dropped"] == ["k01"]
    assert next(h for h in new_story.hook_options if h.id == new_story.hook).item == "k02"  # the hook follows the new opener
    assert [g.id for g in new_fin.graphics] == ["g1"] and new_fin.graphics[0].item == "k02"  # whole-reel graphic moves
    assert meta["removed"] == {"graphics": 1} and new_fin.captions.emphasis_words == []  # word 2 was in k01
    assert new_fin.punch_ins == fin.punch_ins  # the punch-in on k02 stays
    assert "Dropped 1 line" in story_edit.summary(meta)


def test_reorder_keeps_bindings_and_refuses_bad_orders(tmp_path):
    story, fin = _plans(make_project(tmp_path))
    s2, f2, meta = story_edit.reorder(story, fin, ["k02", "k01"])
    assert [it.id for it in s2.items] == ["k02", "k01"] and meta == {"dropped": [], "removed": {}} and f2.punch_ins == fin.punch_ins
    for bad, msg in (([], "at least one"), (["k01", "k01"], "twice"), (["k09"], "unknown")):
        with pytest.raises(story_edit.StoryEditError, match=msg):
            story_edit.reorder(story, fin, bad)


def test_story_lines_adjustment_through_the_api(env):
    ws = make_project(env["root"])
    (ws / "source" / "manifest.json").write_text(json.dumps({"project_fps": "30/1", "clips": [{"id": "c01", "probe": {"duration_s": 3.0}}]}))
    r = env["c"].post("/api/projects/p1/adjust", json={"kind": "story_lines", "value": ["k02"]})
    assert r.status_code == 200, r.text
    assert "Dropped 1 line" in r.json()["note"]
    story, _fin = _plans(ws)
    assert [it.id for it in story.items] == ["k02"]
    readback = (ws / "plan" / "story_readback.txt").read_text()
    assert "is" in readback and "How" not in readback  # the read-back follows the new story
    logged = [json.loads(x) for x in (ws / "plan" / "adjustments.jsonl").read_text().splitlines()]
    assert logged[-1]["kind"] == "story_lines"
    env["launcher"].finish("adjust")
    assert env["c"].post("/api/projects/p1/adjust", json={"kind": "story_lines", "value": "k02"}).status_code == 400


# ------------------------------------------------------------------ 3a.3 word-level edits


def _words6():
    from reel.schemas.perception import WordTable

    return WordTable.model_validate({"language": "en", "words": [
        {"i": i, "clip": "c01", "text": t, "start_us": i * 400_000, "end_us": i * 400_000 + 300_000}
        for i, t in enumerate(["How", "much", "sugar", "is", "in", "here"])]})


def test_cutting_words_splits_the_line_and_rebinds(tmp_path):
    story, fin = _plans(make_project(tmp_path))
    # k02 = words 3–5 ("is in here"), punch-in at word 4; cut word 4 → k02 (3) + k02b (5)
    fin = fin.model_copy(update={"punch_ins": [fin.punch_ins[0].model_copy(update={"at_word": 5})],
                                 "captions": fin.captions.model_copy(update={"emphasis_words": [2, 4]})})
    s2, f2, meta = story_edit.cut_words(story, fin, "k02", [[4, 4]], _words6())
    assert [(it.id, it.word_start, it.word_end, it.first_word) for it in s2.items[1:]] == [("k02", 3, 3, "is"), ("k02b", 5, 5, "here")]
    assert f2.punch_ins[0].item == "k02b" and f2.captions.emphasis_words == [2] and meta["parts"] == 2 and meta["words_removed"] == 1
    assert story_edit.summary(meta) == "Cut 1 word(s), the line is now 2 parts."
    trimmed, _f, m2 = story_edit.cut_words(story, fin, "k02", [[3, 3]], _words6())  # trim the start: still one part
    assert (trimmed.items[1].word_start, m2["parts"]) == (4, 1)
    dropped = fin.model_copy(update={"punch_ins": [fin.punch_ins[0].model_copy(update={"at_word": 4})]})
    _s3, f3, m3 = story_edit.cut_words(story, dropped, "k02", [[4, 4]], _words6())
    assert f3.punch_ins == [] and m3["removed"] == {"punch_ins": 1}


def test_cutting_words_refuses_bad_ranges(tmp_path):
    story, fin = _plans(make_project(tmp_path))
    for item, rng, msg in (("k02", [[0, 1]], "not all in line"), ("k02", [[3, 5]], "whole line"), ("k09", [[3, 3]], "unknown"), ("k02", [[5, 4]], "first word")):
        with pytest.raises(story_edit.StoryEditError, match=msg):
            story_edit.cut_words(story, fin, item, rng, _words6())


def test_story_words_through_the_api(env):
    ws = make_project(env["root"])
    (ws / "source" / "manifest.json").write_text(json.dumps({"project_fps": "30/1", "clips": [{"id": "c01", "probe": {"duration_s": 3.0}}]}))
    tl = env["c"].get("/api/projects/p1/timeline").json()
    assert tl["story"]["k02"]["words"] == [[3, "is"], [4, "in"], [5, "here"]]
    r = env["c"].post("/api/projects/p1/adjust", json={"kind": "story_words", "value": {"item": "k01", "remove": [[1, 1]]}})
    assert r.status_code == 200, r.text
    story, _fin = _plans(ws)
    assert [it.id for it in story.items] == ["k01", "k01b", "k02"]
    env["launcher"].finish("adjust")
    assert env["c"].post("/api/projects/p1/adjust", json={"kind": "story_words", "value": {"item": "k02"}}).status_code == 400


# ------------------------------------------------------------------ C3 gate switches


def test_gate_switch_needs_calibration_to_block_and_recomputes_verdicts(env):
    ws = make_project(env["root"], verdict="sendable")
    # reading_speed failed in warn mode: the reel is sendable. Blocking it isn't cleared by any calibration yet.
    r = env["c"].put("/api/lab/gates/reading_speed", json={"mode": "block"})
    assert r.status_code == 409
    env["s"].calibration_report.parent.mkdir(parents=True, exist_ok=True)
    env["s"].calibration_report.write_text(json.dumps({"gates": {"reading_speed": {"false_alarms": 0, "known_good": 30, "catch_rate": 1.0,
                                                                                   "promote_to_block": True}}}))
    r = env["c"].put("/api/lab/gates/reading_speed", json={"mode": "block"})
    assert r.status_code == 200 and r.json()["recomputed"] >= 1
    assert config.gate_modes()["reading_speed"] == "block"
    v = json.loads((ws / "qa" / "verdict.json").read_text())
    assert v["status"] == "hold" and any("reading_speed" in x for x in v["reasons"])  # no Reviewer call: re-decided from stored results
    cal = env["c"].get("/api/lab").json()["calibration"]
    assert next(g for g in cal["gates"] if g["name"] == "reading_speed")["mode"] == "block"
    assert env["c"].put("/api/lab/gates/reading_speed", json={"mode": "warn"}).status_code == 200
    assert "reading_speed" not in config.gate_overrides()  # back to the code default: the override is removed
    assert json.loads((ws / "qa" / "verdict.json").read_text())["status"] == "sendable"
    assert env["c"].put("/api/lab/gates/nope", json={"mode": "warn"}).status_code == 404


# ------------------------------------------------------------------ C5 bake-off, E1 launcher


def test_lab_reports_the_bakeoff_and_refuses_without_samples(env, monkeypatch, tmp_path):
    from reel.studio import catalog

    out = tmp_path / "bakeoff"
    (out / "20261120-101010").mkdir(parents=True)
    (out / "20261120-101010" / "results.json").write_text(json.dumps({"summary": {"whisper-large-v3": {"wer": 0.21}}}))
    monkeypatch.setattr(catalog, "bakeoff_paths", lambda: (tmp_path / "no-samples", out))
    lab = env["c"].get("/api/lab").json()["bakeoff"]
    assert lab["latest"]["summary"]["whisper-large-v3"]["wer"] == 0.21 and lab["engines_now"]["hinglish"] and lab["samples"] == 0
    assert env["c"].post("/api/lab/bakeoff", json={}).status_code == 400
    (tmp_path / "no-samples" / "clip1").mkdir(parents=True)
    r = env["c"].post("/api/lab/bakeoff", json={})
    assert r.status_code == 200 and "bakeoff" in env["launcher"].procs[-1][0].argv


def test_launcher_plist_keeps_studio_local(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/opt/homebrew/bin:/usr/bin:/bin")
    monkeypatch.setenv("SSL_CERT_FILE", "/Users/x/.mac-ca-bundle.pem")
    plist = server.install_launcher(9000, str(tmp_path / "projects"), home=tmp_path, load=False)
    data = plistlib.loads(plist.read_bytes())
    assert data["Label"] == "com.reel.studio" and data["KeepAlive"] and data["RunAtLoad"]
    assert data["ProgramArguments"][-4:] == ["--port", "9000", "--projects", str((tmp_path / "projects").resolve())]
    assert data["EnvironmentVariables"]["PATH"].startswith("/opt/homebrew/bin")  # launchd's bare PATH would lose claude/npx
    assert data["EnvironmentVariables"]["SSL_CERT_FILE"].endswith(".mac-ca-bundle.pem")
    assert data["WorkingDirectory"] == str(config.REPO_ROOT)
    assert "0.0.0.0" not in plist.read_text()
    assert server.uninstall_launcher(home=tmp_path, unload=False) and not plist.exists()
    assert not server.uninstall_launcher(home=tmp_path, unload=False)


# ------------------------------------------------------------------ kept adjustments


def test_a_revision_that_undoes_a_hand_setting_is_flagged(tmp_path):
    root = make_project(tmp_path)
    ws = Workspace(root)
    _story, fin = _plans(root)
    adjustments.log(ws, "look", "warm")
    adjustments.log(ws, "music_track", "none")
    fin = fin.model_copy(update={"grade": fin.grade.model_copy(update={"look": "warm"})})
    active = adjustments.active(ws, fin)
    assert active == {"look": "warm", "music_track": "none"}
    assert "Keep them exactly" in adjustments.prompt_lines(active)
    reverted = fin.model_copy(update={"grade": fin.grade.model_copy(update={"look": "cool"})})
    issues = adjustments.reverted(active, reverted, "make the captions bigger")
    assert [i.code for i in issues] == ["adjustment_reverted"] and issues[0].severity == "warning"
    assert adjustments.reverted(active, reverted, "make the colour warmer, less yellow") == []  # the request is about the look
    # an adjustment a later revision changed on purpose is no longer in force
    assert "look" not in adjustments.active(ws, reverted)


def test_a_rerun_finish_pass_is_told_the_hand_settings(tmp_path):
    from reel import decide
    from reel.claude_call import CallResult

    root = make_project(tmp_path)
    (root / "source" / "manifest.json").write_text(json.dumps({"project_fps": "30/1", "clips": [{"id": "c01", "probe": {"duration_s": 3.0}}]}))
    ws = Workspace(root)
    adjustments.log(ws, "music_track", "none")
    fin = json.loads((root / "plan" / "finish.json").read_text())
    prompts = []

    def fake(prompt, schema, **kw):
        prompts.append(prompt)
        return CallResult(data=fin, session_id="s", num_turns=1, cost_usd=0.0, usage={}, duration_s=0.0)

    decide.finish_pass(decide.load_inputs(ws), fake)
    assert "set these by hand" in prompts[0] and "music track" in prompts[0]
