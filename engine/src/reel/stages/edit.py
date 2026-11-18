"""Edit stages (build step 5): story pass → finish pass → compile → base render.

Decision-stage input hashes cover everything that changes Claude's answer (tables, brief,
brand, persona, knowledge, libraries, schema, model, effort) so a re-run never spends on
unchanged inputs and never keeps a stale plan. The Claude caller is injectable through
`options["claude_call"]` (tests pass a fake).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from reel import claude_call, decide, project, render
from reel.compile import compile_timeline
from reel.runner import Stage, StageContext
from reel.schemas.plan import FinishPlan, StoryPlan
from reel.schemas.timeline import Timeline
from reel.validate import errors, validate_finish, validate_story
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs

VERSION = 1
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
                                                 "perception/edges.json", "source/manifest.json")} | {"assets": _assets_fp(), "v": VERSION})


def _compile(ctx: StageContext) -> dict:
    inp = _inputs(ctx)
    story = project.load_json_model(StoryPlan, ctx.ws.path("plan", "story.json"))
    fin = project.load_json_model(FinishPlan, ctx.ws.path("plan", "finish.json"))
    tl = compile_timeline(story, fin, inp.words, inp.clips, inp.fps, inp.idx, edges=inp.edges)
    atomic_write_json(ctx.ws.path("timeline", "timeline.json"), tl.model_dump(mode="json"))
    return {"frames": tl.duration_f, "fps": tl.fps, "clips": len(tl.video), "caption_pages": len(tl.captions.pages if tl.captions else [])}


COMPILE = Stage(name="compile", input_hash=_compile_hash, outputs=lambda ctx: [ctx.ws.path("timeline", "timeline.json")], run=_compile)


# ------------------------------------------------------------------ render


def _render_hash(ctx: StageContext) -> str:
    manifest = json.loads(ctx.ws.path("source", "manifest.json").read_text())
    return hash_inputs({"timeline": _fp(ctx, "timeline/timeline.json"), "faces": _fp(ctx, "perception/faces.json"),
                        "mezz": [_fp(ctx, f"mezz/{c['id']}.mov") for c in manifest["clips"]], "v": VERSION, "crf": render.CRF})


def _render(ctx: StageContext) -> dict:
    tl = Timeline.model_validate_json(ctx.ws.path("timeline", "timeline.json").read_text())
    faces_p = ctx.ws.path("perception", "faces.json")
    faces = json.loads(faces_p.read_text()) if faces_p.exists() else None
    out = ctx.ws.path("render", "base.mp4")
    meta = render.render_base(tl, ctx.ws.root, out, faces=faces)
    export = ctx.ws.path("export", "reel.mp4")
    export.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, export)
    return meta | {"captions": "not drawn yet (overlay renderer, build step 6)"}


RENDER = Stage(name="render", input_hash=_render_hash,
               outputs=lambda ctx: [ctx.ws.path("render", "base.mp4"), ctx.ws.path("export", "reel.mp4")], run=_render)

STAGES = [STORY, FINISH, COMPILE, RENDER]
