"""Perception stage (build step 3). Order: OCR (vocabulary) → ASR → VAD/fillers → segments →
scenes, faces, motion, palette → prosody. Visual modules are non-fatal: a failure is recorded
in that module's JSON and the run continues; ASR failure is fatal.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from reel import brief as brief_mod
from reel.perception import asr, prosody, segments, vad, visual
from reel.perception.audio import extract_wav, read_pcm
from reel.runner import Stage, StageContext
from reel.schemas.perception import WordTable
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs

log = logging.getLogger(__name__)
VERSION = 1
OUTPUTS = ("words", "segments", "vad", "scenes", "faces", "energy", "prosody", "palette", "ocr")


def _manifest(ctx: StageContext) -> dict:
    return json.loads(ctx.ws.path("source", "manifest.json").read_text())


def _out(ctx: StageContext, name: str) -> Path:
    return ctx.ws.path("perception", f"{name}.json")


def _content(path: str | None) -> str | None:
    return file_fingerprint(Path(path)) if path else None


def _input_hash(ctx: StageContext) -> str:
    report = ctx.ws.path("mezz", "report.json")
    o = ctx.options
    return hash_inputs({
        "mezz": file_fingerprint(report) if report.exists() else None,
        "language": o.get("language"), "brief": _content(o.get("brief")), "brand": _content(o.get("brand")),
        "asr": o.get("asr_repo"), "visual": not o.get("skip_visual"), "v": VERSION,
    })


def _safe(name: str, fn, timings: dict):
    t0 = time.time()
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — visual modules are best-effort
        log.warning("%s failed: %s", name, exc)
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        timings[name] = round(time.time() - t0, 2)


def _run(ctx: StageContext) -> dict:
    m = _manifest(ctx)
    clips = [(c["id"], ctx.ws.path("mezz", f"{c['id']}.mov")) for c in m["clips"]]
    timings: dict[str, float] = {}
    skip_visual = bool(ctx.options.get("skip_visual"))

    # 1. on-screen text first: it feeds the ASR vocabulary
    ocr_out = {cid: ({"skipped": True} if skip_visual else _safe(f"ocr:{cid}", lambda p=path: visual.ocr(p), timings)) for cid, path in clips}
    atomic_write_json(_out(ctx, "ocr"), ocr_out)
    ocr_texts = [i["text"] for v in ocr_out.values() for i in (v.get("items") or [])]
    brief = brief_mod.load_brief(ctx.options.get("brief"))
    brand = brief_mod.load_brand(ctx.options.get("brand"))
    vocab = brief_mod.vocabulary(brief, brand, ocr_texts)

    # 2. ASR (fatal on failure)
    t0 = time.time()
    durations = {c["id"]: int(round(c["probe"]["duration_s"] * 1e6)) for c in m["clips"]}
    wavs = [(cid, extract_wav(path, ctx.ws.path("perception", "audio", f"{cid}.wav")), durations[cid]) for cid, path in clips]
    backend = asr.MlxWhisper(ctx.options["asr_repo"]) if ctx.options.get("asr_repo") else asr.MlxWhisper()
    language = ctx.options.get("language") or (brief.language if brief and brief.language in ("en", "hi") else None)
    words = asr.transcribe_clips(wavs, backend, language=language, vocabulary=vocab)
    timings["asr"] = round(time.time() - t0, 2)

    # 3. VAD + filler spans, audio energy
    vad_out, energy_out, energy_db = {}, {}, {}
    for cid, path in clips:
        pcm = read_pcm(path)
        clip_words = [w for w in words.words if w.clip == cid]
        vad_out[cid] = _safe(f"vad:{cid}", lambda p=pcm, cw=clip_words: vad.analyse(p, cw), timings)
        energy_db[cid] = prosody.rms_db(pcm)
        energy_out[cid] = {"audio_rms_db": energy_db[cid], "hop_us": prosody.HOP_US}

    # 4. phrases
    seg_table = segments.build_segments(words)

    # 5. visual
    scenes_out, faces_out, palette_out = {}, {}, {}
    for cid, path in clips:
        if skip_visual:
            scenes_out[cid] = faces_out[cid] = palette_out[cid] = {"skipped": True}
            continue
        scenes_out[cid] = _safe(f"scenes:{cid}", lambda p=path: {"cuts_us": visual.scene_cuts(p)}, timings)
        faces_out[cid] = _safe(f"faces:{cid}", lambda p=path: visual.faces(p), timings)
        palette_out[cid] = _safe(f"palette:{cid}", lambda p=path: visual.palette(p), timings)
        energy_out[cid]["motion"] = _safe(f"motion:{cid}", lambda p=path: visual.motion_energy(p), timings)

    # 6. delivery stats per phrase
    stats = prosody.segment_stats(words, seg_table, energy_db)

    atomic_write_json(_out(ctx, "words"), words.model_dump(mode="json"))
    atomic_write_json(_out(ctx, "segments"), seg_table.model_dump(mode="json"))
    atomic_write_json(_out(ctx, "vad"), vad_out)
    atomic_write_json(_out(ctx, "energy"), energy_out)
    atomic_write_json(_out(ctx, "scenes"), scenes_out)
    atomic_write_json(_out(ctx, "faces"), faces_out)
    atomic_write_json(_out(ctx, "palette"), palette_out)
    atomic_write_json(_out(ctx, "prosody"), {"segments": stats})
    return {
        "words": len(words.words), "segments": len(seg_table.segments), "language": words.language,
        "asr_backend": backend.name, "vocabulary_terms": len(vocab), "timings_s": timings,
        "low_conf_words": sum(w.low_conf for w in words.words), "suspect_words": sum(w.suspect for w in words.words),
        "vocab_corrected": [(w.original_text, w.text) for w in words.words if w.original_text],
        "proof_words": [(w.i, w.text, w.vocab_suggestion) for w in words.words if w.vocab_suspect],
    }


def _validate(ctx: StageContext) -> bool:
    WordTable.model_validate_json(_out(ctx, "words").read_text())
    return True


STAGE = Stage(
    name="perception",
    input_hash=_input_hash,
    outputs=lambda ctx: [_out(ctx, n) for n in OUTPUTS],
    run=_run,
    validate=_validate,
)
