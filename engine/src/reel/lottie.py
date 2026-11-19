"""Lottie animations the Editor can place (graphic kind `lottie`): safety checks, indexing, recolouring.

A Lottie file is After Effects animation exported as JSON (Bodymovin); the overlay renders it with
@remotion/lottie. Two sources feed assets/lottie/index.json:
- our own starter pack (reel.lottie_pack, owned, recolourable to the brand accent), built by `reel assets fetch`;
- files the owner downloads (e.g. LottieFiles free animations, Lottie Simple License: commercial use OK, no
  attribution required; the licence forbids compiling a competing collection, so files are added one by one by
  the owner, never scraped) and indexes with `reel library lottie <folder> --source … --license …`.

Safety: lottie-web evaluates After Effects *expressions* with JavaScript eval, so a downloaded file could run code
inside the render browser. Files with expressions are refused, as are images loaded from the network (a render
must never fetch), text layers (their fonts would not exist), oversized or overlong files.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from reel import assets as assets_mod
from reel.library import check_licence
from reel.workspace import atomic_write_json

MAX_BYTES = 512 * 1024
MAX_SECONDS = 12.0
INDEX = ("lottie", "index.json")
SKIPPED: list[tuple[str, str]] = []


def problems(data) -> list[str]:
    """Why this JSON can't be used as a Lottie overlay ([] = safe to use)."""
    if not isinstance(data, dict) or not isinstance(data.get("layers"), list) or not data.get("fr") or "op" not in data:
        return ["not a Lottie animation (needs fr, op and layers)"]
    found: set[str] = set()

    def walk(node, in_layer_list=False):
        if isinstance(node, dict):
            if isinstance(node.get("x"), str) and node["x"].strip():
                found.add("uses After Effects expressions (JavaScript), which could run code during a render")
            if node.get("ty") == 5 and "t" in node:
                found.add("has text layers (their fonts would be missing)")
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data["layers"])
    for a in data.get("assets") or []:
        walk(a.get("layers", []))
        for k in ("u", "p"):
            if isinstance(a.get(k), str) and a[k].lower().startswith(("http:", "https:", "//")):
                found.add("loads images from the internet")
    dur = (float(data["op"]) - float(data.get("ip", 0))) / float(data["fr"])
    if dur <= 0 or dur > MAX_SECONDS:
        found.add(f"length {dur:.1f} s is outside 0–{MAX_SECONDS:.0f} s")
    if not data.get("w") or not data.get("h"):
        found.add("has no width/height")
    return sorted(found)


def inspect(data: dict) -> dict:
    fr = float(data["fr"])
    w, h = int(data["w"]), int(data["h"])
    return {"fps": fr, "duration_ms": int(round((float(data["op"]) - float(data.get("ip", 0))) / fr * 1000)), "width": w, "height": h,
            "aspect": "square" if abs(w - h) <= 0.15 * max(w, h) else "wide" if w > h else "tall"}


def _id(path: Path, raw: bytes) -> str:
    return "lt_" + hashlib.sha1(path.name.encode() + raw).hexdigest()[:8]


def entry_for(path: Path, *, source: str, license_: str, rel_to: Path, tags: list[str] | None = None, description: str = "",
              credit: str = "", recolour: bool = False) -> dict | None:
    """Index entry for one file, or None (and a SKIPPED line) when it fails the checks."""
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        SKIPPED.append((path.name, f"larger than {MAX_BYTES // 1024} KB"))
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        SKIPPED.append((path.name, "not valid JSON"))
        return None
    why = problems(data)
    if why:
        SKIPPED.append((path.name, "; ".join(why)))
        return None
    words = [w for w in path.stem.replace("-", "_").split("_") if w and not w.isdigit()]
    return {"id": _id(path, raw), "name": path.stem, "file": str(path.resolve().relative_to(rel_to.resolve())) if path.resolve().is_relative_to(rel_to.resolve()) else str(path.resolve()),
            "source": source, "license": license_, **({"credit": credit} if credit else {}), "tags": tags or words,
            "description": description or " ".join(words), "recolour": recolour, **inspect(data)}


def index_folder(folder: Path, *, source: str, license_: str, rel_to: Path = assets_mod.ASSETS_DIR, meta: dict | None = None) -> list[dict]:
    """Every *.json in the folder that passes the checks. `meta` (by file stem) adds description/tags/recolour."""
    check_licence(license_)
    SKIPPED.clear()
    out = []
    for f in sorted(folder.glob("*.json")):
        m = (meta or {}).get(f.stem, {})
        e = entry_for(f, source=source, license_=license_, rel_to=rel_to, tags=m.get("tags"), description=m.get("description", ""),
                      credit=m.get("credit", ""), recolour=bool(m.get("recolour")))
        if e:
            out.append(e)
    return out


def write_index(entries: list[dict], *, replace: bool = False, root: Path = assets_mod.ASSETS_DIR) -> Path:
    path = root.joinpath(*INDEX)
    data = json.loads(path.read_text()) if path.exists() else {"animations": []}
    sources = {e["source"] for e in entries}
    by = {e["id"]: e for e in data.get("animations", []) if not (replace and e.get("source") in sources)}
    by.update({e["id"]: e for e in entries})
    atomic_write_json(path, {"animations": sorted(by.values(), key=lambda e: e["id"])})
    return path


def _rgb(hex_: str) -> list[float]:
    h = hex_.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def load_for_render(meta: dict, accent: str | None = None) -> dict:
    """The animation JSON for the overlay props. Recolourable files (our pack) swap their white for the accent."""
    data = json.loads(Path(meta["file"]).read_text())
    if not (meta.get("recolour") and accent and accent.startswith("#") and len(accent) == 7):
        return data
    data = copy.deepcopy(data)
    target = _rgb(accent)

    def walk(node):
        if isinstance(node, dict):
            if node.get("ty") in ("st", "fl") and isinstance(node.get("c"), dict) and node["c"].get("a") == 0:
                k = node["c"].get("k")
                if isinstance(k, list) and len(k) >= 3 and all(abs(x - 1) < 1e-6 for x in k[:3]):
                    node["c"]["k"] = [*target, *(k[3:] or [1])]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data["layers"])
    return data
