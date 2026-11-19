"""Active speaker stage (after perception): perception/speakers.json, one entry per clip.

Its own stage so a change here never re-runs ASR. Only clips whose faces.json has multi-face
stretches load the landmarker; everything else gets an empty entry. Failures are non-fatal
(recorded per clip; the framing then keeps the blurred fill for wide two-shots).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from reel.perception import speakers
from reel.runner import Stage, StageContext
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs

log = logging.getLogger(__name__)
VERSION = 1
INPUTS = ("faces", "scenes", "words", "energy", "vad")


def _out(ctx: StageContext) -> Path:
    return ctx.ws.path("perception", "speakers.json")


def _read(ctx: StageContext, name: str) -> dict:
    p = ctx.ws.path("perception", f"{name}.json")
    return json.loads(p.read_text()) if p.exists() else {}


def _input_hash(ctx: StageContext) -> str:
    fps = {n: (file_fingerprint(p) if (p := ctx.ws.path("perception", f"{n}.json")).exists() else None) for n in INPUTS}
    return hash_inputs({**fps, "code": file_fingerprint(Path(speakers.__file__)), "v": VERSION})


def _run(ctx: StageContext) -> dict:
    faces, scenes, energy, vad = (_read(ctx, n) for n in ("faces", "scenes", "energy", "vad"))
    words = _read(ctx, "words").get("words") or []
    out, meta = {}, {}
    for clip, f in faces.items():
        if not isinstance(f, dict) or not f.get("samples"):
            out[clip] = {"tracks": [], "segments": [], "words": {}, "pieces": [], "skipped": True}
            continue
        mezz = ctx.ws.path("mezz", f"{clip}.mov")
        cw = [(w["i"], w["start_us"], w["end_us"]) for w in words if w["clip"] == clip]
        e = energy.get(clip) or {}
        t0 = time.time()
        try:
            out[clip] = speakers.analyse_clip(mezz, f, (scenes.get(clip) or {}).get("cuts_us") or [], cw,
                                              e.get("audio_rms_db"), e.get("hop_us", 100_000), (vad.get(clip) or {}).get("speech"))
        except Exception as exc:  # noqa: BLE001 — best effort, like the other visual modules
            log.warning("speakers:%s failed: %s", clip, exc)
            out[clip] = {"tracks": [], "segments": [], "words": {}, "pieces": [], "error": f"{type(exc).__name__}: {exc}"}
        meta[clip] = {"s": round(time.time() - t0, 2), "pieces": len(out[clip].get("pieces", [])),
                      "segments": len(out[clip].get("segments", [])), "tracks": len(out[clip].get("tracks", []))}
    atomic_write_json(_out(ctx), out)
    return {"clips": meta}


STAGE = Stage(name="speakers", input_hash=_input_hash, outputs=lambda ctx: [_out(ctx)], run=_run)
