"""Build step 10e: client b-roll — index (fake describer), validation, compile, full-frame render, PiP overlay."""

from fractions import Fraction

import numpy as np
import pytest

from reel import broll, config, overlay, qa, render, tools
from reel import timebase as tb
from reel.claude_call import CallResult
from reel.compile import compile_timeline
from reel.conformance import checks, corpus
from reel.mezzanine import make_mezzanine
from reel.probe import probe
from reel.schemas.plan import Broll
from reel.schemas.timeline import Asset, AssetKind, AudioClip, PipEvent, Provenance, Timeline, VideoClip
from reel.validate import validate_finish
from reel.workspace import Workspace

from test_plan_compile import CLIPS, FPS, IDX, WORDS, _finish, _story

IDX.broll["b_jar"] = {"id": "b_jar", "file": "broll/mezz/b_jar.mov", "duration_ms": 4000, "best_at": "end", "description": "coins into a jar"}


def test_best_moment_and_too_short_validation():
    assert broll.best_src_in_us({"duration_ms": 4000, "best_at": "end"}, 1_000_000) == 3_000_000
    assert broll.best_src_in_us({"duration_ms": 4000, "best_at": "middle"}, 1_000_000) == 1_500_000
    assert broll.best_src_in_us({"duration_ms": 500}, 1_000_000) == 0
    short = dict(IDX.broll["b_jar"], duration_ms=300)
    IDX.broll["b_short"] = short
    fin = _finish(broll=[Broll(id="b1", asset="b_short", item="k02", from_word=18, to_word=24, mode="full", reason="r")])
    assert any(i.code == "broll_too_short" for i in validate_finish(fin, _story(), WORDS, IDX))


def test_compile_full_into_base_and_pip_into_overlay():
    fin = _finish(broll=[Broll(id="b1", asset="b_jar", item="k02", from_word=18, to_word=20, mode="full", reason="r"),
                         Broll(id="b2", asset="b_jar", item="k02", from_word=22, to_word=24, mode="pip", reason="r")])
    tl = compile_timeline(_story(), fin, WORDS, CLIPS, FPS, IDX)
    full = next(c for c in tl.video if c.id == "br_b1")
    assert full.asset == "b_jar" and tl.assets["b_jar"].uri == "broll/mezz/b_jar.mov"
    assert full.src_in_us == 4_000_000 - tb.frame_to_us(full.dur_f, FPS)  # best moment at the end
    (pip,) = tl.pips
    assert pip.id == "b2" and pip.end_f > pip.start_f and not any(c.id == "br_b2" for c in tl.video)


try:
    config.ffmpeg_path()
    READY = True
except config.ToolNotFound:
    READY = False


def _red_clip(path, seconds=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", f"color=c=red:s=720x1280:r=25:d={seconds}", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                  "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)])
    return path


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_index_conforms_and_merges_descriptions(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    folder = tmp_path / "client_broll"
    _red_clip(folder / "red jar.mp4")

    def fake(prompt, schema, **kw):
        clip_id = broll._id(folder / "red jar.mp4")
        return CallResult(data={"clips": [{"id": clip_id, "description": "red frame", "subjects": ["red"], "shot": "wide",
                                           "motion": "static", "mood": "bold", "best_at": "middle"}]},
                          session_id="s", num_turns=1, cost_usd=0.0, usage={}, duration_s=0.0)

    meta = broll.index(ws, folder, Fraction(25), fake)
    from reel import project

    idx = project.indexes(ws)
    (clip,) = idx.broll.values()
    assert meta == {"clips": 1, "described": 1} and clip["description"] == "red frame" and clip["source"] == "client"
    assert (ws.root / clip["file"]).exists() and (ws.root / clip["sheet"]).exists() and clip["duration_ms"] == 3000


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_full_frame_broll_replaces_picture_only_in_its_slot(tmp_path):
    src = corpus.build(tmp_path / "src", ["cfr25_portrait"])[0]
    mezz = tmp_path / "mezz" / "c01.mov"
    mezz.parent.mkdir()
    make_mezzanine(probe(src), mezz, Fraction(25))
    bmezz = tmp_path / "broll" / "mezz" / "b_red.mov"
    bmezz.parent.mkdir(parents=True, exist_ok=True)
    make_mezzanine(probe(_red_clip(tmp_path / "raw" / "red.mp4")), bmezz, Fraction(25))
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=75,
                  assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov"),
                          "b_red": Asset(id="b_red", kind=AssetKind.video, uri="broll/mezz/b_red.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=75, src_in_us=0, src_out_us=3_000_000, src=prov),
                         VideoClip(id="br_b1", asset="b_red", at_f=20, dur_f=15, src_in_us=500_000, src_out_us=1_100_000, src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=75, src_in_us=0, role="voice", src=prov)])
    out = tmp_path / "base.mp4"
    meta = render.render_base(tl, tmp_path, out, finish_audio=False)
    assert meta["frames"] == 75
    fr = qa.frames_at(out, [10, 19, 20, 27, 34, 35, 50])
    red = {f: (img[..., 0].mean() > 200 and img[..., 1].mean() < 60) for f, img in fr.items()}
    assert red == {10: False, 19: False, 20: True, 27: True, 34: True, 35: False, 50: False}, red
    assert checks.beep_time(out) == pytest.approx(2.0, abs=0.01)  # voice untouched under the b-roll


@pytest.mark.integration
@pytest.mark.skipif(not (READY and overlay.available()), reason="needs ffmpeg + renderer")
def test_pip_card_renders_in_the_overlay(tmp_path):
    bmezz = tmp_path / "broll" / "mezz" / "b_red.mov"
    bmezz.parent.mkdir(parents=True, exist_ok=True)
    make_mezzanine(probe(_red_clip(tmp_path / "raw" / "red.mp4")), bmezz, Fraction(25))
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=40, assets={}, video=[], audio=[],
                  pips=[PipEvent(id="p1", uri="broll/mezz/b_red.mov", start_f=10, end_f=30)])
    props = {"fps": 25.0, "width": 1080, "height": 1920, "duration_f": 40, "captions": None, "titles": [], "flashes": [],
             "pips": [p.model_dump() for p in tl.pips], "faces": [], "safe": overlay.SAFE}
    ov = tmp_path / "overlay.mov"
    overlay.render_overlay(props, ov, public_dir=tmp_path)
    fr = qa.frames_at(ov, [5, 20, 35], alpha=True)
    card = lambda img: img[300:700, 600:950]  # noqa: E731  top-right card area (sampled at 270 px wide → scale)
    a = {f: float((img[..., 3] > 200).mean()) for f, img in fr.items()}
    assert a[5] == 0 and a[35] == 0 and a[20] > 0.05, a
    mid = fr[20]
    red = mid[(mid[..., 3] > 250)][:, :3].mean(axis=0)
    assert red[0] > 180 and red[1] < 90, red


def test_reference_look_rules_and_style_md():
    from reel import reference

    assert reference.suggest_look({"black_level": 0.12, "saturation": 0.2, "contrast": 0.2, "warmth": 0.0})[0] == "film"
    assert reference.suggest_look({"black_level": 0.0, "saturation": 0.6, "contrast": 0.3, "warmth": 0.0})[0] == "punchy"
    assert reference.suggest_look({"black_level": 0.0, "saturation": 0.3, "contrast": 0.2, "warmth": 0.1})[0] == "warm"
    md = reference.style_md({"duration_s": 22.0, "shots": 11, "avg_shot_s": 2.0, "cuts_per_min": 27.3, "motion": 8.1,
                             "colour": {"mean_luma": 0.4, "contrast": 0.2, "saturation": 0.3, "warmth": 0.02, "black_level": 0.01},
                             "captions": {"on_screen_share": 0.9, "words_per_block": 3, "upper_share": 0.95, "y_centre": 0.66,
                                          "light_text": True, "boxed": False},
                             "speech": {"words": 60, "words_per_s": 2.7, "talk_share": 0.85}, "look": "clean", "look_strength": 0.4, "sheets": ["reference/sheets/ref_01.png"]})
    assert "27.3 cuts/min" in md and "UPPER CASE" in md and "lower part" in md and "`clean`" in md and "2.7 words/s" in md


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + perception extra")
def test_reference_analysis_measures_cuts_and_captions(tmp_path):
    from reel import reference

    ref = tmp_path / "ref.mp4"
    font = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    cap = f"drawtext=fontfile='{font}':text='SAVE MORE MONEY':fontsize=64:fontcolor=white:x=(w-tw)/2:y=h*0.65"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "color=c=red:s=720x1280:r=25:d=2", "-f", "lavfi", "-i", "color=c=blue:s=720x1280:r=25:d=2",
                  "-f", "lavfi", "-i", "color=c=green:s=720x1280:r=25:d=2",
                  "-filter_complex", f"[0:v][1:v][2:v]concat=n=3:v=1:a=0,{cap}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(ref)])
    ws = Workspace.create(tmp_path / "p")
    reference.analyse(ws, ref)
    import json

    prof = json.loads(ws.path("reference", "style.json").read_text())
    assert prof["shots"] == 3 and prof["captions"]["upper_share"] > 0.9 and 0.6 < prof["captions"]["y_centre"] < 0.75
    assert prof["captions"]["light_text"] is True and ws.path("context", "reference_style.md").exists()


@pytest.mark.integration
@pytest.mark.skipif(not (READY and overlay.available()), reason="needs ffmpeg + renderer")
def test_text_behind_subject_goes_behind_the_person(tmp_path):
    from reel import matte
    from reel.schemas.timeline import TitleEvent

    src = tmp_path / "raw" / "scene.mp4"
    src.parent.mkdir()
    # blue background, a green "person" block in the middle of the frame
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "color=c=blue:s=720x1280:r=25:d=2", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                  "-vf", "drawbox=x=240:y=300:w=240:h=700:color=lime:t=fill", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", str(src)])
    mezz = tmp_path / "mezz" / "c01.mov"
    mezz.parent.mkdir()
    make_mezzanine(probe(src), mezz, Fraction(25))
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=50, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=50, src_in_us=0, src_out_us=2_000_000, src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=50, src_in_us=0, role="voice", src=prov)],
                  titles=[TitleEvent(id="hook_title", text="SAVE", start_f=0, end_f=40, layer="behind")])
    base = tmp_path / "render" / "base.mov"
    render.render_base(tl, tmp_path, base)
    faces = {"c01": {"median_box": {"x": 0.38, "y": 0.30, "w": 0.24, "h": 0.15}}}
    props = overlay.build_props(tl, tmp_path, faces)
    overlay.render_overlay(props, tmp_path / "render" / "overlay.mov")
    overlay.render_overlay(props | {"layer": "behind"}, tmp_path / "render" / "behind.mov", frames=(0, 39))

    def green_mask(frames):  # stands in for the segmenter: the lime block is "the person"
        f = frames.astype(int)
        return ((f[..., 1] > 150) & (f[..., 2] < 100)).astype(np.float32)

    m = matte.make_matte(base, 0, 40, tmp_path / "render" / "matte.mkv", (1080, 1920), "25/1", masker=green_mask)
    assert m["frames"] == 40 and m["person_share"] > 0.05
    final = tmp_path / "render" / "final.mp4"
    meta = overlay.composite(tl, base, tmp_path / "render" / "overlay.mov", final,
                             behind={"layer": tmp_path / "render" / "behind.mov", "matte": tmp_path / "render" / "matte.mkv", "start_f": 0, "end_f": 40})
    assert meta["frames"] == 50 and meta["behind_title"]
    with_title, after = qa.frames_at(final, [30, 45]).values()
    h, w = with_title.shape[:2]
    band = slice(int(0.26 * h), int(0.34 * h))  # the title band, inside the person block vertically
    person = with_title[band, int(0.40 * w):int(0.60 * w)].reshape(-1, 3).astype(int)
    bg = with_title[band, int(0.02 * w):int(0.30 * w)].reshape(-1, 3).astype(int)
    blue_bg = ((bg[:, 2] > 150) & (bg[:, 0] < 80)).mean()
    assert ((person[:, 1] > 150) & (person[:, 2] < 100)).mean() > 0.9  # the person stays in front of the title
    assert blue_bg < 0.9  # the title covers part of the background
    assert ((after[band, int(0.02 * w):int(0.30 * w)].reshape(-1, 3)[:, 2] > 150).mean()) > 0.95  # gone after the window


def test_stock_search_picks_portrait_renditions_and_writes_licence(tmp_path):
    import json as _json

    from reel import stock

    api = {"videos": [
        {"id": 1, "duration": 8, "url": "https://pexels.com/v/1", "user": {"name": "Ana"},
         "video_files": [{"link": "https://x/1_hd.mp4", "width": 1080, "height": 1920}, {"link": "https://x/1_sd.mp4", "width": 540, "height": 960},
                         {"link": "https://x/1_4k.mp4", "width": 2160, "height": 3840}]},
        {"id": 2, "duration": 90, "url": "https://pexels.com/v/2", "user": {"name": "Bo"},
         "video_files": [{"link": "https://x/2.mp4", "width": 1080, "height": 1920}]},  # too long for a cutaway
    ]}
    calls = []

    def fetch(url, key):
        calls.append(url)
        return _json.dumps(api).encode() if "api.pexels.com" in url else b"MP4DATA"

    with pytest.raises(stock.StockError):
        stock.search("coins jar", key="", fetch=fetch)
    res = stock.search("coins jar", key="k", fetch=fetch)
    assert [r["id"] for r in res] == [1] and res[0]["url"] == "https://x/1_hd.mp4"  # smallest portrait ≥ 1280 tall
    (path,) = stock.download(res, tmp_path / "stock", "coins jar", key="k", fetch=fetch)
    side = _json.loads(path.with_suffix(".json").read_text())
    assert path.read_bytes() == b"MP4DATA" and side["source"] == "Pexels" and "no attribution" in side["license"]
