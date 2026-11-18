"""Cut-point self-check: strips + click / flash frame / cut-inside-a-word / duration gates."""

import json

import numpy as np
import pytest

from reel import config, cuts, tools
from reel.schemas.perception import Word, WordTable
from reel.schemas.timeline import FlashEvent, Provenance, Timeline, VideoClip
from reel.workspace import Workspace

try:
    config.ffmpeg_path()
    READY = True
except config.ToolNotFound:
    READY = False

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")]

FPS, CUT_F, N = 25, 50, 100  # 4 s reel, one cut at 2.0 s


def _final(path, *, click=False, flash=False):
    """Two shots (testsrc2 | testsrc) cut at frame 50 over ONE continuous tone + noise bed, so the
    clean render has no discontinuity; optionally a spike in the mix or a white frame at the cut."""
    rate = cuts.AUDIO_RATE
    t = np.arange(4 * rate) / rate
    x = 0.25 * np.sin(2 * np.pi * 220 * t) + 0.01 * np.random.default_rng(0).standard_normal(len(t))
    if click:
        x[int(2.004 * rate)] += 0.6
    raw = path.with_suffix(".f32")
    raw.write_bytes(x.astype(np.float32).tobytes())
    graph = ("[0:v]trim=start_frame=0:end_frame=50,setpts=PTS-STARTPTS[a0];"
             + ("color=c=white:s=270x480:r=25:d=0.04[w];[1:v]trim=start_frame=0:end_frame=49,setpts=PTS-STARTPTS[b0];[a0][w][b0]concat=n=3:v=1:a=0[v]"
                if flash else "[1:v]trim=start_frame=0:end_frame=50,setpts=PTS-STARTPTS[b0];[a0][b0]concat=n=2:v=1:a=0[v]"))
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=s=270x480:r=25:d=4", "-f", "lavfi", "-i", "testsrc=s=270x480:r=25:d=4",
                  "-f", "f32le", "-ar", str(rate), "-ac", "1", "-i", str(raw), "-filter_complex", graph, "-map", "[v]", "-map", "2:a",
                  "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest", str(path)])
    return path


def _tl(duration_f=N, flashes=()):
    prov = lambda item, w: Provenance(item=item, words=w)  # noqa: E731
    return Timeline(fps=f"{FPS}/1", width=270, height=480, duration_f=duration_f, assets={},
                    video=[VideoClip(id="v_k01", asset="c01", at_f=0, dur_f=CUT_F, src_in_us=0, src_out_us=2_000_000, src=prov("k01", [0, 1])),
                           VideoClip(id="v_k02", asset="c02", at_f=CUT_F, dur_f=N - CUT_F, src_in_us=1_000_000, src_out_us=3_000_000,
                                     src=prov("k02", [2, 3]))],
                    audio=[], flashes=list(flashes))


def _words(money_spans_cut=False):
    money = (1_800_000, 2_400_000) if money_spans_cut else (1_000_000, 1_500_000)
    return WordTable(words=[Word(i=0, clip="c01", text="save", start_us=400_000, end_us=900_000),
                            Word(i=1, clip="c01", text="money", start_us=money[0], end_us=money[1]),
                            Word(i=2, clip="c02", text="every", start_us=1_100_000, end_us=1_500_000),
                            Word(i=3, clip="c02", text="month.", start_us=1_600_000, end_us=2_000_000)])


def _check(tmp_path, name, *, tl=None, words=None, **kw):
    ws = Workspace.create(tmp_path / name)
    final = _final(ws.path("render", "final.mp4"), **kw)
    gates, report = cuts.check(ws, tl or _tl(), words or _words())
    return ws, {g.gate: g for g in gates}, report


def test_clean_render_passes_and_writes_strips(tmp_path):
    ws, g, rep = _check(tmp_path, "clean")
    assert all(x.ok for x in g.values()), {k: x.detail for k, x in g.items() if not x.ok}
    assert set(g) == {"cut_pop", "cut_flash", "cut_in_word", "duration_match"}
    (c,) = rep["cuts"]
    assert c["f"] == CUT_F and c["kinds"] == ["cut"] and c["pop"]["db"] < cuts.POP_DB and not c["flash"]["flash"]
    for rel in rep["review_strips"]:
        assert (ws.root / rel).exists()
    assert rep["review_strips"] == ["qa/cuts/head.png", "qa/cuts/cut_001.png", "qa/cuts/tail.png"]
    assert json.loads(ws.path("qa", "cuts.json").read_text())["cuts"][0]["strip"] == "qa/cuts/cut_001.png"
    probe = tools.ffprobe_json(ws.path("qa", "cuts", "cut_001.png"))["streams"][0]
    assert probe["width"] <= 2576 and probe["height"] > cuts.WAVE_H


def test_click_at_the_cut_is_caught(tmp_path):
    _ws, g, rep = _check(tmp_path, "click", click=True)
    assert not g["cut_pop"].ok and g["cut_pop"].at == ["0:02.00"] and "click/pop" in g["cut_pop"].detail
    assert all(config.QA_GATES[k] == "warn" for k in g)  # new gates never block until calibrated
    assert g["cut_flash"].ok and g["cut_in_word"].ok
    assert rep["cuts"][0]["pop"]["db"] >= cuts.POP_DB


def test_flash_frame_at_the_cut_is_caught_unless_intended(tmp_path):
    _ws, g, rep = _check(tmp_path, "flash", flash=True)
    assert not g["cut_flash"].ok and "brighter than both neighbours" in g["cut_flash"].detail
    assert rep["cuts"][0]["flash"]["frame"] == CUT_F and g["cut_pop"].ok
    _ws, g, rep = _check(tmp_path, "flash_ok", flash=True, tl=_tl(flashes=[FlashEvent(id="t1", at_f=CUT_F, frames=2)]))
    assert g["cut_flash"].ok and rep["cuts"][0]["intended"] == ["flash"]


def test_cut_inside_a_word_and_duration_mismatch(tmp_path):
    _ws, g, rep = _check(tmp_path, "word", words=_words(money_spans_cut=True), tl=_tl(duration_f=N + 10))
    w = g["cut_in_word"]
    assert not w.ok and "“money”" in w.detail and "200 ms in, 400 ms left" in w.detail and w.fixable
    assert rep["cuts"][0]["in_word"][0]["side"] == "out"
    assert not g["duration_match"].ok and "video" in g["duration_match"].detail


def test_flash_metric_ignores_a_plain_hard_cut():
    a, b = np.full((8, 8), 40.0, np.float32), np.full((8, 8), 200.0, np.float32)
    plain = {f: (a if f < 10 else b) for f in range(5, 15)}
    assert not cuts.flash_measure(plain, 10)["flash"]
    stray = dict(plain)
    stray[10] = np.full((8, 8), 120.0, np.float32) + np.arange(64, dtype=np.float32).reshape(8, 8)  # one frame of a third shot
    stray.update({f: b for f in range(11, 15)})
    m = cuts.flash_measure(stray, 10)
    assert m["flash"] and m["frame"] == 10 and "stray" in m["why"]
