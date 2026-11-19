"""Client b-roll pool (build step 10e).

`reel run … --broll <folder>`: every clip is conformed like the main footage (mezzanine at the
project fps, rotation baked, bt709), gets a 3-frame contact sheet, and one Claude call describes
all of them (subject, shot, motion, mood, best moment). The project pool lives in
<workspace>/broll/index.json and is merged with the owned library (assets/broll_owned) for the
Editor's finish pass.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reel import claude_call, sheets
from reel.mezzanine import make_mezzanine
from reel.probe import probe
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
PERSONA = Path(__file__).parent / "personas" / "broll_describer.md"
PROMPT = "Describe every b-roll clip listed in broll/describe.md. Look at each contact sheet. Return the descriptions."


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BrollDescription(_Strict):
    id: str
    description: str  # one line: what is visible
    subjects: list[str]
    shot: str  # wide | medium | close | detail | screen | text
    motion: str  # static | pan | handheld | tracking | timelapse
    mood: str
    best_at: str  # "start" | "middle" | "end" — where the strongest moment is


class BrollDescriptions(_Strict):
    clips: list[BrollDescription]


def _id(path: Path) -> str:
    return "b_" + hashlib.sha1(path.name.encode() + str(path.stat().st_size).encode()).hexdigest()[:8]


def conform(ws: Workspace, folder: Path | list[Path], fps) -> list[dict]:
    folders = folder if isinstance(folder, list) else [folder]
    out = []
    for f in sorted((p for d in folders for p in d.iterdir() if p.suffix.lower() in VIDEO_EXT and not p.name.startswith(".")), key=lambda p: p.name):
        cid = _id(f)
        p = probe(f)
        mezz = ws.path("broll", "mezz", f"{cid}.mov")
        if not mezz.exists():
            mezz.parent.mkdir(parents=True, exist_ok=True)
            make_mezzanine(p, mezz, fps)
        dur = p.duration_s
        stamps = [(dur * k, f"{cid} {dur * k:.1f}s") for k in (0.1, 0.5, 0.9)]
        sheet = sheets.make_sheets(mezz, stamps, ws.path("broll", "sheets", cid))[0]
        side = f.with_suffix(".json")
        lic = json.loads(side.read_text()) if side.exists() else {}
        out.append({"id": cid, "name": f.name, "file": str(mezz.relative_to(ws.root)), "duration_ms": int(dur * 1000),
                    "width": p.video.display_width, "height": p.video.display_height, "sheet": str(sheet.relative_to(ws.root)),
                    "source": lic.get("source", "client"), "license": lic.get("license", "client-supplied"),
                    **{k: lic[k] for k in ("licence_id", "source_url", "sha256", "downloaded_at") if lic.get(k)},  # provenance (reel.licences)
                    **({"credit": f"{lic['author']} ({lic['page']})"} if lic.get("author") else {})})
    return out


def describe(ws: Workspace, clips: list[dict], caller=claude_call.call) -> dict[str, BrollDescription]:
    if not clips:
        return {}
    lines = ["# B-roll to describe", "", "| id | file | duration | contact sheet |", "|---|---|---|---|"]
    lines += [f"| {c['id']} | {c['name']} | {c['duration_ms'] / 1000:.1f} s | {c['sheet']} |" for c in clips]
    atomic_write_bytes(ws.path("broll", "describe.md"), ("\n".join(lines) + "\n").encode())
    res = caller(PROMPT, BrollDescriptions.model_json_schema(), cwd=ws.root, persona_file=PERSONA, effort="low",
                 log_file=ws.path("log", "runs.jsonl"), label="broll_describe")
    got = BrollDescriptions.model_validate(res.data)
    return {d.id: d for d in got.clips}


def index(ws: Workspace, folder: Path | list[Path], fps, caller=claude_call.call) -> dict:
    clips = conform(ws, folder, fps)
    desc = describe(ws, clips, caller)
    for c in clips:
        d = desc.get(c["id"])
        if d:
            c.update(d.model_dump(exclude={"id"}))
    atomic_write_json(ws.path("broll", "index.json"), {"clips": clips})
    return {"clips": len(clips), "described": len(desc)}


def best_src_in_us(meta: dict, need_us: int) -> int:
    """Where to start inside a b-roll clip so the needed span sits on its best moment."""
    dur = int(meta.get("duration_ms", 0)) * 1000
    spare = max(0, dur - need_us)
    return {"start": 0, "end": spare}.get(meta.get("best_at", "middle"), spare // 2)
