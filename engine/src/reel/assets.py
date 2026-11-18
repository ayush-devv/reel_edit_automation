"""Asset libraries Claude picks from by id: SFX, music, owned b-roll, caption families."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from reel import config

ASSETS_DIR = config.REPO_ROOT / "assets"


@dataclass
class Indexes:
    sfx: dict[str, dict] = field(default_factory=dict)
    music: dict[str, dict] = field(default_factory=dict)
    broll: dict[str, dict] = field(default_factory=dict)
    caption_families: dict[str, dict] = field(default_factory=dict)


def _load_json_list(path: Path, key: str) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {item["id"]: item for item in data.get(key, [])}


def load(root: Path = ASSETS_DIR) -> Indexes:
    fams = {}
    fam_file = root / "caption_styles" / "families.yaml"
    if fam_file.exists():
        fams = {f["id"]: f for f in (yaml.safe_load(fam_file.read_text()) or {}).get("families", [])}
    return Indexes(
        sfx=_load_json_list(root / "sfx" / "sfx_index.json", "sfx"),
        music=_load_json_list(root / "music" / "music_index.json", "tracks"),
        broll=_load_json_list(root / "broll_owned" / "index.json", "clips"),
        caption_families=fams,
    )
