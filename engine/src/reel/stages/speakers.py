"""Active speaker stage (after perception): perception/speakers.json, one entry per clip.

Its own stage so a change here never re-runs ASR. Only clips whose faces.json has multi-face
stretches load the landmarker; everything else gets an empty entry. Failures are non-fatal
(recorded per clip as `error`; the framing then keeps the blurred fill for wide two-shots) but
never final: while speakers.json holds an error the input hash never matches, so the next run
retries. Each entry carries the hash of its own clip's inputs (`key`) and a re-run reuses every
entry whose key still matches, so a retry re-analyses only the failed clips and leaves the file
byte-identical when nothing new succeeds (the base render, which hashes it, is not redone).
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
VERSION = 2
INPUTS = ("faces", "scenes", "words", "energy", "vad")


def _out(ctx: StageContext) -> Path:
    return ctx.ws.path("perception", "speakers.json")


def _read(ctx: StageContext, name: str) -> dict:
    p = ctx.ws.path("perception", f"{name}.json")
    return json.loads(p.read_text()) if p.exists() else {}


def _code() -> str:
    return hash_inputs([file_fingerprint(Path(p)) for p in (speakers.__file__, __file__)])


def _has_errors(ctx: StageContext) -> bool:
    try:
        prev = json.loads(_out(ctx).read_text()) if _out(ctx).exists() else {}
    except (OSError, ValueError):
        return True  # unreadable output: redo
    return any(isinstance(e, dict) and "error" in e for e in prev.values())


def _input_hash(ctx: StageContext) -> str:
    fps = {n: (file_fingerprint(p) if (p := ctx.ws.path("perception", f"{n}.json")).exists() else None) for n in INPUTS}
    # a recorded error makes the hash volatile: the stage is never "done" while a clip failed, so the next
    # run retries (only the failed clips — see `key` in _run); the stage itself never raises
    retry = time.time_ns() if _has_errors(ctx) else None
    return hash_inputs({**fps, "code": _code(), "v": VERSION, "retry": retry})


def _clip_key(mezz: Path, faces: dict, cuts: list, words: list, energy: dict, speech, code: str) -> str:
    return hash_inputs({"mezz": file_fingerprint(mezz) if mezz.exists() else None, "faces": faces, "cuts": cuts, "words": words,
                        "rms": energy.get("audio_rms_db"), "hop": energy.get("hop_us", 100_000), "speech": speech,
                        "code": code, "v": VERSION})


def _run(ctx: StageContext) -> dict:
    faces, scenes, energy, vad = (_read(ctx, n) for n in ("faces", "scenes", "energy", "vad"))
    words = _read(ctx, "words").get("words") or []
    try:
        prev = _read(ctx, "speakers")
    except ValueError:
        prev = {}
    code = _code()
    out, meta = {}, {}
    for clip, f in faces.items():
        if not isinstance(f, dict) or not f.get("samples"):
            out[clip] = {"tracks": [], "segments": [], "words": {}, "pieces": [], "skipped": True}
            continue
        mezz = ctx.ws.path("mezz", f"{clip}.mov")
        cw = [(w["i"], w["start_us"], w["end_us"]) for w in words if w["clip"] == clip]
        e = energy.get(clip) or {}
        cuts = (scenes.get(clip) or {}).get("cuts_us") or []
        speech = (vad.get(clip) or {}).get("speech")
        key = _clip_key(mezz, f, cuts, cw, e, speech, code)
        old = prev.get(clip)
        if isinstance(old, dict) and old.get("key") == key and "error" not in old:
            out[clip] = old  # unchanged inputs and code, analysed fine last time
            meta[clip] = {"reused": True}
            continue
        t0 = time.time()
        try:
            out[clip] = speakers.analyse_clip(mezz, f, cuts, cw, e.get("audio_rms_db"), e.get("hop_us", 100_000), speech)
        except Exception as exc:  # noqa: BLE001 — best effort, like the other visual modules; retried next run
            log.warning("speakers:%s failed (retried next run): %s", clip, exc)
            out[clip] = {"tracks": [], "segments": [], "words": {}, "pieces": [], "error": f"{type(exc).__name__}: {exc}"}
        out[clip]["key"] = key
        meta[clip] = {"s": round(time.time() - t0, 2), "pieces": len(out[clip].get("pieces", [])),
                      "segments": len(out[clip].get("segments", [])), "tracks": len(out[clip].get("tracks", []))}
        if "error" in out[clip]:
            meta[clip]["error"] = out[clip]["error"]
    atomic_write_json(_out(ctx), out)
    return {"clips": meta}


STAGE = Stage(name="speakers", input_hash=_input_hash, outputs=lambda ctx: [_out(ctx)], run=_run)
