import json
from fractions import Fraction

import pytest

from reel import assets
from reel.compile import ClipInfo, compile_timeline, dry_run
from reel.schemas.perception import Word, WordTable
from reel.schemas.plan import (
    CaptionPlan, Ease, FinishPlan, GradePlan, HookOption, HookTitle, KeepItem, MusicPlan, PatchOpKind, PunchIn, SfxAnchor, SfxCue,
    Speed, StoryPatch, StoryPatchOp, StoryPlan, Token,
)
from reel.schemas.timeline import field_owners
from reel.validate import apply_story_patch, errors, validate_finish, validate_story

FPS = Fraction(30)
TEXT1 = "so guys today i will tell you the one trick to save money every month without fail okay".split()
TEXT2 = "put ten percent into a separate account on salary day and never touch it ever".split()


def _words():
    ws, i = [], 0
    for clip, text in (("c01", TEXT1), ("c02", TEXT2)):
        t = 500_000
        for tok in text:
            ws.append(Word(i=i, clip=clip, text=tok, start_us=t, end_us=t + 300_000))
            t += 400_000
            i += 1
    return WordTable(words=ws)


WORDS = _words()
CLIPS = {"c01": ClipInfo("c01", "mezz/c01.mov", 10_000_000), "c02": ClipInfo("c02", "mezz/c02.mov", 10_000_000)}
IDX = assets.load()
IDX.sfx["whoosh_01"] = {"id": "whoosh_01", "file": "assets/sfx/whoosh_01.wav", "duration_ms": 600, "peak_ms": 300}
IDX.music["bed_01"] = {"id": "bed_01", "file": "assets/music/bed_01.wav", "duration_ms": 60_000}


def _item(id_, clip, a, b, beat="point"):
    by = WORDS.by_index()
    return KeepItem(id=id_, clip=clip, word_start=a, word_end=b, first_word=by[a].text, last_word=by[b].text, beat=beat, reason="r")


def _story(items=None, hook_item="k01"):
    items = items or [_item("k01", "c01", 7, 13, "hook"), _item("k02", "c02", 18, 27), _item("k03", "c01", 0, 4, "setup")]
    return StoryPlan(genre="genre.talking_head", summary="s", hook_options=[HookOption(id="h1", item=hook_item, rank=1, reason="r")],
                     hook="h1", items=items, knowledge_used=[])


def _finish(**kw):
    base = dict(
        hook_title=HookTitle(text="", style="card", reason="r"),
        grade=GradePlan(look="clean", strength=0.4, reason="r"),
        punch_ins=[PunchIn(id="p01", item="k01", at_word=10, scale=1.2, ramp_frames=0, ease=Ease.hold, reason="r")],
        speeds=[], transitions=[],
        captions=CaptionPlan(family="bold_pop", tokens=[Token(key="emph_color", value="#00FF00")], emphasis_words=[9], script="latin", reason="r"),
        sfx=[SfxCue(id="s01", sfx="whoosh_01", anchor=SfxAnchor.cut_after_item, item="k01", word=-1, gain_db=-12, reason="r")],
        music=MusicPlan(track="bed_01", gain_db=-18, duck_db=12, reason="r"),
        broll=[], knowledge_used=[],
    )
    base.update(kw)
    return FinishPlan(**base)


def test_valid_plan_compiles_frame_exact():
    story, fin = _story(), _finish()
    assert not errors(validate_story(story, WORDS, set(CLIPS)))
    assert not errors(validate_finish(fin, story, WORDS, IDX))
    tl = compile_timeline(story, fin, WORDS, CLIPS, FPS, IDX)
    base = [c for c in tl.video if c.id.startswith("v_")]
    assert [c.src.item for c in base] == ["k01", "k02", "k03"]
    assert base[0].at_f == 0
    for a, b in zip(base, base[1:]):
        assert a.at_f + a.dur_f == b.at_f  # contiguous
    assert tl.duration_f == sum(c.dur_f for c in base)
    # source range covers the words, within the breath pad
    by = WORDS.by_index()
    assert base[0].src_in_us <= by[7].start_us and base[0].src_out_us >= by[13].end_us
    assert tl.plan_ref["story"] and tl.plan_ref["finish"]


def test_punch_in_keyframes_are_clip_relative():
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    v = next(c for c in tl.video if c.id == "v_k01")
    assert v.scale[0].f == 0 and v.scale[0].v == 1.0
    k = v.scale[-1]
    assert k.v == 1.2 and 0 < k.f < v.dur_f


def test_sfx_peak_aligned_to_cut():
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    cut = next(c for c in tl.video if c.id == "v_k01")
    sfx = next(a for a in tl.audio if a.role == "sfx")
    assert sfx.at_f == cut.at_f + cut.dur_f - 9  # 300 ms peak = 9 frames at 30 fps


def test_captions_ordered_non_overlapping_and_emphasis():
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    pages = tl.captions.pages
    assert all(len(p.words) <= 3 for p in pages)  # bold_pop max_words
    for a, b in zip(pages, pages[1:]):
        assert a.end_f <= b.start_f
    assert any(w.emph for p in pages for w in p.words if w.i == 9)
    assert tl.captions.tokens["emph_color"] == "#00FF00"


def test_music_and_ducking():
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    music = next(a for a in tl.audio if a.role == "music")
    assert music.dur_f == tl.duration_f and tl.ducking[0].depth_db == 12


def test_quote_mismatch_suggests_fix():
    bad = _item("k01", "c01", 7, 13, "hook").model_copy(update={"first_word": "trick"})
    issues = validate_story(_story([bad]), WORDS, set(CLIPS))
    q = next(i for i in issues if i.code == "quote_mismatch")
    assert "index 9" in q.fix  # 'trick' is word 9


def test_story_rules():
    codes = lambda s: {i.code for i in validate_story(s, WORDS, set(CLIPS))}  # noqa: E731
    assert "hook_not_first" in codes(_story(hook_item="k02"))
    overlap = [_item("k01", "c01", 7, 13), _item("k02", "c01", 12, 15)]
    assert "overlap" in codes(_story(overlap))
    assert "unknown_clip" in codes(_story([_item("k01", "c01", 0, 2).model_copy(update={"clip": "c09"})]))
    assert "word_clip_mismatch" in codes(_story([_item("k01", "c01", 0, 2).model_copy(update={"clip": "c02"})]))


def test_finish_rules():
    story = _story()
    issues = validate_finish(_finish(
        punch_ins=[PunchIn(id="p01", item="k01", at_word=3, scale=2.5, ramp_frames=0, ease=Ease.hold, reason="r")],
        speeds=[Speed(id="sp1", item="k02", rate=0.5, reason="r")],
        sfx=[SfxCue(id="s01", sfx="nope", anchor=SfxAnchor.word, item="k01", word=99, gain_db=5, reason="r")],
        captions=CaptionPlan(family="bold_pop", tokens=[Token(key="font_size", value="9")], emphasis_words=[30], script="klingon", reason="r"),
    ), story, WORDS, IDX)
    codes = {i.code for i in issues}
    assert {"out_of_range", "word_outside_item", "speed_on_speech", "unknown_sfx", "unknown_token", "emphasis_not_kept", "bad_script"} <= codes
    assert all(i.fix for i in issues)


def test_patch_ops_leave_other_items_identical():
    story = _story()
    new = _item("k02", "c02", 18, 22)
    patch = StoryPatch(request="shorter", reason="r", ops=[
        StoryPatchOp(op=PatchOpKind.replace, target="k02", after="", item=new),
        StoryPatchOp(op=PatchOpKind.insert, target="", after="k03", item=_item("k04", "c02", 28, 31)),
        StoryPatchOp(op=PatchOpKind.delete, target="k03", after="", item=None),
    ])
    out, issues = apply_story_patch(story, patch)
    assert not issues
    assert [i.id for i in out.items] == ["k01", "k02", "k04"]
    assert out.items[0] == story.items[0]  # untouched item identical
    assert out.items[1].word_end == 22
    _, bad = apply_story_patch(story, StoryPatch(request="x", reason="r", ops=[StoryPatchOp(op=PatchOpKind.delete, target="zz", after="", item=None)]))
    assert bad and bad[0].code == "unknown_item"


def test_dry_run_readback():
    text = dry_run(_story(), WORDS, CLIPS, FPS, IDX)
    assert "k01 (hook): the one trick" in text and "TOTAL" in text and "cuts/min" in text


@pytest.mark.parametrize("model", [StoryPlan, FinishPlan, StoryPatch])
def test_claude_schemas_fit_structured_outputs(model):
    schema = json.dumps(model.model_json_schema())
    assert '"minimum"' not in schema and '"maximum"' not in schema
    assert '"additionalProperties": true' not in schema

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, node.get("title")
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(model.model_json_schema())

    # what Claude receives: every property required (a revision must restate graphics, effects, holds …)
    from reel import decide

    def req(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert set(node.get("required", [])) == set(node["properties"]), node.get("title")
            for v in node.values():
                req(v)
        elif isinstance(node, list):
            for v in node:
                req(v)

    req(decide.schema(model))


def test_every_timeline_field_has_one_owner():
    owners = field_owners()
    assert owners["video[].at_f"] == "ffmpeg"
    assert owners["captions[].pages"] == "remotion"
    assert set(owners.values()) <= {"ffmpeg", "remotion", "engine"}


def _paused_words(gap_us=1_200_000, after=10):
    """TEXT1 with a long pause after word `after` (inside item k01 = words 7–13)."""
    ws = []
    for w in WORDS.words:
        shift = gap_us if w.clip == "c01" and w.i > after else 0
        ws.append(w.model_copy(update={"start_us": w.start_us + shift, "end_us": w.end_us + shift}))
    return WordTable(words=ws)


def test_long_pause_inside_a_line_becomes_a_jump_cut():
    from reel.compile import proof_list

    words = _paused_words()
    story = _story()
    clips = {**CLIPS, "c01": ClipInfo("c01", "mezz/c01.mov", 12_000_000)}
    tl = compile_timeline(story, _finish(), words, clips, FPS, IDX)
    k01 = [c for c in tl.video if c.src.item == "k01"]
    assert [c.id for c in k01] == ["v_k01", "v_k01.2"]
    assert k01[0].src.words == [7, 10] and k01[1].src.words == [11, 13]
    assert {a.id for a in tl.audio if a.role == "voice"} >= {"a_k01", "a_k01.2"}
    # the 1.2 s pause is gone: output is far shorter than keeping the pause would be
    kept = compile_timeline(story.model_copy(update={"max_pause_ms": 0}), _finish(), words, clips, FPS, IDX)
    assert len([c for c in kept.video if c.src.item == "k01"]) == 1
    assert kept.duration_f - tl.duration_f >= 30  # ≥ 1 s removed at 30 fps
    # punch-in at word 10 is in shot 1; it holds through shot 2
    assert k01[0].scale[-1].v == 1.2 and k01[1].scale and k01[1].scale[0].v == 1.2
    # SFX after k01 lands on the end of its last shot
    sfx = next(a for a in tl.audio if a.role == "sfx")
    assert sfx.at_f == k01[1].at_f + k01[1].dur_f - 9
    # read-back reports it; proof list still finds every word's shot
    assert "1 pause(s) cut" in dry_run(story, words, clips, FPS, IDX)
    assert isinstance(proof_list(tl, story, words), list)


def test_max_pause_range_is_validated():
    bad = _story().model_copy(update={"max_pause_ms": 100})
    assert any(i.code == "out_of_range" for i in validate_story(bad, WORDS, set(CLIPS)))
    assert not errors(validate_story(_story().model_copy(update={"max_pause_ms": 0}), WORDS, set(CLIPS)))


def test_holds_and_pulses_compile_and_validate():
    from reel.schemas.plan import Hold

    fin = _finish(holds=[Hold(id="h1", item="k01", frames=12, reason="r")], beat_pulse=0.04)
    assert not errors(validate_finish(fin, _story(), WORDS, IDX))
    base = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    tl = compile_timeline(_story(), fin, WORDS, CLIPS, FPS, IDX)
    assert tl.duration_f == base.duration_f + 12
    k01 = next(c for c in tl.video if c.id == "v_k01")
    assert k01.hold_f == 12
    later = [c for c in tl.video if c.src.item == "k02"][0]
    assert later.at_f == next(c for c in base.video if c.src.item == "k02").at_f + 12  # everything after shifts
    bad = _finish(holds=[Hold(id="h1", item="k01", frames=90, reason="r")], beat_pulse=0.04, music=_finish().music.model_copy(update={"track": "none"}))
    codes = {i.code for i in validate_finish(bad, _story(), WORDS, IDX)}
    assert {"out_of_range", "pulse_without_music"} <= codes


def test_a_new_punch_cuts_a_running_ramp_short():
    fin = _finish(punch_ins=[PunchIn(id="p1", item="k01", at_word=8, scale=1.2, ramp_frames=30, ease=Ease.linear, reason="r"),
                             PunchIn(id="p2", item="k01", at_word=9, scale=1.4, ramp_frames=0, ease=Ease.hold, reason="r")])
    v = next(c for c in compile_timeline(_story(), fin, WORDS, CLIPS, FPS, IDX).video if c.id == "v_k01")
    fs = [k.f for k in v.scale]
    assert fs == sorted(fs)  # keyframes in time order
    assert v.scale[-1].v == 1.4  # the later punch wins and holds
    mid = v.scale[-2]
    assert 1.0 < mid.v < 1.2  # the first ramp stopped part-way, where the second punch began


def test_silence_hidden_inside_a_smeared_word_is_cut():
    from reel.compile import split_on_silence

    ws = [Word(i=0, clip="c", text="i", start_us=0, end_us=800_000), Word(i=1, clip="c", text="thought", start_us=800_000, end_us=1_000_000)]
    speech = [[0, 150_000], [700_000, 1_000_000]]  # VAD: "I" ends at 0.15 s; the ASR stretched it to 0.8 s
    parts = split_on_silence(0, 1_100_000, ws, speech, 400_000)
    assert len(parts) == 2 and [w.i for w in parts[0][2]] == [0] and [w.i for w in parts[1][2]] == [1]
    assert parts[0][1] == 150_000 + 100_000 and parts[1][0] == 700_000 - 100_000  # cut inside the silence, breath kept
    assert len(split_on_silence(0, 1_100_000, ws, speech, 0)) == 1  # max_pause 0 keeps every pause


def test_shot_edges_snap_off_nearby_camera_cuts():
    from reel.compile import snap_off_camera_cuts

    ws = [Word(i=0, clip="c", text="hello", start_us=1_000_000, end_us=1_400_000)]
    # cut 2 frames after the shot starts, before the first word: start on the cut (no stray frame of the old angle)
    assert snap_off_camera_cuts(900_000, 1_500_000, ws, [960_000])[0] == 960_000
    # cut just before the end, after the last word: end on the cut
    assert snap_off_camera_cuts(900_000, 1_500_000, ws, [1_450_000])[1] == 1_450_000
    # cut inside the word near the start: keep ≥ 0.25 s of the old angle instead, never past the previous word
    start, _ = snap_off_camera_cuts(1_000_000, 1_500_000, ws, [1_100_000], lo_us=950_000)
    assert start == 950_000


def test_captions_do_not_capitalise_a_line_that_continues_a_sentence():
    from reel.compile import clean_caption_words

    w = [Word(i=0, clip="c", text="we", start_us=0, end_us=1), Word(i=1, clip="c", text="drink", start_us=1, end_us=2)]
    assert clean_caption_words(w, prev_text="and then")[0].text == "we"
    assert clean_caption_words(w, prev_text="it works.")[0].text == "We"
    assert clean_caption_words(w)[0].text == "We"  # the reel's first line
