"""The render and overlay stages choose full, audio-only, partial or no re-render (roadmap G1.5). Renders are fakes."""

from __future__ import annotations

import json

import pytest

from reel import overlay, render, splice
from reel.runner import StageContext
from reel.schemas.timeline import Asset, AssetKind, AudioClip, CaptionPage, CaptionTrack, CaptionWord, Provenance, Timeline, VideoClip
from reel.stages import edit
from reel.workspace import Workspace

PROV = Provenance(item="k1", words=[0, 1])


def _tl(music_gain: float = -18.0, grade: str = "none", word: str = "hello") -> Timeline:
    return Timeline(fps="30/1", width=1080, height=1920, duration_f=90,
                    assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov"),
                            "m1": Asset(id="m1", kind=AssetKind.music, uri="/x/m.wav")},
                    video=[VideoClip(id="v_k1", asset="c01", at_f=0, dur_f=90, src_in_us=0, src_out_us=3_000_000, src=PROV)],
                    audio=[AudioClip(id="a_k1", asset="c01", at_f=0, dur_f=90, role="voice", src=PROV),
                           AudioClip(id="music", asset="m1", at_f=0, dur_f=90, role="music", gain_db=music_gain)],
                    grade={"look": grade, "strength": 0.4},
                    captions=CaptionTrack(family="bold_pop", pages=[CaptionPage(start_f=0, end_f=30, words=[CaptionWord(i=0, text=word, start_f=0, end_f=30)]),
                                                                     CaptionPage(start_f=60, end_f=89, words=[CaptionWord(i=1, text="end", start_f=60, end_f=89)])]))


@pytest.fixture
def stage(tmp_path, monkeypatch):
    ws = Workspace.create(tmp_path / "p")
    ctx = StageContext(ws=ws, options={})
    state = {"tl": _tl(), "calls": []}
    monkeypatch.setattr(edit, "_timeline", lambda c: state["tl"])
    monkeypatch.setattr(edit, "licence_gate", lambda c, tl=None: None)
    monkeypatch.setattr(edit, "enhanced_voice", lambda c: {})
    monkeypatch.setattr(edit, "room_tones", lambda c: {})
    monkeypatch.setattr(edit, "clip_luts", lambda c, tl: ({}, {"c01": {}}))
    monkeypatch.setattr(edit, "_mezz_fps", lambda c: [])

    def full(tl, root, out, **kw):
        state["calls"].append("full")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"BASE")
        return {"frames": tl.duration_f}

    def audio(tl, root, out, **kw):
        state["calls"].append("audio")
        return {"frames": tl.duration_f, "audio_only": True}

    monkeypatch.setattr(render, "render_base", full)
    monkeypatch.setattr(render, "render_base_audio", audio)
    return ctx, state


def test_render_stage_rebuilds_only_the_sound_when_only_the_sound_changed(stage):
    ctx, state = stage
    edit._render(ctx)
    state["tl"] = _tl(music_gain=-12)  # a music note
    edit._render(ctx)
    state["tl"] = _tl(music_gain=-12, grade="warm")  # a picture change
    edit._render(ctx)
    assert state["calls"] == ["full", "audio", "full"]
    ctx.ws.path("render", "base.meta.json").unlink()  # no record of what the base shows: never trust it
    state["tl"] = _tl(music_gain=-6, grade="warm")
    edit._render(ctx)
    assert state["calls"][-1] == "full"


@pytest.fixture
def ov(stage, monkeypatch):
    ctx, state = stage
    state["renders"], state["splices"] = [], []

    def fake_render(props, out, public_dir=None, frames=None, **kw):
        state["renders"].append(frames)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"OV")
        return {"overlay_s": 1.0}

    def fake_splice(old, chunks, out, *, total_f, fps):
        if state.get("splice_fails"):
            raise RuntimeError("bad seam")
        state["splices"].append([(a, b) for a, b, _p in chunks])

    monkeypatch.setattr(overlay, "render_overlay", fake_render)
    monkeypatch.setattr(splice, "splice", fake_splice)
    monkeypatch.setattr(overlay, "renderer_fingerprint", lambda: state.get("renderer", "r1"))
    return ctx, state


def _props(tl: Timeline) -> dict:
    d = tl.model_dump(mode="json")
    return {"fps": 30.0, "width": 1080, "height": 1920, "duration_f": tl.duration_f, "captions": d["captions"], "titles": [], "flashes": [],
            "pips": [], "graphics": [], "faces": [], "safe": {}}


def test_overlay_stage_full_then_nothing_then_partial(ov):
    ctx, state = ov
    run = lambda tl: edit.render_overlay_partial(ctx, tl, _props(tl))  # noqa: E731
    assert run(_tl())["partial"] is None and state["renders"] == [None]  # no baseline: full
    assert run(_tl())["partial"] == {"ranges": [], "frames": 0} and len(state["renders"]) == 1  # unchanged: no render at all
    meta = run(_tl(word="HELLO"))  # one caption word
    assert state["renders"][-1] == (0, 42) and state["splices"] == [[(0, 42)]] and meta["partial"]["frames"] == 43
    saved = json.loads(ctx.ws.path("render", "overlay.rendered.props.json").read_text())
    assert saved["props"]["captions"]["pages"][0]["words"][0]["text"] == "HELLO"


def test_overlay_stage_falls_back_to_full_on_any_problem(ov):
    ctx, state = ov
    run = lambda tl: edit.render_overlay_partial(ctx, tl, _props(tl))  # noqa: E731
    run(_tl())
    state["splice_fails"] = True
    assert run(_tl(word="x"))["partial"] is None and state["renders"][-1] is None  # the splice failed: rendered in full
    state["splice_fails"] = False
    state["renderer"] = "r2"  # a new renderer build: every frame may differ
    assert run(_tl(word="y"))["partial"] is None
