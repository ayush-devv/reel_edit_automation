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


# ------------------------------------------------------------------ motion graphics


def _g(id_, kind, frm, to, **kw):
    from reel.schemas.plan import Graphic, GraphicKind

    base = dict(id=id_, kind=GraphicKind(kind), item="k01", from_word=frm, to_word=to, text="", emoji="", value=0.0, style="", position="",
                x=-1.0, y=-1.0, reason="r")
    base.update(kw)
    return Graphic(**base)


GRAPHICS = [
    _g("g1", "emoji_pop", 7, 8, emoji="🔥", position="upper_right"),
    _g("g2", "keyword_card", 9, 10, text="one trick", style="pill"),
    _g("g3", "counter", 11, 13, text="₹{n} saved", value=12500),
    _g("g4", "callout", 7, 9, style="circle", position="face", text="me"),
    _g("g5", "progress_bar", 7, 7),
    _g("g6", "cta_card", 0, 4, item="k03", text="Follow for more", style="card"),
]


def test_graphics_compile_to_word_windows_and_validate():
    fin = _finish(graphics=GRAPHICS)
    assert not errors(validate_finish(fin, _story(), WORDS, IDX)), validate_finish(fin, _story(), WORDS, IDX)
    tl = compile_timeline(_story(), fin, WORDS, CLIPS, FPS, IDX)
    ev = {g.id: g for g in tl.graphics}
    assert ev["g5"].start_f == 0 and ev["g5"].end_f == tl.duration_f  # whole reel
    assert ev["g6"].end_f == tl.duration_f  # end card holds to the last frame
    assert ev["g2"].end_f - ev["g2"].start_f >= 36  # ≥ 1.2 s at 30 fps, even for two short words
    assert ev["g1"].accent == "#00FF00"  # caption emphasis colour when no brand accent
    assert compile_timeline(_story(), fin, WORDS, CLIPS, FPS, IDX, brand_accent="#FF0066").graphics[0].accent == "#FF0066"
    assert part(tl, FFMPEG_FIELDS) == part(_tl(), FFMPEG_FIELDS)  # graphics never re-render the base


def test_graphics_rules():
    from reel import emoji

    bad = _finish(graphics=[
        _g("b1", "counter", 7, 8, text="12500 saved", value=12500),        # no {n}
        _g("b2", "keyword_card", 7, 8, text="this is far too many words", style="pill"),
        _g("b3", "callout", 7, 8, style="circle", position="point"),     # point without x/y
        _g("b4", "cta_card", 7, 8, text="Follow"),                       # not on the last item
        _g("b5", "emoji_pop", 7, 8, emoji="ok"),                         # not an emoji
        _g("b6", "lower_third", 7, 8, text="Name", style="neon"),         # unknown style
    ])
    codes = {i.code for i in validate_finish(bad, _story(), WORDS, IDX)}
    assert {"counter_format", "graphic_text_too_long", "callout_point", "cta_not_last", "bad_style"} <= codes
    if emoji.ICON_SET.exists():
        assert "unknown_emoji" in codes
        assert emoji.name("🔥") == "fire" and emoji.name("❤️") == "red-heart" and emoji.svg_uri("🔥").startswith("data:image/svg+xml;base64,")


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + renderer")
def test_every_graphic_kind_renders_in_its_window(tmp_path):
    from reel import tools
    from reel.schemas.timeline import GraphicEvent

    kinds = [("emoji_pop", dict(emoji="🔥", position="upper_right")), ("keyword_card", dict(text="3 money rules", style="pill")),
             ("lower_third", dict(text="Asha Rao · Founder", style="bar")), ("callout", dict(style="arrow", position="point", x=0.5, y=0.5)),
             ("counter", dict(text="₹{n}", value=12500)), ("text_card", dict(text="Rule one: pay yourself first", style="dark")),
             ("cta_card", dict(text="Follow for part 2", style="card"))]
    span = 20
    events = [GraphicEvent(id=f"g{k}", kind=kind, start_f=k * span, end_f=(k + 1) * span, accent="#FFD400", **kw) for k, (kind, kw) in enumerate(kinds)]
    events.append(GraphicEvent(id="pb", kind="progress_bar", start_f=0, end_f=span * len(kinds), accent="#FFD400"))
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=span * len(kinds), assets={}, video=[], audio=[], graphics=events)
    props = overlay.build_props(tl, tmp_path, None)
    assert props["graphics"][0]["uri"].startswith("data:image/svg+xml")  # emoji resolved to a Noto SVG
    ov = tmp_path / "overlay.mov"
    overlay.render_overlay(props, ov)
    sheet = tmp_path / "sheet.png"
    # one frame from the settled middle of each window; alpha shows where something was drawn
    sel = "+".join(f"eq(n\\,{k * span + 14})" for k in range(len(kinds)))
    tools.ffmpeg(["-y", "-i", str(ov), "-vf", f"select='{sel}',alphaextract,scale=108:192,tile={len(kinds)}x1", "-frames:v", "1", "-update", "1", str(sheet)])
    raw = tools.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(sheet), "-f", "rawvideo", "-pix_fmt", "gray", "-"]).stdout
    a = np.frombuffer(raw, dtype=np.uint8).reshape(192, 108 * len(kinds)).astype(float)
    for k, (kind, _kw) in enumerate(kinds):
        drawn = (a[12:, k * 108:(k + 1) * 108] > 128).mean()  # skip the progress bar rows at the top
        assert drawn > 0.001, (kind, drawn)
    assert (a[0:2, :] > 128).mean() > 0.3  # the progress bar fills across the top
    # colour contact sheet over a test picture (for a human look: tmp_path/look.png)
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=25:d=6", "-i", str(ov), "-filter_complex",
                  f"[0][1]overlay=format=auto,select='{sel}',scale=270:480,tile={len(kinds)}x1", "-frames:v", "1", "-update", "1", str(tmp_path / "look.png")])


def test_top_band_graphics_never_share_the_band():
    fin = _finish(hook_title=HookTitle(text="One money trick", style="card", reason="r"),
                  graphics=[_g("a", "lower_third", 7, 9, text="Asha · Founder", style="bar"),  # opening line: under the hook title
                            _g("b", "keyword_card", 18, 20, item="k02", text="ten percent", style="pill"),
                            _g("c", "emoji_pop", 19, 21, item="k02", emoji="🔥", position="upper_right"),  # overlaps b in time
                            _g("d", "counter", 7, 8, text="{n}%", value=10, position="center")])  # centre: not the top band
    codes = [i.code for i in validate_finish(fin, _story(), WORDS, IDX)]
    assert codes.count("graphic_under_title") == 1 and codes.count("graphics_overlap") == 1
    assert "counter_decimals" in {i.code for i in validate_finish(_finish(graphics=[_g("e", "counter", 18, 20, item="k02", text="{n}x", value=2.255)]),
                                                                    _story(), WORDS, IDX)}


def test_point_callout_maps_source_coordinates_through_the_crop():
    from reel import framing

    # 1920x1080 source cropped to 1080x1920, crop centred on x=0.7 of the source
    shot = framing.Shot(0, (0.7, 0.5), None)
    x, y = overlay.source_point_to_output(shot, 1920, 1080, 1080, 1920, 0.7, 0.5)
    assert x == pytest.approx(0.5, abs=0.01) and y == pytest.approx(0.5, abs=0.01)  # the crop centre lands mid-frame
    fill = framing.Shot(0, (0.5, 0.5), None, layout="fill")
    fx, fy = overlay.source_point_to_output(fill, 1920, 1080, 1080, 1920, 0.25, 0.0)
    assert fx == 0.25 and fy == pytest.approx((1920 - 1080 * 1080 / 1920) / 2 / 1920, abs=0.01)  # top of the fitted picture


def test_brand_colours_must_be_hex():
    assert BrandColors(accent="#f06").accent == "#FF0066"
    with pytest.raises(Exception):
        BrandColors(accent="red")


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + renderer")
def test_top_band_graphics_step_off_a_close_up_face(tmp_path):
    from reel import tools
    from reel.schemas.timeline import GraphicEvent

    events = [GraphicEvent(id="k", kind="keyword_card", start_f=0, end_f=40, text="Which half are you", style="under", accent="#FFD400"),
              GraphicEvent(id="c", kind="counter", start_f=40, end_f=90, text="{n} teaspoons", value=8, accent="#FFD400")]
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=90, assets={}, video=[], audio=[], graphics=events)
    props = overlay.build_props(tl, tmp_path, None)
    props["faces"] = [{"start_f": 0, "end_f": 90, "box": {"x": 0.25, "y": 0.10, "w": 0.5, "h": 0.30}, "text": []}]  # tight close-up, high in frame
    ov = tmp_path / "ov.mov"
    overlay.render_overlay(props, ov)
    raw = tools.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(ov), "-vf", "select='eq(n\\,30)+eq(n\\,80)',alphaextract,scale=108:192",
                     "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"]).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 192, 108)
    for a in frames:
        face_rows = a[int(0.10 * 192):int(0.40 * 192), 27:81]
        assert (face_rows > 128).mean() < 0.01  # nothing drawn on the face
        assert (a[int(0.40 * 192):int(0.58 * 192)] > 128).mean() > 0.01  # the graphic moved below it, above the captions


def test_counter_lands_on_the_word_that_says_the_number():
    fin = _finish(graphics=[_g("c", "counter", 7, 11, text="{n} teaspoons", value=8)])
    tl = compile_timeline(_story(), fin, WORDS, CLIPS, FPS, IDX)
    g = tl.graphics[0]
    k01 = next(c for c in tl.video if c.id == "v_k01")
    by = WORDS.by_index()
    from reel import timebase as tb

    said = k01.at_f + tb.us_to_frame(by[11].start_us, FPS, mode="floor") - tb.us_to_frame(k01.src_in_us, FPS)
    assert abs(g.count_end_f - said) <= 1 and g.end_f >= g.count_end_f + 30  # reaches 8 on word 11, then holds ≥ 1 s
