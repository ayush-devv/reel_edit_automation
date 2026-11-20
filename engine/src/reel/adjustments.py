"""Owner adjustments that survive a chat revision (roadmap G2.4, from the harness comparison).

Reel Studio's Adjust writes straight into plan/finish.json, and a chat revision returns a complete new finish plan,
so a hand-set change (music off, another look) could be undone silently. Each adjustment is logged here; the
revision prompt lists the ones still in force; after a revision, any of them that changed although the request
doesn't mention it raises an `adjustment_reverted` warning for the owner.
"""

from __future__ import annotations

import json
import time

from reel.schemas.plan import FinishPlan
from reel.validate import Issue
from reel.workspace import Workspace

LOG = ("plan", "adjustments.jsonl")
# kind → (words that mean the request is about it, how to read the current value from a finish plan)
FIELDS = {
    "caption_family": (("caption", "font", "subtitle", "text style"), lambda f: f.captions.family),
    "caption_token": (("caption", "colour", "color", "font", "subtitle"), None),
    "look": (("look", "colour", "color", "grade", "warm", "cool", "tone"), lambda f: f.grade.look),
    "look_strength": (("look", "colour", "color", "grade", "strong", "subtle"), lambda f: f.grade.strength),
    "music_track": (("music", "song", "track", "bed", "beat"), lambda f: f.music.track),
    "music_gain_db": (("music", "louder", "quieter", "volume", "level"), lambda f: f.music.gain_db),
    "sfx_off": (("sfx", "sound effect", "sounds", "whoosh"), lambda f: [c.id for c in f.sfx]),
    "punch_ins_off": (("punch", "zoom"), lambda f: [p.id for p in f.punch_ins]),
    "grain": (("grain", "texture", "film"), lambda f: f.grade.grain),
    "vignette": (("vignette", "corners", "dark"), lambda f: f.grade.vignette),
}


def log(ws: Workspace, kind: str, value) -> None:
    f = ws.path(*LOG)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as fh:
        fh.write(json.dumps({"at": time.time(), "kind": kind, "value": value}, ensure_ascii=False) + "\n")


def active(ws: Workspace, fin: FinishPlan | None) -> dict[str, object]:
    """The latest adjustment per kind that the current finish plan still carries (a later revision the owner asked for
    may have changed it on purpose; then it is no longer in force)."""
    f = ws.path(*LOG)
    if not f.exists():
        return {}
    latest: dict[str, object] = {}
    for line in f.read_text().splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("kind") in FIELDS:
            latest[e["kind"]] = e.get("value")
    if fin is None:
        return latest
    return {k: v for k, v in latest.items() if _holds(k, v, fin)}


def _holds(kind: str, value, fin: FinishPlan) -> bool:
    if kind == "caption_token":
        return isinstance(value, dict) and any(t.key == value.get("key") and t.value == value.get("value") for t in fin.captions.tokens)
    get = FIELDS[kind][1]
    cur = get(fin)
    if kind in ("sfx_off", "punch_ins_off"):
        return not cur if value is True else not set(cur) & set(value or [])
    return cur == value


def prompt_lines(adjusted: dict[str, object]) -> str:
    if not adjusted:
        return ""
    lines = [f"- {k.replace('_', ' ')}: {json.dumps(v, ensure_ascii=False)}" for k, v in adjusted.items()]
    return ("\n\nThe owner set these by hand in Adjust. Keep them exactly as they are unless the request is about them:\n" + "\n".join(lines))


def reverted(adjusted: dict[str, object], new_fin: FinishPlan, request: str) -> list[Issue]:
    req = request.casefold()
    out = []
    for kind, value in adjusted.items():
        if _holds(kind, value, new_fin):
            continue
        if any(w in req for w in FIELDS[kind][0]):
            continue  # the request is about this: the change is intended
        out.append(Issue("adjustment_reverted", f"finish ({kind})", f"The revision changed {kind.replace('_', ' ')}, which the owner set by hand "
                         f"({json.dumps(value, ensure_ascii=False)}), although the request doesn't mention it.",
                         "Keep the owner's setting unless the request asks to change it.", "warning"))
    return out
