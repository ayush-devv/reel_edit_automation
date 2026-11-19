import numpy as np

from reel import calibrate_auto as ca
from reel import qa
from reel.schemas.timeline import CaptionPage, CaptionTrack, CaptionWord, Timeline


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
    for defect in ("captions_over_face", "captions_in_ui_zone", "captions_see_through"):
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


def test_promotion_rule():
    good = [{"reel": f"r{k}", "failed": [], "detail": {}} for k in range(6)]
    good[0]["failed"] = ["frozen"]
    bad = {"black_stretch": [{"caught": True, "valid": True}] * 10,
           "frozen_stretch": [{"caught": True, "valid": True}] * 10,
           "loudness_low": [{"caught": True, "valid": True}] * 9 + [{"caught": False, "valid": True}],
           "captions_over_face": [{"caught": True, "valid": True}] * 10}
    rep = ca.report(good, bad)["gates"]
    assert rep["black"]["promote_to_block"] is True
    assert rep["frozen"]["promote_to_block"] is False and rep["frozen"]["false_alarms"] == 1  # a false alarm on a pro final
    assert rep["caption_over_face"]["promote_to_block"] is False and "note" in rep["caption_over_face"]  # no known-good check possible
    assert rep["loudness"]["catch_rate"] == 0.9
