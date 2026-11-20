"""MINE stage (Clip Factory, roadmap G2.2): candidate reels in a long recording, after the analysis stages."""

from __future__ import annotations

from pathlib import Path

from reel import decide, mine
from reel.runner import Stage, StageContext
from reel.workspace import file_fingerprint, hash_inputs

VERSION = 1
MINE_FILES = ("tables/script.md", "tables/segments.json", "tables/words.tsv", "tables/summary.md",
              "perception/words.json", "perception/segments.json", "perception/edges.json", "perception/faces.json")


def _fp(ctx: StageContext, rel: str) -> str | None:
    p = ctx.ws.root / rel
    return file_fingerprint(p) if p.exists() else None


def _input_hash(ctx: StageContext) -> str:
    from reel.stages.edit import _model_key, _opt_file

    return hash_inputs({"files": [_fp(ctx, f) for f in MINE_FILES], "brief": _opt_file(ctx.options.get("brief")),
                        "brand": _opt_file(ctx.options.get("brand")), "target": ctx.options.get("clip_target_s"),
                        "persona": file_fingerprint(mine.PERSONA), "prompt": mine.PROMPT, "schema": decide.schema(mine.ClipCandidates),
                        "code": file_fingerprint(Path(mine.__file__)), "effort": mine.EFFORT, **_model_key(ctx), "v": VERSION})


def _run(ctx: StageContext) -> dict:
    from reel.stages.edit import _caller

    return mine.mine_pass(ctx.ws, ctx.options, _caller(ctx))


STAGE = Stage(name="mine", input_hash=_input_hash, run=_run,
              outputs=lambda ctx: [ctx.ws.path("mine", "candidates.json"), ctx.ws.path("mine", "board.md")])
