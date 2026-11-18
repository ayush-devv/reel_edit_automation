"""Find where a Short's audio comes from in a long episode by audio fingerprint matching.

A Short re-uses the episode's exact audio, so short-time log-mel patterns line up. Each 2 s chunk
of the Short is cross-correlated (FFT, all mel bands at once) against the whole episode; a chunk
counts as found when its correlation peak stands far above the noise. Seconds for a 3-hour
episode, instead of an hour of speech recognition. Music the editor added under the Short lowers
the peaks but speech bands still dominate.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SR = 8000
HOP = 160  # 20 ms frames
N_MELS = 32
CHUNK_S = 2.0
STEP_S = 1.0
Z_MIN = 7.0  # correlation peak must be this many SDs above the chunk's correlation noise


def decode(path: Path, ffmpeg: str) -> np.ndarray:
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def features(y: np.ndarray) -> np.ndarray:
    import librosa

    m = librosa.feature.melspectrogram(y=y, sr=SR, n_fft=512, hop_length=HOP, n_mels=N_MELS, fmin=80, fmax=3800)
    f = np.log(m + 1e-6)
    f -= f.mean(axis=1, keepdims=True)
    f /= f.std(axis=1, keepdims=True) + 1e-6
    return f.astype(np.float32)  # (bands, frames)


def match(short: np.ndarray, episode: np.ndarray) -> tuple[float, float, float, list[tuple[float, float]]]:
    """(share of 2 s chunks found, span start s, span end s, [(short t, episode t)]) — densest 4-minute cluster."""
    fs, fe = features(short), features(episode)
    n = fe.shape[1]
    size = 1 << int(np.ceil(np.log2(n + int(CHUNK_S * SR / HOP))))
    E = np.fft.rfft(fe, size, axis=1)
    frames_per_s = SR / HOP
    clen, step = int(CHUNK_S * frames_per_s), int(STEP_S * frames_per_s)
    hits, chunks = [], 0
    for start in range(0, fs.shape[1] - clen + 1, step):
        c = fs[:, start:start + clen]
        if np.abs(c).mean() < 0.3:  # near-silent chunk: nothing to match
            continue
        chunks += 1
        C = np.fft.rfft(c[:, ::-1], size, axis=1)
        corr = np.fft.irfft((E * C).sum(axis=0), size)[clen - 1:clen - 1 + n - clen + 1]
        k = int(np.argmax(corr))
        z = (corr[k] - corr.mean()) / (corr.std() + 1e-9)
        if z >= Z_MIN:
            hits.append((start / frames_per_s, k / frames_per_s))
    if not hits:
        return 0.0, 0.0, 0.0, []
    ep = sorted(t for _, t in hits)
    best, i = (0, 0, 0), 0
    for j in range(len(ep)):
        while ep[j] - ep[i] > 240:
            i += 1
        if j - i + 1 > best[0]:
            best = (j - i + 1, i, j)
    count, i, j = best
    return count / max(1, chunks), ep[i], ep[j] + CHUNK_S, hits
