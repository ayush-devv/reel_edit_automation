"""Build step 9: QA gates, verdict, fix loop, calibration."""

import json
from pathlib import Path

import numpy as np
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
    assert rs.ok and rs.measured["max_page_cps"] > 80  # one fast page is not a sustained rate: 35 chars over 3 s
    assert not da.ok and da.at == ["0:00.40"]


def _speech_pages(start, seconds, words_per_s, fps=25, words=("remember", "every", "month", "save", "a", "little", "first")):
    """Word-synced pages of 1–3 words following speech at about `words_per_s`, with the uneven word timing of real
    speech (a quick single word, then slower phrases): single pages run far faster than the sustained rate."""
    pages, f, k, sizes, pace = [], start, 0, (1, 3, 2), (0.55, 1.15, 1.15)
    step = fps / words_per_s
    while f < start + seconds * fps - 1:
        n = sizes[len(pages) % 3]
        texts = [words[(k + j) % len(words)] for j in range(n)]
        end = int(round(f + n * step * pace[len(pages) % 3]))
        pages.append(_page(int(round(f)), end, *texts))
        f, k = end, k + n
    return pages


def test_reading_speed_is_a_sustained_rate():
    # fast 1–3-word pages that follow normal speech (~3 words/s) pass, although single pages run at 20+ chars/s
    normal = _tl(_speech_pages(0, 10, 3.0), dur=250)
    rs = qa.reading_speed(normal)
    assert rs.ok and rs.measured["max_page_cps"] > qa.MAX_CPS and rs.measured["max_cps"] < qa.MAX_CPS, rs.measured
    # a 3 s stretch with far more text than anyone can read fails, at that stretch only
    before = _speech_pages(0, 5, 3.0)
    s0 = before[-1].end_f
    dense = [_page(s0 + 15 * k, s0 + 15 * (k + 1), "extraordinarily", "complicated", "sentences") for k in range(5)]  # 39 chars/0.6 s
    tl = _tl(before + dense + _speech_pages(s0 + 75, 5, 3.0), dur=s0 + 75 + 140)
    rs = qa.reading_speed(tl)
    assert not rs.ok and rs.measured["max_cps"] > 50
    worst = qa.tc(s0, qa.tb.parse_rate(tl.fps))
    assert rs.at == [worst] and rs.measured["worst_at"] == worst  # one stretch, at the window holding all of it


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
    # the gate judges what was rendered: a stroke token with no outline drawn does not save yellow-on-yellow …
    assert not qa.caption_pixels(stroked, base, ov, [], safe, [])[0].ok
    # … while an outline that is really there carries the text on any background
    frames = qa.page_frames(stroked)
    ovf, bgf = qa.frames_at(ov, frames, alpha=True), qa.frames_at(base, frames)
    for f in list(ovf):
        o = ovf[f] = ovf[f].copy()
        ys, xs = np.nonzero(o[..., 3] > 128)
        o[max(0, ys.min() - 3):ys.min(), xs.min():xs.max() + 1] = (0, 0, 0, 255)  # a dark outline band on the text
    assert qa.caption_pixels_from(stroked, ovf, bgf, [], safe, [])[0].ok


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


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_head_and_tail_fades_are_not_black_defects(tmp_path):
    def clip(name, parts):
        out = tmp_path / name
        args = []
        for src, d in parts:
            args += ["-f", "lavfi", "-i", f"{src}{':' if '=' in src else '='}s=270x480:r=25:d={d}"]
        tools.ffmpeg(["-y", *args, "-filter_complex", "".join(f"[{k}:v]" for k in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0",
                      "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
        return out

    # 0.4 s fade-from-black head and 0.4 s fade-to-black tail on a 3.8 s reel (pro finals do this)
    edges = clip("edges.mp4", [("color=c=black", 0.4), ("testsrc2", 3.0), ("color=c=black", 0.4)])
    frozen, black = qa.frozen_and_black(_tl([], dur=95), edges, dips=[])
    assert black.ok and black.measured["edge_fades"] == 2, black.detail
    # the same 0.4 s of black in the middle is a defect
    mid = clip("mid.mp4", [("testsrc2", 1.7), ("color=c=black", 0.4), ("testsrc2", 1.7)])
    assert not qa.frozen_and_black(_tl([], dur=95), mid, dips=[])[1].ok


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


def test_framing_holds_still_tracks_movement_and_fills_wide_two_shots():
    from fractions import Fraction

    from reel import framing

    prov = Provenance(item="k0", words=[0, 0])
    c = VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=150, src_in_us=0, src_out_us=6_000_000, src=prov)
    crop_w = 0.316  # 16:9 source → 9:16 crop
    still = [{"t_us": t, "faces": [{"x": 0.45 + 0.005 * (t // 250_000 % 2), "y": 0.3, "w": 0.1, "h": 0.15}]} for t in range(0, 2_000_000, 250_000)]
    walk = [{"t_us": t, "faces": [{"x": 0.2 + 0.25 * (t - 2_000_000) / 2_000_000, "y": 0.3, "w": 0.1, "h": 0.15}]}
            for t in range(2_000_000, 4_000_000, 250_000)]
    two = [{"t_us": t, "faces": [{"x": 0.1, "y": 0.3, "w": 0.12, "h": 0.2}, {"x": 0.78, "y": 0.3, "w": 0.11, "h": 0.19}]}
           for t in range(4_000_000, 6_000_000, 250_000)]
    shots = framing.shots(c, Fraction(25), cuts_us=[2_000_000, 4_000_000], samples=still + walk + two, crop_w=crop_w)
    assert [s.layout for s in shots] == ["crop", "crop", "fill"]
    assert shots[0].path is None  # small jitter stays inside the dead zone: a locked-off shot
    path = shots[1].path
    assert path and path[0][0] >= shots[1].start_f and path[-1][1] > path[0][1]  # follows the walk to the right
    steps = [abs(b[1] - a[1]) / max(1, b[0] - a[0]) * 25 for a, b in zip(path, path[1:])]
    assert max(steps) <= framing.MAX_SPEED * crop_w + 1e-6  # speed cap (crop widths per second)
    # the second, smaller face never steals a tracked shot
    assert framing.follow([{"t_us": 0, "faces": [{"x": 0.7, "y": 0, "w": 0.3, "h": 0.3}, {"x": 0.2, "y": 0, "w": 0.1, "h": 0.1}]}], 0.25)[0][1] == pytest.approx(0.25)


def test_tracked_and_fill_shots_render_frame_exact(tmp_path):
    from fractions import Fraction

    from reel import render, tools
    from reel.schemas.timeline import Asset, AssetKind, AudioClip, Timeline

    src = tmp_path / "mezz" / "c01.mov"
    src.parent.mkdir()
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=25:duration=6", "-f", "lavfi", "-i", "sine=f=440:d=6:r=48000",
                  "-c:v", "prores_ks", "-profile:v", "2", "-c:a", "pcm_s16le", "-ac", "2", str(src)])
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=150, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=150, src_in_us=0, src_out_us=6_000_000,
                                   scale=[Keyframe(f=0, v=1.0), Keyframe(f=20, v=1.2)], src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=150, role="voice", src=prov)])
    walk = [{"t_us": t, "faces": [{"x": 0.2 + 0.25 * t / 3_000_000, "y": 0.3, "w": 0.1, "h": 0.15}]} for t in range(0, 3_000_000, 250_000)]
    two = [{"t_us": t, "faces": [{"x": 0.1, "y": 0.3, "w": 0.12, "h": 0.2}, {"x": 0.78, "y": 0.3, "w": 0.11, "h": 0.19}]} for t in range(3_000_000, 6_000_000, 250_000)]
    faces = {"c01": {"samples": walk + two, "median_box": {"x": 0.3, "y": 0.3, "w": 0.1, "h": 0.15}}}
    meta = render.render_base(tl, tmp_path, tmp_path / "base.mp4", faces=faces, scenes={"c01": {"cuts_us": [3_000_000]}}, finish_audio=False)
    assert meta["frames"] == 150 and meta["size"] == "1080x1920"
    # fill shot: top band is the blurred, darkened copy — far less detail than the sharp centre band
    import numpy as np

    frame = np.frombuffer(tools.run([str(render.ffmpeg_path()), "-v", "error", "-ss", "5", "-i", str(tmp_path / "base.mp4"), "-frames:v", "1",
                                     "-f", "rawvideo", "-pix_fmt", "gray", "-"]).stdout, dtype=np.uint8).reshape(1920, 1080)
    top, mid = frame[100:500].astype(float), frame[800:1100].astype(float)
    assert np.abs(np.diff(top, axis=1)).mean() < 0.5 * np.abs(np.diff(mid, axis=1)).mean()


def test_over_the_shoulder_shot_frames_the_visible_face_not_the_back_of_a_head():
    from fractions import Fraction

    from reel import framing

    prov = Provenance(item="k0", words=[0, 0])
    c = VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=100, src_in_us=0, src_out_us=4_000_000, src=prov)
    # two prominent "faces" far apart (would be a fill), but the landmarker read only the one on the right
    two = [{"t_us": t, "faces": [{"x": 0.05, "y": 0.3, "w": 0.25, "h": 0.4}, {"x": 0.7, "y": 0.25, "w": 0.22, "h": 0.35}]}
           for t in range(0, 4_000_000, 250_000)]
    speakers = {"pieces": [[0, 4_000_000]], "tracks": [{"id": 1, "box": {"x": 0.7, "y": 0.25, "w": 0.22, "h": 0.35}, "start_us": 0, "end_us": 4_000_000}],
                "segments": []}
    shots = framing.shots(c, Fraction(25), [], two, crop_w=0.316, speakers=speakers)
    assert len(shots) == 1 and shots[0].layout == "crop" and shots[0].centre[0] == pytest.approx(0.81)
    # without speaker data the old behaviour stays (fill)
    assert framing.shots(c, Fraction(25), [], two, crop_w=0.316)[0].layout == "fill"
