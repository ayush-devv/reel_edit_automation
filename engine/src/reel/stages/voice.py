"""Voice enhancement stage (after perception): DeepFilterNet3 per clip, strength from its SNR.

Writes mezz/<clip>.voice.wav for clips that need it (the base renderer's voice role reads it
instead of the mezzanine audio) and perception/voice_enhance.json with every decision. ASR,
VAD and room-tone selection keep using the original mezzanine audio. When the tool is
unavailable the clips are recorded as `unavailable` (the ffmpeg voice chain still applies) and
the stage re-runs once it can be fetched (availability is part of the input hash). A clip whose
enhancement fails (tool error, timeout, mismatched output) is recorded `applied: false` with the
reason and keeps its original audio; the rest of the edit is never blocked by it.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from reel import enhance, mix
from reel.perception import audio
from reel.runner import Stage, StageContext
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs

log = logging.getLogger(__name__)
VERSION = 2
UNAVAILABLE = "unavailable"


def _manifest(ctx: StageContext) -> dict:
    return json.loads(ctx.ws.path("source", "manifest.json").read_text())


def _report(ctx: StageContext) -> Path:
    return ctx.ws.path("perception", "voice_enhance.json")


def _voice_rel(clip_id: str) -> str:
    return f"mezz/{clip_id}.voice.wav"


def _enabled(ctx: StageContext) -> bool:
    return ctx.options.get("voice_enhance", True) is not False


def _code() -> str:
    """The code behind the decisions and the output (enhance, room-tone region, PCM reader, this stage)."""
    return hash_inputs([file_fingerprint(Path(p)) for p in (enhance.__file__, mix.__file__, audio.__file__, __file__)])


def _input_hash(ctx: StageContext) -> str:
    vad = ctx.ws.path("perception", "vad.json")
    return hash_inputs({
        "mezz": [file_fingerprint(ctx.ws.path("mezz", f"{c['id']}.mov")) for c in _manifest(ctx)["clips"]],
        "vad": file_fingerprint(vad) if vad.exists() else None,
        "policy": enhance.policy(), "enabled": _enabled(ctx), "v": VERSION, "code": _code(),
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
        pcm = audio.read_pcm(mezz)
        d = enhance.decide(pcm, audio.ANALYSIS_RATE, speech)
        entry = {k: v for k, v in d.items() if k != "apply"} | {"applied": False}
        if d["apply"] and not _enabled(ctx):
            entry["reason"] = "disabled (voice_enhance=false)"
        elif d["apply"] and binary is None:
            entry["reason"] = UNAVAILABLE
        elif d["apply"]:
            try:
                res = enhance.enhance(binary, mezz, out, d["atten_lim_db"], work=work)
                res |= enhance.after(audio.read_pcm(out), audio.ANALYSIS_RATE, speech, d)
            except Exception as exc:  # noqa: BLE001 — optional step: this clip keeps its original audio
                log.warning("voice %s: enhancement failed, keeping the original audio (%s: %s)", cid, type(exc).__name__, exc)
                first = next(iter(str(exc).strip().splitlines()), "")  # ToolError: "<tool> exited N:" + stderr tail
                entry["reason"] = f"enhance failed: {type(exc).__name__}: {first}"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            else:
                entry |= res | {"applied": True, "voice": _voice_rel(cid)}
        if not entry["applied"]:  # no stale or partial enhanced file: the renderer reads the mezzanine audio
            out.unlink(missing_ok=True)
        report["clips"][cid] = entry
        log.info("voice %s: %s", cid, entry["reason"])
    shutil.rmtree(work, ignore_errors=True)  # also clears leftovers of a run killed mid-way
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
