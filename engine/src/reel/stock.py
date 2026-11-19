"""Stock b-roll search (build step 10h): Pexels videos API → this project's b-roll pool.

Licence (pexels.com/license, checked 2026-11-18 in the asset research): free for commercial
use, no attribution required; not allowed to resell unaltered copies or build a competing
stock library — so clips are downloaded per project and never added to a shared library.
Needs PEXELS_API_KEY in the environment.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path

API = "https://api.pexels.com/videos/search"
LICENCE = "Pexels License — free commercial use, no attribution required; no resale of unaltered clips"


class StockError(RuntimeError):
    pass


MAX_CLIP_BYTES = 200 * 1024 * 1024


def _get(url: str, key: str) -> bytes:
    from reel import net

    return net.get(url, {"Authorization": key}, timeout=120, max_bytes=MAX_CLIP_BYTES)


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


MAX_PER_QUERY = 2
MAX_CLIPS = 6
SCOUT = Path(__file__).parent / "personas" / "stock_scout.md"
SCOUT_PROMPT = ("Read tables/summary.md and brief.json (if it exists) in this folder. Write the stock b-roll searches "
                "that would give the editor useful cutaways for this talk.")


def scout_schema() -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["queries"],
            "properties": {"queries": {"type": "array", "minItems": 1, "maxItems": 5, "items": {
                "type": "object", "additionalProperties": False, "required": ["query", "moment"],
                "properties": {"query": {"type": "string", "maxLength": 60}, "moment": {"type": "string", "maxLength": 160}}}}}}


def fetch_for_project(ws_root: Path, out: Path, caller, *, key: str | None = None, fetch=_get, log_file: Path | None = None) -> dict:
    """Edit-time stock b-roll: Claude writes searches from the talk, Pexels fills the project's own pool.

    Never raises: no key, a network error or no results is recorded in the returned status and the edit carries on
    without stock clips. Clips stay in this project (Pexels licence: no shared library).
    """
    key = key or os.environ.get("PEXELS_API_KEY")
    status: dict = {"status": "ok", "queries": [], "clips": [], "errors": []}
    if not key:
        return {**status, "status": "skipped", "reason": "no Pexels API key (Studio → Settings)"}
    try:
        res = caller(SCOUT_PROMPT, scout_schema(), cwd=ws_root, persona_file=SCOUT, effort="low", log_file=log_file, label="stock_scout")
        queries = [q for q in (res.data or {}).get("queries", []) if str(q.get("query", "")).strip()][:5]
    except Exception as exc:  # noqa: BLE001 — the scout is optional; the edit must not fail on it
        return {**status, "status": "failed", "reason": f"couldn't write searches: {str(exc)[:200]}"}
    seen: set = set()
    for q in queries:
        status["queries"].append({"query": q["query"].strip(), "moment": q.get("moment", "")})
        if len(status["clips"]) >= MAX_CLIPS:
            break
        try:
            found = [r for r in search(q["query"].strip(), n=MAX_PER_QUERY + 2, key=key, fetch=fetch) if r["id"] not in seen]
            picked = found[:MAX_PER_QUERY][: MAX_CLIPS - len(status["clips"])]
            for path in download(picked, out, q["query"].strip(), key=key, fetch=fetch):
                status["clips"].append(path.name)
            seen.update(r["id"] for r in picked)
        except Exception as exc:  # noqa: BLE001 — one failed search never stops the others
            status["errors"].append(f"{q['query']}: {str(exc)[:160]}")
    if not status["clips"]:
        status.update(status="failed" if status["errors"] else "empty", reason="no usable clips found")
    return status


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
