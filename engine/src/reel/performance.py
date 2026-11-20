"""How a delivered reel did after posting (roadmap 4.4), and what a client's better reels had in common.

Works today with numbers the owner types in from Instagram/YouTube; an API connector (spike 4.0: Instagram
`instagram_business_manage_insights`, Standard Access for accounts the owner manages) can later write the same readings
with source "api". Kept OUT of everything the Editor reads and every stage fingerprint: a handful of posts must not steer
edits or re-buy paid passes. The report says what it is: a correlation over few reels, never proof.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from reel.workspace import Workspace, atomic_write_json

FILE = ("client", "performance.json")
MIN_REELS = 3  # fewer reels with numbers: no "what worked" line at all
PLATFORMS = ("instagram", "youtube", "other")
FIELDS = {  # name → (low, high) accepted
    "views": (0, 10**10), "reach": (0, 10**10), "avg_watch_s": (0, 3600), "skip_rate": (0, 100),
    "likes": (0, 10**9), "comments": (0, 10**9), "shares": (0, 10**9), "saves": (0, 10**9),
}


class PerformanceError(ValueError):
    pass


def load(ws: Workspace) -> dict:
    p = ws.path(*FILE)
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {"post_url": None, "platform": None, "readings": []}


def record(ws: Workspace, reading: dict, *, post_url: str | None = None, platform: str | None = None, source: str = "manual") -> dict:
    """Add one reading (numbers as the platform showed them on a given day)."""
    clean: dict = {}
    for k, (lo, hi) in FIELDS.items():
        v = reading.get(k)
        if v is None or v == "":
            continue
        try:
            v = float(v)
        except (TypeError, ValueError) as exc:
            raise PerformanceError(f"{k} must be a number") from exc
        if not lo <= v <= hi:
            raise PerformanceError(f"{k} must be between {lo} and {hi}")
        clean[k] = v
    if not clean:
        raise PerformanceError("enter at least one number (views, average watch time, skip rate…)")
    if platform is not None and platform not in PLATFORMS:
        raise PerformanceError(f"platform must be one of {', '.join(PLATFORMS)}")
    if post_url and not post_url.startswith("https://"):
        raise PerformanceError("the post link must start with https://")
    data = load(ws)
    if post_url:
        data["post_url"] = post_url
    if platform:
        data["platform"] = platform
    data["readings"].append({"at": time.time(), "source": source, **clean})
    atomic_write_json(ws.path(*FILE), data)
    return data


def latest(ws: Workspace) -> dict | None:
    rs = load(ws).get("readings") or []
    return rs[-1] if rs else None


def hold_rate(reading: dict, length_s: float | None) -> float | None:
    """Average watch time as a share of the reel's length: the one number comparable across reels of different lengths."""
    if not length_s or reading.get("avg_watch_s") is None:
        return None
    return round(min(reading["avg_watch_s"] / length_s, 3.0), 3)


def _rows(projects_root: Path, client_slug: str) -> list[dict]:
    from reel import client_memory

    rows = []
    for d in sorted(projects_root.iterdir()) if projects_root.exists() else []:
        if not d.is_dir() or d.name.startswith("."):
            continue
        ws = Workspace(d)
        if not ws.path(*FILE).exists() or client_memory.slug(client_memory.client_of(ws)) != client_slug:
            continue
        r = latest(ws)
        e = client_memory.entry(ws) or {}
        if not r:
            continue
        rows.append({"project": d.name, "reading": r, "hold": hold_rate(r, e.get("length_s")), "skip_rate": r.get("skip_rate"),
                     "views": r.get("views"), "length_s": e.get("length_s"), "cuts_per_min": e.get("cuts_per_min"),
                     "caption_family": e.get("caption_family"), "hook_title": e.get("hook_title"), "music_mood": e.get("music_mood")})
    return rows


def _split(rows: list[dict], key: str, label: str, unit: str = "") -> str | None:
    """Better half vs worse half by hold rate: a numeric feature's medians, only when they really differ."""
    have = [r for r in rows if r.get(key) is not None and r.get("hold") is not None]
    if len(have) < MIN_REELS:
        return None
    have.sort(key=lambda r: r["hold"], reverse=True)
    half = len(have) // 2
    top, rest = have[:max(1, half)], have[max(1, half):]
    a, b = statistics.median(r[key] for r in top), statistics.median(r[key] for r in rest)
    if b == 0 or abs(a - b) / abs(b) < 0.15:
        return None
    return f"the reels that held viewers longest had {'more' if a > b else 'less'} {label} (median {a:g}{unit} vs {b:g}{unit})"


def _common(rows: list[dict], key: str, label: str) -> str | None:
    have = [r for r in rows if r.get(key) and r.get("hold") is not None]
    if len(have) < MIN_REELS:
        return None
    best = sorted(have, key=lambda r: r["hold"], reverse=True)[: max(2, len(have) // 3)]
    vals = {r[key] for r in best}
    if len(vals) == 1 and sum(r[key] == next(iter(vals)) for r in have) < len(have):
        return f"the best-held reels all used {label} “{next(iter(vals))}”"
    return None


def client_report(projects_root: Path, client: str) -> dict:
    from reel import client_memory

    s = client_memory.slug(client)
    rows = _rows(projects_root, s) if s else []
    with_hold = [r for r in rows if r["hold"] is not None]
    worked = []
    if len(with_hold) >= MIN_REELS:
        for line in (_split(rows, "length_s", "length", " s"), _split(rows, "cuts_per_min", "cuts per minute"),
                     _common(rows, "hook_title", "the hook title"), _common(rows, "caption_family", "the caption style"),
                     _common(rows, "music_mood", "music mood")):
            if line:
                worked.append(line)
    return {
        "client": client, "reels": len(rows), "with_watch_time": len(with_hold),
        "rows": sorted(rows, key=lambda r: (r["hold"] is None, -(r["hold"] or 0))),
        "what_worked": worked,
        "caveat": (f"A correlation over {len(with_hold)} reel(s), not proof: topic, timing and luck move these numbers too."
                   if with_hold else "No watch-time numbers yet."),
        "needs": max(0, MIN_REELS - len(with_hold)),
    }
