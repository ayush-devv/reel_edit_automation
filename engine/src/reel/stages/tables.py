"""Tables stage (build step 4): edge snapping, selects, footage tables, contact sheets."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from reel import brief as brief_mod
from reel import selects, sheets, tables
from reel.perception.audio import read_pcm
from reel.perception.edges import snap_word_edges
from reel.runner import Stage, StageContext
from reel.schemas.perception import SegmentTable, WordTable
from reel.workspace import atomic_write_bytes, atomic_write_json, file_fingerprint, hash_inputs

log = logging.getLogger(__name__)
VERSION = 1
OVERVIEW_EVERY_S = 2.0


def _p(ctx: StageContext, *parts: str) -> Path:
    return ctx.ws.path(*parts)


def _read(ctx: StageContext, name: str) -> dict:
    return json.loads(_p(ctx, "perception", f"{name}.json").read_text())


def _input_hash(ctx: StageContext) -> str:
    files = [_p(ctx, "perception", f"{n}.json") for n in ("words", "segments", "prosody", "faces", "energy", "scenes", "palette", "ocr")]
    return hash_inputs({"perception": [file_fingerprint(f) if f.exists() else None for f in files],
                        "brief": file_fingerprint(Path(ctx.options["brief"])) if ctx.options.get("brief") else None, "v": VERSION})


def _outputs(ctx: StageContext) -> list[Path]:
    return [_p(ctx, "perception", "edges.json"), *(_p(ctx, "tables", n) for n in ("script.md", "segments.json", "takes.json", "words.tsv", "summary.md", "sheets.json"))]


def _run(ctx: StageContext) -> dict:
    manifest = json.loads(_p(ctx, "source", "manifest.json").read_text())
    words = WordTable.model_validate(_read(ctx, "words"))
    segs = SegmentTable.model_validate(_read(ctx, "segments"))
    prosody = _read(ctx, "prosody").get("segments", [])
    faces, energy, scenes, palette, ocr = (_read(ctx, n) for n in ("faces", "energy", "scenes", "palette", "ocr"))

    # 1. heard edges per word
    edges: dict[int, tuple[int, int]] = {}
    for c in manifest["clips"]:
        cw = [w for w in words.words if w.clip == c["id"]]
        if cw:
            edges.update(snap_word_edges(cw, read_pcm(_p(ctx, "mezz", f"{c['id']}.mov"))))
    atomic_write_json(_p(ctx, "perception", "edges.json"), {str(k): list(v) for k, v in edges.items()})

    # 2. selects
    takes = selects.find_takes(words, segs, prosody)

    # 3. tables
    rows = tables.segment_rows(words, segs, prosody, takes, faces, energy, scenes)
    brief = brief_mod.load_brief(ctx.options.get("brief"))
    atomic_write_json(_p(ctx, "tables", "segments.json"), {"segments": rows})
    atomic_write_json(_p(ctx, "tables", "takes.json"), takes)
    atomic_write_bytes(_p(ctx, "tables", "script.md"), tables.script_md(words, segs, rows).encode())
    atomic_write_bytes(_p(ctx, "tables", "words.tsv"), tables.words_tsv(words, edges).encode())
    atomic_write_bytes(_p(ctx, "tables", "summary.md"), tables.summary_md(manifest, words, rows, takes, palette, ocr, brief).encode())

    # 4. contact sheets: one tile per segment midpoint + overview every 2 s
    sheet_index: dict[str, list[str]] = {}
    for c in manifest["clips"]:
        cid = c["id"]
        mezz = _p(ctx, "mezz", f"{cid}.mov")
        seg_stamps = [((r["t0"] + r["t1"]) / 2, f"{r['seg_id']} {r['t0']:.1f}s") for r in rows if r["clip"] == cid]
        dur = c["probe"]["duration_s"]
        overview = [(t, f"{t:.1f}s") for t in [k * OVERVIEW_EVERY_S for k in range(int(dur / OVERVIEW_EVERY_S) + 1)] if t < dur]
        made = []
        if seg_stamps:
            made += sheets.make_sheets(mezz, seg_stamps, _p(ctx, "tables", "sheets", f"{cid}_segments"))
        made += sheets.make_sheets(mezz, overview, _p(ctx, "tables", "sheets", f"{cid}_overview"))
        sheet_index[cid] = [str(p.relative_to(ctx.ws.root)) for p in made]
    atomic_write_json(_p(ctx, "tables", "sheets.json"), sheet_index)

    return {"segments": len(rows), "take_groups": len(takes["groups"]), "sheets": sum(len(v) for v in sheet_index.values()),
            "edges_moved": sum(1 for w in words.words if edges.get(w.i, (w.start_us, w.end_us)) != (w.start_us, w.end_us))}


STAGE = Stage(name="tables", input_hash=_input_hash, outputs=_outputs, run=_run)
