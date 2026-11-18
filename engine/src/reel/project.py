"""Loading a workspace's compile inputs (word table, clips, fps) and writing plan artefacts."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

from reel.compile import ClipInfo
from reel.probe import probe
from reel.schemas.perception import WordTable
from reel.workspace import Workspace


def project_fps(ws: Workspace) -> Fraction:
    m = json.loads(ws.path("source", "manifest.json").read_text())
    num, den = m["project_fps"].split("/")
    return Fraction(int(num), int(den))


def clip_infos(ws: Workspace) -> dict[str, ClipInfo]:
    m = json.loads(ws.path("source", "manifest.json").read_text())
    out = {}
    for c in m["clips"]:
        mezz = ws.path("mezz", f"{c['id']}.mov")
        dur = probe(mezz).duration_s if mezz.exists() else c["probe"]["duration_s"]
        out[c["id"]] = ClipInfo(id=c["id"], uri=str(mezz.relative_to(ws.root)), duration_us=int(round(dur * 1_000_000)))
    return out


def word_table(ws: Workspace) -> WordTable:
    path = ws.path("perception", "words.json")
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — perception (build step 3) writes it; tests use fixtures.")
    return WordTable.model_validate_json(path.read_text())


def edges(ws: Workspace) -> dict[int, tuple[int, int]] | None:
    """Heard word edges from the tables stage (None if not computed yet)."""
    path = ws.path("perception", "edges.json")
    if not path.exists():
        return None
    return {int(k): (int(v[0]), int(v[1])) for k, v in json.loads(path.read_text()).items()}


def load_json_model(model, path: Path):
    return model.model_validate_json(Path(path).read_text())
