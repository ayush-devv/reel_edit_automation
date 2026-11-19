"""Build step 7 A–C: room tone, voice chain + loudness, SFX library/peaks, music beats + ducking.
Synthetic audio with known answers: voice = 1 kHz bursts, music = 220 Hz bed, SFX = 4 kHz click."""

from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from reel import config, library, mix, render, tools
from reel import timebase as tb
from reel.compile import music_offset_us
from reel.mezzanine import make_mezzanine
from reel.probe import probe
from reel.schemas.timeline import Asset, AssetKind, AudioClip, Ducking, Provenance, Timeline, VideoClip

SR = 48000
FPS = Fraction(25)


def _wav(path: Path, y: np.ndarray, rate: int = SR) -> Path:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), y.astype(np.float32), rate)
    return path


def _tone(freq: float, dur: float, amp: float = 0.3, rate: int = SR) -> np.ndarray:
    t = np.arange(int(dur * rate)) / rate
    return amp * np.sin(2 * np.pi * freq * t)


def _band_db(y: np.ndarray, freq: float, rate: int = SR) -> float:
    """Level of one frequency (Goertzel-style projection), dB."""
    t = np.arange(y.size) / rate
    c = np.abs(np.dot(y, np.exp(-2j * np.pi * freq * t))) * 2 / max(1, y.size)
    return 20 * np.log10(max(c, 1e-9))


# ------------------------------------------------------------------ unit


def test_sfx_categories_from_folder_and_file_names():
    assert library.sfx_category(Path("Whooshes/Fast_Air_Swoosh_03.wav")) == "whoosh"
    assert library.sfx_category(Path("UI/button click soft.wav")) == "click"
    assert library.sfx_category(Path("Cinematic/Riser Tension 2.wav")) == "riser"
    assert library.sfx_category(Path("Foley/door_creak.wav")) is None


def test_index_sfx_measures_peak_and_skips_ambiences(tmp_path):
    y = np.zeros(SR)
    y[int(0.30 * SR):int(0.31 * SR)] = 0.9  # click at 300 ms
    _wav(tmp_path / "lib" / "Hits" / "hit_a.wav", y)
    _wav(tmp_path / "lib" / "Ambience" / "whoosh_long_bed.wav", _tone(100, 8.0, 0.1))  # > 6 s: not an edit SFX
    _wav(tmp_path / "lib" / "Foley" / "door.wav", y)  # no category
    entries = library.index_sfx(tmp_path / "lib", source="test", license_="CC0")
    assert [(e["category"], e["peak_ms"]) for e in entries] == [("hit", 300)]
    path = library.write_index("sfx", entries, root=tmp_path / "assets")
    assert path.exists() and library.sfx_menu({e["id"]: e for e in entries})["hit"][0]["peak_ms"] == 300


def test_music_offset_puts_a_downbeat_on_the_first_cut():
    meta = {"duration_ms": 60_000, "beats_ms": list(range(250, 60_000, 500)), "downbeats_ms": list(range(250, 60_000, 2000))}
    off = music_offset_us(meta, cut_us=3_000_000, total_us=20_000_000)
    assert off == 4_250_000 - 3_000_000  # first downbeat at/after the cut, lined up with it
    assert music_offset_us({"duration_ms": 10_000}, 3_000_000, 20_000_000) == 0  # no beat data


def test_loudness_spec_check():
    assert mix.check_delivery({"input_i": -14.3, "input_tp": -1.6}) == []
    assert mix.check_delivery({"input_i": -18.0, "input_tp": -1.6})
    assert mix.check_delivery({"input_i": -14.0, "input_tp": -0.2})
    assert mix.check_delivery({"input_i": -70.0, "input_tp": -90.0}) == []  # silence: nothing to normalise


def test_room_tone_picks_the_quietest_long_gap():
    rate = 16000
    rng = np.random.default_rng(0)
    y = rng.normal(0, 0.01, rate * 6)
    y[int(rate * 3.9):int(rate * 5.1)] *= 0.1  # quieter stretch fills the 3.9–5.1 s gap
    speech = [[0, 1_000_000], [2_000_000, 3_900_000], [5_100_000, 6_000_000]]
    s, e, db = mix.room_tone_region(y, rate, speech)
    assert 3_900_000 < s < 4_100_000 and 4_900_000 < e < 5_100_000 and db < -55


# ------------------------------------------------------------------ integration (ffmpeg)

try:
    config.ffmpeg_path()
    import librosa  # noqa: F401
    import soundfile  # noqa: F401

    READY = True
except Exception:  # noqa: BLE001
    READY = False


def _clip(tmp: Path, audio: np.ndarray) -> Path:
    wav = _wav(tmp / "src.wav", audio)
    src = tmp / "src.mp4"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", f"testsrc2=size=720x1280:rate=25:duration={audio.size / SR}", "-i", str(wav),
                  "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", str(src)])
    mezz = tmp / "mezz" / "c01.mov"
    mezz.parent.mkdir(parents=True, exist_ok=True)
    make_mezzanine(probe(src), mezz, FPS)
    return mezz


def _decode(path: Path) -> np.ndarray:
    import subprocess

    raw = subprocess.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(path), "-map", "0:a", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def _two_cuts(dur_a: int, dur_b: int, src_b: int) -> tuple[list[VideoClip], list[AudioClip], int]:
    video, audio = [], []
    for k, (src_f, n, at) in enumerate(((0, dur_a, 0), (src_b, dur_b, dur_a))):
        prov = Provenance(item=f"k{k}", words=[0, 0])
        video.append(VideoClip(id=f"v_k{k}", asset="c01", at_f=at, dur_f=n, src_in_us=tb.frame_to_us(src_f, FPS),
                               src_out_us=tb.frame_to_us(src_f + n, FPS), src=prov))
        audio.append(AudioClip(id=f"a_k{k}", asset="c01", at_f=at, dur_f=n, src_in_us=tb.frame_to_us(src_f, FPS), role="voice", src=prov))
    return video, audio, dur_a + dur_b


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + librosa/soundfile")
def test_room_tone_fills_cut_joins(tmp_path):
    rng = np.random.default_rng(1)
    floor = rng.normal(0, 0.003, SR * 6)  # ~ −50 dBFS room
    speech = np.zeros_like(floor)
    for s in (0.2, 1.4, 3.6, 4.6):
        speech[int(s * SR):int((s + 0.6) * SR)] = _tone(1000, 0.6)
    mezz = _clip(tmp_path, floor + speech)
    region = mix.room_tone_region(floor + speech, SR, [[200_000, 2_000_000], [3_600_000, 5_200_000]])
    assert region is not None
    video, audio, total = _two_cuts(50, 40, 90)  # 0–2.0 s, then 3.6–5.2 s
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=total, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=video, audio=audio)
    out = tmp_path / "base.mov"
    render.render_base(tl, tmp_path, out, room_tone={"c01": region})
    y = _decode(out)
    win = int(0.01 * SR)
    rms = np.sqrt((y[: y.size // win * win].reshape(-1, win) ** 2).mean(axis=1))[3:-3]  # inside the reel, incl. the cut join
    assert 20 * np.log10(rms.min() + 1e-12) > -85, "digital silence inside the voice track"


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + librosa/soundfile")
def test_sfx_peak_and_music_ducking(tmp_path):
    voice = np.zeros(SR * 6)
    voice[int(1.0 * SR):int(2.0 * SR)] = _tone(1000, 1.0)  # speech 1.0–2.0 s
    mezz = _clip(tmp_path, voice)
    click = np.zeros(SR)
    click[int(0.3 * SR):int(0.32 * SR)] = _tone(4000, 0.02, 0.8)
    sfx = _wav(tmp_path / "lib" / "hits" / "hit_click.wav", click)
    bed = _wav(tmp_path / "music" / "bed.wav", _tone(220, 10.0, 0.2))
    video, audio, total = _two_cuts(75, 75, 75)  # 0–3 s, then 3–6 s
    anchor_f = 75  # the cut
    audio.append(AudioClip(id="s1", asset="sfx1", at_f=anchor_f - tb.us_to_frame(300_000, FPS), dur_f=25, role="sfx", gain_db=0))
    audio.append(AudioClip(id="music", asset="bed", at_f=0, dur_f=total, role="music", gain_db=-6))
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=total,
                  assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov"),
                          "sfx1": Asset(id="sfx1", kind=AssetKind.sfx, uri=str(sfx)), "bed": Asset(id="bed", kind=AssetKind.music, uri=str(bed))},
                  video=video, audio=audio, ducking=[Ducking(depth_db=12, attack_ms=100, release_ms=200, regions_f=[[25, 50]])])
    out = tmp_path / "base.mov"
    render.render_base(tl, tmp_path, out)
    y = _decode(out)
    # SFX: the 4 kHz click peaks on the cut frame (±1 frame)
    hp = y - np.convolve(y, np.ones(8) / 8, mode="same")  # crude high-pass: keep the click, drop 220 Hz / 1 kHz
    win = int(0.005 * SR)
    peak_t = np.argmax(np.abs(hp[: hp.size // win * win]).reshape(-1, win).max(axis=1)) * 0.005
    assert abs(peak_t - anchor_f / 25) <= 1 / 25 + 0.005, peak_t
    # music: 220 Hz is ~12 dB lower under speech (1.2–1.8 s) than in the clear (3.5–4.5 s)
    under = _band_db(y[int(1.2 * SR):int(1.8 * SR)], 220)
    clear = _band_db(y[int(3.5 * SR):int(4.5 * SR)], 220)
    assert 9.0 <= clear - under <= 15.0, (clear, under)


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + librosa/soundfile")
def test_audio_only_rerender_matches_a_full_render_and_keeps_the_picture(tmp_path):
    """Partial re-render (roadmap G1.5): a music-gain revision rebuilds only the sound; the result is the same as a full
    render of the revised timeline, and the picture packets are the old ones byte for byte."""
    voice = np.zeros(SR * 6)
    voice[int(1.0 * SR):int(2.0 * SR)] = _tone(1000, 1.0)
    mezz = _clip(tmp_path, voice)
    bed = _wav(tmp_path / "music" / "bed.wav", _tone(220, 10.0, 0.2))
    video, audio, total = _two_cuts(75, 75, 75)

    def tl_with(gain: float) -> Timeline:
        return Timeline(fps="25/1", width=1080, height=1920, duration_f=total,
                        assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov"), "bed": Asset(id="bed", kind=AssetKind.music, uri=str(bed))},
                        video=video, audio=[*audio, AudioClip(id="music", asset="bed", at_f=0, dur_f=total, role="music", gain_db=gain)],
                        ducking=[Ducking(depth_db=12, attack_ms=100, release_ms=200, regions_f=[[25, 50]])])

    old, full = tmp_path / "old.mov", tmp_path / "full.mov"
    render.render_base(tl_with(-6), tmp_path, old, stems_dir=tmp_path / "stems_old")
    render.render_base(tl_with(-14), tmp_path, full, stems_dir=tmp_path / "stems_full")
    video_before = tools.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(old), "-map", "0:v", "-c", "copy", "-f", "md5", "-"]).stdout
    meta = render.render_base_audio(tl_with(-14), tmp_path, old, stems_dir=tmp_path / "stems_part")
    assert meta["audio_only"] is True
    video_after = tools.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(old), "-map", "0:v", "-c", "copy", "-f", "md5", "-"]).stdout
    assert video_after == video_before  # the picture is untouched
    a_part, a_full = _decode(old), _decode(full)
    assert a_part.size == a_full.size and np.max(np.abs(a_part - a_full)) < 1e-4  # the sound equals a full render's
    for bus in ("dialogue", "music", "sfx"):
        p, f = (tmp_path / d / f"{bus}.wav" for d in ("stems_part", "stems_full"))
        assert p.read_bytes() == f.read_bytes(), bus


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs librosa/soundfile")
def test_music_index_finds_tempo_and_beats(tmp_path):
    y = np.zeros(SR * 12)
    for k, t in enumerate(np.arange(0.5, 12, 0.5)):  # 120 BPM clicks, accent every 4th
        n = int(t * SR)
        y[n:n + 800] += _tone(1500 if k % 4 == 0 else 800, 800 / SR, 0.9 if k % 4 == 0 else 0.4)
    _wav(tmp_path / "music" / "upbeat" / "test_120.wav", y)
    (e,) = library.index_music(tmp_path / "music", source="synthetic", license_="test")
    assert abs(e["bpm"] - 120) <= 3 and e["mood"] == "upbeat"
    diffs = np.diff(e["beats_ms"])
    assert abs(np.median(diffs) - 500) <= 25
    assert all(abs(((b - 500) % 500)) <= 40 or abs(((b - 500) % 500) - 500) <= 40 for b in e["beats_ms"][:8])


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
@pytest.mark.parametrize("kind", ["zoom", "whip", "blur", "dip_to_black", "dip_to_white", "glitch"])
def test_transitions_keep_frames_and_sync(kind, tmp_path):
    from reel.conformance import checks, corpus
    from reel.schemas.plan import TransitionType
    from reel.schemas.timeline import TransitionEvent

    src = corpus.build(tmp_path / "src", ["cfr25_portrait"])[0]
    mezz = tmp_path / "mezz" / "c01.mov"
    mezz.parent.mkdir()
    make_mezzanine(probe(src), mezz, FPS)
    video, audio, total = _two_cuts(30, 50, 25)  # 0–1.2 s, then 1.0–3.0 s (beep at 2.0 s source → 2.2 s out)
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=total, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=video, audio=audio, transitions=[TransitionEvent(id="t1", at_f=30, type=TransitionType(kind), frames=6)])
    out = tmp_path / "base.mp4"
    meta = render.render_base(tl, tmp_path, out, finish_audio=False)
    assert meta["frames"] == total
    assert checks.beep_time(out) == pytest.approx(2.2, abs=0.01)
    if kind not in ("dip_to_black", "dip_to_white", "glitch"):  # flash detection is confused by the effect itself
        assert abs(checks.av_offset_ms(out)) <= 1000 / 25


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_speed_2x_halves_exactly_and_keeps_sync(tmp_path):
    from reel.conformance import checks, corpus

    src = corpus.build(tmp_path / "src", ["cfr25_portrait"])[0]
    mezz = tmp_path / "mezz" / "c01.mov"
    mezz.parent.mkdir()
    make_mezzanine(probe(src), mezz, FPS)
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=25, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=25, src_in_us=1_000_000, src_out_us=3_000_000, speed=2.0, src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=25, src_in_us=1_000_000, speed=2.0, role="voice", src=prov)])
    out = tmp_path / "fast.mp4"
    meta = render.render_base(tl, tmp_path, out, finish_audio=False)
    assert meta["frames"] == 25  # 2.0 s of source at 2× = 1.0 s
    assert checks.flash_time(out) == pytest.approx(0.5, abs=1 / 25)
    assert abs(checks.av_offset_ms(out)) <= 1000 / 25


def test_compiler_retimes_non_speech_items():
    from reel.schemas.plan import Speed
    from test_plan_compile import CLIPS, FPS as F30, IDX, WORDS, _finish, _story

    base = compile_tl = None
    from reel.compile import compile_timeline

    base = compile_timeline(_story(), _finish(), WORDS, CLIPS, F30, IDX)
    fast = compile_timeline(_story(), _finish(speeds=[Speed(id="sp1", item="k02", rate=2.0, reason="r")]), WORDS, CLIPS, F30, IDX)
    b, f = base.video[1], fast.video[1]
    assert f.speed == 2.0 and f.dur_f == round(b.dur_f / 2)
    assert fast.duration_f == base.duration_f - (b.dur_f - f.dur_f)


def test_look_strength_blends_linearly_and_correction_is_clamped():
    from reel import color

    rng = np.random.default_rng(2)
    x = rng.random((500, 3))
    full = color.transform(x, [1, 1, 1], 1.0, "punchy", 1.0)
    half = color.transform(x, [1, 1, 1], 1.0, "punchy", 0.5)
    assert np.allclose(half, (x + full) / 2, atol=1e-9)
    blue = np.full((2, 8, 8, 3), (90, 110, 200), dtype=np.uint8)  # strong blue cast
    m = color.measure(blue)
    assert m["gains"][2] == color.WB_CLAMP[0] and m["gains"][0] > 1.0  # pulled toward neutral, but clamped
    assert not color.needs_lut([1, 1, 1], 1.0, "none", 0.7) and color.needs_lut([1, 1, 1], 1.0, "warm", 0.3)


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_render_corrects_a_tinted_clip_toward_neutral(tmp_path):
    from reel import color
    from reel.perception.audio import read_frames
    from reel.schemas.timeline import Grade

    src = tmp_path / "tint.mp4"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=25:duration=2,colorchannelmixer=rr=0.8:bb=1.15",
                  "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", "-c:v", "libx264", "-preset", "ultrafast",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)])
    mezz = tmp_path / "mezz" / "c01.mov"
    mezz.parent.mkdir()
    make_mezzanine(probe(src), mezz, FPS)
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=50, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=50, src_in_us=0, src_out_us=2_000_000, src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=50, src_in_us=0, role="voice", src=prov)], grade=Grade())
    m = color.measure(read_frames(mezz, fps=1.0, width=160)[0])
    lut = color.write_lut(tmp_path / "c01.cube", m["gains"], m["exposure"], "none", 0.0)
    plain, graded = tmp_path / "plain.mp4", tmp_path / "graded.mp4"
    render.render_base(tl, tmp_path, plain, finish_audio=False)
    render.render_base(tl, tmp_path, graded, finish_audio=False, luts={"c01": lut})

    def cast(path):  # spread of the channel means = how far from neutral
        mean = read_frames(path, fps=1.0, width=160)[0].reshape(-1, 3).mean(axis=0)
        return float(mean.max() - mean.min())

    assert cast(graded) < cast(plain) * 0.8, (cast(graded), cast(plain))


def test_compiled_ducking_covers_kept_speech_and_sfx_peak_lands():
    from reel.compile import compile_timeline
    from test_plan_compile import CLIPS, FPS as F30, IDX, WORDS, _finish, _story

    tl = compile_timeline(_story(), _finish(), WORDS, CLIPS, F30, IDX)
    regions = tl.ducking[0].regions_f
    for page in tl.captions.pages:
        for w in page.words:
            assert any(s <= w.start_f and w.end_f <= e for s, e in regions), w
    sfx = next(a for a in tl.audio if a.role == "sfx")  # whoosh_01, peak 300 ms, on the cut after k01
    cut = tl.video[0].at_f + tl.video[0].dur_f
    assert sfx.at_f + 9 == cut  # 300 ms = 9 frames at 30 fps


def test_exposure_only_corrects_outside_the_comfortable_band():
    from reel import color

    grey = lambda v: np.full((1, 8, 8, 3), v, dtype=np.uint8)  # noqa: E731
    assert color.measure(grey(128))["exposure"] == 1.0  # 0.50: fine as shot
    assert color.measure(grey(40))["exposure"] > 1.1  # dark: lifted
    assert color.measure(grey(200))["exposure"] < 1.0  # very bright: pulled down a little


def _gray_frame(path, t, size=(108, 192)):
    import numpy as np

    from reel import tools
    from reel.config import ffmpeg_path

    raw = tools.run([str(ffmpeg_path()), "-v", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1", "-s", f"{size[0]}x{size[1]}",
                     "-f", "rawvideo", "-pix_fmt", "gray", "-"]).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(size[1], size[0]).astype(float)


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
@pytest.mark.parametrize("kind", ["shake", "rgb_split", "light_leak", "exposure_pulse"])
def test_footage_effects_only_touch_their_window(kind, tmp_path):
    from reel import tools
    from reel.schemas.timeline import EffectEvent

    src = tmp_path / "mezz" / "c01.mov"
    src.parent.mkdir()
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=25:duration=4", "-f", "lavfi", "-i", "sine=f=440:d=4:r=48000",
                  "-c:v", "prores_ks", "-profile:v", "2", "-c:a", "pcm_s16le", "-ac", "2", str(src)])
    prov = Provenance(item="k0", words=[0, 0])
    plain = Timeline(fps="25/1", width=1080, height=1920, duration_f=100, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                     video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=100, src_in_us=0, src_out_us=4_000_000, src=prov)],
                     audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=100, role="voice", src=prov)])
    fx = plain.model_copy(update={"effects": [EffectEvent(id="e1", type=kind, start_f=50, end_f=75, intensity=1.0)]})
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    render.render_base(plain, tmp_path, a, finish_audio=False)
    meta = render.render_base(fx, tmp_path, b, finish_audio=False)
    assert meta["frames"] == 100
    outside = abs(_gray_frame(a, 1.0) - _gray_frame(b, 1.0)).mean()
    inside = abs(_gray_frame(a, 2.04) - _gray_frame(b, 2.04)).mean()
    assert outside < 1.0, outside  # untouched before the window
    assert inside > 3.0, inside  # visible inside it


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_grain_and_vignette_cover_the_whole_reel(tmp_path):
    from reel import tools
    from reel.schemas.timeline import Grade

    src = tmp_path / "mezz" / "c01.mov"
    src.parent.mkdir()
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "color=c=gray:size=1080x1920:rate=25:duration=2", "-f", "lavfi", "-i", "sine=f=440:d=2:r=48000",
                  "-c:v", "prores_ks", "-profile:v", "2", "-c:a", "pcm_s16le", "-ac", "2", str(src)])
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=50, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=50, src_in_us=0, src_out_us=2_000_000, src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=50, role="voice", src=prov)],
                  grade=Grade(look="none", strength=0.0, correct=False, grain=0.4, vignette=0.6))
    out = tmp_path / "g.mp4"
    assert render.render_base(tl, tmp_path, out, finish_audio=False)["frames"] == 50
    f = _gray_frame(out, 1.0)
    assert f[:15, :15].mean() < f[90:100, 50:58].mean() - 10  # corners darker than the centre
    full = _gray_frame(out, 1.0, size=(1080, 1920))
    assert full[900:1000, 400:680].std() > 3.0  # grain: the flat grey is no longer flat (full resolution)


def test_music_offset_puts_the_most_cuts_on_beats():
    # beats every 500 ms, downbeats every 2 s; cuts at 3.0 s, 4.75 s and 6.25 s
    meta = {"duration_ms": 60_000, "beats_ms": list(range(0, 60_000, 500)), "downbeats_ms": list(range(0, 60_000, 2000))}
    cuts = [3_000_000, 4_750_000, 6_250_000]
    off = music_offset_us(meta, cuts[0], 20_000_000, cuts)
    # first cut stays on a downbeat, and the 250 ms-phase cuts can't all land: any downbeat offset gives 1 on-beat cut,
    # so the earliest fitting downbeat wins the tie
    assert (cuts[0] + off) % 2_000_000 == 0
    cuts2 = [3_000_000, 4_000_000, 6_500_000]  # all on the half-second grid
    off2 = music_offset_us(meta, cuts2[0], 20_000_000, cuts2)
    assert all((c + off2) % 500_000 == 0 for c in cuts2)


def test_beat_pulses_land_on_downbeats_and_respect_punch_ins():
    from reel.compile import add_beat_pulses
    from reel.schemas.plan import Ease
    from reel.schemas.timeline import Keyframe

    prov = Provenance(item="k0", words=[0, 0])
    a = VideoClip(id="v_k0", asset="c", at_f=0, dur_f=100, src_in_us=0, src_out_us=4_000_000, src=prov)
    b = VideoClip(id="v_k1", asset="c", at_f=100, dur_f=100, src_in_us=0, src_out_us=4_000_000, src=prov,
                  scale=[Keyframe(f=0, v=1.0, ease=Ease.hold), Keyframe(f=48, v=1.2, ease=Ease.hold)])
    meta = {"downbeats_ms": [1000, 2000, 3000, 5000, 6000]}  # at 25 fps: frames 25, 50, 75, 125, 150
    n = add_beat_pulses([a, b], meta, 0, 200, Fraction(25), 0.04)
    assert n == 4  # frame 150 sits on b's punch-in keyframe (148): skipped
    peaks = [k for k in a.scale if k.v > 1.0]
    assert [k.f for k in peaks] == [27, 52, 77] and all(k.v == pytest.approx(1.04) for k in peaks)
    assert any(k.f == 27 and k.v == pytest.approx(1.04) for k in b.scale)  # pulse on top of the 1.0 base before the punch


def _one_clip_tl(mezz_uri, dur_f, **clip_kw):
    prov = Provenance(item="k0", words=[0, 0])
    v = VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=dur_f, src_in_us=0, src_out_us=clip_kw.pop("src_out_us", 2_000_000), src=prov, **clip_kw)
    a = AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=dur_f, role="voice", src=prov, speed=clip_kw.get("speed", 1.0))
    return Timeline(fps="25/1", width=1080, height=1920, duration_f=dur_f, assets={"c01": Asset(id="c01", kind=AssetKind.video, uri=mezz_uri)},
                    video=[v], audio=[a])


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_hold_freezes_the_last_frame_and_keeps_length(tmp_path):
    src = tmp_path / "mezz" / "c01.mov"
    src.parent.mkdir()
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=25:duration=3", "-f", "lavfi", "-i", "sine=f=440:d=3:r=48000",
                  "-c:v", "prores_ks", "-profile:v", "2", "-c:a", "pcm_s16le", "-ac", "2", str(src)])
    tl = _one_clip_tl("mezz/c01.mov", 50 + 20, hold_f=20)
    out = tmp_path / "h.mp4"
    assert render.render_base(tl, tmp_path, out, finish_audio=False)["frames"] == 70
    still_a, still_b = _gray_frame(out, 2.2, (1080, 1920)), _gray_frame(out, 2.7, (1080, 1920))
    moving_a, moving_b = _gray_frame(out, 0.5, (1080, 1920)), _gray_frame(out, 1.0, (1080, 1920))
    assert abs(still_a - still_b).mean() < 1.0 < abs(moving_a - moving_b).mean()  # frozen during the hold only
    pcm = tools.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(out), "-f", "s16le", "-ac", "1", "-ar", "48000", "-"]).stdout
    y = np.frombuffer(pcm, dtype=np.int16).astype(float)
    assert np.abs(y[48000 * 1: 48000 * 1 + 4800]).mean() > 1000 and np.abs(y[int(48000 * 2.3): int(48000 * 2.6)]).mean() < 50


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
def test_speed_ramp_length_matches_the_integral(tmp_path):
    from reel.compile import ramp_factor

    src = tmp_path / "mezz" / "c01.mov"
    src.parent.mkdir()
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=25:duration=6", "-f", "lavfi", "-i", "anoisesrc=d=6:r=48000:a=0.1",
                  "-c:v", "prores_ks", "-profile:v", "2", "-c:a", "pcm_s16le", "-ac", "2", str(src)])
    factor = ramp_factor(1.0, 4.0)  # 6 s of source, 1× → 4× ⇒ 6·ln4/3 ≈ 2.77 s
    dur_f = round(150 * factor)
    tl = _one_clip_tl("mezz/c01.mov", dur_f, src_out_us=6_000_000, speed=1.0, speed_to=4.0)
    tl.audio[0].speed = 1.0 / factor
    meta = render.render_base(tl, tmp_path, tmp_path / "r.mp4", finish_audio=False)
    assert meta["frames"] == dur_f == 69


def test_no_beat_pulse_inside_a_punch_in_ramp():
    from reel.compile import add_beat_pulses
    from reel.schemas.plan import Ease
    from reel.schemas.timeline import Keyframe

    prov = Provenance(item="k0", words=[0, 0])
    c = VideoClip(id="v_k0", asset="c", at_f=0, dur_f=100, src_in_us=0, src_out_us=4_000_000, src=prov,
                  scale=[Keyframe(f=0, v=1.0, ease=Ease.hold), Keyframe(f=10, v=1.0, ease=Ease.linear), Keyframe(f=70, v=1.25, ease=Ease.linear)])
    assert add_beat_pulses([c], {"downbeats_ms": [1600]}, 0, 100, Fraction(25), 0.04) == 0  # frame 40: mid-ramp
