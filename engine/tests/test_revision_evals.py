"""3b.3 revision evals: did it, collateral outside the asked region, don't break; the project copy stays separate."""

from __future__ import annotations

import pytest

from reel.evalh import revisions
from reel.schemas.timeline import Grade, Provenance, Timeline, VideoClip


def _tl(clips, look="clean", dur=250):
    return Timeline(fps="25/1", width=1080, height=1920, duration_f=dur, assets={}, audio=[], grade=Grade(look=look, strength=0.4),
                    video=[VideoClip(id=f"v{n}", asset="c01", at_f=a, dur_f=d, src_in_us=a * 40_000, src_out_us=(a + d) * 40_000,
                                     src=Provenance(item=f"k{n}", words=[0, 0])) for n, (a, d) in enumerate(clips)])


def _props(pages):
    return {"fps": "25/1", "width": 1080, "height": 1920, "duration_f": 1000, "faces": [], "safe": {}, "layer": "main",
            "captions": {"family": "bold_pop", "tokens": {}, "script": "latin", "timing": "word",
                         "pages": [{"start_f": a, "end_f": b, "words": [{"text": t}]} for a, b, t in pages]},
            "titles": [], "flashes": [], "pips": [], "graphics": []}


PAGES = [(k * 50, k * 50 + 50, f"w{k}") for k in range(20)]  # 40 s of 2-second caption pages


def test_a_local_caption_fix_inside_the_region_has_little_collateral():
    new = [*PAGES[:10], (500, 550, "CHANGED"), *PAGES[11:]]  # the page at 20–22 s
    m = revisions.measure(_tl([(0, 1000)], dur=1000), _tl([(0, 1000)], dur=1000), _props(PAGES), _props(new),
                          {"kind": "captions", "region_s": [19.5, 22.5]}, 0, 0, 0)
    assert m["did_it"] and m["dont_break"] and not m["music_changed"] and not m["look_changed"]
    assert m["collateral_s"] <= 4.0  # only the animation pads and the neighbouring pages leak out of the region


def test_a_change_in_the_wrong_place_is_not_did_it_and_is_collateral():
    new = [(0, 50, "CHANGED"), *PAGES[1:]]
    m = revisions.measure(_tl([(0, 1000)], dur=1000), _tl([(0, 1000)], dur=1000), _props(PAGES), _props(new),
                          {"kind": "captions", "region_s": [30.0, 32.0]}, 0, 0, 0)
    assert not m["did_it"] and m["collateral_s"] == 2.0  # the whole changed page is outside the asked region


def test_a_global_look_change_counts_any_picture_change_as_collateral():
    m = revisions.measure(_tl([(0, 250)]), _tl([(0, 250)], look="warm"), _props(PAGES), _props(PAGES), {"kind": "look"}, 0, 0, 0)
    assert m["did_it"] and m["collateral_s"] == 0.0
    cut = revisions.measure(_tl([(0, 125), (125, 125)]), _tl([(0, 100), (100, 125)], look="warm", dur=225), _props(PAGES), _props(PAGES),
                            {"kind": "look"}, 0, 0, 0)
    assert cut["did_it"] and cut["collateral_s"] > 0  # it also cut the reel: collateral


def test_a_cut_is_seen_and_new_warnings_break():
    m = revisions.measure(_tl([(0, 125), (125, 125)]), _tl([(0, 100), (100, 125)], dur=225), _props(PAGES), _props(PAGES),
                          {"kind": "cut", "region_s": [3.5, 5.5]}, 2, 3, 0)
    assert m["did_it"] and not m["dont_break"]


def test_cases_load_and_validate(tmp_path):
    (tmp_path / "a.yaml").write_text("project: projects/x\nnote: n\nexpect: {kind: music}\n")
    assert revisions.load_cases(tmp_path)[0]["id"] == "a"
    (tmp_path / "b.yaml").write_text("project: projects/x\nnote: n\nexpect: {kind: vibes}\n")
    with pytest.raises(ValueError, match="kind"):
        revisions.load_cases(tmp_path)
    shipped = revisions.load_cases()
    assert len(shipped) >= 6 and {c["expect"]["kind"] for c in shipped} == set(revisions.KINDS)


def test_the_copy_never_touches_the_original(tmp_path):
    src = tmp_path / "proj"
    (src / "plan").mkdir(parents=True)
    (src / "render").mkdir()
    (src / "plan" / "finish.json").write_text("{}")
    (src / "render" / "final.mp4").write_bytes(b"x")
    dst = revisions.copy_project(src, tmp_path / "work" / "proj")
    assert (dst / "plan" / "finish.json").exists() and not (dst / "render").exists()
    from reel.workspace import atomic_write_json

    atomic_write_json(dst / "plan" / "finish.json", {"changed": True})  # how revise writes: a new inode
    assert (src / "plan" / "finish.json").read_text() == "{}"


def test_a_crashing_case_counts_against_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(revisions, "SCOREBOARD", tmp_path / "sb.jsonl")
    out = revisions.run_all(lambda *a, **k: None, cases=[{"id": "x", "project": "projects/missing", "note": "n", "expect": {"kind": "music"}}],
                            work_root=tmp_path / "w")
    assert out["n"] == 1 and out["did_it"] == 0 and "error" in out["cases"][0] and (tmp_path / "sb.jsonl").exists()
