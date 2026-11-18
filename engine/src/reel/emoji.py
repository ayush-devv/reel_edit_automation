"""Emoji as Noto Emoji SVGs (Apache-2.0, via @iconify-json/noto pinned in renderer/package.json).

Images, not a colour font: the headless renderer draws nothing for COLRv1 emoji fonts, and an
SVG stays sharp at any size. The overlay receives a data: URI per emoji (no network at render).
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache

from reel import config

ICON_SET = config.REPO_ROOT / "renderer" / "node_modules" / "@iconify-json" / "noto"


@lru_cache(maxsize=1)
def _set() -> tuple[dict, dict, int, int]:
    icons = json.loads((ICON_SET / "icons.json").read_text())
    chars = json.loads((ICON_SET / "chars.json").read_text())
    return icons["icons"], chars, int(icons.get("width", 128)), int(icons.get("height", 128))


def _key(e: str) -> list[str]:
    cps = [f"{ord(c):x}" for c in e.strip()]
    plain = [c for c in cps if c != "fe0f"]
    return ["-".join(cps), "-".join(plain)]


def name(e: str) -> str | None:
    if not e.strip() or not ICON_SET.exists():
        return None
    icons, chars, _, _ = _set()
    for k in _key(e):
        n = chars.get(k)
        if n and n in icons:
            return n
    return None


def svg_uri(e: str) -> str | None:
    n = name(e)
    if n is None:
        return None
    icons, _, w, h = _set()
    ic = icons[n]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ic.get("width", w)} {ic.get("height", h)}">'
           f'{ic["body"]}</svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
