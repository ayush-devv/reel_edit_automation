"""Voice enhancement stage (after perception): DeepFilterNet3 per clip, strength from its SNR.

Writes mezz/<clip>.voice.wav for clips that need it (the base renderer's voice role reads it
instead of the mezzanine audio) and perception/voice_enhance.json with every decision. ASR,
VAD and room-tone selection keep using the original mezzanine audio. When the tool is
unavailable the clips are recorded as `unavailable` (the ffmpeg voice chain still applies) and
the stage re-runs once it can be fetched (availability is part of the input hash).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from reel import enhance
from reel.perception.audio import ANALYSIS_RATE, read_pcm
from reel.runner import Stage, StageContext
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs

log = logging.getLogger(__name__)
VERSION = 1
UNAVAILABLE = "unavailable"


def _manifest(ctx: StageContext) -> dict:
    return json.loads(ctx.ws.path("source", "manifest.json").read_text())


def _report(ctx: StageContext) -> Path:
    return ctx.ws.path("perception", "voice_enhance.json")


def _voice_rel(clip_id: str) -> str:
    return f"mezz/{clip_id}.voice.wav"


def _enabled(ctx: StageContext) -> bool:
    return ctx.options.get("voice_enhance", True) is not False


def _input_hash(ctx: StageContext) -> str:
    vad = ctx.ws.path("perception", "vad.json")
    return hash_inputs({
        "mezz": [file_fingerprint(ctx.ws.path("mezz", f"{c['id']}.mov")) for c in _manifest(ctx)["clips"]],
        "vad": file_fingerprint(vad) if vad.exists() else None,
        "policy": enhance.policy(), "enabled": _enabled(ctx), "v": VERSION,
        # fetched here (cached after the first time): a run that fell back offline re-runs once the tool is there
        "available": _enabled(ctx) and enhance.deep_filter() is not None,
    })


def _outputs(ctx: StageContext) -> list[Path]:
    rep = _report(ctx)
    if not rep.exists():
        return [rep]
    clips = json.loads(rep.read_text()).get("clips", {})
    return [rep, *(ctx.ws.root / c["voice"] for c in clips.values() if c.get("applied"))]


def _run(ctx: StageContext) -> dict:
    m = _manifest(ctx)
    vad = json.loads(ctx.ws.path("perception", "vad.json").read_text())
    binary = enhance.deep_filter() if _enabled(ctx) else None
    report = {"tool": f"deep-filter {enhance.DF_VERSION}" if binary else None, "policy": enhance.policy(), "clips": {}}
    work = ctx.ws.path("mezz", ".voice_tmp")
    for c in m["clips"]:
        cid = c["id"]
        out = ctx.ws.root / _voice_rel(cid)
        mezz = ctx.ws.path("mezz", f"{cid}.mov")
        speech = (vad.get(cid) or {}).get("speech") or []
        pcm = read_pcm(mezz)
        d = enhance.decide(pcm, ANALYSIS_RATE, speech)
        entry = {k: v for k, v in d.items() if k != "apply"} | {"applied": False}
        if d["apply"] and not _enabled(ctx):
            entry["reason"] = "disabled (voice_enhance=false)"
        elif d["apply"] and binary is None:
            entry["reason"] = UNAVAILABLE
        elif d["apply"]:
            entry |= enhance.enhance(binary, mezz, out, d["atten_lim_db"], work=work)
            entry |= enhance.after(read_pcm(out), ANALYSIS_RATE, speech, d) | {"applied": True, "voice": _voice_rel(cid)}
        if not entry["applied"]:
            out.unlink(missing_ok=True)
        report["clips"][cid] = entry
        log.info("voice %s: %s", cid, entry["reason"])
    if work.exists():
        work.rmdir()
    atomic_write_json(_report(ctx), report)
    clips = report["clips"].values()
    return {"enhanced": sum(c["applied"] for c in clips), "clips": len(report["clips"]),
            "df_s": round(sum(c.get("df_s", 0.0) for c in clips), 2)}


def _validate(ctx: StageContext) -> bool:
    rep = json.loads(_report(ctx).read_text())
    for c in rep["clips"].values():
        if c.get("applied") and enhance.wav_frames(ctx.ws.root / c["voice"]) != c["samples"]:
            return False
    return True


STAGE = Stage(name="voice", input_hash=_input_hash, outputs=_outputs, run=_run, validate=_validate)
