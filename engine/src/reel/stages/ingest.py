"""Ingest: register source clips, probe them, fingerprint them, choose the project fps.

Sources are never modified. They are referenced (symlinked) into `source/` so the
workspace is self-describing without duplicating large media.
"""

from __future__ import annotations

import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

from reel.probe import probe
from reel.runner import Stage, StageContext
from reel.timebase import snap_fps
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".hevc"}


def _sources(ctx: StageContext) -> list[Path]:
    src = Path(ctx.options["input"]).resolve()
    files = [src] if src.is_file() else sorted(p for p in src.iterdir() if p.suffix.lower() in VIDEO_EXT and not p.name.startswith("."))
    if not files:
        raise FileNotFoundError(f"No video files found in {src}")
    return files


def _manifest(ctx: StageContext) -> Path:
    return ctx.ws.path("source", "manifest.json")


def choose_project_fps(fps_values: list[Fraction], durations: list[float], override: str | None = None) -> Fraction:
    """Dominant source fps by total duration, snapped to a standard rate (never 25 → 30)."""
    if override:
        num, _, den = override.partition("/")
        return Fraction(int(num), int(den or 1))
    weight: Counter = Counter()
    for f, d in zip(fps_values, durations):
        weight[snap_fps(f)] += max(d, 0.001)
    return weight.most_common(1)[0][0]


def _input_hash(ctx: StageContext) -> str:
    files = _sources(ctx)
    return hash_inputs({
        "files": [(str(f), f.stat().st_size, int(f.stat().st_mtime)) for f in files],
        "fps_override": ctx.options.get("fps"),
    })


def _run(ctx: StageContext) -> dict:
    clips = []
    for i, f in enumerate(_sources(ctx)):
        clip_id = f"c{i + 1:02d}"
        link = ctx.ws.path("source", f"{clip_id}{f.suffix.lower()}")
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(f)
        p = probe(f)
        if p.video is None:
            raise ValueError(f"{f.name}: no video stream")
        clips.append({
            "id": clip_id,
            "file": str(f),
            "link": str(link.relative_to(ctx.ws.root)),
            "fingerprint": file_fingerprint(f),
            "probe": p.model_dump(),
        })
    fps = choose_project_fps(
        [Fraction(c["probe"]["video"]["nominal_fps"]).limit_denominator(1001) for c in clips],
        [c["probe"]["duration_s"] for c in clips],
        ctx.options.get("fps"),
    )
    manifest = {"clips": clips, "project_fps": f"{fps.numerator}/{fps.denominator}"}
    atomic_write_json(_manifest(ctx), manifest)
    return {"clips": len(clips), "project_fps": manifest["project_fps"]}


def _validate(ctx: StageContext) -> bool:
    m = json.loads(_manifest(ctx).read_text())
    return bool(m.get("clips")) and all(Path(c["file"]).exists() for c in m["clips"])


STAGE = Stage(
    name="ingest",
    input_hash=_input_hash,
    outputs=lambda ctx: [_manifest(ctx)],
    run=_run,
    validate=_validate,
)
