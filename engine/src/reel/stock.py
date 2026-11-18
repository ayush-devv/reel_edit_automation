"""Stock b-roll search (build step 10h): Pexels videos API → this project's b-roll pool.

Licence (pexels.com/license, checked 2026-11-18 in the asset research): free for commercial
use, no attribution required; not allowed to resell unaltered copies or build a competing
stock library — so clips are downloaded per project and never added to a shared library.
Needs PEXELS_API_KEY in the environment.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.pexels.com/videos/search"
LICENCE = "Pexels License — free commercial use, no attribution required; no resale of unaltered clips"


class StockError(RuntimeError):
    pass


def _get(url: str, key: str) -> bytes:
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "reel-editor/0.1"})
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:  # noqa: S310 — fixed https host
        return r.read()


def pick_file(video: dict, min_h: int = 1280) -> dict | None:
    """Best rendition: portrait first, at least `min_h` tall, smallest that qualifies."""
    files = [f for f in video.get("video_files", []) if f.get("link") and f.get("height")]
    tall = [f for f in files if f["height"] >= f.get("width", 0) and f["height"] >= min_h]
    pool = tall or [f for f in files if f["height"] >= 720]
    return min(pool, key=lambda f: f["height"] * f.get("width", 1)) if pool else None


def search(query: str, *, n: int = 3, key: str | None = None, fetch=_get) -> list[dict]:
    key = key or os.environ.get("PEXELS_API_KEY")
    if not key:
        raise StockError("set PEXELS_API_KEY (free key at pexels.com/api) to search stock b-roll")
    url = f"{API}?{urllib.parse.urlencode({'query': query, 'orientation': 'portrait', 'per_page': max(n * 2, 6), 'size': 'medium'})}"
    data = json.loads(fetch(url, key))
    out = []
    for v in data.get("videos", []):
        f = pick_file(v)
        if f and 2 <= v.get("duration", 0) <= 30:
            out.append({"id": v["id"], "url": f["link"], "w": f.get("width"), "h": f["height"], "duration": v["duration"],
                        "page": v.get("url"), "author": (v.get("user") or {}).get("name")})
        if len(out) >= n:
            break
    return out


def download(results: list[dict], folder: Path, query: str, *, key: str | None = None, fetch=_get) -> list[Path]:
    key = key or os.environ.get("PEXELS_API_KEY", "")
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for r in results:
        dst = folder / f"pexels_{r['id']}.mp4"
        if not dst.exists():
            dst.write_bytes(fetch(r["url"], key))
        meta = {"source": "Pexels", "license": LICENCE, "query": query, "page": r["page"], "author": r["author"]}
        dst.with_suffix(".json").write_text(json.dumps(meta, indent=1))
        paths.append(dst)
    return paths
