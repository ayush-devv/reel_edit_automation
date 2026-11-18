"""S0 mezzanine conformance on the synthetic corpus. Skipped until the pinned ffmpeg exists."""

from fractions import Fraction

import pytest

from reel import config
from reel.conformance import checks, corpus
from reel.mezzanine import make_mezzanine
from reel.probe import probe
from reel.runner import run_pipeline
from reel.stages import PIPELINE
from reel.stages.ingest import choose_project_fps
from reel.workspace import Workspace

try:
    config.ffmpeg_path()
    HAVE_FFMPEG = True
except config.ToolNotFound:
    HAVE_FFMPEG = False

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not HAVE_FFMPEG, reason="pinned ffmpeg (ffmpeg-full) not installed")]


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("corpus")
    corpus.build(d)
    return d


@pytest.mark.parametrize("clip", corpus.CLIPS, ids=lambda c: c.name)
def test_mezzanine_conforms(clip, corpus_dir, tmp_path):
    src = next(corpus_dir.glob(f"{clip.name}.*"))
    p = probe(src)
    fps = choose_project_fps([Fraction(p.video.nominal_fps).limit_denominator(1001)], [p.duration_s])
    assert f"{fps.numerator}/{fps.denominator}" == clip.expect_fps
    out = tmp_path / f"{clip.name}.mov"
    make_mezzanine(p, out, fps)
    res = checks.check_mezzanine(p, out, fps, expect_probe=clip.name != "no_audio")
    assert res["ok"], res["failures"]


def test_source_properties_detected(corpus_dir):
    rot = probe(next(corpus_dir.glob("rotated_landscape_tag.*")))
    assert rot.video.rotation in (90, 270) and rot.video.display_height > rot.video.display_width
    vfr = probe(next(corpus_dir.glob("vfr_jitter.*")))
    assert vfr.video.is_vfr
    hdr = probe(next(corpus_dir.glob("hdr_hlg_10bit.*")))
    assert hdr.video.hdr == "hlg"


def test_reel_run_end_to_end_idempotent(corpus_dir, tmp_path):
    src = next(corpus_dir.glob("cfr25_portrait.*"))
    ws = Workspace.create(tmp_path / "proj")
    s1 = run_pipeline(ws, PIPELINE, options={"input": str(src)})
    assert s1["stages"]["mezzanine"]["status"] == "done"
    finished = s1["stages"]["mezzanine"]["finished"]
    s2 = run_pipeline(ws, PIPELINE, options={"input": str(src)})
    assert s2["stages"]["mezzanine"]["finished"] == finished  # skipped on second run
