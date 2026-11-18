"""Build step 10a: NLE package — captions files, FCPXML on the frame grid, OTIO round trip, edit list."""

from fractions import Fraction
from xml.etree import ElementTree as ET

import pytest

from reel import config, package
from reel.compile import compile_timeline
from reel.conformance import corpus
from reel.mezzanine import make_mezzanine
from reel.probe import probe
from reel.schemas.timeline import Asset, AssetKind

from test_plan_compile import CLIPS, FPS, IDX, WORDS, _finish, _story


def test_srt_and_vtt_timing():
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    srt, vtt = package.srt(tl), package.vtt(tl)
    first = tl.captions.pages[0]
    assert srt.startswith("1\n" + package._ts(first.start_f, FPS, ",") + " --> ")
    assert vtt.startswith("WEBVTT\n\n") and srt.count(" --> ") == vtt.count(" --> ") == len(tl.captions.pages)
    assert package._ts(45, Fraction(30), ",") == "00:00:01,500"


def test_edit_list_carries_reasons():
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    md = package.edit_list(tl, _story(), _finish(), WORDS)
    assert md.count("| k0") == 3 and "**Look** `clean`" in md and "**Punch-in** p01" in md


try:
    config.ffmpeg_path()
    import opentimelineio  # noqa: F401

    READY = True
except Exception:  # noqa: BLE001
    READY = False


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + opentimelineio")
def test_fcpxml_and_otio_on_the_frame_grid(tmp_path):
    import opentimelineio as otio

    src = corpus.build(tmp_path / "src", ["cfr25_portrait"])[0]
    for cid in ("c01", "c02"):
        mezz = tmp_path / "mezz" / f"{cid}.mov"
        mezz.parent.mkdir(exist_ok=True)
        make_mezzanine(probe(src), mezz, Fraction(30))
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    for cid in ("c01", "c02"):
        tl.assets[cid] = Asset(id=cid, kind=AssetKind.video, uri=f"mezz/{cid}.mov", duration_us=4_000_000)
    pkg = tmp_path / "export" / "package"
    doc = ET.fromstring(package.fcpxml(tl, tmp_path, pkg, "t").split("\n", 2)[2])
    spine = doc.find(".//spine")
    clips = spine.findall("asset-clip")
    assert len(clips) == 3
    end = 0
    for c in clips:  # back to back, every time a whole number of frames
        off, dur = (Fraction(c.get(k)[:-1]) for k in ("offset", "duration"))
        assert off == end and (off * FPS).denominator == 1 and (dur * FPS).denominator == 1
        end = off + dur
    assert end * FPS == tl.duration_f
    assert clips[0].find("asset-clip[@lane='1']") is not None  # overlay connected on top
    t = package.otio_timeline(tl, tmp_path, pkg, "t")
    path = tmp_path / "t.otio"
    otio.adapters.write_to_file(t, str(path))
    back = otio.adapters.read_from_file(str(path))
    assert back.video_tracks()[0].duration().to_frames() == tl.duration_f
    assert len(back.audio_tracks()) == 4 and not back.audio_tracks()[1].enabled


def test_variant_crop_keeps_face_then_burned_in_text():
    from reel.variants import crop_y

    face = {"x": 0.4, "y": 0.30, "w": 0.2, "h": 0.12}
    banner = {"x": 0.1, "y": 0.04, "w": 0.8, "h": 0.04}
    y = crop_y({"faces": [{"box": face, "text": []}]}, 1920, 1350)
    assert y <= face["y"] * 1920 and y + 1350 >= (face["y"] + face["h"]) * 1920
    y2 = crop_y({"faces": [{"box": face, "text": [banner]}]}, 1920, 1350)
    assert y2 <= banner["y"] * 1920 and y2 + 1350 >= (face["y"] + face["h"]) * 1920  # both fit → both kept
    low_face = {"x": 0.4, "y": 0.80, "w": 0.2, "h": 0.12}
    y3 = crop_y({"faces": [{"box": low_face, "text": [banner]}]}, 1920, 1080)
    assert y3 + 1080 >= (low_face["y"] + low_face["h"]) * 1920  # can't keep both → face wins
    assert crop_y({"faces": [{"box": None, "text": [banner]}]}, 1920, 1350) <= banner["y"] * 1920


def test_client_notes_parse_and_anchor():
    from reel import notes

    parsed = notes.parse("0:01 make this faster\n- 00:00:02.5 - remove the um\n3s: bigger captions\n[0:04] cut this\nLove the colours overall")
    assert [(n.t, n.text) for n in parsed] == [(1.0, "make this faster"), (2.5, "remove the um"), (3.0, "bigger captions"),
                                                (4.0, "cut this"), (None, "Love the colours overall")]
    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, FPS, IDX)
    req = notes.revision_request(parsed[:1] + parsed[-1:], tl, _story(), WORDS)
    assert "item k01 (hook" in req and "make this faster" in req and "(whole reel) Love the colours" in req
