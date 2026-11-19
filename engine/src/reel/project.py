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


def vad_speech(ws: Workspace) -> dict[str, list[list[int]]]:
    """Voice-activity speech spans per clip (µs), for pause tightening inside smeared ASR words."""
    path = ws.path("perception", "vad.json")
    if not path.exists():
        return {}
    return {k: v.get("speech", []) for k, v in json.loads(path.read_text()).items() if isinstance(v, dict)}


def scene_cuts(ws: Workspace) -> dict[str, list[int]]:
    """Camera cuts inside each source clip (µs)."""
    path = ws.path("perception", "scenes.json")
    if not path.exists():
        return {}
    return {k: v.get("cuts_us", []) for k, v in json.loads(path.read_text()).items() if isinstance(v, dict)}


def edges(ws: Workspace) -> dict[int, tuple[int, int]] | None:
    """Heard word edges from the tables stage (None if not computed yet)."""
    path = ws.path("perception", "edges.json")
    if not path.exists():
        return None
    return {int(k): (int(v[0]), int(v[1])) for k, v in json.loads(path.read_text()).items()}


def load_json_model(model, path: Path):
    return model.model_validate_json(Path(path).read_text())


def brief_path(ws: Workspace, options: dict | None = None) -> str | None:
    """The run's brief, else the one the Studio saved in the project (revise and adjust runs may not pass it)."""
    given = (options or {}).get("brief")
    if given:
        return str(given)
    saved = ws.path("brief.json")
    return str(saved) if saved.exists() else None


def studio_client(ws: Workspace) -> str | None:
    """The client the owner set in Reel Studio (studio.json), if any."""
    f = ws.path("studio.json")
    try:
        return (json.loads(f.read_text()).get("client") or None) if f.exists() else None
    except ValueError:
        return None


def indexes(ws: Workspace):
    """Global asset libraries + this project's client b-roll pool (broll/index.json)."""
    from reel import assets

    idx = assets.load()
    pool = ws.path("broll", "index.json")
    if pool.exists():
        idx.broll.update({c["id"]: c for c in json.loads(pool.read_text()).get("clips", [])})
    return idx
