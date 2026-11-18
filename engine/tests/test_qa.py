"""Build step 9: QA gates, verdict, fix loop, calibration."""

import json
from pathlib import Path

import pytest

from reel import autofix, calibrate, config, qa, tools, verdict
from reel.brief import Brief
from reel.schemas.review import Review
from reel.schemas.timeline import CaptionPage, CaptionTrack, CaptionWord, Keyframe, Provenance, Timeline, VideoClip
from reel.workspace import Workspace, atomic_write_json


def _tl(pages, dur=150, fps="25/1", tokens=None, scale=None):
    prov = Provenance(item="k0", words=[0, 0])
    return Timeline(fps=fps, width=1080, height=1920, duration_f=dur, assets={},
                    video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=dur, src_in_us=0, src_out_us=dur * 40_000, scale=scale or [], src=prov)],
                    audio=[], captions=CaptionTrack(family="bold_pop", tokens=tokens or {"base_color": "#FFFF00"}, pages=pages))


def _page(s, e, *texts):
    step = (e - s) // max(1, len(texts))
    return CaptionPage(start_f=s, end_f=e, words=[CaptionWord(i=k, text=t, start_f=s + k * step, end_f=s + (k + 1) * step) for k, t in enumerate(texts)])


def test_contrast_ratio_matches_wcag():
    assert qa.contrast_ratio((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0, abs=0.01)
    assert qa.contrast_ratio((255, 255, 0), (255, 255, 0)) == pytest.approx(1.0)


def test_reading_speed_and_dead_air():
    tl = _tl([_page(0, 10, "supercalifragilistic", "expialidocious"), _page(100, 140, "ok")])  # 0.4 s for 35 chars; 3.6 s gap
    rs, da = qa.reading_speed(tl), qa.dead_air(tl)
    assert not rs.ok and rs.at == ["0:00.00"] and rs.measured["max_cps"] > 80
    assert not da.ok and da.at == ["0:00.40"]


def test_brief_compliance():
    brief = Brief(project="p", must_keep_lines=["never touch it"], banned_claims=["guaranteed returns"], cta="follow for more")
    ok = qa.brief_compliance(None, "put ten percent away and never touch it follow for more tips", brief)
    bad = qa.brief_compliance(None, "guaranteed returns every month", brief)
    assert ok.ok and not bad.ok and bad.blocking and bad.fixable
    assert "must-keep" in bad.detail and "banned" in bad.detail and "CTA" in bad.detail


def test_face_cut_after_punch_in():
    tl = _tl([], scale=[Keyframe(f=0, v=1.0), Keyframe(f=10, v=1.6)])
    near_edge = [{"start_f": 0, "end_f": 150, "box": {"x": 0.30, "y": 0.05, "w": 0.4, "h": 0.25}}]
    centred = [{"start_f": 0, "end_f": 150, "box": {"x": 0.40, "y": 0.35, "w": 0.2, "h": 0.12}}]
    assert not qa.face_cut(tl, near_edge).ok and qa.face_cut(tl, centred).ok


def test_verdict_rules():
    gates = [qa.GateResult("loudness", True, mode="block"), qa.GateResult("dead_air", False, mode="warn", detail="1 gap")]
    v = verdict.decide_verdict(gates, Review(sendable=True, summary="fine", issues=[], strengths=["hook"]))
    assert v["status"] == "sendable" and v["warnings"] and not v["fix_request"]
    brief_fail = qa.GateResult("brief", False, mode="block", detail="CTA missing", fixable=True, fix_hint="Keep the CTA.")
    v = verdict.decide_verdict([brief_fail], None)
    assert v["status"] == "hold" and "CTA missing" in v["fix_request"]
    review = Review.model_validate({"sendable": False, "summary": "slow open", "strengths": [], "issues": [
        {"id": "r1", "severity": "major", "category": "hook", "at": "0:00.00", "problem": "slow open", "fix_target": "story", "fix": "start at k2"}]})
    v = verdict.decide_verdict([], review)
    assert v["status"] == "hold" and not v["fix_request"]  # untrusted Reviewer: hold, no auto-fix
    config.REVIEWER_TRUSTED = True
    try:
        assert "start at k2" in verdict.decide_verdict([], review)["fix_request"]
    finally:
        config.REVIEWER_TRUSTED = False


def test_proof_words_gate_respects_confirmations():
    proof = [{"i": 7, "text": "Dioma", "at": "0:01.00", "why": "unconfirmed name", "suggestion": "DearMa"}]
    assert not qa.proof_words(proof, {}).ok
    assert qa.proof_words(proof, {"7": {"ok": True, "text": "DearMa"}}).ok


def test_calibration_report(tmp_path):
    for k, (owner, rev, failed) in enumerate([(True, True, []), (True, True, ["dead_air"]), (False, True, ["caption_contrast"]), (False, False, [])]):
        d = tmp_path / f"p{k}" / "qa"
        d.mkdir(parents=True)
        atomic_write_json(d / "owner_label.json", {"sendable": owner})
        atomic_write_json(d / "review.json", {"sendable": rev})
        atomic_write_json(d / "gates.json", [{"gate": g, "ok": False} for g in failed])
    r = calibrate.report(calibrate.collect(tmp_path))
    assert r["labels"] == 4 and r["reviewer"]["false_sendable"] == 1 and r["reviewer"]["accuracy"] == 0.75
    assert r["gates_failing_on_sendable"] == {"dead_air": {"false_positives": 1, "fp_rate": 0.5}}
    assert not r["reviewer"]["trust_ready"]


def test_fix_loop_revises_until_sendable_and_stops_on_unfixable(tmp_path, monkeypatch):
    ws = Workspace.create(tmp_path / "p")
    verdicts = iter([{"status": "hold", "reasons": ["brief: CTA missing"], "fix_request": "keep the CTA"},
                     {"status": "sendable", "reasons": [], "fix_request": ""}])
    revisions = []

    def fake_pipeline(ws_, stages, options=None, force=None):
        atomic_write_json(ws_.path("qa", "verdict.json"), next(verdicts))
        return {"stages": {}}

    monkeypatch.setattr(autofix, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(autofix, "apply_revision", lambda ws_, opts, req, caller: revisions.append(req) or {"reply": "kept the CTA"})
    res = autofix.run(ws, [], {}, caller=lambda *a, **k: None)
    assert [h["status"] for h in res["loops"]] == ["hold", "sendable"] and revisions == ["keep the CTA"]

    verdicts = iter([{"status": "hold", "reasons": ["loudness"], "fix_request": ""}])
    revisions.clear()
    res = autofix.run(ws, [], {}, caller=lambda *a, **k: None)
    assert len(res["loops"]) == 1 and revisions == []  # nothing the Editor can fix → hold at once

    verdicts = iter([{"status": "hold", "reasons": ["x"], "fix_request": "fix x"}] * 10)
    res = autofix.run(ws, [], {}, caller=lambda *a, **k: None, max_loops=3)
    assert len(revisions) == 3 and res["loops"][-1]["status"] == "hold"


# ------------------------------------------------------------------ pixels (ffmpeg)

try:
    config.ffmpeg_path()
    READY = True
except config.ToolNotFound:
    READY = False


def _media(tmp_path: Path, base_color: str, stroke_box: bool = False):
    base = tmp_path / "base.mov"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", f"color=c={base_color}:s=1080x1920:r=25:d=2", "-c:v", "prores_ks", "-pix_fmt", "yuv422p10le", str(base)])
    ov = tmp_path / "overlay.mov"
    # opaque yellow caption block (on an opaque black outline block if stroke_box) over a transparent canvas
    graph = "color=c=black@0.0:s=1080x1920:r=25:d=2,format=rgba[bg];color=c=yellow:s=480x110:r=25:d=2,format=rgba[t];"
    if stroke_box:
        graph += "color=c=black:s=500x130:r=25:d=2,format=rgba[o];[bg][o]overlay=290:1170:format=auto[bg2];[bg2][t]overlay=300:1180:format=auto"
    else:
        graph += "[bg][t]overlay=300:1180:format=auto"
    tools.ffmpeg(["-y", "-filter_complex", graph, "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-t", "2", str(ov)])
    return base, ov


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_caption_pixel_gates(tmp_path):
    base, ov = _media(tmp_path, "yellow")
    tl = _tl([_page(10, 40, "SAVE", "MONEY")], dur=50)
    face = [{"start_f": 0, "end_f": 50, "box": {"x": 0.3, "y": 0.58, "w": 0.4, "h": 0.1}}]  # face under the caption
    safe = {"top": 220, "bottom": 420, "left": 60, "right": 130}
    contrast, over_face, safe_zone = qa.caption_pixels(tl, base, ov, face, safe, [])
    assert not contrast.ok and contrast.measured["min_ratio"] < 1.5  # yellow on yellow
    assert not over_face.ok and safe_zone.ok
    stroked = _tl([_page(10, 40, "SAVE", "MONEY")], dur=50, tokens={"base_color": "#FFFF00", "stroke": "true"})
    assert qa.caption_pixels(stroked, base, ov, [], safe, [])[0].ok  # outlined text passes on any background


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_frozen_and_black_detection(tmp_path):
    final = tmp_path / "final.mp4"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=s=270x480:r=25:d=2", "-f", "lavfi", "-i", "color=c=red:s=270x480:r=25:d=4",
                  "-f", "lavfi", "-i", "color=c=black:s=270x480:r=25:d=1", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0",
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", str(final)])
    tl = _tl([], dur=175)
    frozen, black = qa.frozen_and_black(tl, final, dips=[])
    assert not frozen.ok and not black.ok
    _f, black_in_dip = qa.frozen_and_black(tl, final, dips=[(145, 175)])
    assert black_in_dip.ok  # an intended dip-to-black is not a defect


def test_cli_registers_every_command(capsys):
    from reel import cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for cmd in ("doctor", "probe", "run", "revise", "notes", "stock", "improve", "proof", "label", "calibrate", "library", "bakeoff", "eval",
                "conformance", "schema", "validate", "compile", "dry-run"):
        assert cmd in out, cmd
    assert cli.main(["schema", "revision"]) == 0


def test_caption_token_values_are_validated_and_pages_balanced():
    from reel.compile import balanced_pages
    from reel.validate import token_rule

    import re as _re
    for key, good, bad in (("stroke", "#000000", "thick"), ("box", "true", "yes"), ("emph_color", "#FFD400", "yellow"),
                           ("zone", "lower_third", "bottom"), ("weight", "900", "bold")):
        rx = token_rule(key)[0]
        assert _re.fullmatch(rx, good) and not _re.fullmatch(rx, bad), key
    from reel.schemas.perception import Word

    def words(text, pause_after=()):
        out, t = [], 0
        for k, tok in enumerate(text.split()):
            out.append(Word(i=k, clip="c", text=tok, start_us=t, end_us=t + 200_000))
            t += 200_000 + (400_000 if k in pause_after else 40_000)
        return out

    texts = lambda pages: [" ".join(w.text for w in p) for p in pages]  # noqa: E731
    # punctuation wins over a fixed word count: "one simple trick / to save money."
    assert texts(balanced_pages(words("Today I will show you one simple trick to save money."), 3)) == \
        ["Today I", "will show you", "one simple trick", "to save money."]  # phrases stay whole
    pages = balanced_pages(words("put ten percent, into a separate account every month, and never touch it."), 3)
    assert all(len(p) > 1 for p in pages)  # no orphans
    assert any(p[-1].text.endswith(",") for p in pages)  # breaks at the commas
    # a pause is a better break than mid-phrase; Hindi postpositions stay with the word before
    assert texts(balanced_pages(words("save money every single month", pause_after=(1,)), 3)) == ["save money", "every single month"]
    assert all(p[0].text not in ("ka", "ko", "mein") for p in balanced_pages(words("apni salary ka das pratishat har mahine account mein daalo"), 3))


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_frames_at_handles_hundreds_of_frames(tmp_path):
    clip = tmp_path / "long.mp4"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=s=160x284:r=25:d=12", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)])
    wanted = list(range(0, 300, 2))  # 150 frames: one select expression this long makes ffmpeg fail
    got = qa.frames_at(clip, wanted, width=80)
    assert sorted(got) == wanted


def test_per_shot_framing_follows_faces_across_camera_cuts():
    from fractions import Fraction

    from reel import framing

    prov = Provenance(item="k0", words=[0, 0])
    c = VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=100, src_in_us=1_000_000, src_out_us=5_000_000, src=prov)
    samples = [{"t_us": t, "faces": [{"x": 0.70, "y": 0.3, "w": 0.1, "h": 0.1}]} for t in range(1_000_000, 3_000_000, 250_000)]  # host right
    samples += [{"t_us": t, "faces": [{"x": 0.10, "y": 0.3, "w": 0.2, "h": 0.2}, {"x": 0.8, "y": 0.3, "w": 0.05, "h": 0.05}]}
                for t in range(3_000_000, 4_000_000, 250_000)]  # guest left (largest face wins)
    shots = framing.shots(c, Fraction(25), cuts_us=[3_000_000, 4_000_000], samples=samples)
    assert [s.start_f for s in shots] == [0, 50, 75]
    assert shots[0].centre[0] == pytest.approx(0.75) and shots[1].centre[0] == pytest.approx(0.20)
    assert shots[2].centre == shots[1].centre and shots[2].box is None  # no face → keep the previous framing
    assert framing.piecewise([10, 20, 30], [0, 50, 75]) == "if(lt(n,50),10,if(lt(n,75),20,30))"


def test_caption_words_are_tidied_not_the_audio():
    from reel.compile import clean_caption_words
    from reel.schemas.perception import Word

    ws = [Word(i=k, clip="c", text=t, start_us=k, end_us=k + 1) for k, t in enumerate("back in the sunny d days i i thought ORANGE. CEO".split())]
    out = clean_caption_words(ws)
    assert [w.text for w in out] == ["Back", "in", "the", "sunny", "d", "days", "I", "thought", "orange.", "CEO"]
