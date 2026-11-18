"""Build step 6: overlay events in the compiler, brand precedence, hook-title rules, owner-split
hashes, burned-in text zones; overlay render + composite (integration, needs node + Remotion)."""

from fractions import Fraction

import numpy as np
import pytest

from reel import config, overlay, render
from reel import timebase as tb
from reel.brief import Brand, BrandColors, brand_caption_overrides
from reel.compile import compile_timeline
from reel.conformance import corpus
from reel.mezzanine import make_mezzanine
from reel.perception.audio import read_frames
from reel.probe import probe
from reel.schemas.plan import HookTitle, Transition, TransitionType
from reel.schemas.timeline import FFMPEG_FIELDS, REMOTION_FIELDS, Asset, AssetKind, AudioClip, CaptionPage, CaptionTrack, CaptionWord, Provenance, Timeline, TitleEvent, VideoClip, part
from reel.validate import errors, validate_finish

from test_plan_compile import CLIPS, FPS, IDX, WORDS, _finish, _story


def _tl(**kw):
    return compile_timeline(_story(), _finish(**kw), WORDS, CLIPS, FPS, IDX)


def test_flash_is_an_overlay_event_other_transitions_stay_ffmpeg():
    tl = _tl(transitions=[Transition(id="t1", after_item="k01", type=TransitionType.flash, frames=4, reason="r"),
                          Transition(id="t2", after_item="k02", type=TransitionType.whip, frames=6, reason="r")])
    cut = tl.video[0].at_f + tl.video[0].dur_f
    assert [(f.id, f.at_f) for f in tl.flashes] == [("t1", cut)]
    assert [t.id for t in tl.transitions] == ["t2"]


def test_hook_title_spans_the_opening_line_within_limits():
    tl = _tl(hook_title=HookTitle(text="  One trick, every month ", style="card", reason="r"))
    (t,) = tl.titles
    assert t.text == "One trick, every month" and t.start_f == 0
    assert tb.us_to_frame(1_500_000, FPS, mode="ceil") <= t.end_f <= tb.us_to_frame(3_000_000, FPS)
    assert _tl().titles == []  # "" = no title


def test_brand_kit_beats_editor_tokens_and_locks_family():
    brand = Brand(client="acme", colors=BrandColors(accent="#FF0066", text="#FAFAFA"), fonts={"heading": "Plus Jakarta Sans"},
                  caption_family="clean_phrase", caption_tokens={"box_color": "#112233CC"})
    fam, toks = brand_caption_overrides(brand)
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX, brand_family=fam, brand_tokens=toks)
    c = tl.captions
    assert c.family == "clean_phrase"
    assert c.tokens["emph_color"] == "#FF0066" and c.tokens["base_color"] == "#FAFAFA" and c.tokens["box_color"] == "#112233CC"
    assert c.tokens["font"] == "Plus Jakarta Sans" and c.tokens["box"] == "true"  # family default kept
    assert max(len(p.words) for p in c.pages) <= IDX.caption_families["clean_phrase"]["max_words"]
    # without a lock the Editor's token override applies
    assert _tl().captions.tokens["emph_color"] == "#00FF00"


def test_hook_title_rules():
    long = _finish(hook_title=HookTitle(text="this title is far too long for anyone to read quickly", style="card", reason="r"))
    assert any(i.code == "title_too_long" for i in validate_finish(long, _story(), WORDS, IDX))
    words = WORDS.model_copy(deep=True)
    words.words[3] = words.words[3].model_copy(update={"text": "Dioma", "original_text": "Dioma", "vocab_suspect": True})
    bad = _finish(hook_title=HookTitle(text="Dioma money tip", style="card", reason="r"))
    assert any(i.code == "title_unconfirmed_name" for i in validate_finish(bad, _story(), words, IDX))
    assert not errors(validate_finish(_finish(hook_title=HookTitle(text="One money trick", style="card", reason="r")), _story(), WORDS, IDX))


def test_caption_only_change_leaves_the_base_slice_unchanged():
    a = _tl()
    b = _tl(hook_title=HookTitle(text="New title", style="card", reason="r"))
    assert part(a, FFMPEG_FIELDS) == part(b, FFMPEG_FIELDS)
    assert part(a, REMOTION_FIELDS) != part(b, REMOTION_FIELDS)


def test_text_zones_keep_persistent_text_only_in_output_coords():
    ocr = {"c01": {"items": [
        *({"t_us": t, "text": "Brand Tips", "score": 0.99, "box": [0.2, 0.10, 0.8, 0.15]} for t in range(0, 5_000_000, 1_000_000)),
        {"t_us": 0, "text": "00:00:01", "score": 0.99, "box": [0.0, 0.0, 0.1, 0.02]},     # timecode: no letters
        {"t_us": 0, "text": "Flicker", "score": 0.99, "box": [0.1, 0.8, 0.3, 0.85]},      # seen once in 5 samples
    ]}}
    zones = overlay.text_zones(ocr, "c01", 720, 1280, 1080, 1920, None)
    assert len(zones) == 1
    z = zones[0]
    assert z["x"] == pytest.approx(0.2, abs=0.01) and z["y"] == pytest.approx(0.10, abs=0.01) and z["h"] == pytest.approx(0.05, abs=0.01)


# ------------------------------------------------------------------ integration: Remotion + composite

try:
    config.ffmpeg_path()
    READY = overlay.available()
except config.ToolNotFound:
    READY = False


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + renderer/node_modules")
def test_overlay_composite_keeps_base_outside_the_text(tmp_path):
    src = corpus.build(tmp_path / "src", ["cfr25_portrait"])[0]
    fps = Fraction(25)
    mezz = tmp_path / "mezz" / "c01.mov"
    mezz.parent.mkdir()
    make_mezzanine(probe(src), mezz, fps)
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=40,
                  assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=40, src_in_us=0, src_out_us=1_600_000, src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=40, src_in_us=0, role="voice", src=prov)],
                  captions=CaptionTrack(family="bold_pop", tokens={"font": "Inter Black", "weight": "900", "case": "upper", "base_color": "#FFFFFF",
                                                                   "emph_color": "#FFD400", "highlight": "word", "anim": "pop", "zone": "lower_middle", "stroke": "true"},
                                        pages=[CaptionPage(start_f=0, end_f=40, words=[CaptionWord(i=0, text="SAVE", start_f=0, end_f=20),
                                                                                       CaptionWord(i=1, text="MONEY", start_f=20, end_f=40, emph=True)])]),
                  titles=[TitleEvent(id="hook_title", text="One trick", start_f=0, end_f=40)])
    base = tmp_path / "render" / "base.mov"
    render.render_base(tl, tmp_path, base)
    ov = tmp_path / "render" / "overlay.mov"
    overlay.render_overlay(overlay.build_props(tl, tmp_path, None), ov)
    final = tmp_path / "render" / "final.mp4"
    meta = overlay.composite(tl, base, ov, final)
    assert meta["frames"] == 40 and meta["size"] == "1080x1920"

    def frame(path):  # one mid frame, full size, RGB
        frames, h, w = read_frames(path, fps=1.0, width=1080)
        return frames[0].astype(int)

    b, f = frame(base), frame(final)
    bottom = np.abs(b[1650:1900] - f[1650:1900]).mean()      # below captions: untouched (codec noise only)
    caption = np.abs(b[1150:1300] - f[1150:1300]).mean()     # caption band: changed
    assert bottom < 4.0 and caption > 10.0, (bottom, caption)


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + renderer")
def test_adaptive_tokens_fix_illegible_captions_but_respect_brand(tmp_path):
    from reel import adapt, tools

    mezz = tmp_path / "mezz" / "c01.mov"
    mezz.parent.mkdir()
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "color=c=#FFF200:s=720x1280:r=25:d=2", "-c:v", "prores_ks", "-pix_fmt", "yuv422p10le", str(mezz)])
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=50, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=50, src_in_us=0, src_out_us=2_000_000, src=prov)], audio=[],
                  captions=CaptionTrack(family="bold_pop", tokens={"base_color": "#FFFFFF", "emph_color": "#FFD400", "stroke": "false"},
                                        pages=[CaptionPage(start_f=0, end_f=40, words=[CaptionWord(i=0, text="SAVE", start_f=0, end_f=40)])]))
    out, changes = adapt.adapt(tl, tmp_path, palette=["#146C7F", "#E3E706"], locked=set())
    t = out.captions.tokens
    assert t["stroke"] == "#000000" and t["emph_color"] != "#FFD400" and len(changes) == 2  # white/yellow on yellow
    kept, _ = adapt.adapt(tl, tmp_path, palette=[], locked={"emph_color", "stroke"})
    assert kept.captions.tokens == tl.captions.tokens  # brand-locked: untouched
