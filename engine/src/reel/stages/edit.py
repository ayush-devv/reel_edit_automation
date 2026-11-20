"""Edit stages: story pass → finish pass → compile → base render → overlay → composite.

Decision-stage input hashes cover everything that changes Claude's answer (tables, brief,
brand, persona, knowledge, libraries, schema, model, effort) so a re-run never spends on
unchanged inputs and never keeps a stale plan. The Claude caller is injectable through
`options["claude_call"]` (tests pass a fake).
"""

from __future__ import annotations

import json
import logging
import shutil
from fractions import Fraction
from pathlib import Path

from reel import brief as brief_mod
from reel import claude_call, decide, mix, overlay, project, render, tools
from reel import timebase as tb
from reel.compile import compile_timeline, proof_list
from reel.runner import Stage, StageContext
from reel.schemas.plan import FinishPlan, StoryPlan
from reel.schemas.timeline import FFMPEG_FIELDS, REMOTION_FIELDS, Timeline, part
from reel.validate import errors, validate_finish
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs

VERSION = 2
log = logging.getLogger(__name__)
TABLE_FILES = ("tables/script.md", "tables/segments.json", "tables/takes.json", "tables/words.tsv", "tables/summary.md",
               "tables/sheets.json", "perception/words.json", "perception/edges.json")


def _fp(ctx: StageContext, rel: str) -> str | None:
    p = ctx.ws.root / rel
    return file_fingerprint(p) if p.exists() else None


def _opt_file(path: str | None) -> str | None:
    return file_fingerprint(Path(path)) if path else None


def _knowledge_fp() -> str:
    from reel import config

    files = (sorted((config.KNOWLEDGE_DIR / "graph").glob("*.yaml")) + sorted((config.KNOWLEDGE_DIR / "learned").glob("*.yaml"))
             + [config.KNOWLEDGE_DIR / "capabilities.yaml"])
    return hash_inputs([file_fingerprint(f) for f in files] + [_code_fp("knowledge", "capability_status")])


def _assets_fp() -> str:
    from reel import assets

    # assets/licenses/ is left out: a registry edit is checked by the stages' validate hooks (finish re-runs only when
    # its plan uses an asset the gate now refuses), so it never re-buys every project's finish pass
    lic = assets.ASSETS_DIR / "licenses"
    return hash_inputs([file_fingerprint(f) for f in sorted(assets.ASSETS_DIR.rglob("*"))
                        if f.is_file() and f.suffix in (".json", ".yaml") and not f.is_relative_to(lic)])


def _caller(ctx: StageContext):
    return ctx.options.get("claude_call") or claude_call.call


def _inputs(ctx: StageContext) -> decide.Inputs:
    return decide.load_inputs(ctx.ws, ctx.options.get("brief"), ctx.options.get("brand"))


def _model_key(ctx: StageContext) -> dict:
    return {"model": claude_call.DEFAULT_MODEL, "v": VERSION}


# ------------------------------------------------------------------ client b-roll pool (optional)


# ------------------------------------------------------------------ stock b-roll at edit time (optional, Pexels)


def _stock_dir(ctx: StageContext) -> Path:
    return ctx.ws.path("stock", "clips")


def _stock_hash(ctx: StageContext) -> str:
    """Hash the inputs that produce the searches, never the search results (Pexels changes over time):
    a rerun with the same talk and brief keeps the clips it already has."""
    from reel import stock

    if not ctx.options.get("stock"):
        return "off"
    return hash_inputs({"summary": _fp(ctx, "tables/summary.md"), "brief": _opt_file(ctx.options.get("brief")),
                        "keys": sorted(stock.available_keys()), "caps": [stock.MAX_PER_QUERY, stock.MAX_CLIPS],
                        "persona": file_fingerprint(stock.SCOUT), "v": VERSION})


def _stock(ctx: StageContext) -> dict:
    from reel import stock

    if not ctx.options.get("stock"):
        return {"status": "off"}
    brief = ctx.options.get("brief")
    if brief and Path(brief).exists() and not ctx.ws.path("brief.json").exists():
        shutil.copyfile(brief, ctx.ws.path("brief.json"))  # the scout reads it from the workspace
    status = stock.fetch_for_project(ctx.ws.root, _stock_dir(ctx), _caller(ctx), log_file=ctx.ws.path("log", "runs.jsonl"))
    atomic_write_json(ctx.ws.path("stock", "status.json"), status)
    if status["status"] != "ok":
        log.warning("stock b-roll %s: %s", status["status"], status.get("reason") or "; ".join(status.get("errors", [])))
    return {k: status[k] for k in ("status",)} | {"clips": len(status["clips"])}


STOCK = Stage(name="stock", input_hash=_stock_hash, run=_stock,
              outputs=lambda ctx: [ctx.ws.path("stock", "status.json")] if ctx.options.get("stock") else [])


# ------------------------------------------------------------------ b-roll pool: the client's folder + this project's stock clips


def _broll_folders(ctx: StageContext) -> list[Path]:
    folders = [Path(ctx.options["broll"])] if ctx.options.get("broll") else []
    if ctx.options.get("stock") and _stock_dir(ctx).is_dir():
        folders.append(_stock_dir(ctx))
    return folders


def _broll_hash(ctx: StageContext) -> str:
    from reel import broll

    folders = _broll_folders(ctx)
    if not folders:
        return "none"
    files = sorted((f.name, f.stat().st_size, int(f.stat().st_mtime)) for d in folders for f in d.iterdir() if f.suffix.lower() in broll.VIDEO_EXT)
    return hash_inputs({"files": files, "fps": project.project_fps(ctx.ws).__str__(), "persona": file_fingerprint(broll.PERSONA), "v": VERSION})


def _broll(ctx: StageContext) -> dict:
    from reel import broll

    folders = _broll_folders(ctx)
    if not folders:
        return {"clips": 0}
    return broll.index(ctx.ws, folders, project.project_fps(ctx.ws), _caller(ctx))


BROLL = Stage(name="broll", input_hash=_broll_hash, run=_broll,
              outputs=lambda ctx: [ctx.ws.path("broll", "index.json")] if _broll_folders(ctx) else [])


# ------------------------------------------------------------------ reference style (optional)


def _reference_hash(ctx: StageContext) -> str:
    from reel import reference

    ref = ctx.options.get("reference")
    return hash_inputs({"ref": file_fingerprint(Path(ref)), "code": file_fingerprint(Path(reference.__file__)), "v": VERSION}) if ref else "none"


def _reference(ctx: StageContext) -> dict:
    from reel import bakeoff, config, reference

    ref = ctx.options.get("reference")
    if not ref:
        return {}
    eng = config.ASR_ENGINES["en"]
    return reference.analyse(ctx.ws, Path(ref), asr_backend=bakeoff.engines([eng])[eng])


REFERENCE = Stage(name="reference", input_hash=_reference_hash, run=_reference,
                  outputs=lambda ctx: [ctx.ws.path("context", "reference_style.md")] if ctx.options.get("reference") else [])


# ------------------------------------------------------------------ story


def _client_key(ctx: StageContext) -> dict:
    """3a.2: the client's style profile, only when one exists (no profile: old hashes unchanged)."""
    from reel import client_memory

    fp = client_memory.fingerprint(ctx.ws)
    return {"client_style": fp} if fp else {}


def _story_hash(ctx: StageContext) -> str:
    window = {"window": _fp(ctx, "window.json")} if ctx.ws.path("window.json").exists() else {}  # absent: old hashes unchanged
    return hash_inputs({**window, **_client_key(ctx), "tables": [_fp(ctx, f) for f in TABLE_FILES], "reference": _fp(ctx, "context/reference_style.md"), "brief": _opt_file(ctx.options.get("brief")),
                        "brand": _opt_file(ctx.options.get("brand")), "persona": file_fingerprint(decide.STORY_PERSONA),
                        "knowledge": _knowledge_fp(), "schema": decide.schema(StoryPlan), "effort": decide.STORY_EFFORT,
                        "prompts": [decide.STORY_PROMPT, decide.READBACK_PROMPT], **_model_key(ctx)})


def _story_valid(ctx: StageContext) -> bool:
    inp = _inputs(ctx)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    return not errors(inp.story_issues(story))


STORY = Stage(name="story", input_hash=_story_hash,
              outputs=lambda ctx: [ctx.ws.path("plan", "story.json"), ctx.ws.path("plan", "story_readback.txt")],
              run=lambda ctx: decide.story_pass(_inputs(ctx), _caller(ctx)), validate=_story_valid)


# ------------------------------------------------------------------ finish


def _finish_hash(ctx: StageContext) -> str:
    from reel.clipfactory import batch_style

    # Clip Factory siblings only (old hashes unchanged). Sibling b-roll use is a menu hint, deliberately not hashed:
    # a reel that finished first must not re-run because a later sibling picked clips.
    style = batch_style(ctx.ws)
    batch = {"batch_style": style} if style else {}
    return hash_inputs({**batch, **_client_key(ctx), "story": _fp(ctx, "plan/story.json"), "brand": _opt_file(ctx.options.get("brand")), "broll": _fp(ctx, "broll/index.json"),
                        "reference": _fp(ctx, "context/reference_style.md"), "persona": file_fingerprint(decide.FINISH_PERSONA), "knowledge": _knowledge_fp(), "assets": _assets_fp(),
                        "schema": decide.schema(FinishPlan), "effort": decide.FINISH_EFFORT, "prompt": decide.FINISH_PROMPT,
                        **_model_key(ctx)})


def _finish_valid(ctx: StageContext) -> bool:
    inp = _inputs(ctx)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ctx.ws.path("plan", "finish.json"))
    return not errors(validate_finish(fin, story, inp.words, inp.idx, inp.kids))


def _finish(ctx: StageContext) -> dict:
    from reel.clipfactory import record_batch_style

    meta = decide.finish_pass(_inputs(ctx), _caller(ctx))
    record_batch_style(ctx.ws)  # Clip Factory: the first reel of a set fixes its look for the siblings
    return meta


FINISH = Stage(name="finish", input_hash=_finish_hash, outputs=lambda ctx: [ctx.ws.path("plan", "finish.json")],
               run=_finish, validate=_finish_valid)


# ------------------------------------------------------------------ compile


def _compile_hash(ctx: StageContext) -> str:
    return hash_inputs({f: _fp(ctx, f) for f in ("plan/story.json", "plan/finish.json", "perception/words.json",
                                                 "perception/edges.json", "source/manifest.json", "perception/palette.json",
                                                 "broll/index.json", "perception/vad.json", "perception/scenes.json")}
                       | {"assets": _assets_fp(), "brand": _opt_file(ctx.options.get("brand")), "proof": _fp(ctx, "qa/proof_confirmed.json"),
                          "logo": _logo_source_fp(ctx), "code": _code_fp("compile", "adapt", "script"), "v": VERSION})


def _logo_source_fp(ctx: StageContext) -> str | None:
    """The brand logo's contents (not just its path): replacing the image must re-compile and re-render."""
    bp = ctx.options.get("brand")
    if not bp:
        return None
    try:
        logo = brief_mod.load_brand(bp).logo
    except Exception:  # noqa: BLE001 — an unreadable brand kit fails in compile with a clear error
        return None
    if not logo:
        return None
    src = Path(logo) if Path(logo).is_absolute() else Path(bp).parent / logo
    return file_fingerprint(src) if src.is_file() else None


def _brand_logo(ctx: StageContext, brand) -> str | None:
    """Copy the brand logo into the workspace (the overlay's public dir); returns its workspace path."""
    if not brand or not brand.logo:
        return None
    src = Path(brand.logo)
    if not src.is_absolute() and ctx.options.get("brand"):
        src = Path(ctx.options["brand"]).parent / src
    if not src.is_file():
        raise FileNotFoundError(f"brand logo not found: {src}")
    rel = f"brand/logo{src.suffix.lower()}"
    dst = ctx.ws.path(*rel.split("/"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return rel


def _compile(ctx: StageContext) -> dict:
    inp = _inputs(ctx)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ctx.ws.path("plan", "finish.json"))
    tl, adapted = compile_for(ctx, inp, story, fin)
    atomic_write_json(ctx.ws.path("timeline", "timeline.json"), tl.model_dump(mode="json"))
    proof = proof_list(tl, story, inp.words)
    atomic_write_json(ctx.ws.path("qa", "proof_list.json"), proof)
    return {"adapted_tokens": adapted, "proof_words": len(proof), "caption_timing": tl.captions.timing if tl.captions else None, "frames": tl.duration_f, "fps": tl.fps, "clips": len(tl.video), "caption_pages": len(tl.captions.pages if tl.captions else [])}


def compile_for(ctx: StageContext, inp, story: StoryPlan, fin: FinishPlan) -> tuple[Timeline, list]:
    """A finish plan → the timeline the renderers read (brand overrides, proof fixes, caption adaptation). The compile
    stage and the hook preview's alternative look both use it, so a preview is exactly what the full render would be."""
    family, tokens = brief_mod.brand_caption_overrides(inp.brand)
    fixes = {int(k): v["text"] for k, v in (_read_json(ctx, "qa", "proof_confirmed.json") or {}).items() if v.get("text")}
    logo = _brand_logo(ctx, inp.brand)
    accent = (inp.brand.colors.accent or inp.brand.colors.primary) if inp.brand else None
    tl = compile_timeline(story, fin, inp.words, inp.clips, inp.fps, inp.idx, edges=inp.edges, brand_family=family, brand_tokens=tokens,
                          brand_look=inp.brand.look if inp.brand else None, word_fixes=fixes, brand_accent=accent, brand_logo=logo,
                          vad=inp.vad, scene_cuts=inp.scenes)
    from reel import adapt

    pal = _read_json(ctx, "perception", "palette.json") or {}
    palette = [c["hex"] for v in pal.values() for c in (v.get("colors") or [])]
    tl, adapted = adapt.adapt(tl, ctx.ws.root, palette, locked=set(tokens))
    if tl.captions and not accent:  # graphics follow the caption emphasis colour that survived adaptation
        emph = tl.captions.tokens.get("emph_color")
        if emph:
            tl = tl.model_copy(update={"graphics": [g.model_copy(update={"accent": emph}) for g in tl.graphics]})
    return tl, adapted


COMPILE = Stage(name="compile", input_hash=_compile_hash,
                outputs=lambda ctx: [ctx.ws.path("timeline", "timeline.json"), ctx.ws.path("qa", "proof_list.json")], run=_compile)


# ------------------------------------------------------------------ render (base), overlay, composite


def _timeline(ctx: StageContext) -> Timeline:
    return Timeline.model_validate_json(ctx.ws.path("timeline", "timeline.json").read_text())


def _read_json(ctx: StageContext, *parts: str) -> dict | None:
    p = ctx.ws.path(*parts)
    return json.loads(p.read_text()) if p.exists() else None


def _faces(ctx: StageContext) -> dict | None:
    return _read_json(ctx, "perception", "faces.json")


def _speakers(ctx: StageContext) -> dict | None:
    return _read_json(ctx, "perception", "speakers.json")


def _mezz_fps(ctx: StageContext) -> list:
    manifest = json.loads(ctx.ws.path("source", "manifest.json").read_text())
    return [_fp(ctx, f"mezz/{c['id']}.mov") for c in manifest["clips"]]


def _code_fp(*modules: str) -> str:
    """Fingerprint of engine modules a stage's output depends on (code changes re-run the stage)."""
    import importlib

    return hash_inputs([file_fingerprint(Path(importlib.import_module(f"reel.{m}").__file__)) for m in modules])


def _render_code_fp() -> str:
    """The base render's own code: a change to the renderer, mix or colour re-renders."""
    from reel import color

    from reel import framing

    return hash_inputs([file_fingerprint(Path(m.__file__)) for m in (render, mix, color, framing)])


def _render_hash(ctx: StageContext) -> str:
    # only the ffmpeg-owned slice: a caption-only change never re-renders the base
    return hash_inputs({"timeline": part(_timeline(ctx), FFMPEG_FIELDS), "faces": _fp(ctx, "perception/faces.json"),
                        "vad": _fp(ctx, "perception/vad.json"), "scenes": _fp(ctx, "perception/scenes.json"), "assets": _assets_fp(),
                        "speakers": _fp(ctx, "perception/speakers.json"),
                        "code": _render_code_fp(),
                        "broll": _fp(ctx, "broll/index.json"),
                        "voice": [_fp(ctx, "perception/voice_enhance.json"), *(_fp(ctx, str(p.relative_to(ctx.ws.root))) for p, _g in enhanced_voice(ctx).values())],
                        "mezz": _mezz_fps(ctx), "v": VERSION, "crf": render.CRF})


def enhanced_voice(ctx: StageContext) -> dict[str, tuple[Path, float]]:
    """Per clip: (enhanced voice wav, room-tone gain dB) from the voice stage, for clips it enhanced."""
    clips = (_read_json(ctx, "perception", "voice_enhance.json") or {}).get("clips", {})
    return {cid: (ctx.ws.root / c["voice"], float(c.get("room_tone_gain_db", 0.0))) for cid, c in clips.items() if c.get("applied")}


def room_tones(ctx: StageContext) -> dict[str, tuple[int, int, float]]:
    from reel.perception.audio import ANALYSIS_RATE, read_pcm

    vad = _read_json(ctx, "perception", "vad.json") or {}
    out = {}
    for clip_id, v in vad.items():
        mezz = ctx.ws.path("mezz", f"{clip_id}.mov")
        if mezz.exists():
            region = mix.room_tone_region(read_pcm(mezz), ANALYSIS_RATE, v.get("speech", []))
            if region:
                out[clip_id] = region
    return out


def clip_luts(ctx: StageContext, tl: Timeline) -> tuple[dict, dict]:
    """Per-clip LUT = correction toward neutral (measured) + the reel's look at its strength."""
    from reel import color
    from reel.perception.audio import read_frames

    luts, measured = {}, {}
    for asset in sorted({c.asset for c in tl.video}):  # base clips and full-frame b-roll get the same treatment
        m = color.measure(read_frames(ctx.ws.root / tl.assets[asset].uri, fps=1.0, width=160)[0])
        gains, exposure = (m["gains"], m["exposure"]) if tl.grade.correct else ([1.0, 1.0, 1.0], 1.0)
        measured[asset] = m
        if color.needs_lut(gains, exposure, tl.grade.look, tl.grade.strength):
            luts[asset] = color.write_lut(ctx.ws.path("render", "luts", f"{asset}.cube"), gains, exposure, tl.grade.look, tl.grade.strength)
    return luts, measured


def licence_gate(ctx: StageContext, tl: Timeline | None = None):
    """The licence gate on the compiled timeline (reel.licences): raises LicenceRefused with every reason."""
    from reel import licences

    use = licences.UseContext.from_brief(brief_mod.load_brief(project.brief_path(ctx.ws, ctx.options)), ctx.ws.root.name,
                                         project.studio_client(ctx.ws))
    res = licences.gate(tl or _timeline(ctx), project.indexes(ctx.ws), use)
    if not res.ok:
        raise licences.LicenceRefused(res)
    return res


def _video_fp(ctx: StageContext, tl: Timeline) -> str:
    """Everything the base PICTURE depends on (partial re-render, roadmap G1.5): when only this is unchanged, a
    re-render needs the audio only. Audio fields, music/SFX assets, room tone and voice enhancement are left out."""
    d = part(tl, FFMPEG_FIELDS)
    d.pop("audio", None)
    d.pop("ducking", None)
    d["assets"] = {k: v for k, v in d["assets"].items() if v.get("kind") in ("video", "image", "matte")}
    return hash_inputs({"timeline": d, "faces": _fp(ctx, "perception/faces.json"), "scenes": _fp(ctx, "perception/scenes.json"),
                        "speakers": _fp(ctx, "perception/speakers.json"), "broll": _fp(ctx, "broll/index.json"), "mezz": _mezz_fps(ctx),
                        "code": _render_code_fp(), "v": VERSION, "crf": render.CRF})


def _render(ctx: StageContext) -> dict:
    licence_gate(ctx)  # never spend a render on a reel that can't be delivered
    ev = enhanced_voice(ctx)
    # an enhanced clip's floor is its enhanced floor (room tone is lowered to it; the voice chain denoises against it)
    rt = {k: (s, e, round(db + ev[k][1], 1) if k in ev else db) for k, (s, e, db) in room_tones(ctx).items()}
    tl = _timeline(ctx)
    base, meta_file = ctx.ws.path("render", "base.mov"), ctx.ws.path("render", "base.meta.json")
    video_fp = _video_fp(ctx, tl)
    prev = (_read_json(ctx, "render", "base.meta.json") or {}).get("video_fp")
    meta_file.unlink(missing_ok=True)  # written again only after a successful render: never describes a half-written base
    common = dict(room_tone=rt, stems_dir=ctx.ws.path("render", "stems"), enhanced_voice=ev, faces=_faces(ctx),
                  scenes=_read_json(ctx, "perception", "scenes.json"), speakers=_speakers(ctx))
    meta = None
    if prev == video_fp and base.exists():  # only the sound changed (music, SFX, gains, ducking): keep the picture
        try:
            meta = render.render_base_audio(tl, ctx.ws.root, base, **common)
            measured = (_read_json(ctx, "render", "base.grade.json") or {})
        except Exception as exc:  # noqa: BLE001 — the audio-only path is an optimisation; the full render is the truth
            log.warning("audio-only re-render failed (%s); rendering in full", exc)
            meta = None
    if meta is None:
        luts, measured = clip_luts(ctx, tl)
        meta = render.render_base(tl, ctx.ws.root, base, luts=luts, **common) | {"audio_only": False}
        atomic_write_json(ctx.ws.path("render", "base.grade.json"), measured)
    atomic_write_json(meta_file, {"video_fp": video_fp})
    return meta | {"voice_enhanced": sorted(ev), "grade": {"look": tl.grade.look, "strength": tl.grade.strength, "clips": measured}, "room_tone": {k: {"s": round(v[0] / 1e6, 2), "e": round(v[1] / 1e6, 2), "dbfs": v[2]} for k, v in rt.items()}}


RENDER = Stage(name="render", input_hash=_render_hash,
               outputs=lambda ctx: [ctx.ws.path("render", "base.mov"), *(ctx.ws.path("render", "stems", f"{b}.wav") for b in ("dialogue", "music", "sfx"))],
               run=_render)


def _overlay_hash(ctx: StageContext) -> str:
    return hash_inputs({"timeline": part(_timeline(ctx), REMOTION_FIELDS), "base": _fp(ctx, "render/base.mov") if _behind(_timeline(ctx)) else None,
                        "scenes": _fp(ctx, "perception/scenes.json"), "code": _code_fp("overlay", "framing", "render"), "faces": _fp(ctx, "perception/faces.json"),
                        "ocr": _fp(ctx, "perception/ocr.json"), "speakers": _fp(ctx, "perception/speakers.json"),
                        "renderer": overlay.renderer_fingerprint(), "v": VERSION})


def _behind(tl: Timeline):
    return next((t for t in tl.titles if t.layer == "behind"), None)


def _overlay(ctx: StageContext) -> dict:
    tl = _timeline(ctx)
    t = _behind(tl)
    behind_meta = {}
    if t:  # text behind the subject: its own layer for the title window + a person matte from the base render
        from reel import matte

        props = overlay.build_props(tl, ctx.ws.root, _faces(ctx), _read_json(ctx, "perception", "ocr.json"), _read_json(ctx, "perception", "scenes.json"),
                                    _speakers(ctx)) | {"layer": "behind"}
        overlay.render_overlay(props, ctx.ws.path("render", "behind.mov"), public_dir=ctx.ws.root, frames=(t.start_f, t.end_f - 1))
        behind_meta = matte.make_matte(ctx.ws.path("render", "base.mov"), t.start_f, t.end_f, ctx.ws.path("render", "matte.mkv"),
                                       (tl.width, tl.height), tl.fps)
    props = overlay.build_props(tl, ctx.ws.root, _faces(ctx), _read_json(ctx, "perception", "ocr.json"), _read_json(ctx, "perception", "scenes.json"),
                                _speakers(ctx))
    meta = render_overlay_partial(ctx, tl, props)
    return meta | {"caption_family": tl.captions.family if tl.captions else None, "titles": len(tl.titles), "flashes": len(tl.flashes),
                   "behind": behind_meta}


def _public_fps(ctx: StageContext, props: dict) -> dict:
    """Files the overlay reads from the workspace (pip clips, logo): a replaced file must re-render, same props or not."""
    uris = {e.get("uri") for e in props.get("pips", []) + props.get("graphics", []) if e.get("uri") and "/" in str(e.get("uri"))}
    return {u: _fp(ctx, u) for u in sorted(uris)}


def render_overlay_partial(ctx: StageContext, tl: Timeline, props: dict) -> dict:
    """Re-render only the overlay frames the timeline changed and splice them in (roadmap G1.5); otherwise in full.

    Baseline = render/overlay.rendered.props.json, written only after a successful render or splice. Any failure in
    the partial path falls back to a full render, so this optimisation can never fail an edit."""
    import time

    from reel import rediff, splice

    out = ctx.ws.path("render", "overlay.mov")
    base = ctx.ws.path("render", "overlay.rendered.props.json")
    stamp = {"renderer": overlay.renderer_fingerprint(), "public": _public_fps(ctx, props)}
    saved = json.loads(base.read_text()) if base.exists() and out.exists() else {}
    old = saved.get("props") if all(saved.get(k) == v for k, v in stamp.items()) else None
    ranges = rediff.changed_ranges(old, props)
    base.unlink(missing_ok=True)
    meta = None
    t0 = time.time()
    if ranges == []:  # nothing the overlay draws changed: the current overlay.mov is already right
        meta = {"overlay_s": 0.0, "partial": {"ranges": [], "frames": 0}}
    elif ranges:
        chunks = []
        try:
            for k, (a, b) in enumerate(ranges):
                c = ctx.ws.path("render", f".overlay_chunk{k}.mov")
                overlay.render_overlay(props, c, public_dir=ctx.ws.root, frames=(a, b))
                chunks.append((a, b, c))
            splice.splice(out, chunks, out, total_f=int(props["duration_f"]), fps=tb.parse_rate(tl.fps))
            meta = {"overlay_s": round(time.time() - t0, 1),
                    "partial": {"ranges": [list(r) for r in ranges], "frames": sum(b - a + 1 for a, b in ranges)}}
        except Exception as exc:  # noqa: BLE001 — fall back to the full render
            log.warning("partial overlay render failed (%s); rendering in full", exc)
        finally:
            for _a, _b, c in chunks:
                c.unlink(missing_ok=True)
                c.with_suffix(".props.json").unlink(missing_ok=True)
    if meta is None:
        meta = overlay.render_overlay(props, out, public_dir=ctx.ws.root) | {"partial": None}
    else:
        atomic_write_json(out.with_suffix(".props.json"), props)  # variants re-render from the current props
    atomic_write_json(base, {**stamp, "props": props})
    return meta


OVERLAY = Stage(name="overlay", input_hash=_overlay_hash, outputs=lambda ctx: [ctx.ws.path("render", "overlay.mov")], run=_overlay)


def _composite_hash(ctx: StageContext) -> str:
    return hash_inputs({"base": _fp(ctx, "render/base.mov"), "overlay": _fp(ctx, "render/overlay.mov"), "behind": _fp(ctx, "render/behind.mov"),
                        "matte": _fp(ctx, "render/matte.mkv"), "code": _code_fp("overlay", "mix"), "v": VERSION, "crf": render.CRF})


def _composite(ctx: StageContext) -> dict:
    out = ctx.ws.path("render", "final.mp4")
    tl = _timeline(ctx)
    t = _behind(tl)
    behind = ({"layer": ctx.ws.path("render", "behind.mov"), "matte": ctx.ws.path("render", "matte.mkv"), "start_f": t.start_f, "end_f": t.end_f}
              if t else None)
    meta = overlay.composite(tl, ctx.ws.path("render", "base.mov"), ctx.ws.path("render", "overlay.mov"), out, behind=behind)
    export = ctx.ws.path("export", "reel.mp4")
    export.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, export)
    return meta


COMPOSITE = Stage(name="composite", input_hash=_composite_hash,
                  outputs=lambda ctx: [ctx.ws.path("render", "final.mp4"), ctx.ws.path("export", "reel.mp4")], run=_composite)

# ------------------------------------------------------------------ QA + verdict


def _qa_hash(ctx: StageContext) -> str:
    from reel import config, cuts, verdict
    from reel import qa as qa_mod
    from reel.schemas.review import Review

    return hash_inputs({"final": _fp(ctx, "render/final.mp4"), "proof": _fp(ctx, "qa/proof_confirmed.json"),
                        "brief": _opt_file(ctx.options.get("brief")), "reference": _opt_file(ctx.options.get("reference")),
                        "persona": file_fingerprint(verdict.REVIEWER_PERSONA),
                        "schema": decide.schema(Review), "gates": config.QA_GATES, "trusted": config.REVIEWER_TRUSTED,
                        "code": hash_inputs([file_fingerprint(Path(m.__file__)) for m in (verdict, qa_mod, cuts)]),
                        "cut_inputs": [_fp(ctx, f) for f in ("timeline/timeline.json", "perception/words.json", "perception/edges.json")],
                        "skip_review": bool(ctx.options.get("skip_review")), **_model_key(ctx)})


def _qa(ctx: StageContext) -> dict:
    from reel import verdict

    return verdict.run(ctx.ws, ctx.options, _caller(ctx))


QA = Stage(name="qa", input_hash=_qa_hash, outputs=lambda ctx: [ctx.ws.path("qa", "verdict.json"), ctx.ws.path("qa", "verdict.md"),
                                                                ctx.ws.path("qa", "cuts.json")], run=_qa)

# ------------------------------------------------------------------ cover frame (cap.export.cover_frame)


def _cover_hash(ctx: StageContext) -> str:
    from reel import cover

    return hash_inputs({f: _fp(ctx, f) for f in ("render/base.mov", "timeline/timeline.json", "plan/story.json", "plan/finish.json",
                                                 "perception/words.json")}
                       | {"code": _code_fp("cover", "cuts"), "model": cover.LANDMARKER_SHA256, "font": cover.INTER_SHA256, "v": VERSION})


def _cover(ctx: StageContext) -> dict:
    from reel import cover

    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ctx.ws.path("plan", "finish.json"))
    try:
        return cover.build(ctx.ws, _timeline(ctx), story, fin, project.word_table(ctx.ws))
    except Exception as exc:  # noqa: BLE001 — a thumbnail must never stop packaging and delivery
        log.exception("cover failed; falling back to a plain frame")
        out = ctx.ws.path("render", "cover")
        out.mkdir(parents=True, exist_ok=True)
        tl = _timeline(ctx)
        fps = tb.parse_rate(tl.fps)
        at = float(Fraction(min(tl.duration_f - 1, max(0, tl.duration_f // 10))) / fps)  # early, past the first cut usually
        for name in ("cover_clean.jpg", "cover.jpg"):
            tools.ffmpeg(["-y", "-ss", f"{at:.3f}", "-i", str(ctx.ws.path("render", "base.mov")), "-frames:v", "1", "-vf", "scale=1080:1920",
                          "-q:v", "2", str(out / name)])
        f = round(at * fps)
        atomic_write_json(out / "cover.json", {"error": f"{type(exc).__name__}: {exc}", "frame": f, "tc": f"{int(at // 60)}:{at % 60:05.2f}",
                                               "title": "", "fallback": "plain frame at 10 % of the reel; rerun with --force cover"})
        return {"error": f"{type(exc).__name__}: {exc}", "fallback_frame": f}


COVER = Stage(name="cover", input_hash=_cover_hash, run=_cover,
              outputs=lambda ctx: [ctx.ws.path("render", "cover", f) for f in ("cover.jpg", "cover_clean.jpg", "cover.json")])

# ------------------------------------------------------------------ hook preview in two looks (roadmap G1.6)


def _preview_hash(ctx: StageContext) -> str:
    return hash_inputs({"timeline": _fp(ctx, "timeline/timeline.json"), "finish": _fp(ctx, "plan/finish.json"), "brand": _opt_file(ctx.options.get("brand")),
                        "code": _code_fp("preview", "render", "overlay"), "renderer": overlay.renderer_fingerprint(), "v": VERSION})


def _preview(ctx: StageContext) -> dict:
    """export/preview/hook_A.mp4 (the Editor's look) and hook_B.mp4 (another caption style + a contrasting colour look,
    where the brand kit doesn't lock them), the opening seconds only, plus preview.json for the A/B choice."""
    from reel import preview
    from reel.validate import errors, validate_finish

    inp = _inputs(ctx)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ctx.ws.path("plan", "finish.json"))
    options = {"A": fin}
    fam_b, look_b = preview.alternative(fin, story, inp.idx.caption_families, inp.brand)
    if fam_b or look_b:
        fin_b = preview.variant(fin, fam_b, look_b)
        if not errors(validate_finish(fin_b, story, inp.words, inp.idx, inp.kids)):
            options["B"] = fin_b
    out = ctx.ws.path("export", "preview")
    out.mkdir(parents=True, exist_ok=True)
    fps = tb.parse_rate(_timeline(ctx).fps)
    n = None
    looks = {}
    for name, f in options.items():
        tl, _adapted = compile_for(ctx, inp, story, f)
        n = n or min(tl.duration_f, preview.hook_end_f(tl, story) + round(preview.TAIL_S * fps))
        short = preview.trim(tl, n)
        base, ov = out / f".base_{name}.mov", out / f".overlay_{name}.mov"
        luts, _m = clip_luts(ctx, short)
        render.render_base(short, ctx.ws.root, base, faces=_faces(ctx), luts=luts, scenes=_read_json(ctx, "perception", "scenes.json"),
                           speakers=_speakers(ctx))
        props = overlay.build_props(short, ctx.ws.root, _faces(ctx), _read_json(ctx, "perception", "ocr.json"),
                                    _read_json(ctx, "perception", "scenes.json"), _speakers(ctx))
        overlay.render_overlay(props, ov, public_dir=ctx.ws.root)
        preview.quick_composite(base, ov, out / f"hook_{name}.mp4")
        for tmp in (base, ov, ov.with_suffix(".props.json")):
            tmp.unlink(missing_ok=True)
        looks[name] = {"caption_family": tl.captions.family if tl.captions else None, "look": tl.grade.look, "file": f"export/preview/hook_{name}.mp4",
                       "plan": {"caption_family": fam_b, "look": look_b} if name == "B" else {}}
    atomic_write_json(out / "preview.json", {"frames": n, "seconds": round(float(n / fps), 2), "options": looks, "chosen": None})
    return {"options": sorted(looks), "frames": n}


PREVIEW = Stage(name="preview", input_hash=_preview_hash, outputs=lambda ctx: [ctx.ws.path("export", "preview", "preview.json")], run=_preview)


# ------------------------------------------------------------------ story check-in (roadmap 3a.1)


def _checkin_hash(ctx: StageContext) -> str:
    from reel import checkin

    return hash_inputs({"story": _fp(ctx, "plan/story.json"), "takes": _fp(ctx, "tables/takes.json"), "brief": _opt_file(ctx.options.get("brief")),
                        "code": file_fingerprint(Path(checkin.__file__)), "v": VERSION})


def _checkin(ctx: StageContext) -> dict:
    from reel import checkin

    return checkin.build(ctx.ws, _inputs(ctx))


CHECKIN = Stage(name="checkin", input_hash=_checkin_hash, outputs=lambda ctx: [ctx.ws.path("plan", "checkin.json")], run=_checkin)


def checkin_pipeline(base: list[Stage]) -> list[Stage]:
    """`run --story-checkin`: the given pipeline up to the story pass, then the check-in; the run ends there."""
    names = [s.name for s in base]
    return [*base[:names.index("story") + 1], CHECKIN]


def preview_pipeline() -> list[Stage]:
    """`run --preview-first`: everything up to the compiled timeline, then the two hook previews; the run ends there."""
    return [*STAGES[:STAGES.index(COMPILE) + 1], PREVIEW]


# ------------------------------------------------------------------ post copy pack (roadmap G1.1)


def _kept_text(ctx: StageContext) -> str:
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    by = project.word_table(ctx.ws).by_index()
    return "\n".join(" ".join(by[i].text for i in range(it.word_start, it.word_end + 1) if i in by) for it in story.items)


def _copy_hash(ctx: StageContext) -> str:
    from reel import postcopy

    return hash_inputs({"story": _fp(ctx, "plan/story.json"), "summary": _fp(ctx, "tables/summary.md"), "words": _fp(ctx, "perception/words.json"),
                        "timeline": _fp(ctx, "timeline/timeline.json"),  # the credits it must leave room for
                        "brief": _opt_file(project.brief_path(ctx.ws, ctx.options)), "brand": _opt_file(ctx.options.get("brand")),
                        "persona": file_fingerprint(postcopy.PERSONA), "schema": postcopy.schema(), "code": _code_fp("postcopy"),
                        **_model_key(ctx)})


def _copy(ctx: StageContext) -> dict:
    from reel import library, postcopy

    summary = ctx.ws.path("tables", "summary.md")
    credits = library.credit_lines(_timeline(ctx), project.indexes(ctx.ws))
    out = postcopy.write(ctx.ws.root, _caller(ctx), kept_text=_kept_text(ctx), summary=summary.read_text() if summary.exists() else "",
                         brief=brief_mod.load_brief(project.brief_path(ctx.ws, ctx.options)), brand=brief_mod.load_brand(ctx.options.get("brand")),
                         credits=credits, log_file=ctx.ws.path("log", "runs.jsonl"))
    atomic_write_json(ctx.ws.path("plan", "copy.json"), out)
    if out["status"] != "ok":
        log.warning("post copy %s: %s", out["status"], out.get("reason") or "; ".join(out.get("problems", [])))
    return {"status": out["status"], "problems": len(out.get("problems", []))}


COPY = Stage(name="copy", input_hash=_copy_hash, outputs=lambda ctx: [ctx.ws.path("plan", "copy.json")], run=_copy)


# ------------------------------------------------------------------ NLE package (every run, ADR-0018)


def _package_hash(ctx: StageContext) -> str:
    from reel import package

    files = ["render/final.mp4", "render/overlay.mov", "timeline/timeline.json", "plan/story.json", "plan/finish.json", "qa/verdict.json",
             "render/cover/cover.json", "render/cover/cover.jpg", "plan/copy.json", *(f"render/stems/{b}.wav" for b in package.STEMS)]
    from reel import licences

    # the brief, licence registry and subscriptions decide the licence gate: a change re-checks and re-writes the manifest
    return hash_inputs({f: _fp(ctx, f) for f in files} | {"code": _code_fp("package", "licences"), "v": VERSION,
                                                          "licences": licences.fingerprint(project.brief_path(ctx.ws, ctx.options))})


def _package(ctx: StageContext) -> dict:
    from reel import package
    from reel.runner import load_state

    tl = _timeline(ctx)
    gate = licence_gate(ctx, tl)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ctx.ws.path("plan", "finish.json"))
    comp = load_state(ctx.ws)["stages"].get("composite", {}).get("meta", {})
    v = _read_json(ctx, "qa", "verdict.json") or {}
    return package.build(ctx.ws, tl, story, fin, project.word_table(ctx.ws), project.indexes(ctx.ws), lufs_in=comp.get("lufs_in"), verdict=v.get("status"),
                         gate=gate)


def _package_valid(ctx: StageContext) -> bool:
    """A delivered package stays valid only while its licences do (a lapsed subscription, a ledger entry from another client)."""
    licence_gate(ctx)
    return True


PACKAGE = Stage(name="package", input_hash=_package_hash,
                outputs=lambda ctx: [ctx.ws.path("export", "package", f) for f in ("reel.mp4", "overlay.mov", "timeline.fcpxml", "timeline.otio",
                                                                                     "captions.srt", "edit_list.md", "README.md",
                                                                                     "licences/manifest.json")],
                run=_package, validate=_package_valid)

# ------------------------------------------------------------------ delivery variants + review copy


def _deliverables(ctx: StageContext) -> list[str]:
    from reel import brief as b, variants

    brief = b.load_brief(ctx.options.get("brief"))
    # brief deliverables + extra ones asked for at delivery time (Reel Studio "Deliver"; kept in run_options.json
    # so a delivery never edits the brief, whose fingerprint would re-ask the Editor)
    wanted = [*(brief.deliverables if brief else []), *(ctx.options.get("deliverables") or [])]
    return [d for d in dict.fromkeys(wanted) if d in variants.PROFILES]


def _variants_hash(ctx: StageContext) -> str:
    from reel import variants

    return hash_inputs({f: _fp(ctx, f) for f in ("render/final.mp4", "render/base.mov", "timeline/timeline.json", "render/overlay.props.json")}
                       | {"deliverables": _deliverables(ctx), "renderer": overlay.renderer_fingerprint(),
                          "code": file_fingerprint(Path(variants.__file__)), "v": VERSION})


def _variants(ctx: StageContext) -> dict:
    from reel import variants

    tl = _timeline(ctx)
    out = {"review": variants.review_copy(ctx.ws, tl, (_read_json(ctx, "qa", "verdict.json") or {}).get("status"))}
    for name in _deliverables(ctx):
        out[name] = variants.make_variant(ctx.ws, tl, name)
    from fractions import Fraction

    from reel import timebase as tb

    out["platform_notes"] = variants.platform_notes(float(Fraction(tl.duration_f) / tb.parse_rate(tl.fps)))
    return out


VARIANTS = Stage(name="variants", input_hash=_variants_hash,
                 outputs=lambda ctx: [ctx.ws.path("export", "review", "review.mp4"),
                                      *(ctx.ws.path("export", "variants", f"reel_{n}.mp4") for n in _deliverables(ctx))],
                 run=_variants)

STAGES = [STOCK, BROLL, REFERENCE, STORY, FINISH, COMPILE, RENDER, OVERLAY, COMPOSITE, QA, COVER, COPY, PACKAGE, VARIANTS]
