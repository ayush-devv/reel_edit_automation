"""Voice enhancement (DeepFilterNet3): strength decision, pinned fetch, stage hash/fallback (unit),
then sample alignment, measured noise reduction and the renderer's use of the enhanced voice
(integration: need the binary, i.e. macOS arm64 + one download)."""

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from reel import config, enhance, render, tools
from reel import timebase as tb
from reel.perception.audio import ANALYSIS_RATE, read_pcm
from reel.runner import StageContext, run_pipeline
from reel.schemas.timeline import Asset, AssetKind, AudioClip, Provenance, Timeline, VideoClip
from reel.stages import edit, voice
from reel.workspace import Workspace, atomic_write_json

SR = 48000
FPS = Fraction(25)

try:
    config.ffmpeg_path()
    FFMPEG = True
except Exception:  # noqa: BLE001
    FFMPEG = False


@pytest.fixture(autouse=True)
def _fresh_fetch_cache():
    enhance.deep_filter.cache_clear()
    yield
    enhance.deep_filter.cache_clear()


def _speech_like(dur: float, rate: int, on: float = 1.5, period: float = 2.5) -> tuple[np.ndarray, list[list[int]]]:
    """Voiced, formant-shaped, syllable-modulated signal: `on` s of 'speech' every `period` s."""
    t = np.arange(int(dur * rate)) / rate
    f0 = 140 + 30 * np.sin(2 * np.pi * 0.7 * t)
    ph = 2 * np.pi * np.cumsum(f0) / rate
    x = np.zeros_like(t)
    for h in range(1, 30):
        fh = f0 * h
        amp = np.exp(-((fh - 700) / 400) ** 2) + 0.6 * np.exp(-((fh - 1200) / 500) ** 2) + 0.05
        x += np.where(fh < rate / 2, amp * np.sin(h * ph), 0.0)
    x *= np.clip(np.sin(2 * np.pi * 4 * t), 0, None) ** 0.6 * ((t % period) < on)
    spans = [[int(s * 1e6), int(min(s + on, dur) * 1e6)] for s in np.arange(0, dur, period)]
    return 0.3 * x / np.max(np.abs(x)), spans


def _db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(np.asarray(x, np.float64) ** 2) + 1e-20))


# ------------------------------------------------------------------ unit: strength decision


def test_decide_skips_clean_audio_and_strengthens_with_noise():
    x, spans = _speech_like(10.0, ANALYSIS_RATE)
    x *= 3  # speech ≈ −19 dBFS over its spans
    rng = np.random.default_rng(0)
    decisions = {}
    for noise_db in (None, -75, -62, -50, -40, -30):
        n = 0 if noise_db is None else rng.normal(0, 10 ** (noise_db / 20), x.size)
        decisions[noise_db] = enhance.decide((x + n).astype(np.float32), ANALYSIS_RATE, spans)
    assert not decisions[None]["apply"] and not decisions[-75]["apply"]  # digital silence / studio floor: left alone
    assert not decisions[-62]["apply"] and decisions[-62]["snr_db"] >= enhance.SKIP_SNR_DB  # high SNR: left alone
    applied = [decisions[k] for k in (-50, -40, -30)]
    assert all(d["apply"] for d in applied)
    limits = [d["atten_lim_db"] for d in applied]
    assert limits == sorted(limits) and limits[0] < limits[-1] < 100  # never "full" suppression
    for k in (-50, -40, -30):  # the floor estimate tracks the added noise
        assert abs(decisions[k]["floor_db"] - k) < 1.5, decisions[k]
    assert not enhance.decide(x[:0], ANALYSIS_RATE, spans)["apply"]
    assert not enhance.decide(x.astype(np.float32), ANALYSIS_RATE, [])["apply"]


# ------------------------------------------------------------------ unit: pinned fetch


def test_fetch_installs_only_a_binary_matching_the_pinned_hash(tmp_path, monkeypatch):
    src = tmp_path / "release" / "deep-filter"
    src.parent.mkdir()
    src.write_bytes(b"#!/bin/sh\necho fake\n")
    models = tmp_path / "models"
    monkeypatch.setattr(enhance, "DF_URL", src.as_uri())
    monkeypatch.setattr(enhance, "_model_dir", lambda: models)
    monkeypatch.setattr(enhance, "supported_platform", lambda: True)

    monkeypatch.setattr(enhance, "DF_SHA256", "0" * 64)  # tampered / wrong download
    assert enhance.deep_filter() is None
    assert not (models / enhance.DF_ASSET).exists()

    import hashlib

    monkeypatch.setattr(enhance, "DF_SHA256", hashlib.sha256(src.read_bytes()).hexdigest())
    enhance.deep_filter.cache_clear()
    path = enhance.deep_filter()
    assert path == models / enhance.DF_ASSET and path.stat().st_mode & 0o111
    src.unlink()  # cached copy is re-verified and reused, no download
    enhance.deep_filter.cache_clear()
    assert enhance.deep_filter() == path


def test_fetch_offline_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(enhance, "DF_URL", (tmp_path / "missing").as_uri())
    monkeypatch.setattr(enhance, "_model_dir", lambda: tmp_path / "models")
    monkeypatch.setattr(enhance, "supported_platform", lambda: True)
    assert enhance.deep_filter() is None


# ------------------------------------------------------------------ stage: hash, skip, fallback


def _workspace(tmp_path: Path, audio: np.ndarray, spans: list[list[int]]) -> Workspace:
    """Minimal workspace for the voice stage: manifest, an audio-only mezzanine, VAD spans."""
    import soundfile as sf

    ws = Workspace.create(tmp_path / "proj")
    atomic_write_json(ws.path("source", "manifest.json"), {"clips": [{"id": "c01"}]})
    wav = tmp_path / "src.wav"
    sf.write(str(wav), np.stack([audio, audio], axis=1).astype(np.float32), SR)
    ws.path("mezz").mkdir(parents=True, exist_ok=True)
    tools.ffmpeg(["-y", "-i", str(wav), "-c:a", "pcm_s16le", "-ar", str(SR), "-ac", "2", str(ws.path("mezz", "c01.mov"))])
    atomic_write_json(ws.path("perception", "vad.json"), {"c01": {"speech": spans}})
    return ws


def _copy_enhance(calls):
    def fake(binary, src, out, atten, *, work):  # stands in for the binary: a plain sample-exact copy
        calls.append(atten)
        tools.ffmpeg(["-y", "-i", str(src), "-map", "0:a:0", "-c:a", "pcm_s16le", str(out)])
        return {"samples": enhance.wav_frames(out), "channels": 2, "df_s": 0.0}
    return fake


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
def test_stage_falls_back_then_reruns_when_the_tool_appears(tmp_path, monkeypatch):
    x, spans = _speech_like(8.0, SR)
    ws = _workspace(tmp_path, x + np.random.default_rng(0).normal(0, 0.01, x.size), spans)  # −40 dBFS noise
    ctx = StageContext(ws=ws)

    monkeypatch.setattr(enhance, "deep_filter", lambda: None)  # offline / unsupported platform
    s1 = run_pipeline(ws, [voice.STAGE])
    rep = json.loads(ws.path("perception", "voice_enhance.json").read_text())
    assert s1["stages"]["voice"]["status"] == "done"
    assert rep["clips"]["c01"]["applied"] is False and rep["clips"]["c01"]["reason"] == voice.UNAVAILABLE
    assert not ws.path("mezz", "c01.voice.wav").exists() and edit.enhanced_voice(ctx) == {}

    calls = []
    monkeypatch.setattr(enhance, "deep_filter", lambda: Path("/fake/deep-filter"))
    monkeypatch.setattr(enhance, "enhance", _copy_enhance(calls))
    s2 = run_pipeline(ws, [voice.STAGE])  # availability is in the input hash: re-runs
    assert len(calls) == 1 and s2["stages"]["voice"]["finished"] != s1["stages"]["voice"]["finished"]
    c = json.loads(ws.path("perception", "voice_enhance.json").read_text())["clips"]["c01"]
    assert c["applied"] and c["voice"] == "mezz/c01.voice.wav" and c["samples"] == enhance.wav_frames(ws.path("mezz", "c01.voice.wav"))
    assert set(edit.enhanced_voice(ctx)) == {"c01"}

    s3 = run_pipeline(ws, [voice.STAGE])  # nothing changed: skipped
    assert len(calls) == 1 and s3["stages"]["voice"]["finished"] == s2["stages"]["voice"]["finished"]

    ws.path("mezz", "c01.voice.wav").unlink()  # an output vanished: redone
    run_pipeline(ws, [voice.STAGE])
    assert len(calls) == 2

    monkeypatch.setattr(enhance, "STRENGTH", ((float("-inf"), 12.0),))  # policy change: redone
    run_pipeline(ws, [voice.STAGE])
    assert calls[-1] == 12.0 and len(calls) == 3

    run_pipeline(ws, [voice.STAGE], options={"voice_enhance": False})  # switched off: original voice
    assert not ws.path("mezz", "c01.voice.wav").exists() and edit.enhanced_voice(StageContext(ws=ws)) == {}


def _failing_enhance(exc):
    def fake(binary, src, out, atten, *, work):  # writes a partial output, then fails
        out.write_bytes(b"RIFF partial")
        raise exc
    return fake


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("exc", [tools.ToolError(["deep-filter"], 1, "thread panicked"),
                                 RuntimeError("deep-filter output 10 samples @ 48000 Hz × 1 ch; need 99 @ 48000 × 2"),
                                 subprocess.TimeoutExpired("deep-filter", 3600)])
def test_enhance_failure_keeps_the_original_audio_and_never_blocks(exc, tmp_path, monkeypatch):
    x, spans = _speech_like(8.0, SR)
    ws = _workspace(tmp_path, x + np.random.default_rng(0).normal(0, 0.01, x.size), spans)
    monkeypatch.setattr(enhance, "deep_filter", lambda: Path("/fake/deep-filter"))
    monkeypatch.setattr(enhance, "enhance", _failing_enhance(exc))
    s = run_pipeline(ws, [voice.STAGE])  # no raise: the step is skipped for that clip
    c = json.loads(ws.path("perception", "voice_enhance.json").read_text())["clips"]["c01"]
    assert s["stages"]["voice"]["status"] == "done"
    assert c["applied"] is False and c["reason"].startswith(f"enhance failed: {type(exc).__name__}") and "voice" not in c
    assert not ws.path("mezz", "c01.voice.wav").exists()  # partial output removed
    assert edit.enhanced_voice(StageContext(ws=ws)) == {}  # the renderer reads the mezzanine audio


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
def test_enhance_measurement_failure_after_a_good_output_drops_it(tmp_path, monkeypatch):
    x, spans = _speech_like(8.0, SR)
    ws = _workspace(tmp_path, x + np.random.default_rng(0).normal(0, 0.01, x.size), spans)
    monkeypatch.setattr(enhance, "deep_filter", lambda: Path("/fake/deep-filter"))
    monkeypatch.setattr(enhance, "enhance", _copy_enhance([]))
    monkeypatch.setattr(enhance, "after", lambda *a: (_ for _ in ()).throw(ValueError("bad levels")))
    run_pipeline(ws, [voice.STAGE])
    c = json.loads(ws.path("perception", "voice_enhance.json").read_text())["clips"]["c01"]
    assert c["applied"] is False and "samples" not in c and c["reason"] == "enhance failed: ValueError: bad levels"
    assert not ws.path("mezz", "c01.voice.wav").exists()


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
def test_enhance_leaves_no_partial_file_when_the_copy_fails(tmp_path, monkeypatch):
    import soundfile as sf

    src = tmp_path / "src.wav"
    sf.write(str(src), np.zeros((SR, 2), np.float32), SR)
    fake = tmp_path / "deep-filter"  # copies its input: `deep-filter -D --atten-lim-db X -o DIR FILE`
    fake.write_text('#!/bin/sh\nmkdir -p "$5" && cp "$6" "$5/"\n')
    fake.chmod(0o755)
    out, work = tmp_path / "mezz" / "c01.voice.wav", tmp_path / "mezz" / ".voice_tmp"
    out.parent.mkdir()
    assert enhance.enhance(fake, src, out, 12.0, work=work)["samples"] == SR  # the fake binary works

    out.unlink()

    def broken_copy(src_, dst, n):
        dst.write_bytes(b"RIFF partial")
        raise OSError("disk full")

    monkeypatch.setattr(enhance, "_copy_frames", broken_copy)
    with pytest.raises(OSError):
        enhance.enhance(fake, src, out, 12.0, work=work)
    assert sorted(p.name for p in out.parent.iterdir()) == [".voice_tmp"] and list(work.iterdir()) == []


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
def test_input_hash_covers_the_enhance_and_mix_code(tmp_path, monkeypatch):
    from reel import mix

    x, spans = _speech_like(4.0, SR)
    ws = _workspace(tmp_path, x, spans)
    monkeypatch.setattr(enhance, "deep_filter", lambda: None)
    ctx = StageContext(ws=ws)
    h0 = voice._input_hash(ctx)
    for mod in (enhance, mix):
        copy = tmp_path / f"copy_{Path(mod.__file__).name}"
        shutil.copyfile(mod.__file__, copy)
        monkeypatch.setattr(mod, "__file__", str(copy))
        assert voice._input_hash(ctx) == h0  # same code, same hash
        copy.write_text(copy.read_text() + "\n# changed\n")
        h1 = voice._input_hash(ctx)
        assert h1 != h0  # a code change re-runs the stage
        monkeypatch.undo()
        monkeypatch.setattr(enhance, "deep_filter", lambda: None)


# ------------------------------------------------------------------ integration: the real binary


@pytest.fixture(scope="module")
def deep_filter():
    if not FFMPEG:
        pytest.skip("needs ffmpeg")
    enhance.deep_filter.cache_clear()
    path = enhance.deep_filter()
    if path is None:
        pytest.skip("DeepFilterNet binary unavailable (platform or offline)")
    return path


@pytest.fixture(scope="module")
def speech(tmp_path_factory) -> tuple[np.ndarray, list[list[int]]]:
    """Real (synthetic-voice) speech at 48 kHz: two phrases with a 1.2 s pause, edges padded."""
    if shutil.which("say") is None:
        return _speech_like(12.0, SR)
    d = tmp_path_factory.mktemp("say")
    subprocess.run(["say", "-o", str(d / "v.aiff"), "Put ten percent of your salary into a separate account every month."], check=True)
    raw = subprocess.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(d / "v.aiff"), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    v = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    v = 0.3 * v / np.max(np.abs(v))
    gap = lambda s: np.zeros(int(s * SR))  # noqa: E731
    parts, spans, cur = [gap(0.6), v, gap(1.2), v, gap(0.6)], [], 0
    for k, p in enumerate(parts):
        if k % 2:
            spans.append([int(cur * 1e6 / SR), int((cur + p.size) * 1e6 / SR)])
        cur += p.size
    return np.concatenate(parts), spans


def _xcorr_lag(a: np.ndarray, b: np.ndarray, max_lag: int = 2400) -> int:
    """Lag of b relative to a (samples), by FFT cross-correlation."""
    n = 1 << int(np.ceil(np.log2(a.size + b.size)))
    c = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)
    lags = np.r_[np.arange(0, max_lag + 1), np.arange(-max_lag, 0)]
    return int(lags[np.argmax(np.r_[c[: max_lag + 1], c[-max_lag:]])])


def _read_wav(path: Path) -> np.ndarray:
    import soundfile as sf

    y, rate = sf.read(str(path), always_2d=True)
    assert rate == SR
    return y


@pytest.mark.integration
@pytest.mark.parametrize("trim_s", [0.0, 3.737])  # two lengths, one not a multiple of the 480-sample hop
def test_enhanced_voice_is_sample_aligned(deep_filter, speech, trim_s, tmp_path):
    import soundfile as sf

    clean, _spans = speech
    clean = clean[: clean.size - int(trim_s * SR)]
    noisy = clean + np.random.default_rng(2).normal(0, 10 ** (-35 / 20), clean.size)
    src = tmp_path / "in.wav"
    sf.write(str(src), np.stack([noisy, 0.8 * noisy], axis=1).astype(np.float32), SR, subtype="PCM_16")
    out = tmp_path / "c01.voice.wav"
    meta = enhance.enhance(deep_filter, src, out, 24.0, work=tmp_path / "work")
    y = _read_wav(out)
    assert y.shape == (clean.size, 2) and meta["samples"] == clean.size  # same length, same channels
    for ch in range(2):
        assert abs(_xcorr_lag(clean, y[:, ch])) <= 1  # no delay: lag 0 ± 1 sample
    assert not (tmp_path / "work").exists() or not any((tmp_path / "work").iterdir())


@pytest.mark.integration
def test_noise_reduction_improves_snr(deep_filter, speech, tmp_path):
    import soundfile as sf

    clean, spans = speech
    noisy = clean + np.random.default_rng(3).normal(0, 10 ** (-35 / 20), clean.size)  # phone-ish: SNR ≈ 20 dB
    d = enhance.decide(read_16k(noisy), ANALYSIS_RATE, spans)
    assert d["apply"], d
    src = tmp_path / "in.wav"
    sf.write(str(src), np.stack([noisy, noisy], axis=1).astype(np.float32), SR, subtype="PCM_16")
    out = tmp_path / "c01.voice.wav"
    enhance.enhance(deep_filter, src, out, d["atten_lim_db"], work=tmp_path / "work")
    after = enhance.after(read_pcm(out), ANALYSIS_RATE, spans, d)
    gain = after["snr_db_after"] - d["snr_db"]
    print(f"SNR {d['snr_db']} → {after['snr_db_after']} dB (+{gain:.1f}) at atten-lim {d['atten_lim_db']} dB; "
          f"speech {d['speech_db']} → {after['speech_db_after']} dBFS; room-tone gain {after['room_tone_gain_db']} dB")
    assert gain >= 0.6 * d["atten_lim_db"]  # most of the allowed attenuation is achieved
    assert abs(after["speech_db_after"] - d["speech_db"]) < 3.0  # the voice itself keeps its level
    assert -d["atten_lim_db"] - 3 <= after["room_tone_gain_db"] < -6  # room tone follows the new floor


def read_16k(x: np.ndarray) -> np.ndarray:
    """48 kHz → 16 kHz, the analysis rate (exact 3:1 by averaging is enough for levels)."""
    n = x.size // 3 * 3
    return x[:n].reshape(-1, 3).mean(axis=1).astype(np.float32)


@pytest.mark.integration
def test_renderer_swaps_in_the_enhanced_voice_sample_exactly(deep_filter, speech, tmp_path):
    clean, spans = speech
    noisy = clean + np.random.default_rng(4).normal(0, 10 ** (-35 / 20), clean.size)
    ws = _workspace(tmp_path, noisy, spans)
    run_pipeline(ws, [voice.STAGE])
    ctx = StageContext(ws=ws)
    ev = edit.enhanced_voice(ctx)
    assert set(ev) == {"c01"}
    n_f = int(clean.size / SR * FPS) - 2
    prov = Provenance(item="k0", words=[0, 0])
    tl = Timeline(fps="25/1", width=1080, height=1920, duration_f=n_f - 25,
                  assets={"c01": Asset(id="c01", kind=AssetKind.video, uri="mezz/c01v.mov")},
                  video=[VideoClip(id="v_k0", asset="c01", at_f=0, dur_f=n_f - 25, src_in_us=tb.frame_to_us(25, FPS),
                                   src_out_us=tb.frame_to_us(n_f, FPS), src=prov)],
                  audio=[AudioClip(id="a_k0", asset="c01", at_f=0, dur_f=n_f - 25, src_in_us=tb.frame_to_us(25, FPS), role="voice", src=prov)])
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", f"color=gray:size=320x568:rate=25:duration={clean.size / SR}", "-i", str(ws.path("mezz", "c01.mov")),
                  "-map", "0:v", "-map", "1:a", "-c:v", "prores_ks", "-c:a", "copy", "-shortest", str(ws.path("mezz", "c01v.mov"))])
    raw_orig, raw_enh = tmp_path / "orig.mov", tmp_path / "enh.mov"
    render.render_base(tl, ws.root, raw_orig, finish_audio=False)
    render.render_base(tl, ws.root, raw_enh, finish_audio=False, enhanced_voice={"c01": (ev["c01"][0], 0.0)})
    a, b = (_decode(p) for p in (raw_orig, raw_enh))
    assert a.size == b.size and abs(_xcorr_lag(a, b)) <= 1  # the swap keeps sync to the sample
    assert _db(b) < _db(a)  # and the noise is lower

    # finished audio: room tone from the original's quiet stretch, lowered to the enhanced floor — no dead air
    from reel.stages.edit import room_tones

    rt = {k: (s, e, db + ev[k][1]) for k, (s, e, db) in room_tones(ctx).items()}
    fin = tmp_path / "fin.mov"
    render.render_base(tl, ws.root, fin, room_tone=rt, enhanced_voice=ev)
    y = _decode(fin)
    win = int(0.05 * SR)
    lv = 20 * np.log10(np.sqrt((y[: y.size // win * win].reshape(-1, win) ** 2).mean(axis=1)) + 1e-12)[2:-2]
    assert lv.min() > -85, "digital silence in the finished voice track"


def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(path), "-map", "0:a", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)
