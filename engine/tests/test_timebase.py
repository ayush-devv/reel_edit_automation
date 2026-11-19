from fractions import Fraction

import pytest

from reel import timebase as tb


def test_parse_rate():
    assert tb.parse_rate("30000/1001") == Fraction(30000, 1001)
    assert tb.parse_rate("25") == Fraction(25)
    assert tb.parse_rate("0/0") == 0


@pytest.mark.parametrize(
    "measured, expected",
    [
        (Fraction(25), Fraction(25)),  # never forced to 30
        (Fraction(2997, 100), Fraction(30000, 1001)),
        (Fraction(30), Fraction(30)),
        (Fraction(5994, 100), Fraction(60000, 1001)),
        (Fraction(120), Fraction(60)),
        (Fraction(240), Fraction(60)),
        (Fraction(2398, 100), Fraction(24000, 1001)),
    ],
)
def test_snap_fps(measured, expected):
    assert tb.snap_fps(measured) == expected


def test_frame_us_roundtrip():
    fps = Fraction(30000, 1001)
    for f in range(0, 5000, 7):
        assert tb.us_to_frame(tb.frame_to_us(f, fps), fps) == f


def test_audio_bounds_no_drift_ntsc():
    """29.97 fps = 1601.6 samples/frame; cumulative rounding must sum exactly."""
    fps = Fraction(30000, 1001)
    counts = [37, 41, 29, 53, 61, 17, 88, 23, 45, 9] * 20  # 200 cuts
    segs = tb.layout_segments(counts)
    bounds = tb.audio_bounds(segs, fps)
    # contiguous
    for (a0, a1), (b0, _) in zip(bounds, bounds[1:]):
        assert a1 == b0
    total_frames = sum(counts)
    assert bounds[-1][1] - bounds[0][0] == tb.frame_to_sample(total_frames, fps)
    # each segment within one sample of the exact value
    for seg, (s0, s1) in zip(segs, bounds):
        exact = seg.out_frames * tb.samples_per_frame(fps)
        assert abs((s1 - s0) - exact) <= 1


def test_layout_rejects_empty_segment():
    with pytest.raises(ValueError):
        tb.layout_segments([10, 0, 5])


def test_frames_for_duration():
    assert tb.frames_for_duration(Fraction(60), Fraction(30)) == 1800
    assert tb.frames_for_duration(Fraction(4), Fraction(30000, 1001)) == 120


def test_src_to_out_frame_matches_the_ramp_integral():
    from fractions import Fraction

    from reel import timebase as tb
    from reel.compile import ramp_factor

    fps = Fraction(25)
    assert tb.src_to_out_frame(2_000_000, fps, 2.0) == 25  # constant 2×: 2 s of source = 1 s out
    end = tb.src_to_out_frame(6_000_000, fps, 1.0, 4.0, 6_000_000)
    assert end == round(150 * ramp_factor(1.0, 4.0))  # whole ramp = the compiled length
    assert tb.src_to_out_frame(3_000_000, fps, 1.0, 4.0, 6_000_000) < 75  # slow start: half the source comes out early
