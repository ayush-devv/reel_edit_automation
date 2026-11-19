"""Partial re-render (roadmap G1.5): splicing a re-rendered stretch gives the same frames as a full render."""

from __future__ import annotations

from fractions import Fraction

import pytest

from reel import config, overlay, rediff, splice, tools
from reel.schemas.timeline import GraphicEvent, Timeline

from test_overlay import READY

FPS = Fraction(30)


def _tl(second_text: str) -> Timeline:
    g = [GraphicEvent(id="g1", kind="keyword_card", start_f=5, end_f=25, text="First", style="pill", position="upper"),
         GraphicEvent(id="g2", kind="keyword_card", start_f=40, end_f=55, text=second_text, style="pill", position="upper")]
    return Timeline(fps="30/1", width=270, height=480, duration_f=60, assets={}, video=[], audio=[], graphics=g)


def _md5s(path) -> list[str]:
    out = tools.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(path), "-f", "framemd5", "-"]).stdout.decode()
    return [line.rsplit(",", 1)[-1].strip() for line in out.splitlines() if line and not line.startswith("#")]


def test_kept_ranges_surround_the_chunks(tmp_path):
    c = tmp_path / "c.mov"
    assert splice.kept_ranges([(28, 59, c)], 60) == [(0, 28)]
    assert splice.kept_ranges([(10, 19, c)], 60) == [(0, 10), (20, 60)]
    assert splice.kept_ranges([(0, 4, c), (30, 39, c)], 60) == [(5, 30), (40, 60)]


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + renderer")
def test_spliced_overlay_matches_a_full_render(tmp_path):
    a, b = overlay.build_props(_tl("Second"), tmp_path, None), overlay.build_props(_tl("Changed"), tmp_path, None)
    ranges = rediff.changed_ranges(a, b)
    assert ranges == [(28, 59)]
    ov_a, ov_b = tmp_path / "a.mov", tmp_path / "b.mov"
    overlay.render_overlay(a, ov_a)
    overlay.render_overlay(b, ov_b)  # the reference: B rendered in full
    chunk = tmp_path / "chunk.mov"
    overlay.render_overlay(b, chunk, frames=ranges[0])
    out = tmp_path / "spliced.mov"
    splice.splice(ov_a, [(*ranges[0], chunk)], out, total_f=60, fps=FPS)
    full, part = _md5s(ov_b), _md5s(out)
    assert len(part) == 60 and part == full  # every frame identical to the full render
    assert _md5s(ov_a)[:28] == part[:28] and _md5s(ov_a)[40:] != part[40:]


def test_a_bad_chunk_is_refused(tmp_path):
    pytest.importorskip("numpy")
    if not READY:
        pytest.skip("needs pinned ffmpeg")
    prores = ["-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le"]  # one flavour, like the real renders
    src = tmp_path / "src.mov"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30:duration=2", *prores, str(src)])
    short = tmp_path / "short.mov"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30:duration=0.2", *prores, str(short)])
    with pytest.raises(RuntimeError, match="frames"):
        splice.splice(src, [(10, 29, short)], tmp_path / "out.mov", total_f=60, fps=FPS)  # 6 frames for a 20-frame gap
    other = tmp_path / "other.mov"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=30", "-frames:v", "20", "-c:v", "prores_ks", "-profile:v", "3", str(other)])
    with pytest.raises(RuntimeError, match="the movie is"):
        splice.splice(src, [(10, 29, other)], tmp_path / "out.mov", total_f=60, fps=FPS)  # a different ProRes flavour
    good = tmp_path / "good.mov"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=30", "-frames:v", "20", *prores, str(good)])
    out = tmp_path / "out.mov"
    splice.splice(src, [(10, 29, good)], out, total_f=60, fps=FPS)  # a chunk in the MIDDLE: both seams
    assert splice.frame_count(out) == 60
    md5 = lambda p: _md5s(p)  # noqa: E731
    s, g, o = md5(src), md5(good), md5(out)
    assert o[:10] == s[:10] and o[10:30] == g and o[30:] == s[30:]  # exactly the right frames on each side of both seams
