"""Voice enhancement: DeepFilterNet3 noise suppression on each clip's voice track.

- Tool: the pinned `deep-filter` 0.5.6 release binary (MIT/Apache-2.0, model embedded), fetched
  once into the model cache and checked against a pinned SHA-256. macOS arm64 only; anywhere
  else, offline, or on any failure the step is skipped and the ffmpeg voice chain (afftdn …)
  still cleans the voice.
- Strength from the clip's own SNR (speech RMS over VAD spans vs the quiet-stretch floor):
  clean audio is left alone, noisier audio gets a larger attenuation limit. The limit is never
  "full" (100 dB): fully suppressed pauses sound like dead air.
- Output: a 48 kHz WAV per clip, sample-aligned with the mezzanine audio (same length, no
  delay). `deep-filter -D` removes the STFT/look-ahead delay but drops that many samples off
  the end, so the input is padded and the output cut back to the original length.
ASR/VAD keep reading the original audio; only the renderer's voice role uses the enhanced file.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import ssl
import sys
import time
import urllib.request
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

from reel import config, mix, tools

log = logging.getLogger(__name__)

DF_VERSION = "0.5.6"
DF_ASSET = f"deep-filter-{DF_VERSION}-aarch64-apple-darwin"
DF_URL = f"https://github.com/Rikorose/DeepFilterNet/releases/download/v{DF_VERSION}/{DF_ASSET}"
# GitHub publishes no digest for this asset: pinned from the first download (2026-11-19)
DF_SHA256 = "4601e7f4e4c03e59a4c5b5000216ef3add3e808799cfccd95e14e83ea4611081"
DOWNLOAD_TIMEOUT_S = 20

PAD_SAMPLES = 4800  # 0.1 s; > the 1440-sample delay that `-D` takes off the end
SKIP_SNR_DB = 40.0  # at or above: already clean, leave it alone
SKIP_FLOOR_DB = -70.0  # floor at or below: nothing to suppress
# (minimum SNR, attenuation limit dB): first match wins
STRENGTH = ((30.0, 10.0), (20.0, 16.0), (float("-inf"), 24.0))
FRAME_US = 50_000
ROOM_TONE_GAIN_MIN_DB = -40.0


def policy() -> dict:
    """Everything that changes the decision or the output (part of the stage's input hash)."""
    return {"df": DF_SHA256, "pad": PAD_SAMPLES, "skip_snr": SKIP_SNR_DB, "skip_floor": SKIP_FLOOR_DB,
            "strength": [list(s) for s in STRENGTH], "flags": ["-D"]}


# ------------------------------------------------------------------ tool fetch


def _model_dir() -> Path:
    from reel.perception.visual import MODEL_DIR

    return MODEL_DIR


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download(url: str) -> bytes:
    """urllib first; on failure the system curl, which trusts the macOS keychain (python.org
    builds and certifi do not, e.g. behind a TLS-inspecting proxy). The hash check follows."""
    try:
        ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
        with urllib.request.urlopen(url, context=ctx, timeout=DOWNLOAD_TIMEOUT_S) as r:  # noqa: S310 — pinned URL + hash
            return r.read()
    except Exception as exc:  # noqa: BLE001
        curl = shutil.which("curl")
        if not curl or not url.startswith("https://"):
            raise
        log.info("urllib download failed (%s); retrying with curl", exc)
        return tools.run([curl, "-fsSL", "--proto", "=https", "--max-time", str(DOWNLOAD_TIMEOUT_S * 6), url]).stdout


def supported_platform() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


@lru_cache(maxsize=1)
def deep_filter() -> Path | None:
    """Path to the verified `deep-filter` binary, downloading it once; None when unavailable."""
    if not supported_platform():
        log.warning("voice enhancement skipped: no DeepFilterNet binary for %s/%s", sys.platform, platform.machine())
        return None
    path = _model_dir() / DF_ASSET
    try:
        if path.exists() and _sha256(path) == DF_SHA256:
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _download(DF_URL)
        digest = hashlib.sha256(data).hexdigest()
        if digest != DF_SHA256:
            raise ValueError(f"sha256 mismatch: got {digest}, pinned {DF_SHA256}")
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.chmod(0o755)
        tmp.replace(path)
        return path
    except Exception as exc:  # noqa: BLE001 — enhancement is optional; the ffmpeg chain still applies
        log.warning("voice enhancement skipped: DeepFilterNet unavailable (%s: %s)", type(exc).__name__, exc)
        return None


# ------------------------------------------------------------------ strength decision


def _mask(n: int, rate: int, spans_us: list[list[int]]) -> np.ndarray:
    m = np.zeros(n, bool)
    for s, e in spans_us:
        m[int(s * rate / 1e6):int(e * rate / 1e6)] = True
    return m


def _db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(x.astype(np.float64) ** 2) + 1e-20))


def levels(pcm: np.ndarray, rate: int, speech_us: list[list[int]]) -> dict | None:
    """Speech level (RMS over VAD spans) and noise floor (quiet non-speech stretch), dBFS."""
    if pcm.size == 0 or not speech_us:
        return None
    speech = _mask(pcm.size, rate, speech_us)
    if not speech.any():
        return None
    region = mix.room_tone_region(pcm, rate, speech_us)
    if region is not None:
        floor, where = float(region[2]), "room_tone"
    else:  # no 0.5 s pause: quietest tenth of the short non-speech frames
        fr = int(rate * FRAME_US / 1e6)
        n = pcm.size // fr
        quiet = ~speech[: n * fr].reshape(n, fr).any(axis=1)
        if not quiet.any():
            return None
        frames = pcm[: n * fr].reshape(n, fr)[quiet].astype(np.float64)
        floor, where = float(np.percentile(10 * np.log10(np.mean(frames ** 2, axis=1) + 1e-20), 10)), "pause_frames"
    return {"speech_db": round(_db(pcm[speech]), 1), "floor_db": round(floor, 1), "floor_from": where,
            "region_us": list(region[:2]) if region else None}


def decide(pcm: np.ndarray, rate: int, speech_us: list[list[int]]) -> dict:
    """{"apply", "atten_lim_db", "snr_db", "speech_db", "floor_db", "reason", …} for one clip."""
    lv = levels(pcm, rate, speech_us)
    if lv is None:
        return {"apply": False, "reason": "no speech or no pause to measure the noise floor"}
    snr = round(lv["speech_db"] - lv["floor_db"], 1)
    out = {**lv, "snr_db": snr}
    if lv["floor_db"] <= SKIP_FLOOR_DB:
        return {**out, "apply": False, "reason": f"noise floor {lv['floor_db']} dBFS ≤ {SKIP_FLOOR_DB}: clean"}
    if snr >= SKIP_SNR_DB:
        return {**out, "apply": False, "reason": f"SNR {snr} dB ≥ {SKIP_SNR_DB}: clean"}
    atten = next(a for lo, a in STRENGTH if snr >= lo)
    return {**out, "apply": True, "atten_lim_db": atten, "reason": f"SNR {snr} dB → attenuation limit {atten:g} dB"}


# ------------------------------------------------------------------ processing


def _copy_frames(src: Path, dst: Path, n: int) -> None:
    """First `n` sample frames of `src` into `dst` (same format), streamed."""
    with wave.open(str(src)) as r, wave.open(str(dst), "wb") as w:
        w.setparams(r.getparams())
        left = n
        while left > 0:
            chunk = r.readframes(min(left, 1 << 18))
            if not chunk:
                break
            w.writeframes(chunk)
            left -= len(chunk) // (r.getsampwidth() * r.getnchannels())


def enhance(binary: Path, src: Path, out: Path, atten_lim_db: float, *, work: Path, timeout: float = 3600) -> dict:
    """Enhanced 48 kHz copy of `src`'s first audio stream at `out`, sample-aligned with it."""
    work.mkdir(parents=True, exist_ok=True)
    stem = out.stem.replace(".", "_")
    raw, padded, df_out = work / f"{stem}.raw.wav", work / f"{stem}.wav", work / "df"
    for p in (raw, padded):
        p.unlink(missing_ok=True)
    shutil.rmtree(df_out, ignore_errors=True)
    try:
        tools.ffmpeg(["-y", "-i", str(src), "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", "-ar", str(config.AUDIO_RATE), str(raw)])
        with wave.open(str(raw)) as r:
            n, channels = r.getnframes(), r.getnchannels()
        tools.ffmpeg(["-y", "-i", str(raw), "-af", f"apad=pad_len={PAD_SAMPLES}", "-c:a", "pcm_s16le", str(padded)])
        t0 = time.time()
        tools.run([binary, "-D", "--atten-lim-db", f"{atten_lim_db:g}", "-o", df_out, padded], timeout=timeout)
        seconds = time.time() - t0
        result = df_out / padded.name
        with wave.open(str(result)) as r:
            got, rate, ch = r.getnframes(), r.getframerate(), r.getnchannels()
        if rate != config.AUDIO_RATE or ch != channels or got < n:
            raise RuntimeError(f"deep-filter output {got} samples @ {rate} Hz × {ch} ch; need {n} @ {config.AUDIO_RATE} × {channels}")
        tmp = out.with_name(f".{out.stem}.tmp.wav")
        _copy_frames(result, tmp, n)
        tmp.replace(out)
    finally:
        for p in (raw, padded):
            p.unlink(missing_ok=True)
        shutil.rmtree(df_out, ignore_errors=True)
    return {"samples": n, "channels": channels, "df_s": round(seconds, 2), "realtime_x": round(n / config.AUDIO_RATE / max(seconds, 1e-6), 1)}


def wav_frames(path: Path) -> int:
    with wave.open(str(path)) as r:
        return r.getnframes()


def after(enhanced_pcm: np.ndarray, rate: int, speech_us: list[list[int]], decision: dict) -> dict:
    """Levels of the enhanced track over the same spans, and the room-tone gain that matches them."""
    speech = _mask(enhanced_pcm.size, rate, speech_us)
    res = {"speech_db_after": round(_db(enhanced_pcm[speech]), 1) if speech.any() else None}
    region = decision.get("region_us")
    if region:
        seg = enhanced_pcm[int(region[0] * rate / 1e6):int(region[1] * rate / 1e6)]
        floor_after = round(_db(seg), 1)
        res["floor_db_after"] = floor_after
        res["room_tone_gain_db"] = round(min(0.0, max(ROOM_TONE_GAIN_MIN_DB, floor_after - decision["floor_db"])), 1)
        if res["speech_db_after"] is not None:
            res["snr_db_after"] = round(res["speech_db_after"] - floor_after, 1)
    return res
