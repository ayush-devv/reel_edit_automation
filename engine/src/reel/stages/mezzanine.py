"""S0 stage: build one mezzanine per clip and verify it (ADR-0015)."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

from reel import mezzanine
from reel.conformance import checks
from reel.probe import SourceProbe
from reel.runner import Stage, StageContext
from reel.workspace import atomic_write_json, hash_inputs


def _manifest(ctx: StageContext) -> dict:
    return json.loads(ctx.ws.path("source", "manifest.json").read_text())


def _out(ctx: StageContext, clip_id: str) -> Path:
    return ctx.ws.path("mezz", f"{clip_id}.mov")


def _report(ctx: StageContext) -> Path:
    return ctx.ws.path("mezz", "report.json")


def _input_hash(ctx: StageContext) -> str:
    m = _manifest(ctx)
    return hash_inputs({
        "clips": [(c["id"], c["fingerprint"]) for c in m["clips"]],
        "fps": m["project_fps"],
        "encoder": ctx.options.get("encoder", "prores_ks"),
        "filter_version": 1,
    })


def _outputs(ctx: StageContext) -> list[Path]:
    return [_out(ctx, c["id"]) for c in _manifest(ctx)["clips"]] + [_report(ctx)]


def _run(ctx: StageContext) -> dict:
    m = _manifest(ctx)
    num, den = m["project_fps"].split("/")
    fps = Fraction(int(num), int(den))
    report = {"project_fps": m["project_fps"], "clips": []}
    for c in m["clips"]:
        src = SourceProbe(**c["probe"])
        out = _out(ctx, c["id"])
        mezzanine.make_mezzanine(src, out, fps, encoder=ctx.options.get("encoder", "prores_ks"))
        result = checks.check_mezzanine(src, out, fps)
        report["clips"].append({"id": c["id"], **result})
    atomic_write_json(_report(ctx), report)
    failed = [c["id"] for c in report["clips"] if not c["ok"]]
    if failed:
        raise RuntimeError(f"mezzanine conformance failed for {failed}: see {_report(ctx)}")
    return {"clips": len(report["clips"])}


def _validate(ctx: StageContext) -> bool:
    rep = json.loads(_report(ctx).read_text())
    return all(c.get("ok") for c in rep.get("clips", []))


STAGE = Stage(name="mezzanine", input_hash=_input_hash, outputs=_outputs, run=_run, validate=_validate)
