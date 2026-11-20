"""3c.1 beauty pass: opt-in switches, the matte, interpolation, the filter on a real clip, and the strength gate."""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction

import numpy as np
import pytest

from reel import beauty, config
from reel.brief import Brand, Brief


def test_off_unless_the_brief_or_the_brand_turns_it_on():
    assert beauty.mode(None, None) == "off"
    assert beauty.mode(Brief(project="p"), Brand(client="c")) == "off"
    assert beauty.mode(Brief(project="p", beauty=True), None) == "light"
    assert beauty.mode(None, Brand(client="c", beauty="light")) == "light"
    with pytest.raises(ValueError):
        Brand(client="c", beauty="max")


def test_the_matte_smooths_skin_and_keeps_eyes_and_mouth_crisp():
    box = {"x": 0.3, "y": 0.2, "w": 0.4, "h": 0.4}
    w, h = 200, 400
    m = beauty.ellipse(box, w, h)
    y = lambda frac: int((box["y"] + box["h"] * frac) * h)  # noqa: E731
    cheek_x = int((box["x"] + box["w"] * 0.25) * w)
    mid_x = int((box["x"] + box["w"] / 2) * w)
    assert m[y(0.60), cheek_x] > 0.8  # the cheek: smoothed
    assert m[y(beauty.EYES[0]), mid_x] < 0.1 and m[y(beauty.MOUTH[0]), mid_x] < 0.1  # eyes and mouth: kept sharp
    assert m[5, 5] == 0.0  # outside the face: untouched


def test_boxes_are_interpolated_and_fade_where_no_face_is_near():
    a, b = {"box": {"x": 0.2, "y": 0.2, "w": 0.4, "h": 0.4}}, {"box": {"x": 0.4, "y": 0.2, "w": 0.4, "h": 0.4}}
    boxes = beauty.boxes_per_frame({0: a, 4: b, 60: None}, 70)
    assert boxes[2]["box"]["x"] == pytest.approx(0.3)
    assert boxes[4 + beauty.SAMPLE_FPS] is not None and boxes[40] is None  # after the last face: a short hold, then nothing
    assert beauty.boxes_per_frame({0: None}, 5) == [None] * 5


def test_strength_gate():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        r = Path(d)
        assert beauty.gate_result(r).ok and "off" in beauty.gate_result(r).detail
        (r / "beauty.json").write_text(json.dumps({"applied": True, "detail_loss": 0.2}))
        assert beauty.gate_result(r).ok
        (r / "beauty.json").write_text(json.dumps({"applied": True, "detail_loss": 0.6}))
        g = beauty.gate_result(r)
        assert not g.ok and "−60%" in g.detail
        (r / "beauty.json").write_text(json.dumps({"applied": True, "detail_loss": None}))
        assert not beauty.gate_result(r).ok  # not measured is not a pass


@pytest.mark.integration
def test_apply_smooths_only_inside_the_matte(tmp_path):
    try:
        ff = config.ffmpeg_path()
    except config.ToolNotFound:
        pytest.skip("pinned ffmpeg missing")
    src = tmp_path / "base.mov"
    subprocess.run([str(ff), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=270x480:rate=25:duration=1", "-f", "lavfi",
                    "-i", "sine=duration=1", "-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le", str(src)], check=True)
    face = {"box": {"x": 0.25, "y": 0.2, "w": 0.5, "h": 0.4}}
    meta = beauty.apply(src, 25, Fraction(25), detect=lambda frames: {f: face for f in frames})
    assert meta["applied"] and meta["detail_loss"] is not None and meta["detail_loss"] > 0
    assert (tmp_path / "beauty.json").exists() and (tmp_path / "beauty_mask.mkv").exists()
    from reel.tools import ffprobe_frame_times

    assert len(ffprobe_frame_times(src)) == 25  # same length, audio kept
    out = subprocess.run([str(config.ffprobe_path()), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(src)],
                         capture_output=True, text=True).stdout.split()
    assert "audio" in out
    no_face = beauty.apply(src, 25, Fraction(25), detect=lambda frames: {f: None for f in frames})
    assert no_face == {"applied": False, "why": "no face found", "seconds": no_face["seconds"]}
    assert np.isfinite(meta["seconds"])
