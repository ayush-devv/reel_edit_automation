"""Build step 5: Editor decision loop (fake Claude), base renderer (real ffmpeg), opt-in live run."""

import json
import os
import shutil
import subprocess
from fractions import Fraction

import pytest

from reel import claude_call, config, decide, render
from reel import timebase as tb
from reel.claude_call import CallResult
from reel.conformance import checks, corpus
from reel.mezzanine import make_mezzanine
from reel.probe import probe
from reel.schemas.plan import FinishPlan, StoryPlan, TransitionType
from reel.schemas.timeline import Asset, AssetKind, AudioClip, Keyframe, Provenance, Timeline, VideoClip
from reel.workspace import Workspace, atomic_write_json

from test_plan_compile import WORDS, _finish, _item, _story


class FakeClaude:
    """Returns queued structured outputs; records every call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, prompt, schema, **kw):
        self.calls.append({"prompt": prompt, **kw})
        data = self.responses.pop(0)
        return CallResult(data=data, session_id=f"s{len(self.calls)}", num_turns=1, cost_usd=0.01, usage={}, duration_s=0.0)


@pytest.fixture
def ws(tmp_path):
    w = Workspace.create(tmp_path / "proj")
    atomic_write_json(w.path("source", "manifest.json"), {"project_fps": "30/1", "clips": [
        {"id": "c01", "probe": {"duration_s": 10.0}}, {"id": "c02", "probe": {"duration_s": 10.0}}]})
    atomic_write_json(w.path("perception", "words.json"), WORDS.model_dump(mode="json"))
    return w


def _plain_finish(**kw) -> dict:
    return _finish(sfx=[], music=_finish().music.model_copy(update={"track": "none"}), **kw).model_dump(mode="json")


def test_story_pass_valid_writes_plan_and_session(ws):
    good = _story().model_dump(mode="json")
    fake = FakeClaude(good, good)
    meta = decide.story_pass(decide.load_inputs(ws), fake)
    assert meta["calls"] == 2 and not meta["changed_on_readback"]
    assert fake.calls[1]["resume"] == "s1" and "read-back" in fake.calls[1]["prompt"]
    assert StoryPlan.model_validate_json(ws.path("plan", "story.json").read_text()) == _story()
    assert "TOTAL" in ws.path("plan", "story_readback.txt").read_text()
    assert json.loads(ws.path("plan", "sessions.json").read_text())["story"] == "s2"
    pack = ws.path("context", "brief_and_knowledge.md").read_text()
    assert "Core principles" in pack and "Source footage: 20.0 s" in pack


def test_invalid_plan_is_fixed_on_the_same_session(ws):
    bad = _story().model_dump(mode="json")
    bad["items"][0]["first_word"] = "banana"
    good = _story().model_dump(mode="json")
    fake = FakeClaude(bad, good, good)
    meta = decide.story_pass(decide.load_inputs(ws), fake)
    assert meta["calls"] == 3
    fix = fake.calls[1]
    assert fix["resume"] == "s1" and "quote_mismatch" in fix["prompt"] and "fix" in fix["prompt"]


def test_gives_up_after_max_retries(ws):
    bad = _story().model_dump(mode="json")
    bad["hook"] = "nope"
    fake = FakeClaude(*[bad] * (decide.MAX_RETRIES + 1))
    with pytest.raises(decide.DecisionError):
        decide.story_pass(decide.load_inputs(ws), fake)
    assert len(fake.calls) == decide.MAX_RETRIES + 1
    assert json.loads(ws.path("plan", "story_issues.json").read_text())["issues"][0]["code"] == "unknown_hook"


def test_schema_violation_becomes_an_issue(ws):
    broken = _story().model_dump(mode="json")
    del broken["summary"]
    good = _story().model_dump(mode="json")
    fake = FakeClaude(broken, good, good)
    decide.story_pass(decide.load_inputs(ws), fake)
    assert "schema" in fake.calls[1]["prompt"]


def test_finish_accepts_renderable_transitions_and_rejects_bad_looks(ws):
    atomic_write_json(ws.path("plan", "story.json"), _story().model_dump(mode="json"))
    whip = _plain_finish(transitions=[{"id": "t01", "after_item": "k01", "type": TransitionType.whip, "frames": 6, "reason": "r"}])
    bad_look = dict(whip, grade={"look": "sepia_dream", "strength": 0.5, "reason": "r"})
    fake = FakeClaude(bad_look, whip)
    meta = decide.finish_pass(decide.load_inputs(ws), fake)
    assert "unknown_look" in fake.calls[1]["prompt"] and meta["calls"] == 2
    fin = FinishPlan.model_validate_json(ws.path("plan", "finish.json").read_text())
    assert [t.type for t in fin.transitions] == [TransitionType.whip]
    ctx = ws.path("context", "finish_context.md").read_text()
    assert "SFX library" in ctx and "teal_orange" in ctx


def test_revision_applies_patch_and_keeps_history(ws):
    atomic_write_json(ws.path("plan", "story.json"), _story().model_dump(mode="json"))
    atomic_write_json(ws.path("plan", "finish.json"), _plain_finish())
    atomic_write_json(ws.path("plan", "sessions.json"), {"finish": "fin-1"})
    rev = {"story_patch": {"request": "drop the intro", "ops": [{"op": "delete", "target": "k03", "after": "", "item": None}], "reason": "r"},
           "finish": _plain_finish(), "reply": "Removed the intro line."}
    fake = FakeClaude(rev)
    res = decide.revise(decide.load_inputs(ws), "drop the intro", fake)
    assert fake.calls[0]["resume"] == "fin-1" and "drop the intro" in fake.calls[0]["prompt"]
    assert res["reply"] == "Removed the intro line."
    assert [i.id for i in StoryPlan.model_validate_json(ws.path("plan", "story.json").read_text()).items] == ["k01", "k02"]
    assert ws.path("plan", "history", "001_story.json").exists() and ws.path("plan", "history", "001_request.json").exists()


def test_effective_target_never_exceeds_footage():
    from reel.brief import Brief

    assert decide.effective_target(Brief(project="x"), 13.1) == (6.5, 13.1)
    assert decide.effective_target(Brief(project="x", target_length_s=(20, 45)), 90.0) == (20, 45)


def test_renderer_rejects_unsupported_features():
    tl = Timeline(fps="30/1", width=1080, height=1920, duration_f=30, assets={},
                  video=[VideoClip(id="v_k01", asset="c01", at_f=0, dur_f=30, src_in_us=0, src_out_us=1_000_000, x=[Keyframe(f=0, v=0.1)], src=Provenance(item="k01", words=[0, 1]))],
                  audio=[])
    with pytest.raises(render.RenderError, match="pans render"):
        render.build_command(tl, config.REPO_ROOT, config.REPO_ROOT / "x.mp4")


def test_scale_expression_shape():
    from reel.schemas.plan import Ease

    e = render.scale_expr([Keyframe(f=0, v=1.0, ease=Ease.hold), Keyframe(f=10, v=1.2, ease=Ease.hold)])
    assert e == "if(lt(on,0),1,if(lt(on,10),1,1.2))"
    ramp = render.scale_expr([Keyframe(f=0, v=1.0), Keyframe(f=10, v=1.0, ease=Ease.linear), Keyframe(f=20, v=1.5, ease=Ease.linear)])
    assert "(on-10)/10" in ramp and ramp.endswith("1.5)))")


def test_claude_command_is_stripped_and_read_only(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        out = {"is_error": False, "session_id": "abc", "structured_output": {"ok": True}, "total_cost_usd": 0.01, "permission_denials": []}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out), stderr="")

    monkeypatch.setattr(claude_call.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_call, "claude_version", lambda: "test")
    monkeypatch.setattr(claude_call.subprocess, "run", fake_run)
    res = claude_call.call("p", {"type": "object"}, cwd=tmp_path, log_file=tmp_path / "runs.jsonl", label="t")
    cmd = seen["cmd"]
    assert res.data == {"ok": True}
    for flag in ("--safe-mode", "--strict-mcp-config", "--disable-slash-commands", "--exclude-dynamic-system-prompt-sections"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == "Read" and cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert json.loads((tmp_path / "runs.jsonl").read_text())["session_id"] == "abc"


# ------------------------------------------------------------------ real ffmpeg

try:
    config.ffmpeg_path()
    HAVE_FFMPEG = True
except config.ToolNotFound:
    HAVE_FFMPEG = False


@pytest.mark.integration
@pytest.mark.skipif(not HAVE_FFMPEG, reason="pinned ffmpeg (ffmpeg-full) not installed")
def test_render_keeps_sync_across_cuts_and_punch_ins(tmp_path):
    """Corpus clip with flash + beep at 2.0 s: put it after a cut and under a punch-in; A/V must stay locked."""
    src = corpus.build(tmp_path / "src", ["cfr25_portrait"])[0]
    p = probe(src)
    fps = Fraction(25)
    mezz = tmp_path / "mezz" / "c01.mov"
    mezz.parent.mkdir()
    make_mezzanine(p, mezz, fps)
    first = (0, 30)    # 0.0–1.2 s
    second = (25, 75)  # 1.0–3.0 s, contains the flash at 2.0 s
    segs = tb.layout_segments([first[1] - first[0], second[1] - second[0]])
    video, audio = [], []
    for k, ((a, b), seg) in enumerate(zip((first, second), segs)):
        prov = Provenance(item=f"k{k}", words=[0, 0])
        scale = [Keyframe(f=0, v=1.0), Keyframe(f=10, v=1.3)] if k == 1 else []
        video.append(VideoClip(id=f"v_k{k}", asset="c01", at_f=seg.out_start, dur_f=seg.out_frames, src_in_us=tb.frame_to_us(a, fps),
                               src_out_us=tb.frame_to_us(b, fps), scale=scale, src=prov))
        audio.append(AudioClip(id=f"a_k{k}", asset="c01", at_f=seg.out_start, dur_f=seg.out_frames, src_in_us=tb.frame_to_us(a, fps), role="voice", src=prov))
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=segs[-1].out_end,
                  assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")}, video=video, audio=audio)
    out = tmp_path / "render" / "base.mp4"
    meta = render.render_base(tl, tmp_path, out)
    assert meta["frames"] == 80 and meta["size"] == "1080x1920"
    flash, beep = checks.flash_time(out), checks.beep_time(out)
    assert flash == pytest.approx(1.2 + 1.0, abs=1 / 25)  # 30 frames of the first cut + 1.0 s into the second
    assert abs(checks.av_offset_ms(out)) <= 1000 / 25, (flash, beep)


# ------------------------------------------------------------------ live Claude (opt-in, costs money)


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("REEL_LIVE_CLAUDE") != "1" or not shutil.which("claude"), reason="set REEL_LIVE_CLAUDE=1 to call Claude")
def test_live_edit_end_to_end(tmp_path):
    from test_perception_integration import SCRIPT  # noqa: F401  (same synthetic speech)

    from reel import tools
    from reel.runner import run_pipeline
    from reel.stages import EDIT_PIPELINE

    aiff = tmp_path / "voice.aiff"
    subprocess.run(["say", "-o", str(aiff), SCRIPT], check=True)
    clip = tmp_path / "talk.mp4"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30", "-i", str(aiff), "-shortest",
                  "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)])
    ws = Workspace.create(tmp_path / "proj")
    state = run_pipeline(ws, EDIT_PIPELINE, options={"input": str(clip), "language": "en"})
    assert state["stages"]["render"]["status"] == "done"
    runs = [json.loads(line) for line in ws.path("log", "runs.jsonl").read_text().splitlines()]
    assert runs and all(not r["permission_denials"] for r in runs)
    assert ws.path("export", "reel.mp4").exists()


def test_resumed_call_cost_is_the_delta_not_the_session_total(monkeypatch, tmp_path):
    totals = iter([0.10, 0.13])

    def fake_run(cmd, **kw):
        out = {"is_error": False, "session_id": "abc", "structured_output": {}, "total_cost_usd": next(totals), "permission_denials": []}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out), stderr="")

    monkeypatch.setattr(claude_call.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_call, "claude_version", lambda: "test")
    monkeypatch.setattr(claude_call.subprocess, "run", fake_run)
    log = tmp_path / "runs.jsonl"
    first = claude_call.call("p", {}, cwd=tmp_path, log_file=log, label="a")
    second = claude_call.call("fix", {}, cwd=tmp_path, log_file=log, label="a:fix1", resume="abc", meta={"fixing": ["quote_mismatch@items[0]"]})
    assert first.cost_usd == pytest.approx(0.10) and second.cost_usd == pytest.approx(0.03)
    assert json.loads(log.read_text().splitlines()[1])["fixing"] == ["quote_mismatch@items[0]"]


def test_readback_change_ignores_reworded_reasons():
    a = _story()
    b = a.model_copy(update={"summary": "reworded"})
    assert decide.cut_signature(a) == decide.cut_signature(b)
    assert decide.cut_signature(a) != decide.cut_signature(_story(items=list(reversed(a.items)), hook_item="k03"))


def test_revision_that_reorders_the_opening_moves_the_hook(ws):
    atomic_write_json(ws.path("plan", "story.json"), _story().model_dump(mode="json"))
    atomic_write_json(ws.path("plan", "finish.json"), _plain_finish())
    k2 = _story().items[1].model_dump(mode="json")
    rev = {"story_patch": {"request": "open with the tip", "reason": "r", "ops": [
        {"op": "delete", "target": "k02", "after": "", "item": None},
        {"op": "insert", "target": "", "after": "^", "item": k2}]}, "finish": _plain_finish(), "reply": "Tip first."}
    fake = FakeClaude(rev)
    decide.revise(decide.load_inputs(ws), "open with the tip", fake)
    story = StoryPlan.model_validate_json(ws.path("plan", "story.json").read_text())
    assert len(fake.calls) == 1 and story.items[0].id == "k02"
    assert next(h for h in story.hook_options if h.id == story.hook).item == "k02"
