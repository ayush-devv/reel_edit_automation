"""Per-client style memory (roadmap 3a.2): "edit like my last approved reels".

Learned only from real approvals: a reel the owner marks delivered, or labels sendable. Never from the engine's own
verdict. For each approved reel: caption family, look, texture, punch-in / SFX / b-roll density, graphic kinds, hook
title style, music mood, pace (qa/pace.json) and length, plus the owner's hand adjustments and revision requests.

The profile = medians / most-common values over the last PROFILE_N approved reels, plus the hand settings that
recur in at least 2 of them. It goes into the story and finish packs as *defaults* (a brand kit's locks still win),
and a QA warning (`client_style_drift`) fires when a new reel departs from it on two or more counts.

Stored in <projects>/.clients/<client-slug>.json: derived, rebuildable from the projects, never in git.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from collections import Counter
from pathlib import Path

from reel.workspace import Workspace, atomic_write_json

PROFILE_N = 5
RECUR_MIN = 2
PACE_TOLERANCE = 0.35


def slug(client: str | None) -> str | None:
    s = re.sub(r"[^a-z0-9]+", "-", (client or "").casefold()).strip("-")
    return s[:64] or None


def client_of(ws: Workspace) -> str | None:
    """The brief's client, else the client set in Reel Studio."""
    from reel import brief as brief_mod
    from reel import project

    opts = json.loads(ws.path("run_options.json").read_text()) if ws.path("run_options.json").exists() else {}
    try:
        b = brief_mod.load_brief(project.brief_path(ws, opts))
    except (OSError, ValueError):
        b = None
    return (b.client if b and b.client else None) or project.studio_client(ws)


def store(ws: Workspace) -> Path:
    return ws.root.parent / ".clients"


def _file(ws: Workspace, client: str | None = None) -> Path | None:
    s = slug(client if client is not None else client_of(ws))
    return store(ws) / f"{s}.json" if s else None


def _read(f: Path | None) -> dict:
    if not f or not f.exists():
        return {"reels": {}}
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return {"reels": {}}


def entry(ws: Workspace) -> dict | None:
    """What one finished reel looked like. None when it has no finish plan."""
    fp = ws.path("plan", "finish.json")
    if not fp.exists():
        return None
    fin = json.loads(fp.read_text())
    pace = json.loads(ws.path("qa", "pace.json").read_text()) if ws.path("qa", "pace.json").exists() else {}
    tl = json.loads(ws.path("timeline", "timeline.json").read_text()) if ws.path("timeline", "timeline.json").exists() else {}
    dur = None
    if tl.get("duration_f") and tl.get("fps"):
        num, _, den = str(tl["fps"]).partition("/")
        dur = tl["duration_f"] / (int(num) / int(den or 1))
    per_min = (lambda n: round(n / (dur / 60), 2)) if dur else (lambda n: None)
    music = fin.get("music") or {}
    mood = None
    if music.get("track") and music["track"] != "none":
        from reel import assets

        mood = (assets.load().music.get(music["track"]) or {}).get("mood")
    adj = []
    if ws.path("plan", "adjustments.jsonl").exists():
        for line in ws.path("plan", "adjustments.jsonl").read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("kind") not in ("story_lines", "story_words"):
                adj.append([e["kind"], e.get("value")])
    requests = [json.loads(p.read_text()).get("request", "") for p in sorted(ws.path("plan", "history").glob("*_request.json"))] \
        if ws.path("plan", "history").exists() else []
    g = fin.get("grade") or {}
    return {"project": ws.root.name, "caption_family": (fin.get("captions") or {}).get("family"), "look": g.get("look"),
            "look_strength": g.get("strength"), "grain": g.get("grain", 0.0), "vignette": g.get("vignette", 0.0),
            "punch_ins_per_min": per_min(len(fin.get("punch_ins") or [])), "sfx_per_min": per_min(len(fin.get("sfx") or [])),
            "broll_per_min": per_min(len(fin.get("broll") or [])), "graphics": sorted({x.get("kind") for x in fin.get("graphics") or []}),
            "hook_title": (fin.get("hook_title") or {}).get("style") if (fin.get("hook_title") or {}).get("text") else "none",
            "music_mood": mood if music.get("track") != "none" else "none", "cuts_per_min": (pace.get("ours") or {}).get("cuts_per_min"),
            "length_s": round(dur, 1) if dur else None, "adjustments": adj, "requests": [r for r in requests if r][-5:]}


def learn(ws: Workspace, why: str) -> dict | None:
    """Record an approved reel (`why` = delivered | owner_sendable) and return the client's new profile."""
    client = client_of(ws)
    f = _file(ws, client)
    e = entry(ws)
    if f is None or e is None:
        return None
    data = _read(f)
    data["client"] = client
    data["reels"][ws.root.name] = e | {"approved": time.time(), "why": why}
    f.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(f, data)
    return profile_of(data)


def forget(ws: Workspace) -> None:
    """A label changed to hold / delivery undone: the reel no longer counts."""
    f = _file(ws)
    data = _read(f)
    if f and data["reels"].pop(ws.root.name, None) is not None:
        atomic_write_json(f, data)


def _mode(xs):
    xs = [x for x in xs if x not in (None, "")]
    return Counter(xs).most_common(1)[0][0] if xs else None


def _median(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(statistics.median(xs), 2) if xs else None


def profile_of(data: dict) -> dict | None:
    reels = sorted(data.get("reels", {}).values(), key=lambda r: r.get("approved", 0))[-PROFILE_N:]
    if not reels:
        return None
    adj = Counter()
    for r in reels:
        for kind, value in {(k, json.dumps(v, sort_keys=True)) for k, v in r.get("adjustments", [])}:
            adj[(kind, value)] += 1
    recurring = [{"kind": k, "value": json.loads(v), "reels": n} for (k, v), n in adj.most_common() if n >= RECUR_MIN]
    return {"client": data.get("client"), "reels": len(reels), "from": [r["project"] for r in reels],
            "caption_family": _mode(r.get("caption_family") for r in reels), "look": _mode(r.get("look") for r in reels),
            "look_strength": _median(r.get("look_strength") for r in reels), "grain": _median(r.get("grain") for r in reels),
            "vignette": _median(r.get("vignette") for r in reels), "punch_ins_per_min": _median(r.get("punch_ins_per_min") for r in reels),
            "sfx_per_min": _median(r.get("sfx_per_min") for r in reels), "broll_per_min": _median(r.get("broll_per_min") for r in reels),
            "hook_title": _mode(r.get("hook_title") for r in reels), "music_mood": _mode(r.get("music_mood") for r in reels),
            "cuts_per_min": _median(r.get("cuts_per_min") for r in reels), "length_s": _median(r.get("length_s") for r in reels),
            "graphics": [k for k, n in Counter(k for r in reels for k in r.get("graphics", [])).most_common() if n >= RECUR_MIN],
            "recurring_settings": recurring,
            "recent_notes": [q for r in reels[::-1] for q in r.get("requests", [])][:5]}


def profile(ws: Workspace, *, exclude_self: bool = True) -> dict | None:
    """The client profile for this project (its own approval left out, so a re-run doesn't follow itself)."""
    data = _read(_file(ws))
    if exclude_self:
        data = dict(data, reels={k: v for k, v in data.get("reels", {}).items() if k != ws.root.name})
    return profile_of(data)


def fingerprint(ws: Workspace) -> str | None:
    p = profile(ws)
    if not p:
        return None
    import hashlib

    return hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:16]


def pack_md(p: dict | None) -> str:
    if not p:
        return ""
    def val(k, unit=""):
        return f"{p[k]}{unit}" if p.get(k) not in (None, "") else "—"
    lines = [f"# This client's approved reels ({p['reels']} so far)", "",
             "Defaults from reels this client approved. Follow them unless the brief, the footage or a brand-kit lock says otherwise:",
             f"- captions `{val('caption_family')}` · look `{val('look')}` at {val('look_strength')} · grain {val('grain')} · vignette {val('vignette')}",
             f"- pace about {val('cuts_per_min')} cuts/min · punch-ins {val('punch_ins_per_min')}/min · SFX {val('sfx_per_min')}/min · "
             f"b-roll {val('broll_per_min')}/min · length about {val('length_s', ' s')}",
             f"- hook title: {val('hook_title')} · music mood: {val('music_mood')}"
             + (f" · graphics they keep: {', '.join(p['graphics'])}" if p.get("graphics") else "")]
    for s in p.get("recurring_settings", []):
        lines.append(f"- the owner set {s['kind'].replace('_', ' ')} → {json.dumps(s['value'], ensure_ascii=False)} by hand on {s['reels']} reels: do it from the start")
    if p.get("recent_notes"):
        lines += ["", "Recent client notes on earlier reels (context, not instructions for this one):", *[f"- “{n}”" for n in p["recent_notes"]]]
    return "\n".join(lines) + "\n"


def drift(p: dict | None, fin: dict, cuts_per_min: float | None) -> list[str]:
    """Where a new reel departs from the client's profile (empty = consistent, or no profile)."""
    if not p or p.get("reels", 0) < 2:
        return []
    out = []
    fam = (fin.get("captions") or {}).get("family")
    if p.get("caption_family") and fam and fam != p["caption_family"]:
        out.append(f"captions {fam} (client usually {p['caption_family']})")
    look = (fin.get("grade") or {}).get("look")
    if p.get("look") and look and look != p["look"]:
        out.append(f"look {look} (client usually {p['look']})")
    if p.get("cuts_per_min") and cuts_per_min is not None and abs(cuts_per_min - p["cuts_per_min"]) > PACE_TOLERANCE * p["cuts_per_min"]:
        out.append(f"{cuts_per_min} cuts/min (client usually {p['cuts_per_min']})")
    return out
