"""Cover frame: scoring (sharp, eyes open, larger face wins), spacing, candidates, title, cover.jpg."""

import json

import numpy as np
import pytest

from reel import config, cover, package, tools
from reel.compile import compile_timeline
from reel.schemas.plan import HookTitle
from reel.workspace import Workspace

from test_plan_compile import CLIPS, FPS, IDX, WORDS, _finish, _story

RNG = np.random.default_rng(7)
SHARP = RNG.integers(0, 256, (480, 270, 3), dtype=np.uint8)  # full of detail
BLURRED = np.full((480, 270, 3), 128, np.uint8) + np.linspace(0, 40, 270, dtype=np.uint8)[None, :, None]  # no detail at all

OPEN = {"eyeBlinkLeft": 0.05, "eyeBlinkRight": 0.08, "mouthSmileLeft": 0.3, "mouthSmileRight": 0.3}
CLOSED = {**OPEN, "eyeBlinkLeft": 0.8, "eyeBlinkRight": 0.75}
LARGE = {"x": 0.3, "y": 0.15, "w": 0.4, "h": 0.3}  # 12 % of the frame
SMALL = {"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.15}  # 3 %
TINY = {"x": 0.45, "y": 0.2, "w": 0.05, "h": 0.1}  # 0.5 %: not a face for a cover


def _scored(frame, rgb, box, blend):
    return {"frame": frame, **cover.score_frame(rgb, {"box": box, "blend": blend} if box else None)}


def test_scoring_picks_the_sharp_open_eyed_larger_face():
    cands = [_scored(0, BLURRED, LARGE, OPEN), _scored(200, SHARP, LARGE, CLOSED), _scored(400, SHARP, SMALL, OPEN),
             _scored(600, SHARP, LARGE, OPEN), _scored(800, SHARP, TINY, OPEN)]
    by = {c["frame"]: c for c in cands}
    assert by[200]["rejected"] == "eyes closed" and by[200]["score"] == 0
    assert by[800]["face_area"] == 0 and by[800]["score"] <= cover.NO_FACE  # tiny face dropped: ranks as faceless
    assert by[600]["score"] > by[0]["score"] and by[600]["score"] > by[400]["score"] > by[800]["score"]
    top = cover.pick(cands, total=1000)
    assert top[0]["frame"] == 600 and 200 not in [c["frame"] for c in top]
    smiling = cover.score_frame(SHARP, {"box": LARGE, "blend": {**OPEN, "mouthSmileLeft": 0.9, "mouthSmileRight": 0.9, "jawOpen": 0.4}})
    assert smiling["score"] > by[600]["score"]  # expression is rewarded, moderately
    assert smiling["score"] < 2 * by[600]["score"]


def test_faceless_frames_rank_by_sharpness():
    assert cover.score_frame(SHARP, None)["score"] > cover.score_frame(BLURRED, None)["score"]


def test_spacing_rule_keeps_candidates_four_percent_apart():
    sc = lambda f, s, rej=None: {"frame": f, "score": s, "rejected": rej}  # noqa: E731
    cands = [sc(100, 0.9), sc(110, 0.85), sc(139, 0.8), sc(140, 0.7), sc(500, 0.6), sc(520, 0.5), sc(700, 0.4), sc(900, 0.3), sc(990, 0.2),
             sc(300, 0.99, "eyes closed")]
    top = cover.pick(cands, total=1000)  # 4 % of 1000 frames = 40
    assert [c["frame"] for c in top] == [100, 140, 500, 700, 900]
    for a in top:
        assert all(a is b or abs(a["frame"] - b["frame"]) >= 40 for b in top)


def test_candidates_include_highlights_and_stay_early():
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    cands = cover.candidate_frames(tl, _story())
    whys = [w for _, w in cands]
    assert len(cands) <= cover.N_CANDIDATES and len({f for f, _ in cands}) == len(cands)
    assert "hook" in whys and "punch-in" in whys and any(w.startswith("emphasis") for w in whys)
    assert all(f < tl.duration_f * cover.EARLY_SHARE for f, w in cands if w == "early")
    k01 = next(c for c in tl.video if c.src.item == "k01")
    assert all(k01.at_f <= f < k01.at_f + k01.dur_f for f, w in cands if w == "hook")


def test_title_is_the_hook_title_or_the_hook_line_in_six_words():
    assert cover.title_text(_finish(), _story(), WORDS) == "the one trick to save money"  # hook item k01 = words 7–13
    fin = _finish(hook_title=HookTitle(text="Save ten percent of every single salary, forever.", style="card", reason="r"))
    assert cover.title_text(fin, _story(), WORDS) == "Save ten percent of every single"
    lines, size = cover.layout("Save ten percent of every single", None)
    assert 1 <= len(lines) <= 3 and " ".join(lines) == "Save ten percent of every single" and size >= 60


def test_pinned_downloads_reject_a_checksum_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(cover, "MODEL_DIR", tmp_path / "models")
    monkeypatch.setattr(cover, "FONT_DIR", tmp_path / "fonts")
    monkeypatch.setattr(cover, "_download", lambda url, timeout=120: b"not the pinned file")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        cover.landmarker_model()
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        cover.inter_font()
    assert not (tmp_path / "models" / "face_landmarker.task").exists()  # nothing unverified is cached
    font, note = cover.cover_font("Save money")  # offline / tampered: a system font, and the README says so
    assert "fallback" in note


try:
    config.ffmpeg_path()
    READY = True
except config.ToolNotFound:
    READY = False


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_cover_build_writes_1080x1920_cover_and_candidates(tmp_path, monkeypatch):
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    ws = Workspace.create(tmp_path / "p")
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", f"testsrc2=s=1080x1920:r=30:d={tl.duration_f / 30 + 0.2:.2f}", "-frames:v", str(tl.duration_f),
                  "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(ws.path("render", "base.mov"))])
    eyes = {}

    def fake_faces(frames):  # a face in the upper half; every third frame blinks
        eyes.update({f: (CLOSED if f % 3 == 0 else OPEN) for f in frames})
        return {f: {"box": dict(LARGE), "blend": eyes[f]} for f in frames}

    monkeypatch.setattr(cover, "detect_faces", fake_faces)
    fin = _finish(hook_title=HookTitle(text="One trick to save money monthly", style="card", reason="r"))
    meta = cover.build(ws, tl, _story(), fin, WORDS)
    out = ws.path("render", "cover")
    for name in ("cover.jpg", "cover_clean.jpg"):
        s = tools.ffprobe_json(out / name)["streams"][0]
        assert (s["width"], s["height"]) == (1080, 1920), name
    rep = json.loads((out / "cover.json").read_text())
    assert rep["frame"] == meta["frame"] and rep["frame"] % 3 != 0  # never a blink
    assert 1 <= len(rep["top"]) <= cover.TOP_K and len(list((out / "covers").glob("*.jpg"))) == len(rep["top"])
    assert rep["title"] == "One trick to save money monthly" and rep["text"]["placement"] == "bottom"  # face is high: title low
    assert cover.GRID_TOP <= rep["text"]["text_top"] and rep["text"]["text_bottom"] <= cover.GRID_BOTTOM
    # the package carries the files and records the choice
    pkg = ws.path("export", "package")
    got = package._cover(ws, pkg)
    assert (pkg / "cover.jpg").exists() and (pkg / "covers" / "cover_1.jpg").exists()
    md = package.cover_section(got)
    assert f"frame **{rep['frame']}**" in md and rep["tc"] in md and md.count("| covers/cover_") == len(rep["top"])


def test_cover_without_drawtext_ships_the_clean_frame(tmp_path, monkeypatch):
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    ws = Workspace.create(tmp_path / "p")
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", f"testsrc2=s=1080x1920:r=30:d={tl.duration_f / 30 + 0.2:.2f}", "-frames:v", str(tl.duration_f),
                  "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(ws.path("render", "base.mov"))])
    monkeypatch.setattr(cover, "detect_faces", lambda frames: {f: {"box": dict(LARGE), "blend": OPEN} for f in frames})
    real = cover.write_jpeg

    def no_drawtext(rgb, out, *, text="", font=None, face_box=None):
        if text:
            raise tools.ToolError(["ffmpeg"], 8, "No such filter: 'drawtext'")
        return real(rgb, out)

    monkeypatch.setattr(cover, "write_jpeg", no_drawtext)
    cover.build(ws, tl, _story(), _finish(hook_title=HookTitle(text="One trick", style="card", reason="r")), WORDS)
    out = ws.path("render", "cover")
    assert (out / "cover.jpg").read_bytes() == (out / "cover_clean.jpg").read_bytes()
    assert "skipped" in json.loads((out / "cover.json").read_text())["text"]


def test_cover_stage_falls_back_to_a_plain_frame_and_never_blocks_packaging(tmp_path, monkeypatch):
    from reel.runner import StageContext
    from reel.stages import edit
    from reel.workspace import atomic_write_json

    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    ws = Workspace.create(tmp_path / "p")
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", f"testsrc2=s=1080x1920:r=30:d={tl.duration_f / 30 + 0.2:.2f}", "-frames:v", str(tl.duration_f),
                  "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(ws.path("render", "base.mov"))])
    atomic_write_json(ws.path("timeline", "timeline.json"), tl.model_dump(mode="json"))
    atomic_write_json(ws.path("plan", "story.json"), _story().model_dump(mode="json"))
    atomic_write_json(ws.path("plan", "finish.json"), _finish().model_dump(mode="json"))
    atomic_write_json(ws.path("perception", "words.json"), WORDS.model_dump(mode="json"))

    def boom(*a, **k):
        raise RuntimeError("landmarker exploded")

    monkeypatch.setattr(cover, "build", boom)
    meta = edit._cover(StageContext(ws=ws, options={}))
    out = ws.path("render", "cover")
    assert "landmarker exploded" in meta["error"]
    assert all((out / f).exists() for f in ("cover.jpg", "cover_clean.jpg", "cover.json"))
    assert "plain frame" in package.cover_section(json.loads((out / "cover.json").read_text()))
