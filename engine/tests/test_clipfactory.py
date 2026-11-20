"""G2.2 Clip Factory: miner checks, engine-side scoring and selection, reel projects that share the source."""

import json

import pytest

from reel import clipfactory, decide, mine
from reel.claude_call import CallResult
from reel.schemas.perception import Segment, SegmentTable, Word, WordTable
from reel.schemas.plan import StoryPlan
from reel.validate import errors
from reel.workspace import Workspace, atomic_write_json

WORDS_PER_SEG = 30
WORD_US = 500_000  # one word every 0.5 s → 15 s per segment
N_SEGS = 40  # 10 minutes


def _words() -> WordTable:
    ws = []
    for i in range(N_SEGS * WORDS_PER_SEG):
        text = f"w{i}" + ("." if i % WORDS_PER_SEG == WORDS_PER_SEG - 1 else "")
        if i == 300:  # segment 10 opens on a back-reference
            text = "So"
        ws.append(Word(i=i, clip="c01", text=text, start_us=i * WORD_US, end_us=i * WORD_US + 400_000))
    return WordTable(language="en", words=ws)


def _segments() -> SegmentTable:
    return SegmentTable(segments=[Segment(seg_id=f"s{n:03d}", clip="c01", word_start=n * WORDS_PER_SEG, word_end=n * WORDS_PER_SEG + WORDS_PER_SEG - 1,
                                          start_us=n * WORDS_PER_SEG * WORD_US, end_us=(n + 1) * WORDS_PER_SEG * WORD_US - 100_000)
                                  for n in range(N_SEGS)])


def _faces() -> dict:
    # the speaker is off camera from 450 s to 500 s (segments 30–33)
    return {"c01": {"samples": [{"t_us": t * 1_000_000, "faces": [] if 450 <= t < 500 else [{"x": 0.4, "y": 0.3, "w": 0.2, "h": 0.3}]}
                                for t in range(0, 600)], "presence": 0.9}}


def _seg_range(a: int, b: int) -> dict:
    """Ranges of whole segments a..b (inclusive)."""
    w = _words().by_index()
    lo, hi = a * WORDS_PER_SEG, b * WORDS_PER_SEG + WORDS_PER_SEG - 1
    return {"clip": "c01", "word_start": lo, "word_end": hi, "first_word": w[lo].text, "last_word": w[hi].text}


def _cand(cid, ranges, family="tip", **marks) -> dict:
    scores = {"hook": 4, "standalone": 4, "payoff": 4, "energy": 3, "shareability": 4} | marks
    return {"id": cid, "title": f"title {cid}", "hook_text": "hook", "ranges": ranges, "family": family, "scores": scores,
            "standalone_risks": [], "reason": "because"}


class FakeClaude:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, prompt, schema, **kw):
        self.calls.append({"prompt": prompt, **kw})
        return CallResult(data=self.responses.pop(0), session_id=f"s{len(self.calls)}", num_turns=1, cost_usd=0.02, usage={}, duration_s=0.0)


@pytest.fixture
def source(tmp_path):
    w = Workspace.create(tmp_path / "podcast")
    atomic_write_json(w.path("source", "manifest.json"), {"project_fps": "30/1", "clips": [{"id": "c01", "probe": {
        "duration_s": 600.0, "video": {"display_width": 1920, "display_height": 1080}}}]})
    atomic_write_json(w.path("perception", "words.json"), _words().model_dump(mode="json"))
    atomic_write_json(w.path("perception", "segments.json"), _segments().model_dump(mode="json"))
    atomic_write_json(w.path("perception", "faces.json"), _faces())
    w.path("mezz").mkdir(parents=True, exist_ok=True)
    w.path("mezz", "c01.mov").write_bytes(b"not really a movie")
    w.path("mezz", "c01.voice.wav").write_bytes(b"voice")
    w.path("tables").mkdir(parents=True, exist_ok=True)
    w.path("tables", "script.md").write_text("# Script\n\n## Clip c01\n\n" + "\n".join(f"[s{n:03d} …] text" for n in range(N_SEGS)) + "\n")
    w.path("tables", "summary.md").write_text("# Footage summary\n")
    atomic_write_json(w.path("run_options.json"), {"input": "/x/podcast.mp4", "language": "en", "brief": None})
    atomic_write_json(w.path("studio.json"), {"name": "Podcast ep 4", "client": "Acme"})
    return w


def _check(plan_dict, **kw):
    plan = mine.ClipCandidates.model_validate(plan_dict)
    return mine.validate_candidates(plan, _words(), _segments(), faces=_faces(), **kw)


def test_good_candidate_passes():
    issues = _check({"candidates": [_cand("c01", [_seg_range(2, 4)])]})  # 3 segments = 45 s
    assert not errors(issues), issues


@pytest.mark.parametrize("change, code", [
    (lambda r: r.update(word_start=r["word_start"] + 3, first_word="w63"), "mid_sentence_start"),
    (lambda r: r.update(word_end=r["word_end"] - 2, last_word="w147"), "ends_mid_thought"),
    (lambda r: r.update(first_word="banana"), "quote_mismatch"),
    (lambda r: r.update(word_end=99_999), "unknown_word"),
    (lambda r: r.update(clip="c09"), "unknown_clip"),
])
def test_range_checks(change, code):
    r = _seg_range(2, 4)
    change(r)
    assert code in {i.code for i in errors(_check({"candidates": [_cand("c01", [r])]}))}


def test_length_face_and_back_reference_checks():
    short = _check({"candidates": [_cand("c01", [_seg_range(2, 2)])]})  # 15 s < 20 s
    long_ = _check({"candidates": [_cand("c01", [_seg_range(2, 8)])]})  # 105 s > 75 s
    face = _check({"candidates": [_cand("c01", [_seg_range(30, 32)])]})  # speaker off camera
    ref = _check({"candidates": [_cand("c01", [_seg_range(10, 12)])]})  # opens on "So"
    assert "too_short" in {i.code for i in errors(short)} and "too_long" in {i.code for i in errors(long_)}
    assert "low_face" in {i.code for i in errors(face)}
    assert [i.code for i in ref] == ["opens_on_reference"] and not errors(ref)  # a warning, not an error
    marks = _check({"candidates": [_cand("c01", [_seg_range(2, 4)], hook=9)]})
    assert "out_of_range" in {i.code for i in errors(marks)}


def test_engine_scores_and_selects_with_overlap_family_and_yield_rules():
    plan = mine.ClipCandidates.model_validate({"candidates": [
        _cand("c01", [_seg_range(2, 4)], family="tip", hook=5, standalone=5),     # best
        _cand("c02", [_seg_range(3, 5)], family="story"),                         # overlaps c01 by 2/3 → rejected
        _cand("c03", [_seg_range(12, 14)], family="tip"),                          # second tip: family cap (cap 2 → 1 per family)
        _cand("c04", [_seg_range(20, 22)], family="story"),                        # kept
        _cand("c05", [_seg_range(25, 27)], family="proof", hook=1, standalone=1, payoff=1, shareability=1, energy=1),  # score 1 → rejected
    ]})
    rows = {r["id"]: r for r in mine.select(plan, 600.0, words=_words())}
    assert mine.yield_cap(600.0) == 2
    assert rows["c01"]["status"] == "selected" and rows["c01"]["rank"] == 1 and rows["c01"]["score"] == pytest.approx(49 / 11, abs=0.01)
    assert rows["c02"]["status"] == "rejected" and "better-ranked" in rows["c02"]["why"]
    assert rows["c03"]["status"] == "rejected" and "variety" in rows["c03"]["why"]
    assert rows["c04"]["status"] == "selected"
    assert rows["c05"]["status"] == "rejected" and "score" in rows["c05"]["why"]


def test_mine_pass_repairs_then_writes_the_board(source):
    bad = {"candidates": [_cand("c01", [dict(_seg_range(2, 4), first_word="nope")])]}
    good = {"candidates": [_cand("c01", [_seg_range(2, 4)]), _cand("c02", [_seg_range(10, 12)], family="story")]}
    fake = FakeClaude(bad, good)
    meta = mine.mine_pass(source, {}, fake)
    assert meta["calls"] == 2 and meta["candidates"] == 2 and "quote_mismatch" in fake.calls[1]["prompt"]
    data = mine.load(source)
    assert data["yield_cap"] == 2 and data["target_s"] == [20.0, 75.0]
    c02 = next(r for r in data["candidates"] if r["id"] == "c02")
    assert any("opens_on_reference" in w for w in c02["warnings"])
    board = source.path("mine", "board.md").read_text()
    assert "Editor's estimate" in board and "viral" not in board.lower()


def test_long_sources_are_mined_in_overlapping_chunks():
    assert mine.chunks(None, 600.0) == [(0.0, 600.0)]
    ch = mine.chunks(None, 3600.0)
    assert ch[0] == (0.0, 900.0) and ch[1][0] == 840.0 and ch[-1][1] == 3600.0


def _mined(source, *cands):
    fake = FakeClaude({"candidates": list(cands)})
    mine.mine_pass(source, {}, fake)


def test_spawn_shares_files_by_hard_link_and_windows_the_tables(source):
    _mined(source, _cand("c01", [_seg_range(2, 4)]))
    (child_root,) = clipfactory.spawn(source, ["c01"], make_sheets=False)
    child = Workspace(child_root)
    src_mezz, child_mezz = source.path("mezz", "c01.mov"), child.path("mezz", "c01.mov")
    assert not child_mezz.is_symlink() and child_mezz.stat().st_ino == src_mezz.stat().st_ino  # a hard link
    assert child.path("mezz", "c01.voice.wav").exists()
    window = clipfactory.load_window(child)
    # candidate 30–75 s; 20 s either side is 10–95 s, widened to the whole segments it touches: s000–s006
    assert window == [("c01", 0, 209)]
    tsv = child.path("tables", "words.tsv").read_text().splitlines()[1:]
    idx = [int(line.split("\t")[0]) for line in tsv]
    assert idx[0] == 0 and idx[-1] == 209  # global indices kept
    script = child.path("tables", "script.md").read_text()
    assert "[s006" in script and "[s007" not in script
    brief = json.loads(child.path("brief.json").read_text())
    assert brief["target_length_s"] == [20.0, 75.0] and "Clip Factory reel" in brief["notes"]
    meta = json.loads(child.path("studio.json").read_text())
    assert meta["parent"] == "podcast" and meta["client"] == "Acme" and meta["name"] == "title c01"
    assert json.loads(child.path("run_options.json").read_text())["candidate"] == "c01"
    picks = source.path("mine", "picks.jsonl").read_text().splitlines()
    assert json.loads(picks[-1])["picked"] == ["c01"]
    # deleting the source leaves the reel project's media in place
    src_mezz.unlink()
    assert child_mezz.read_bytes() == b"not really a movie"


def test_the_window_holds_in_every_story_path(source):
    _mined(source, _cand("c01", [_seg_range(2, 4)]))
    (child_root,) = clipfactory.spawn(source, ["c01"], make_sheets=False)
    (child_root / "mezz" / "c01.mov").unlink()  # the fixture's mezzanine isn't a real movie; clip lengths come from the manifest
    inp = decide.load_inputs(Workspace(child_root))
    assert inp.source_s == pytest.approx(104.9, abs=0.2)  # the window's speech (s000–s006), not the 600 s recording
    inside = StoryPlan.model_validate({"genre": "genre.tutorial", "summary": "s", "hook_options": [{"id": "h1", "item": "k01", "rank": 1, "reason": "r"}],
                                       "hook": "h1", "items": [{"id": "k01", "clip": "c01", "word_start": 60, "word_end": 89, "first_word": "w60",
                                                                "last_word": "w89.", "beat": "hook", "reason": "r"}], "knowledge_used": []})
    assert not errors(inp.story_issues(inside))
    outside = inside.model_copy(update={"items": [inside.items[0].model_copy(update={"word_start": 600, "word_end": 629, "first_word": "w600",
                                                                                      "last_word": "w629."})]})
    assert "outside_window" in {i.code for i in errors(inp.story_issues(outside))}
    # a chat revision that moves the reel outside its window is refused too (decide.revise checks through Inputs)
    from reel.schemas.plan import Revision, StoryPatch, StoryPatchOp

    atomic_write_json(child_root / "plan" / "story.json", inside.model_dump(mode="json"))
    rev = Revision.model_construct(story_patch=StoryPatch(request="use the bit at 5 min", reason="r",
                                                          ops=[StoryPatchOp(op="replace", target="k01", after="", item=outside.items[0])]),
                                   finish=None, reply="")
    new_story, _ = decide._patched(inside, rev)
    assert "outside_window" in {i.code for i in errors(inp.story_issues(new_story))}
    # an ordinary project has no window and keeps its whole footage
    source.path("mezz", "c01.mov").unlink()
    assert decide.load_inputs(source).window is None


def test_reel_projects_never_run_the_analysis_stages():
    from reel.stages import CLIP_PIPELINE, MINE_PIPELINE, PIPELINE

    names = [s.name for s in CLIP_PIPELINE]
    assert not {s.name for s in PIPELINE} & set(names) and names[0] == "stock" and "story" in names
    assert [s.name for s in MINE_PIPELINE][-1] == "mine"


def test_unknown_candidate_and_unmined_source_are_refused(source):
    with pytest.raises(ValueError, match="no candidates"):
        clipfactory.spawn(source, ["c01"])
    _mined(source, _cand("c01", [_seg_range(2, 4)]))
    with pytest.raises(ValueError, match="unknown candidate"):
        clipfactory.spawn(source, ["c09"])


def test_batch_style_anchor_is_fixed_once(source):
    _mined(source, _cand("c01", [_seg_range(2, 4)]), _cand("c02", [_seg_range(20, 22)], family="story"))
    a, b = (Workspace(p) for p in clipfactory.spawn(source, ["c01", "c02"], make_sheets=False))
    assert clipfactory.batch_style(a) is None  # nobody finished yet
    atomic_write_json(a.path("plan", "finish.json"), {"captions": {"family": "bold_pop"}, "grade": {"look": "warm"}})
    clipfactory.record_batch_style(a)
    atomic_write_json(b.path("plan", "finish.json"), {"captions": {"family": "clean"}, "grade": {"look": "cool"}})
    clipfactory.record_batch_style(b)  # the anchor is already set: no change
    assert clipfactory.batch_style(b) == {"from": a.root.name, "caption_family": "bold_pop", "look": "warm"}
    assert clipfactory.batch_style(a) is None  # the anchor doesn't follow itself
    assert clipfactory.batch_style(source) is None  # not a reel project
