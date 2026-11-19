"""Stock b-roll search: Pexels and Pixabay video APIs → this project's b-roll pool.

Licences (checked in the asset research, docs/product/asset-engine-plan.md):
- Pexels (pexels.com/license): free commercial use, no attribution required; no resale of unaltered clips, no
  competing stock library. New Pexels API keys were paused in Nov 2026, so Pixabay is the second source.
- Pixabay (Content License): free commercial use, no attribution required; no redistribution of unmodified files as
  stock, and watch for trademarks/identifiable people. The API asks for 24 h caching and no hotlinking: we download.
Either way clips are downloaded per project and never added to a shared library.
Keys: PEXELS_API_KEY and/or PIXABAY_API_KEY in the environment (Reel Studio passes the ones saved in Settings).
"""

from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path

API = "https://api.pexels.com/videos/search"
PIXABAY_API = "https://pixabay.com/api/videos/"
LICENCE = "Pexels License — free commercial use, no attribution required; no resale of unaltered clips"
PIXABAY_LICENCE = "Pixabay Content License — free commercial use, no attribution required; no redistribution of unmodified clips"
SOURCE = {"pexels": ("Pexels", LICENCE), "pixabay": ("Pixabay", PIXABAY_LICENCE)}
KEY_ENV = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}
ORDER = ("pexels", "pixabay")  # Pexels first when its key exists (portrait filter), else Pixabay


class StockError(RuntimeError):
    pass


MAX_CLIP_BYTES = 200 * 1024 * 1024


def _get(url: str, key: str) -> bytes:
    from reel import net

    return net.get(url, {"Authorization": key} if key else None, timeout=120, max_bytes=MAX_CLIP_BYTES)


def pick_file(video: dict, min_h: int = 1280) -> dict | None:
    """Best Pexels rendition: portrait first, at least `min_h` tall, smallest that qualifies."""
    files = [f for f in video.get("video_files", []) if f.get("link") and f.get("height")]
    tall = [f for f in files if f["height"] >= f.get("width", 0) and f["height"] >= min_h]
    pool = tall or [f for f in files if f["height"] >= 720]
    return min(pool, key=lambda f: f["height"] * f.get("width", 1)) if pool else None


def search(query: str, *, n: int = 3, key: str | None = None, fetch=_get) -> list[dict]:
    """Pexels video search (portrait first)."""
    key = key or os.environ.get("PEXELS_API_KEY")
    if not key:
        raise StockError("set PEXELS_API_KEY (pexels.com/api) to search Pexels")
    url = f"{API}?{urllib.parse.urlencode({'query': query, 'orientation': 'portrait', 'per_page': max(n * 2, 6), 'size': 'medium'})}"
    data = json.loads(fetch(url, key))
    out = []
    for v in data.get("videos", []):
        f = pick_file(v)
        if f and 2 <= v.get("duration", 0) <= 30:
            out.append({"provider": "pexels", "id": v["id"], "url": f["link"], "w": f.get("width"), "h": f["height"], "duration": v["duration"],
                        "page": v.get("url"), "author": (v.get("user") or {}).get("name")})
        if len(out) >= n:
            break
    return out


def pick_pixabay(videos: dict) -> dict | None:
    """Best Pixabay rendition: portrait if any, else the sharpest of large/medium (cropping a vertical slice of a
    landscape clip needs resolution), never above 4K."""
    files = [f for f in (videos or {}).values() if isinstance(f, dict) and f.get("url") and f.get("width") and f.get("height")]
    tall = [f for f in files if f["height"] >= f["width"] and f["height"] >= 1280]
    if tall:
        return min(tall, key=lambda f: f["height"])
    wide = [f for f in files if 1080 <= f["height"] <= 2160]
    return max(wide, key=lambda f: f["height"]) if wide else None


def search_pixabay(query: str, *, n: int = 3, key: str | None = None, fetch=_get) -> list[dict]:
    key = key or os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise StockError("set PIXABAY_API_KEY (free key at pixabay.com/api/docs) to search Pixabay")
    url = f"{PIXABAY_API}?{urllib.parse.urlencode({'key': key, 'q': query[:100], 'video_type': 'film', 'safesearch': 'true', 'per_page': max(n * 3, 3)})}"
    data = json.loads(fetch(url, ""))  # the key is in the query string; no auth header
    out = []
    for v in data.get("hits", []):
        f = pick_pixabay(v.get("videos"))
        if f and 2 <= v.get("duration", 0) <= 30:
            out.append({"provider": "pixabay", "id": v["id"], "url": f["url"], "w": f["width"], "h": f["height"], "duration": v["duration"],
                        "page": v.get("pageURL"), "author": v.get("user")})
        if len(out) >= n:
            break
    return out


SEARCH = {"pexels": search, "pixabay": search_pixabay}


def available_keys(keys: dict[str, str | None] | None = None) -> dict[str, str]:
    keys = keys if keys is not None else {p: os.environ.get(env) for p, env in KEY_ENV.items()}
    return {p: k for p in ORDER if (k := (keys.get(p) or "").strip())}


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


def fetch_for_project(ws_root: Path, out: Path, caller, *, key: str | None = None, keys: dict[str, str | None] | None = None, fetch=_get,
                      log_file: Path | None = None) -> dict:
    """Edit-time stock b-roll: Claude writes searches from the talk; Pexels and/or Pixabay fill the project's own pool.

    `key` is a Pexels key (kept for callers that pass one); `keys` maps provider → key; default: the environment.
    Never raises: no key, a network error or no results is recorded in the returned status and the edit carries on
    without stock clips. Clips stay in this project (licences: no shared library).
    """
    have = available_keys({"pexels": key} if key else keys)
    status: dict = {"status": "ok", "providers": list(have), "queries": [], "clips": [], "errors": []}
    if not have:
        return {**status, "status": "skipped", "reason": "no stock key: add a Pixabay (or Pexels) API key in Studio → Settings"}
    try:
        res = caller(SCOUT_PROMPT, scout_schema(), cwd=ws_root, persona_file=SCOUT, effort="low", log_file=log_file, label="stock_scout")
        queries = [q for q in (res.data or {}).get("queries", []) if str(q.get("query", "")).strip()][:5]
    except Exception as exc:  # noqa: BLE001 — the scout is optional; the edit must not fail on it
        return {**status, "status": "failed", "reason": f"couldn't write searches: {str(exc)[:200]}"}
    seen: set = set()
    for q in queries:
        query = q["query"].strip()
        status["queries"].append({"query": query, "moment": q.get("moment", "")})
        if len(status["clips"]) >= MAX_CLIPS:
            break
        for provider, k in have.items():  # first provider with results wins for this query
            try:
                found = [r for r in SEARCH[provider](query, n=MAX_PER_QUERY + 2, key=k, fetch=fetch) if (provider, r["id"]) not in seen]
                picked = found[:MAX_PER_QUERY][: MAX_CLIPS - len(status["clips"])]
                for path in download(picked, out, query, key=k, fetch=fetch):
                    status["clips"].append(path.name)
                seen.update((provider, r["id"]) for r in picked)
                if picked:
                    break
            except Exception as exc:  # noqa: BLE001 — one failed search never stops the others
                status["errors"].append(f"{provider} · {query}: {str(exc)[:160]}")
    if not status["clips"]:
        status.update(status="failed" if status["errors"] else "empty", reason="no usable clips found")
    return status


def download(results: list[dict], folder: Path, query: str, *, key: str | None = None, fetch=_get) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for r in results:
        provider = r.get("provider", "pexels")
        dst = folder / f"{provider}_{r['id']}.mp4"
        if not dst.exists():
            # Pexels file URLs are public CDN links; the key header is only sent to Pexels itself.
            dst.write_bytes(fetch(r["url"], (key or os.environ.get("PEXELS_API_KEY", "")) if provider == "pexels" else ""))
        source, licence = SOURCE[provider]
        meta = {"source": source, "license": licence, "query": query, "page": r["page"], "author": r["author"]}
        dst.with_suffix(".json").write_text(json.dumps(meta, indent=1))
        paths.append(dst)
    return paths
