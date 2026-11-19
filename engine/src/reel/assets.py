"""Asset libraries Claude picks from by id: SFX, music, owned b-roll, caption families."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from reel import config

ASSETS_DIR = config.REPO_ROOT / "assets"
log = logging.getLogger(__name__)


@dataclass
class Indexes:
    sfx: dict[str, dict] = field(default_factory=dict)
    music: dict[str, dict] = field(default_factory=dict)
    broll: dict[str, dict] = field(default_factory=dict)
    caption_families: dict[str, dict] = field(default_factory=dict)


def _load_json_list(path: Path, key: str, root: Path | None = None) -> dict[str, dict]:
    """Items by id. With `root` (audio libraries): a relative `file` (fetched into assets/, see
    library._stored_path) becomes absolute under `root`, and items whose file is not on this machine
    are left out — the index is committed, the audio is not (`reel assets fetch` re-creates it)."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    items = {item["id"]: item for item in data.get(key, [])}
    if root is None:
        return items
    missing = 0
    for iid, item in list(items.items()):
        if item.get("file") and not Path(item["file"]).is_absolute():
            item["file"] = str((root / item["file"]).resolve())
        if item.get("file") and not Path(item["file"]).exists():
            del items[iid]
            missing += 1
    if missing:
        log.info("%s: %d indexed file(s) missing on this machine — run `reel assets fetch`", path.name, missing)
    return items


def load(root: Path = ASSETS_DIR) -> Indexes:
    fams = {}
    fam_file = root / "caption_styles" / "families.yaml"
    if fam_file.exists():
        fams = {f["id"]: f for f in (yaml.safe_load(fam_file.read_text()) or {}).get("families", [])}
    return Indexes(
        sfx=_load_json_list(root / "sfx" / "sfx_index.json", "sfx", root),
        music=_load_json_list(root / "music" / "music_index.json", "tracks", root),
        broll=_load_json_list(root / "broll_owned" / "index.json", "clips"),
        caption_families=fams,
    )
