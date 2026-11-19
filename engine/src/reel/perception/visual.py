"""Visual perception: scenes (PySceneDetect), faces (MediaPipe BlazeFace), motion energy,
colour palette (k-means) and on-screen text (RapidOCR). All lazy-imported.
"""

from __future__ import annotations

import os
import ssl
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

from reel.perception.audio import read_frames

FACE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/"
                  "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite")
MODEL_DIR = Path(os.environ.get("REEL_MODEL_DIR", Path.home() / ".cache" / "reel" / "models"))


# ------------------------------------------------------------------ scenes


def scene_cuts(mezz: Path) -> list[int]:
    """Cut times in µs (scene starts after the first)."""
    from scenedetect import AdaptiveDetector, detect

    scenes = detect(str(mezz), AdaptiveDetector(), show_progress=False)
    return [int(round(start.get_seconds() * 1e6)) for start, _ in scenes[1:]]


# ------------------------------------------------------------------ faces


def _face_model() -> Path:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / "blaze_face_short_range.tflite"
    if not path.exists():
        ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
        with urllib.request.urlopen(FACE_MODEL_URL, context=ctx, timeout=60) as r:  # noqa: S310 — fixed https URL
            data = r.read()
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path


def _iou(a: dict, b: dict) -> float:
    x0, y0 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x1, y1 = min(a["x"] + a["w"], b["x"] + b["w"]), min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


FACE_DETECT_VERSION = 2  # 2: tiled re-detection for small faces in wide shots


def faces(mezz: Path, fps: float = 4.0, width: int = 480) -> dict:
    """Face boxes per sample, normalised to the frame (x, y, w, h in 0–1)."""
    import mediapipe as mp

    frames, h, w = read_frames(mezz, fps, width)
    opts = mp.tasks.vision.FaceDetectorOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(_face_model())),
        min_detection_confidence=0.5,
    )
    samples = []
    # Context manager closes the detector deterministically (no noisy teardown in __del__).
    with mp.tasks.vision.FaceDetector.create_from_options(opts) as det:
        def detect(img: np.ndarray, ox: int = 0, oy: int = 0) -> list[dict]:
            res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)))
            out = []
            for d in res.detections:
                b = d.bounding_box
                out.append({"x": round((ox + b.origin_x) / w, 4), "y": round((oy + b.origin_y) / h, 4),
                            "w": round(b.width / w, 4), "h": round(b.height / h, 4),
                            "score": round(float(d.categories[0].score), 3) if d.categories else None})
            return out

        for k, frame in enumerate(frames):
            boxes = detect(frame)
            if not boxes and w > h:
                # wide shots: faces too small for the short-range model on the whole frame — look again on square
                # tiles across the frame (each face is then ~1.8× larger to the model), merging overlaps
                for x0 in sorted({0, (w - h) // 2, w - h}):
                    for b in detect(frame[:, x0:x0 + h], x0, 0):
                        if not any(_iou(b, o) > 0.3 for o in boxes):
                            boxes.append(b)
            samples.append({"t_us": int(round(k / fps * 1e6)), "faces": boxes})
    with_face = [s["faces"][0] for s in samples if s["faces"]]
    median = None
    if with_face:
        median = {key: round(float(np.median([f[key] for f in with_face])), 4) for key in ("x", "y", "w", "h")}
    return {"fps": fps, "samples": samples, "presence": round(len(with_face) / max(1, len(samples)), 3), "median_box": median}


# ------------------------------------------------------------------ motion


def motion_energy(mezz: Path, fps: float = 10.0, width: int = 96) -> dict:
    """Mean absolute luma difference between consecutive samples (0–255 scale)."""
    frames, _, _ = read_frames(mezz, fps, width, gray=True)
    if len(frames) < 2:
        return {"fps": fps, "values": []}
    f = frames[..., 0].astype(np.float32)
    diff = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    return {"fps": fps, "values": [0.0] + [round(float(v), 2) for v in diff]}


# ------------------------------------------------------------------ palette


def kmeans(pixels: np.ndarray, k: int = 5, iters: int = 12, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Plain k-means on RGB pixels → (centres[k,3], weights[k])."""
    rng = np.random.default_rng(seed)
    pts = pixels.reshape(-1, 3).astype(np.float32)
    if len(pts) > 20_000:
        pts = pts[rng.choice(len(pts), 20_000, replace=False)]
    k = min(k, len(pts))
    centres = pts[rng.choice(len(pts), k, replace=False)]
    for _ in range(iters):
        labels = np.argmin(((pts[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            members = pts[labels == j]
            if len(members):
                centres[j] = members.mean(axis=0)
    labels = np.argmin(((pts[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
    weights = np.bincount(labels, minlength=k) / len(labels)
    order = np.argsort(-weights)
    return centres[order], weights[order]


def _luma(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def palette(mezz: Path, samples: int = 6, width: int = 64) -> dict:
    frames, h, _ = read_frames(mezz, 1.0, width)
    if len(frames) == 0:
        return {"colors": []}
    pick = frames[np.linspace(0, len(frames) - 1, min(samples, len(frames))).astype(int)]
    centres, weights = kmeans(pick, k=5)
    caption_zone = pick[:, int(h * 0.60): int(h * 0.85)].astype(np.float32)
    rgb = pick.astype(np.float32)
    return {
        "colors": [{"hex": "#{:02X}{:02X}{:02X}".format(*map(int, c)), "weight": round(float(w), 3)} for c, w in zip(centres, weights)],
        "luma_mean": round(float(_luma(rgb).mean()), 1),
        "caption_zone_luma": round(float(_luma(caption_zone).mean()), 1),
        "warmth": round(float((rgb[..., 0] - rgb[..., 2]).mean()), 1),  # >0 warm, <0 cool
        "saturation": round(float((rgb.max(-1) - rgb.min(-1)).mean()), 1),
    }


# ------------------------------------------------------------------ OCR


@lru_cache(maxsize=1)
def _ocr():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def ocr(mezz: Path, fps: float = 1.0, width: int = 720, min_score: float = 0.6) -> dict:
    frames, h, w = read_frames(mezz, fps, width)
    engine = _ocr()
    items, last = [], set()
    for k, frame in enumerate(frames):
        result, _ = engine(np.ascontiguousarray(frame[..., ::-1]))  # RapidOCR expects BGR
        texts = set()
        for box, text, score in result or []:
            if float(score) < min_score or not text.strip():
                continue
            texts.add(text.strip())
            if text.strip() in last:
                continue  # same text as the previous sample
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            items.append({"t_us": int(round(k / fps * 1e6)), "text": text.strip(), "score": round(float(score), 3),
                          "box": [round(min(xs) / w, 3), round(min(ys) / h, 3), round(max(xs) / w, 3), round(max(ys) / h, 3)]})
        last = texts
    return {"fps": fps, "items": items}
