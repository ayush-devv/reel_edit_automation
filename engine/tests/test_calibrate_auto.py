import numpy as np
import pytest

from reel import calibrate_auto as ca
from reel import qa
from reel.schemas.timeline import CaptionPage, CaptionTrack, CaptionWord, FlashEvent, GraphicEvent, PipEvent, Timeline, TitleEvent


def _tl():
    pages = [CaptionPage(start_f=k * 10, end_f=k * 10 + 10, words=[CaptionWord(i=k, text="WORD", start_f=k * 10, end_f=k * 10 + 10)]) for k in range(6)]
    return Timeline(fps="25/1", width=1080, height=1920, duration_f=60, assets={}, video=[], audio=[],
                    captions=CaptionTrack(family="x", tokens={"base_color": "#FFFFFF", "stroke": "#000000"}, pages=pages))


def _frames():
    """270x480 samples: dark background, a white caption with a black outline at ~66 % height, a face at 25–40 %."""
    tl = _tl()
    ov, bg = {}, {}
    for f in qa.page_frames(tl):
        o = np.zeros((480, 270, 4), dtype=np.uint8)
        o[310:330, 80:190, :3] = 255
        o[310:330, 80:190, 3] = 255
        o[306:310, 76:194, 3] = 255  # outline (black, opaque)
        ov[f] = o
        bg[f] = np.full((480, 270, 3), 40, dtype=np.uint8)
    faces = [{"start_f": 0, "end_f": 60, "box": {"x": 0.3, "y": 0.25, "w": 0.4, "h": 0.15}}]
    return tl, ov, bg, faces


SAFE = {"top": 220, "bottom": 420, "left": 60, "right": 130}


def test_clean_caption_frames_pass_every_caption_gate():
    tl, ov, bg, faces = _frames()
    assert all(r.ok for r in qa.caption_pixels_from(tl, ov, bg, faces, SAFE, [])), qa.caption_pixels_from(tl, ov, bg, faces, SAFE, [])


def test_each_injected_caption_defect_is_caught():
    tl, ov, bg, faces = _frames()
    for defect in ("captions_over_face", "captions_in_ui_zone", "captions_see_through", "captions_wrong_colour"):
        gate = ca.DEFECTS[defect]
        res = {r.gate: r for r in ca._caption_trial(tl, ov, bg, faces, SAFE, defect, 0)}
        assert not res[gate].ok, (defect, res[gate].detail)


def test_text_in_the_background_colour_fails_contrast_even_with_good_tokens():
    tl, ov, bg, faces = _frames()
    tl.captions.tokens.pop("stroke")  # no outline: the rendered fill alone must carry it
    for o in ov.values():
        o[306:310, :, 3] = 0
    bad = {f: ca.recolour(o, bg[f]) for f, o in ov.items()}
    res = {r.gate: r for r in qa.caption_pixels_from(tl, bad, bg, faces, SAFE, [])}
    assert not res["caption_contrast"].ok


def test_shift_and_fade_helpers():
    a = np.zeros((10, 4, 4), dtype=np.uint8)
    a[5] = 255
    assert ca.shift_rows(a, -3)[2].max() == 255 and ca.shift_rows(a, -3)[5].max() == 0
    assert ca.shift_rows(a, 2)[7].max() == 255
    assert ca.fade(a, 0.1)[5, 0, 3] == 25


def _report(n_good: int, frozen_fa: int = 1):
    good = [{"reel": f"r{k}", "failed": [], "detail": {}} for k in range(n_good)]
    for k in range(frozen_fa):
        good[k]["failed"] = ["frozen"]
    bad = {"black_stretch": [{"caught": True, "valid": True}] * 10,
           "frozen_stretch": [{"caught": True, "valid": True}] * 10,
           "loudness_low": [{"caught": True, "valid": True}] * 9 + [{"caught": False, "valid": True}],
           "captions_over_face": [{"caught": True, "valid": True, "recall": 0.8}] * 10}
    return ca.report(good, bad)


def test_promotion_rule():
    rep = _report(6)
    g = rep["gates"]
    # 0/6 false alarms is not enough evidence: up to ~39 % false alarms at 95 % confidence, so black stays warn
    assert g["black"]["promote_to_block"] is False and any("6/30" in w for w in g["black"]["waiting_for"])
    assert g["black"]["fa_upper_95"] == pytest.approx(0.393, abs=0.002)
    assert g["frozen"]["promote_to_block"] is False and g["frozen"]["false_alarms"] == 1  # a false alarm on a pro final
    assert g["caption_over_face"]["promote_to_block"] is False and "note" in g["caption_over_face"]  # no known-good check possible
    assert g["caption_over_face"]["defects"]["captions_over_face"]["mean_recall"] == 0.8
    assert g["loudness"]["catch_rate"] == 0.9
    assert rep["rule_params"]["min_known_good"] == 30 and "30 known-good" in rep["rule"]
    assert "39%" in rep["statistics"] and "10%" in rep["statistics"]
    # with 30 known-good reels and no false alarm, a gate catching ≥ 90 % may block
    g30 = _report(30)["gates"]
    assert g30["black"]["promote_to_block"] is True and "waiting_for" not in g30["black"]
    assert g30["frozen"]["promote_to_block"] is False  # 1 false alarm


def test_false_alarm_upper_bound():
    assert ca.fa_upper_95(0, 6) == pytest.approx(1 - 0.05 ** (1 / 6), abs=1e-6)
    assert ca.fa_upper_95(0, 30) == pytest.approx(0.0950, abs=1e-3)
    assert ca.fa_upper_95(1, 6) == pytest.approx(0.5818, abs=2e-3)  # exact Clopper-Pearson, k = 1
    assert ca.fa_upper_95(0, 0) is None and ca.fa_upper_95(3, 3) == 1.0


def test_injection_times_follow_the_excerpt_length():
    long = ca.injection_times(20.0, 10)
    assert len(long) == 10 and long[0] >= qa.HEAD_TAIL_S and long[-1] + ca.FREEZE_S <= 20.0 - qa.HEAD_TAIL_S
    short = ca.injection_times(7.0, 10)  # a short reel: the span shrinks instead of running past the end
    assert len(short) == 10 and short[-1] + ca.FREEZE_S <= 7.0 - qa.HEAD_TAIL_S and short[0] < short[-1]
    assert ca.injection_times(4.0, 10) == []  # cannot hold a 3.8 s freeze clear of both fade windows


def test_recall_counts_only_pages_the_defect_changed():
    tl, ov, bg, faces = _frames()
    tl.captions.tokens.pop("stroke")
    for o in ov.values():
        o[306:310, :, 3] = 0
    fps = qa.tb.parse_rate(tl.fps)
    clean = {r.gate: set(r.at) for r in qa.caption_pixels_from(tl, ov, bg, faces, SAFE, [])}
    for trial in range(3):
        mutated, changed = ca.mutate_captions(tl, ov, bg, faces, SAFE, "captions_wrong_colour", trial)
        assert len(changed) == 2  # one third of six pages
        gate = {r.gate: r for r in qa.caption_pixels_from(tl, mutated, bg, faces, SAFE, [])}["caption_contrast"]
        recall, new, eligible = ca.caption_recall(gate, clean["caption_contrast"], {qa.tc(f, fps) for f in changed})
        assert recall == 1.0 and new == eligible == 2
    # a gate that flags one page out of six mutated pages has recall 1/6: not a catch
    one = qa.GateResult("safe_zone", False, at=["0:00.20"])
    assert ca.caption_recall(one, set(), {qa.tc(f, fps) for f in ov})[0] == pytest.approx(1 / 6)
    # pages already failing at baseline or not judged by the gate are not eligible
    skip = qa.GateResult("safe_zone", False, at=["0:00.20"], measured={"skipped": ["0:00.60"]})
    assert ca.caption_recall(skip, {"0:01.00"}, {"0:00.20", "0:00.60", "0:01.00"}) == (1.0, 1, 1)


# ------------------------------------------------------------------ non-caption elements in the overlay


def _extras_tl():
    """The six-page timeline plus a hook title (pages 0–1), a progress bar (whole reel), a PiP card (page 3),
    a full-screen text card (page 4) and a white flash in the middle of page 5."""
    tl = _tl()
    tl.titles = [TitleEvent(id="hook", text="Guess the sugar in this OJ", start_f=0, end_f=20)]
    tl.graphics = [GraphicEvent(id="bar", kind="progress_bar", start_f=0, end_f=60),
                   GraphicEvent(id="card", kind="text_card", start_f=40, end_f=50, text="BIG IDEA")]
    tl.pips = [PipEvent(id="pip", uri="broll/x.mov", start_f=30, end_f=40)]
    tl.flashes = [FlashEvent(id="fl", at_f=55, frames=4)]
    return tl


FACE_HIGH = [{"start_f": 0, "end_f": 60, "box": {"x": 0.3, "y": 0.15, "w": 0.4, "h": 0.25}}]  # rows 72–192 of 480


def _extras_frames(tl):
    """270x480 samples as the renderer would draw them: captions at ~66 % plus every extra element."""
    ov, bg = {}, {}
    for f in qa.page_frames(tl):
        o = np.zeros((480, 270, 4), dtype=np.uint8)
        o[310:330, 80:190] = (255, 255, 255, 255)
        o[306:310, 76:194, 3] = 255  # black outline
        o[0:3, :] = (255, 212, 0, 255)  # progress bar, 10 px
        if f < 20:  # hook title card: 60 % black box with white text, at the top (Overlay.tsx Titles)
            o[72:122, 15:237] = (0, 0, 0, 153)
            o[85:110, 40:210] = (255, 255, 255, 255)
        if 30 <= f < 40:  # PiP card, top right: x 476–930, y 260–865 px
            o[65:217, 119:233] = (128, 90, 60, 255)
        if 40 <= f < 50:  # full-screen text card under the captions
            o[..., :3] = np.where(o[..., 3:] > 0, o[..., :3], np.array([11, 13, 18], dtype=np.uint8))
            o[..., 3] = 255
            o[150:200, 40:230, :3] = 255
        ov[f] = o
        bg[f] = np.full((480, 270, 3), 40, dtype=np.uint8)
    return ov, bg


def test_titles_graphics_pips_and_cards_are_not_judged_as_captions():
    tl = _extras_tl()
    ov, bg = _extras_frames(tl)
    res = {r.gate: r for r in qa.caption_pixels_from(tl, ov, bg, FACE_HIGH, SAFE, [])}
    assert all(r.ok for r in res.values()), {g: (r.detail, r.at) for g, r in res.items()}
    assert res["safe_zone"].measured["skipped"] == ["0:01.80"]  # the text-card page: nothing to judge
    assert qa.page_frames(tl)[5] == 51  # the flash page is sampled off the flash
    # the same pixels judged without knowing about the extras fail: they were the false alarms
    bare = _tl()
    ov_bare = {f: ov[f] for f in qa.page_frames(bare) if f in ov}
    res_bare = {r.gate: r for r in qa.caption_pixels_from(bare, ov_bare, bg, FACE_HIGH, SAFE, [])}
    assert not res_bare["safe_zone"].ok and not res_bare["caption_over_face"].ok


def test_captions_drifting_onto_the_face_or_ui_zone_still_fail_among_extras():
    tl = _extras_tl()
    ov, bg = _extras_frames(tl)
    fps = qa.tb.parse_rate(tl.fps)
    clean = {r.gate: set(r.at) for r in qa.caption_pixels_from(tl, ov, bg, FACE_HIGH, SAFE, [])}
    for defect in ("captions_over_face", "captions_in_ui_zone", "captions_see_through", "captions_wrong_colour"):
        gate = ca.DEFECTS[defect]
        for trial in range(3, 6):
            mutated, changed = ca.mutate_captions(tl, ov, bg, FACE_HIGH, SAFE, defect, trial)
            res = {r.gate: r for r in qa.caption_pixels_from(tl, mutated, bg, FACE_HIGH, SAFE, [])}
            recall, _, eligible = ca.caption_recall(res[gate], clean[gate], {qa.tc(f, fps) for f in changed})
            assert eligible and recall >= ca.MIN_RECALL, (defect, trial, recall, res[gate].detail)
    # onto the face during the hook title and under the PiP: the title/PiP are masked, the caption on the face is not
    mutated, _ = ca.mutate_captions(tl, ov, bg, FACE_HIGH, SAFE, "captions_over_face", 3)
    at = set({r.gate: r for r in qa.caption_pixels_from(tl, mutated, bg, FACE_HIGH, SAFE, [])}["caption_over_face"].at)
    assert {qa.tc(5, fps), qa.tc(15, fps), qa.tc(35, fps)} <= at
    # the strip happens on copies: the decoded samples stay untouched for the next trial
    assert ov[5][90, 100, 3] == 255


def test_mask_follows_renderer_placements():
    tl = _extras_tl()
    m = qa.non_caption_mask(tl, 5, (480, 270), FACE_HIGH, SAFE)
    rows = np.nonzero(m.any(axis=1))[0]
    assert m[0:3].all() and m[72:122, 15:237].all()  # progress bar + title card
    assert not m[300:480].any()  # the caption band and bottom UI zone stay judged
    assert rows.max() < 140  # the title band stops well above the 0.45H caption floor
    assert qa.non_caption_mask(tl, 45, (480, 270), FACE_HIGH, SAFE) is None  # text card
    assert qa.non_caption_mask(tl, 55, (480, 270), FACE_HIGH, SAFE) is None  # flash
    pip = qa.non_caption_mask(tl, 35, (480, 270), FACE_HIGH, SAFE)
    assert pip[65:217, 119:233].all() and not pip[310:330, 0:100].any()
    # a cta card is full-screen; a behind-layer title is not in this overlay
    tl.graphics.append(GraphicEvent(id="cta", kind="cta_card", style="card", start_f=58, end_f=60, text="Follow"))
    tl.titles.append(TitleEvent(id="b", text="HUGE", start_f=20, end_f=30, layer="behind"))
    assert qa.non_caption_mask(tl, 59, (480, 270), FACE_HIGH, SAFE) is None
    assert not qa.non_caption_mask(tl, 25, (480, 270), FACE_HIGH, SAFE)[40:].any()


# ------------------------------------------------------------------ page sampling at peak opacity


def _fade_tl(pages, fps="25/1", anim="fade", timing="word"):
    ps = [CaptionPage(start_f=s, end_f=e, words=[CaptionWord(i=k, text="WORD", start_f=s, end_f=e)]) for k, (s, e) in enumerate(pages)]
    return Timeline(fps=fps, width=1080, height=1920, duration_f=max(e for _, e in pages) + 10, assets={}, video=[], audio=[],
                    captions=CaptionTrack(family="x", timing=timing, pages=ps,
                                          tokens={"base_color": "#FFFFFF", "stroke": "#000000", "anim": anim, "anim_ms": "150"}))


def test_pages_are_sampled_at_peak_opacity():
    # 25 fps, 150 ms → animF = 4; pages end at a gap, so they also fade out over their last 3 frames
    tl = _fade_tl([(0, 20), (30, 33), (40, 46)])
    (f0, op0), (f1, op1), (f2, op2) = qa.page_samples(tl)
    assert (f0, op0) == (10, 1.0)  # long page: the midpoint is fully opaque
    assert op1 < 1 and 30 <= f1 < 33  # 3 frames: never fully visible
    assert (f2, op2) == (43, 0.75)  # fade-in full at 44 but fade-out starts at 43: the peak is 43
    # 30 fps, 150 ms = 4.5 frames → Math.round = 5 (Python round() would say 4); back-to-back: no fade-out
    tl = _fade_tl([(0, 7), (7, 30)], fps="30/1", timing="phrase", anim="pop")
    assert qa.page_samples(tl)[0] == (5, 1.0)
    # pop / no animation: the midpoint, as before
    assert qa.page_frames(_tl()) == [5, 15, 25, 35, 45, 55]


def test_short_faded_page_is_not_called_see_through():
    tl = _fade_tl([(0, 20), (30, 34)])  # 4 frames: peaks at 1/3 opacity (frame 32)
    assert qa.page_samples(tl)[1] == (32, pytest.approx(1 / 3))
    ov, bg = {}, {}
    for f, op in qa.page_samples(tl):
        o = np.zeros((480, 270, 4), dtype=np.uint8)
        o[310:330, 80:190, :3] = 255
        o[306:310, 76:194, 3] = 255
        o[310:330, 80:190, 3] = 255
        o[..., 3] = (o[..., 3] * op).astype(np.uint8)  # what the renderer draws at that frame
        ov[f], bg[f] = o, np.full((480, 270, 3), 40, dtype=np.uint8)
    res = {r.gate: r for r in qa.caption_pixels_from(tl, ov, bg, [], SAFE, [])}
    assert all(r.ok for r in res.values()), {g: r.detail for g, r in res.items()}
    assert res["caption_contrast"].measured["partial_opacity"] == [qa.tc(qa.page_frames(tl)[1], qa.tb.parse_rate(tl.fps))]
    # a 3-frame page never gets past 1/6 opacity: nothing to judge, not a failure
    assert qa.page_samples(_fade_tl([(0, 20), (30, 33)]))[1][1] < 0.2
    # the same faintness on a page that should be fully visible is a see-through caption
    for f in ov:
        ov[f][..., 3] = (ov[f][..., 3] * 0.15).astype(np.uint8)
    assert not {r.gate: r for r in qa.caption_pixels_from(tl, ov, bg, [], SAFE, [])}["caption_contrast"].ok
