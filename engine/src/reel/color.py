"""Colour (build step 7F, ADR-0023): per-clip correction, then a look at partial strength.

Per clip, one 33³ LUT folds together
  1. correction toward neutral — gray-world white balance + exposure toward a mid-grey target,
     both clamped so deliberate looks in the footage survive;
  2. the Editor's look (or the brand's), blended with the identity at `strength`.
Applied with a single `lut3d` in RGB with explicit bt709 matrices on both conversions.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

LUT_SIZE = 33
WB_CLAMP = (0.90, 1.10)  # per-channel gain limits (gentle)
EXPOSURE_CLAMP = (0.85, 1.20)
# Exposure is only corrected outside a comfortable band (mean luma, 0–1 display-referred):
# deliberately bright or moody footage inside the band is left alone.
EXPOSURE_BAND = (0.30, 0.60)
EXPOSURE_TARGET = {"under": 0.36, "over": 0.55}


def _smooth(x: np.ndarray, amount: float) -> np.ndarray:
    """S-curve contrast around 0.5 (amount 0 = none)."""
    s = x * x * (3 - 2 * x)
    return np.clip(x + amount * (s - x), 0, 1)


def _sat(rgb: np.ndarray, amount: float) -> np.ndarray:
    y = (rgb @ np.array([0.2126, 0.7152, 0.0722]))[..., None]
    return np.clip(y + (rgb - y) * amount, 0, 1)


def _look_clean(c):
    return _sat(_smooth(c, 0.25), 1.05)


def _look_warm(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    return np.clip(np.stack([r * 1.05 + 0.01, g ** 0.98, b * 0.93], -1), 0, 1)


def _look_cool(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    return np.clip(np.stack([r * 0.95, g, b * 1.05 + 0.01], -1), 0, 1)


def _look_punchy(c):
    return _sat(_smooth(c, 0.6), 1.2)


def _look_film(c):
    lifted = 0.04 + c * 0.92  # lifted blacks, soft highlights
    return _sat(_look_warm(_smooth(lifted, 0.15)), 0.9)


def _look_teal_orange(c):
    y = (c @ np.array([0.2126, 0.7152, 0.0722]))[..., None]
    shadows, highs = np.clip(1 - y * 2, 0, 1), np.clip(y * 2 - 1, 0, 1)
    teal, orange = np.array([-0.05, 0.02, 0.05]), np.array([0.05, 0.01, -0.05])
    return np.clip(_smooth(c, 0.3) + shadows * teal + highs * orange, 0, 1)


LOOKS = {
    "none": (lambda c: c, "no look — correction only"),
    "clean": (_look_clean, "neutral, slightly crisper contrast; safe default for talking heads and tutorials"),
    "warm": (_look_warm, "warm, friendly skin; lifestyle, food, family, testimonials"),
    "cool": (_look_cool, "cooler, calmer, techy; product, finance, tech"),
    "punchy": (_look_punchy, "high contrast + saturation; energetic hooks, fitness, promos"),
    "film": (_look_film, "lifted blacks, soft highlights, muted; aesthetic vlogs, brand stories"),
    "teal_orange": (_look_teal_orange, "cinematic teal shadows / warm skin; travel, cinematic montages"),
}


def measure(frames: np.ndarray) -> dict:
    """Correction from sampled frames (N,H,W,3 uint8): gray-world gains + exposure, clamped."""
    x = frames.reshape(-1, 3).astype(np.float64) / 255.0
    lum = x @ np.array([0.2126, 0.7152, 0.0722])
    keep = (lum > 0.04) & (lum < 0.96)  # ignore crushed / clipped pixels
    x = x[keep] if keep.sum() > 100 else x
    mean = x.mean(axis=0)
    gray = mean.mean()
    gains = np.clip(gray / np.maximum(mean, 1e-6), *WB_CLAMP)
    y = float((mean * gains) @ np.array([0.2126, 0.7152, 0.0722]))
    if y < EXPOSURE_BAND[0]:
        exposure = EXPOSURE_TARGET["under"] / max(y, 1e-6)
    elif y > EXPOSURE_BAND[1]:
        exposure = EXPOSURE_TARGET["over"] / y
    else:
        exposure = 1.0
    exposure = float(np.clip(exposure, *EXPOSURE_CLAMP))
    return {"gains": [round(float(g), 4) for g in gains], "exposure": round(exposure, 4), "mean_rgb": [round(float(m), 4) for m in mean]}


def transform(rgb: np.ndarray, gains: list[float], exposure: float, look: str, strength: float) -> np.ndarray:
    corrected = np.clip(rgb * np.asarray(gains) * exposure, 0, 1)
    fn = LOOKS.get(look, LOOKS["none"])[0]
    return np.clip(corrected + strength * (fn(corrected) - corrected), 0, 1)


def write_lut(path: Path, gains: list[float], exposure: float, look: str, strength: float, size: int = LUT_SIZE) -> Path:
    """.cube (R fastest) for ffmpeg lut3d."""
    axis = np.linspace(0, 1, size)
    b, g, r = np.meshgrid(axis, axis, axis, indexing="ij")
    grid = np.stack([r, g, b], -1).reshape(-1, 3)
    out = transform(grid, gains, exposure, look, strength)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'TITLE "reel {look} {strength:.2f}"', f"LUT_3D_SIZE {size}"] + [f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}" for v in out]
    path.write_text("\n".join(lines) + "\n")
    return path


def needs_lut(gains: list[float], exposure: float, look: str, strength: float) -> bool:
    return not (all(abs(g - 1) < 0.005 for g in gains) and abs(exposure - 1) < 0.005 and (look == "none" or strength <= 0))
