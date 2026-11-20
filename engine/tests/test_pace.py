"""G2.1: pacing numbers and the reference-relative pace gates."""

import subprocess

import pytest

from reel import config, qa, verdict
from reel.schemas.timeline import CaptionPage, CaptionTrack, CaptionWord, Keyframe, PipEvent, Provenance, Timeline, VideoClip


def _clip(cid, at, dur, scale=None):
    return VideoClip(id=cid, asset="c01", at_f=at, dur_f=dur, src_in_us=0, src_out_us=dur * 40_000, scale=scale or [],
                     src=Provenance(item="k0", words=[0, 0]))


def _tl(video, dur, pages=(), pips=()):
    return Timeline(fps="25/1", width=1080, height=1920, duration_f=dur, assets={}, video=video, audio=[], pips=list(pips),
                    captions=CaptionTrack(family="bold_pop", tokens={}, pages=list(pages)))


def test_pace_profile_counts_cuts_and_the_longest_stretch():
    p = qa.pace_profile([2.0, 3.0, 9.0], 10.0)
    assert p == {"cuts": 3, "duration_s": 10.0, "cuts_per_min": 18.0, "longest_static_s": 6.0}
    assert qa.pace_profile([], 7.5)["longest_static_s"] == 7.5  # one shot: the whole reel is static
    assert qa.pace_profile([0.0, 12.0], 10.0)["cuts"] == 0  # cuts at or past the edges don't count


def test_without_a_reference_the_gates_report_and_pass():
    ours = qa.pace_profile([5.0], 60.0)
    pace, static = qa.pace_gates(ours, None)
    assert pace.ok and static.ok and "no reference" in pace.detail and pace.measured["ours"] == ours


def test_pace_is_judged_against_the_reference():
    ref = qa.pace_profile([k * 3.0 for k in range(1, 20)], 60.0)  # 19 cuts/min, longest 3 s
    slow = qa.pace_profile([10.0, 20.0, 30.0], 60.0)  # 3 cuts/min, longest 30 s
    pace, static = qa.pace_gates(slow, ref)
    assert not pace.ok and "Cut faster" in pace.fix_hint and pace.fixable
    assert not static.ok and static.measured["reference"]["longest_static_s"] == 3.0
    close = qa.pace_profile([k * 3.2 for k in range(1, 18)], 60.0)  # 17 cuts/min: inside ±35 % of 19
    p2, _s2 = qa.pace_gates(close, ref)
    assert p2.ok
    busy = qa.pace_profile([k * 1.0 for k in range(1, 60)], 60.0)  # 59 cuts/min
    p3, s3 = qa.pace_gates(busy, ref)
    assert not p3.ok and "fewer punch-ins" in p3.fix_hint and s3.ok


def test_timeline_changes_counts_cuts_punch_ins_and_pips():
    v = [_clip("a", 0, 100, scale=[Keyframe(f=0, v=1.0), Keyframe(f=50, v=1.15)]), _clip("b", 100, 100)]
    tl = _tl(v, 200, pips=[PipEvent(id="p1", uri="broll/x.mov", start_f=150, end_f=180)])
    t = qa.timeline_changes(tl)
    assert (t["cuts"], t["punch_ins"], t["pip_changes"]) == (1, 1, 2)
    assert t["longest_unchanged_s"] == 2.0  # changes at 2.0, 4.0, 6.0, 7.2 s of 8 s


def test_speech_share_merges_overlapping_words():
    pages = [CaptionPage(start_f=0, end_f=50, words=[CaptionWord(i=0, text="a", start_f=0, end_f=30), CaptionWord(i=1, text="b", start_f=20, end_f=50)])]
    assert qa.speech_share(_tl([_clip("a", 0, 100)], 100, pages)) == 0.5


def test_a_failed_measurement_is_not_a_pass():
    gates = verdict.pace_results({"timeline": {}, "speech_share": 0.0, "error": "ImportError: no scenedetect"})
    assert [g.gate for g in gates] == ["pace", "static_stretch"] and not any(g.ok for g in gates)
    assert all(g.mode == config.QA_GATES["pace"] for g in gates) and "not measured" in gates[0].detail


def test_reviewer_gets_the_pace_numbers():
    pace = {"ours": qa.pace_profile([3.0], 30.0), "reference": qa.pace_profile([1.0, 2.0], 30.0),
            "timeline": {"cuts": 1, "punch_ins": 2, "pip_changes": 0, "changes_per_min": 6.0, "longest_unchanged_s": 12.0}, "speech_share": 0.8}
    loud = qa.GateResult("loudness", True, measured={"lufs": -14.2})
    text = "\n".join(verdict.pace_lines(pace, [loud]))
    assert "2.0 per minute" in text and "reference reel: 4.0 per minute" in text and "-14.2 LUFS" in text and "silent 20 %" in text


def _ff(*args):
    subprocess.run([str(config.ffmpeg_path()), "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.mark.integration
def test_measure_pace_finds_hard_cuts(tmp_path):
    pytest.importorskip("scenedetect")
    try:
        config.ffmpeg_path()
    except config.ToolNotFound:
        pytest.skip("pinned ffmpeg missing")
    parts = []
    for n, colour in enumerate(("red", "blue", "green")):
        p = tmp_path / f"p{n}.mp4"
        _ff("-f", "lavfi", "-i", f"testsrc2=size=320x568:rate=25,hue=h={n * 120}", "-f", "lavfi", "-i", f"color={colour}:size=320x568:rate=25",
            "-filter_complex", "[0][1]blend=all_mode=average", "-t", "2", "-pix_fmt", "yuv420p", str(p))
        parts.append(p)
    lst = tmp_path / "l.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    out = tmp_path / "cuts.mp4"
    _ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out))
    prof = qa.measure_pace(out)
    assert prof["cuts"] == 2 and 1.5 <= prof["longest_static_s"] <= 2.5
