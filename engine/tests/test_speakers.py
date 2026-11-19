"""Active speaker detection: window attribution, hysteresis, word snapping, framing integration,
and (integration, local real footage) the landmarker on a generated two-person clip."""

from __future__ import annotations

from fractions import Fraction

import pytest

from reel import framing
from reel.perception import speakers as asd
from reel.schemas.timeline import Provenance, VideoClip

U = asd.UNCERTAIN


# ------------------------------------------------------------------ attribution


def test_attribution_needs_margin_floor_and_speech():
    act = [
        {0: 0.040, 1: 0.002},  # clear lead → 0
        {0: 0.030, 1: 0.028},  # both moving → uncertain
        {0: 0.004, 1: 0.001},  # lead, but under the jitter floor → uncertain
        {0: 0.040, 1: 0.001},  # silent window → None, whatever the mouths do
        {0: None, 1: 0.035},  # face 0 not seen: 1 leads against "silent"
        {0: 0.001, 1: 0.050},
    ]
    speech = [True, True, True, False, True, True]
    assert asd.attribute(act, speech) == [0, U, U, None, 1, 1]


def test_attribution_margin_is_normalised_to_the_piece_peak():
    # leads are measured against the piece's p95 activity (≈ 0.034 here): 0.007 is enough, 0.004 is not
    act = [{0: 0.040, 1: 0.0}, {0: 0.016, 1: 0.009}, {0: 0.016, 1: 0.012}]
    labels = asd.attribute(act, [True] * 3)
    assert labels[0] == 0 and labels[1] == 0 and labels[2] == U
    # a margin over 1.0 can never be met
    assert asd.attribute(act, [True] * 3, margin=1.01) == [U, U, U]


def test_window_activity_from_jaw_motion():
    still = [(t, 0.30, 0.0) for t in range(0, 400_000, 83_333)]
    talk = [(t, 0.05 + 0.25 * (k % 2), 0.0) for k, t in enumerate(range(0, 400_000, 83_333))]
    assert asd.window_activity(talk, 0, 400_000) > asd.window_activity(still, 0, 400_000) + 0.1
    assert asd.window_activity(talk, 1_000_000, 1_400_000) is None


# ------------------------------------------------------------------ hysteresis


def test_switch_needs_three_windows_and_is_backdated():
    labels = [0, 0, 0, 1, 1, 0, 1, 1, 1, 1]
    # two windows of 1 are not enough; the run of three from index 6 switches, backdated to 6
    assert asd.smooth(labels) == [0, 0, 0, 0, 0, 0, 1, 1, 1, 1]


def test_silence_holds_the_speaker_and_does_not_break_a_run():
    labels = [0, 0, 0, None, None, 1, None, 1, None, 1, None]
    out = asd.smooth(labels)
    assert out[:5] == [0] * 5
    assert out[5:] == [1] * 6  # 1, (silence), 1, (silence), 1 → confirmed, backdated to its first window


def test_uncertain_needs_three_windows_too():
    assert asd.smooth([0, 0, 0, U, U, 0, 0]) == [0] * 7
    assert asd.smooth([0, 0, 0, U, U, U, 1]) == [0, 0, 0, U, U, U, U]


def test_opening_before_first_confirmed_speaker():
    # silence before the first speaker takes it; unconfirmed speech of someone else stays uncertain
    assert asd.smooth([None, None, 1, 1, 1]) == [1] * 5
    assert asd.smooth([0, 0, None, 1, 1, 1]) == [U, U, 1, 1, 1, 1]
    assert asd.smooth([None, 0, None]) == [None, U, None]


# ------------------------------------------------------------------ segments, snapping, gating


def test_segments_switch_in_word_gaps_never_mid_word():
    words = [(0, 900_000), (1_000_000, 1_500_000), (2_300_000, 2_700_000), (2_800_000, 3_900_000)]
    states = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]  # switch at window 5 = 2.0 s, inside the 1.5–2.3 s pause
    segs = asd.segments(states, 0, 4_000_000, words)
    assert [s["track"] for s in segs] == [0, 1]
    t = segs[0]["end_us"]
    assert segs[1]["start_us"] == t and t == 2_200_000  # 100 ms before the next word
    # a switch time inside a word moves out of it
    assert asd.snap(3_000_000, words, 0, 4_000_000) not in range(2_800_001, 3_900_000)
    assert asd.snap(2_450_000, words, 0, 4_000_000) == 2_200_000  # nearer the word start → the gap before it
    assert asd.segments([U, U, 0, 0], 0, 1_600_000, [])[0]["track"] is None


def test_speech_gate_uses_relative_rms_and_word_or_vad_presence():
    rms = [-20.0] * 4 + [-60.0] * 4 + [-22.0] * 4  # 100 ms hops: loud, near silent, loud
    gate = asd.speech_windows(0, 1_200_000, rms, 100_000, words=[(0, 300_000)], speech=[(850_000, 1_200_000)])
    assert gate == [True, False, True]
    assert asd.speech_windows(0, 1_200_000, rms, 100_000, words=[], speech=[]) == [False] * 3
    assert asd.speech_windows(0, 1_200_000, rms, 100_000, words=None, speech=None) == [True, False, True]


def test_pieces_and_tracks_from_face_samples():
    one = {"x": 0.45, "y": 0.3, "w": 0.1, "h": 0.15}
    left, right = {"x": 0.10, "y": 0.3, "w": 0.1, "h": 0.15}, {"x": 0.75, "y": 0.3, "w": 0.1, "h": 0.15}
    samples = ([{"t_us": t, "faces": [one]} for t in range(0, 2_000_000, 250_000)]
               + [{"t_us": t, "faces": [left, right]} for t in range(2_000_000, 8_000_000, 250_000)])
    assert asd.multi_face_pieces(samples, cuts_us=[5_000_000]) == [(2_000_000, 5_000_000), (5_000_000, 8_000_000)]
    tracks = asd.face_tracks(samples, 2_000_000, 5_000_000)
    assert [t["box"]["x"] for t in tracks] == [0.10, 0.75]
    x, y, w, h = asd.crop_region([left], 1920, 1080)
    assert x < 0.10 * 1920 and x + w > 0.20 * 1920 and w == h


def test_single_face_clip_needs_no_model(tmp_path):
    faces = {"samples": [{"t_us": t, "faces": [{"x": 0.4, "y": 0.3, "w": 0.1, "h": 0.1}]} for t in range(0, 4_000_000, 250_000)]}
    out = asd.analyse_clip(tmp_path / "missing.mov", faces, [], words=[(0, 0, 100_000)])
    assert out["segments"] == [] and out["tracks"] == [] and out["words"] == {}


def test_speaker_at():
    sp = {"c01": {"segments": [{"start_us": 0, "end_us": 2_000_000, "track": 0}, {"start_us": 2_000_000, "end_us": 3_000_000, "track": None}]}}
    assert asd.speaker_at(sp, "c01", 1_999_999) == 0
    assert asd.speaker_at(sp, "c01", 2_500_000) is None
    assert asd.speaker_at(sp, "c02", 0) is None and asd.speaker_at(None, "c01", 0) is None


# ------------------------------------------------------------------ framing


LEFT = {"x": 0.10, "y": 0.3, "w": 0.12, "h": 0.2}
RIGHT = {"x": 0.78, "y": 0.3, "w": 0.11, "h": 0.19}
CROP_W = 0.316  # 16:9 source → 9:16 crop


def _two_shot(dur_us=8_000_000):
    prov = Provenance(item="k0", words=[0, 0])
    c = VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=dur_us * 25 // 1_000_000, src_in_us=0, src_out_us=dur_us, src=prov)
    samples = [{"t_us": t, "faces": [LEFT, RIGHT]} for t in range(0, dur_us, 250_000)]
    return c, samples


def _speakers(segs):
    return {"tracks": [{"id": 0, "box": LEFT}, {"id": 1, "box": RIGHT}],
            "segments": [{"start_us": a, "end_us": b, "track": t} for a, b, t in segs]}


def test_two_shot_crops_on_the_speaker_and_switches_at_word_gaps():
    c, samples = _two_shot()
    # segment edges come from speakers.json (already at word gaps): 3.2 s and 6.12 s
    sp = _speakers([(0, 3_200_000, 0), (3_200_000, 6_120_000, 1), (6_120_000, 8_000_000, 0)])
    shots = framing.shots(c, Fraction(25), [], samples, crop_w=CROP_W, speakers=sp)
    assert [(s.start_f, s.layout) for s in shots] == [(0, "crop"), (80, "crop"), (153, "crop")]
    assert shots[0].box == LEFT and shots[1].box == RIGHT and shots[2].box == LEFT  # overlay face spans follow the speaker
    assert shots[0].centre[0] == pytest.approx(0.16) and shots[1].centre[0] == pytest.approx(0.835)
    # no speakers.json → the whole-frame fill, as before
    assert [s.layout for s in framing.shots(c, Fraction(25), [], samples, crop_w=CROP_W)] == ["fill"]


def test_two_shot_keeps_fill_for_uncertain_and_drops_short_switches():
    c, samples = _two_shot()
    sp = _speakers([(0, 2_000_000, 0), (2_000_000, 2_600_000, 1), (2_600_000, 5_000_000, 0),  # 0.6 s blip of 1: ignored
                    (5_000_000, 6_520_000, None), (6_520_000, 8_000_000, 1)])  # overlap → fill
    shots = framing.shots(c, Fraction(25), [], samples, crop_w=CROP_W, speakers=sp)
    assert [(s.start_f, s.layout, s.box == RIGHT) for s in shots] == [(0, "crop", False), (125, "fill", False), (163, "crop", True)]
    assert all(b.start_f - a.start_f >= 25 for a, b in zip(shots, shots[1:]))  # ≥ 1 s apart


def test_two_shot_falls_back_to_fill_when_speech_is_mostly_uncertain():
    c, samples = _two_shot()
    sp = _speakers([(0, 2_000_000, 0), (2_000_000, 8_000_000, None)])
    assert [s.layout for s in framing.shots(c, Fraction(25), [], samples, crop_w=CROP_W, speakers=sp)] == ["fill"]
    # speakers.json only covers a sliver of the shot → fill
    sp = _speakers([(0, 1_500_000, 0)])
    assert [s.layout for s in framing.shots(c, Fraction(25), [], samples, crop_w=CROP_W, speakers=sp)] == ["fill"]


def test_speaker_cuts_respect_clip_bounds_and_speed():
    prov = Provenance(item="k0", words=[0, 0])
    c = VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=50, src_in_us=2_000_000, src_out_us=6_000_000, speed=2.0, src=prov)
    samples = [{"t_us": t, "faces": [LEFT, RIGHT]} for t in range(0, 8_000_000, 250_000)]
    sp = _speakers([(0, 4_000_000, 0), (4_000_000, 8_000_000, 1)])
    shots = framing.shots(c, Fraction(25), [], samples, crop_w=CROP_W, speakers=sp)
    assert [(s.start_f, s.box == LEFT) for s in shots] == [(0, True), (25, False)]  # 2 s of source at 2× = 25 frames


def test_overlay_face_spans_follow_speaker_crops(tmp_path, monkeypatch):
    from reel import overlay, render
    from reel.schemas.timeline import Asset, AssetKind, AudioClip, Timeline

    c, samples = _two_shot()
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=200, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[c], audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=200, role="voice", src=prov)])
    monkeypatch.setattr(render, "source_size", lambda p: (1920, 1080))
    faces = {"c01": {"samples": samples, "median_box": LEFT}}
    sp = {"c01": _speakers([(0, 4_000_000, 0), (4_000_000, 8_000_000, 1)])}
    spans = overlay.build_props(tl, tmp_path, faces, None, None, sp)["faces"]
    assert [(s["start_f"], s["end_f"]) for s in spans] == [(0, 100), (100, 200)]
    for s in spans:  # the speaker's face is inside the vertical frame, not cut off at the side
        assert 0.0 <= s["box"]["x"] and s["box"]["x"] + s["box"]["w"] <= 1.0
    assert overlay.build_props(tl, tmp_path, faces, None, None, None)["faces"][0]["end_f"] == 200  # one fill span


@pytest.mark.integration
def test_speaker_crops_render_frame_exact(tmp_path):
    """crop (left) → fill (uncertain) → crop (right) inside one clip renders every frame."""
    import numpy as np

    from reel import render, tools
    from reel.schemas.timeline import Asset, AssetKind, AudioClip, Timeline

    src = tmp_path / "mezz" / "c01.mov"
    src.parent.mkdir()
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=25:duration=6", "-f", "lavfi", "-i", "sine=f=440:d=6:r=48000",
                  "-c:v", "prores_ks", "-profile:v", "2", "-c:a", "pcm_s16le", "-ac", "2", str(src)])
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=150, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=150, src_in_us=0, src_out_us=6_000_000, src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=150, role="voice", src=prov)])
    samples = [{"t_us": t, "faces": [LEFT, RIGHT]} for t in range(0, 6_000_000, 250_000)]
    faces = {"c01": {"samples": samples, "median_box": LEFT}}
    sp = {"c01": _speakers([(0, 2_000_000, 0), (2_000_000, 4_000_000, None), (4_000_000, 6_000_000, 1)])}
    out = tmp_path / "base.mp4"
    meta = render.render_base(tl, tmp_path, out, faces=faces, speakers=sp, finish_audio=False)
    assert meta["frames"] == 150 and meta["size"] == "1080x1920"

    def frame(t):
        raw = tools.run([str(render.ffmpeg_path()), "-v", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1",
                         "-f", "rawvideo", "-pix_fmt", "gray", "-"]).stdout
        return np.frombuffer(raw, dtype=np.uint8).reshape(1920, 1080).astype(float)

    crop_left, fill, crop_right = frame(1), frame(3), frame(5)
    detail = lambda f: np.abs(np.diff(f, axis=1)).mean()  # noqa: E731
    assert detail(fill[100:500]) < 0.5 * detail(fill[800:1100])  # fill: blurred band above the sharp whole frame
    assert np.abs(crop_left - crop_right).mean() > 5 and np.abs(crop_left - fill).mean() > 5  # three different pictures


# ------------------------------------------------------------------ integration (landmarker, local footage)


def _sample_footage():
    from reel import config

    rel = "samples/gold/thediaryofaceo_HAXzFdJ9U-0/raw/raw.mp4"  # real podcast, never committed
    return next((p / rel for p in [config.REPO_ROOT, *config.REPO_ROOT.parents] if (p / rel).exists()), None)


def _model_ready() -> bool:
    try:
        asd.landmarker_model()
        import mediapipe  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.integration
def test_landmarker_finds_who_talks_in_a_generated_two_shot(tmp_path):
    """Two real close-ups side by side (a talking crop + a listening crop), swapped after 4 s, with
    the talking side's audio: the speaker must be left for 0–4 s, right for 4–8 s."""
    from reel import tools
    from reel.perception import prosody, visual
    from reel.perception.audio import read_pcm

    src = _sample_footage()
    if src is None or not _model_ready():
        pytest.skip("needs the local DOAC gold sample and the face landmarker model")
    clip = tmp_path / "two.mp4"
    fc = ("[0:v]scale=1920:1080,crop=960:1080:230:0,setsar=1[a0];[1:v]scale=1920:1080,crop=960:1080:730:0,setsar=1[a1];[a0][a1]hstack[A];"
          "[2:v]scale=1920:1080,crop=960:1080:787:0,setsar=1[b0];[3:v]scale=1920:1080,crop=960:1080:230:0,setsar=1[b1];[b0][b1]hstack[B];"
          "[A][B]concat=n=2:v=1:a=0,fps=25[v];[0:a][3:a]concat=n=2:v=0:a=1[a]")
    args = ["-y"]
    for ss in (127, 181, 121, 140):  # talking (left), listening (right) | listening (left), talking (right)
        args += ["-ss", str(ss), "-t", "4", "-i", str(src)]
    tools.ffmpeg(args + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
                         "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)])
    faces = visual.faces(clip)
    out = asd.analyse_clip(clip, faces, [], None, prosody.rms_db(read_pcm(clip)))
    assert len(out["tracks"]) == 2
    left, right = sorted(out["tracks"], key=lambda t: t["box"]["x"])
    segs = [s for s in out["segments"] if s["track"] is not None]
    assert segs[0]["track"] == left["id"] and segs[-1]["track"] == right["id"]
    switch = next(s["start_us"] for s in segs if s["track"] == right["id"])
    assert abs(switch - 4_000_000) <= 600_000
    assert asd.speaker_at({"c01": out}, "c01", 1_000_000) == left["id"]
    assert asd.speaker_at({"c01": out}, "c01", 6_000_000) == right["id"]
