"""Person matte for text-behind-subject titles (build step 10g).

MediaPipe selfie segmenter (Apache-2.0) on the rendered base frames of the title window only;
the mask becomes a grey-scale video that ffmpeg uses to put the person back over the title.
"""

from __future__ import annotations

import os
import ssl
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np

from reel import config
from reel.perception.visual import MODEL_DIR

SEG_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/"
                 "selfie_segmenter/float16/latest/selfie_segmenter.tflite")
SEG_W = 256  # segmentation resolution (mask is upscaled + feathered)


def _model() -> Path:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / "selfie_segmenter.tflite"
    if not path.exists():
        ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
        with urllib.request.urlopen(SEG_MODEL_URL, context=ctx, timeout=60) as r:  # noqa: S310 — fixed https URL
            data = r.read()
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path


def mediapipe_masks(frames: np.ndarray) -> np.ndarray:
    """frames (N,H,W,3 uint8) → person probability masks (N,H,W float 0–1)."""
    import mediapipe as mp

    opts = mp.tasks.vision.ImageSegmenterOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(_model())),
                                                 output_confidence_masks=True)
    out = []
    with mp.tasks.vision.ImageSegmenter.create_from_options(opts) as seg:
        for f in frames:
            res = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(f)))
            m = res.confidence_masks[0].numpy_view().copy()
            out.append(m[..., 0] if m.ndim == 3 else m)
    return np.stack(out) if out else np.zeros((0,) + frames.shape[1:3], dtype=np.float32)


def window_frames(video: Path, start_f: int, end_f: int, width: int = SEG_W) -> np.ndarray:
    probe = subprocess.run([str(config.ffprobe_path()), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(video)], check=True, capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    height = int(round(h * width / w / 2) * 2)
    raw = subprocess.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(video), "-vf",
                          f"trim=start_frame={start_f}:end_frame={end_f},scale={width}:{height}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width, 3)


def make_matte(base: Path, start_f: int, end_f: int, out: Path, size: tuple[int, int], fps: str,
               masker: Callable[[np.ndarray], np.ndarray] = mediapipe_masks) -> dict:
    """Grey-scale matte video for frames [start_f, end_f) of `base`, at output size, feathered."""
    frames = window_frames(base, start_f, end_f)
    masks = masker(frames)
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    proc = subprocess.Popen([str(config.ffmpeg_path()), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
                             "-s", f"{masks.shape[2]}x{masks.shape[1]}", "-r", fps, "-i", "-",
                             "-vf", f"scale={w}:{h}:flags=bicubic,gblur=sigma=2", "-c:v", "ffv1", "-pix_fmt", "gray", str(out)],
                            stdin=subprocess.PIPE)
    proc.communicate((np.clip(masks, 0, 1) * 255).astype(np.uint8).tobytes())
    if proc.returncode:
        raise RuntimeError("matte encode failed")
    return {"frames": int(masks.shape[0]), "person_share": round(float((masks > 0.5).mean()), 3)}
