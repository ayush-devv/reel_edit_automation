"""Edit stages: story pass → finish pass → compile → base render → overlay → composite.

Decision-stage input hashes cover everything that changes Claude's answer (tables, brief,
brand, persona, knowledge, libraries, schema, model, effort) so a re-run never spends on
unchanged inputs and never keeps a stale plan. The Claude caller is injectable through
`options["claude_call"]` (tests pass a fake).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from reel import brief as brief_mod
from reel import claude_call, decide, mix, overlay, project, render
from reel.compile import compile_timeline
from reel.runner import Stage, StageContext
from reel.schemas.plan import FinishPlan, StoryPlan
from reel.schemas.timeline import FFMPEG_FIELDS, REMOTION_FIELDS, Timeline, part
from reel.validate import errors, validate_finish, validate_story
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs

VERSION = 2
TABLE_FILES = ("tables/script.md", "tables/segments.json", "tables/takes.json", "tables/words.tsv", "tables/summary.md",
               "tables/sheets.json", "perception/words.json", "perception/edges.json")


def _fp(ctx: StageContext, rel: str) -> str | None:
    p = ctx.ws.root / rel
    return file_fingerprint(p) if p.exists() else None


def _opt_file(path: str | None) -> str | None:
    return file_fingerprint(Path(path)) if path else None


def _knowledge_fp() -> str:
    from reel import config

    files = sorted((config.KNOWLEDGE_DIR / "graph").glob("*.yaml"))
    return hash_inputs([file_fingerprint(f) for f in files])


def _assets_fp() -> str:
    from reel import assets

    return hash_inputs([file_fingerprint(f) for f in sorted(assets.ASSETS_DIR.rglob("*")) if f.is_file() and f.suffix in (".json", ".yaml")])


def _caller(ctx: StageContext):
    return ctx.options.get("claude_call") or claude_call.call


def _inputs(ctx: StageContext) -> decide.Inputs:
    return decide.load_inputs(ctx.ws, ctx.options.get("brief"), ctx.options.get("brand"))


def _model_key(ctx: StageContext) -> dict:
    return {"model": claude_call.DEFAULT_MODEL, "v": VERSION}


# ------------------------------------------------------------------ story


def _story_hash(ctx: StageContext) -> str:
    return hash_inputs({"tables": [_fp(ctx, f) for f in TABLE_FILES], "brief": _opt_file(ctx.options.get("brief")),
                        "brand": _opt_file(ctx.options.get("brand")), "persona": file_fingerprint(decide.STORY_PERSONA),
                        "knowledge": _knowledge_fp(), "schema": decide.schema(StoryPlan), "effort": decide.STORY_EFFORT,
                        "prompts": [decide.STORY_PROMPT, decide.READBACK_PROMPT], **_model_key(ctx)})


def _story_valid(ctx: StageContext) -> bool:
    inp = _inputs(ctx)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    return not errors(validate_story(story, inp.words, set(inp.clips), inp.kids))


STORY = Stage(name="story", input_hash=_story_hash,
              outputs=lambda ctx: [ctx.ws.path("plan", "story.json"), ctx.ws.path("plan", "story_readback.txt")],
              run=lambda ctx: decide.story_pass(_inputs(ctx), _caller(ctx)), validate=_story_valid)


# ------------------------------------------------------------------ finish


def _finish_hash(ctx: StageContext) -> str:
    return hash_inputs({"story": _fp(ctx, "plan/story.json"), "brand": _opt_file(ctx.options.get("brand")),
                        "persona": file_fingerprint(decide.FINISH_PERSONA), "knowledge": _knowledge_fp(), "assets": _assets_fp(),
                        "schema": decide.schema(FinishPlan), "effort": decide.FINISH_EFFORT, "prompt": decide.FINISH_PROMPT,
                        **_model_key(ctx)})


def _finish_valid(ctx: StageContext) -> bool:
    inp = _inputs(ctx)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ctx.ws.path("plan", "finish.json"))
    return not errors(validate_finish(fin, story, inp.words, inp.idx, inp.kids))


FINISH = Stage(name="finish", input_hash=_finish_hash, outputs=lambda ctx: [ctx.ws.path("plan", "finish.json")],
               run=lambda ctx: decide.finish_pass(_inputs(ctx), _caller(ctx)), validate=_finish_valid)


# ------------------------------------------------------------------ compile


def _compile_hash(ctx: StageContext) -> str:
    return hash_inputs({f: _fp(ctx, f) for f in ("plan/story.json", "plan/finish.json", "perception/words.json",
                                                 "perception/edges.json", "source/manifest.json")}
                       | {"assets": _assets_fp(), "brand": _opt_file(ctx.options.get("brand")), "v": VERSION})


def _compile(ctx: StageContext) -> dict:
    inp = _inputs(ctx)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ctx.ws.path("plan", "finish.json"))
    family, tokens = brief_mod.brand_caption_overrides(inp.brand)
    tl = compile_timeline(story, fin, inp.words, inp.clips, inp.fps, inp.idx, edges=inp.edges, brand_family=family, brand_tokens=tokens,
                          brand_look=inp.brand.look if inp.brand else None)
    atomic_write_json(ctx.ws.path("timeline", "timeline.json"), tl.model_dump(mode="json"))
    return {"frames": tl.duration_f, "fps": tl.fps, "clips": len(tl.video), "caption_pages": len(tl.captions.pages if tl.captions else [])}


COMPILE = Stage(name="compile", input_hash=_compile_hash, outputs=lambda ctx: [ctx.ws.path("timeline", "timeline.json")], run=_compile)


# ------------------------------------------------------------------ render (base), overlay, composite


def _timeline(ctx: StageContext) -> Timeline:
    return Timeline.model_validate_json(ctx.ws.path("timeline", "timeline.json").read_text())


def _read_json(ctx: StageContext, *parts: str) -> dict | None:
    p = ctx.ws.path(*parts)
    return json.loads(p.read_text()) if p.exists() else None


def _faces(ctx: StageContext) -> dict | None:
    return _read_json(ctx, "perception", "faces.json")


def _mezz_fps(ctx: StageContext) -> list:
    manifest = json.loads(ctx.ws.path("source", "manifest.json").read_text())
    return [_fp(ctx, f"mezz/{c['id']}.mov") for c in manifest["clips"]]


def _render_code_fp() -> str:
    """The base render's own code: a change to the renderer, mix or colour re-renders."""
    from reel import color

    return hash_inputs([file_fingerprint(Path(m.__file__)) for m in (render, mix, color)])


def _render_hash(ctx: StageContext) -> str:
    # only the ffmpeg-owned slice: a caption-only change never re-renders the base
    return hash_inputs({"timeline": part(_timeline(ctx), FFMPEG_FIELDS), "faces": _fp(ctx, "perception/faces.json"),
                        "vad": _fp(ctx, "perception/vad.json"), "assets": _assets_fp(), "code": _render_code_fp(),
                        "mezz": _mezz_fps(ctx), "v": VERSION, "crf": render.CRF})


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
    for asset in sorted({c.asset for c in tl.video if c.id.startswith("v_")}):
        m = color.measure(read_frames(ctx.ws.root / tl.assets[asset].uri, fps=1.0, width=160)[0])
        gains, exposure = (m["gains"], m["exposure"]) if tl.grade.correct else ([1.0, 1.0, 1.0], 1.0)
        measured[asset] = m
        if color.needs_lut(gains, exposure, tl.grade.look, tl.grade.strength):
            luts[asset] = color.write_lut(ctx.ws.path("render", "luts", f"{asset}.cube"), gains, exposure, tl.grade.look, tl.grade.strength)
    return luts, measured


def _render(ctx: StageContext) -> dict:
    rt = room_tones(ctx)
    tl = _timeline(ctx)
    luts, measured = clip_luts(ctx, tl)
    meta = render.render_base(tl, ctx.ws.root, ctx.ws.path("render", "base.mov"), faces=_faces(ctx), room_tone=rt, luts=luts)
    return meta | {"grade": {"look": tl.grade.look, "strength": tl.grade.strength, "clips": measured}, "room_tone": {k: {"s": round(v[0] / 1e6, 2), "e": round(v[1] / 1e6, 2), "dbfs": v[2]} for k, v in rt.items()}}


RENDER = Stage(name="render", input_hash=_render_hash, outputs=lambda ctx: [ctx.ws.path("render", "base.mov")], run=_render)


def _overlay_hash(ctx: StageContext) -> str:
    return hash_inputs({"timeline": part(_timeline(ctx), REMOTION_FIELDS), "faces": _fp(ctx, "perception/faces.json"),
                        "ocr": _fp(ctx, "perception/ocr.json"),
                        "renderer": overlay.renderer_fingerprint(), "v": VERSION})


def _overlay(ctx: StageContext) -> dict:
    tl = _timeline(ctx)
    meta = overlay.render_overlay(overlay.build_props(tl, ctx.ws.root, _faces(ctx), _read_json(ctx, "perception", "ocr.json")), ctx.ws.path("render", "overlay.mov"))
    return meta | {"caption_family": tl.captions.family if tl.captions else None, "titles": len(tl.titles), "flashes": len(tl.flashes)}


OVERLAY = Stage(name="overlay", input_hash=_overlay_hash, outputs=lambda ctx: [ctx.ws.path("render", "overlay.mov")], run=_overlay)


def _composite_hash(ctx: StageContext) -> str:
    return hash_inputs({"base": _fp(ctx, "render/base.mov"), "overlay": _fp(ctx, "render/overlay.mov"), "v": VERSION, "crf": render.CRF})


def _composite(ctx: StageContext) -> dict:
    out = ctx.ws.path("render", "final.mp4")
    meta = overlay.composite(_timeline(ctx), ctx.ws.path("render", "base.mov"), ctx.ws.path("render", "overlay.mov"), out)
    export = ctx.ws.path("export", "reel.mp4")
    export.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, export)
    return meta


COMPOSITE = Stage(name="composite", input_hash=_composite_hash,
                  outputs=lambda ctx: [ctx.ws.path("render", "final.mp4"), ctx.ws.path("export", "reel.mp4")], run=_composite)

STAGES = [STORY, FINISH, COMPILE, RENDER, OVERLAY, COMPOSITE]
