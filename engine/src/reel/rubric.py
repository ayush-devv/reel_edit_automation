"""A rubric frozen per brief (roadmap 3b.1; VideoArgus, arXiv 2608.05485).

The Reviewer scores the finished reel against criteria written **before any output exists**, from the brief and the
client's style profile only, by code. It may not add, drop or rename a criterion (a changed list is sent back), so
the yardstick can't drift toward whatever the Editor made. An unmet *required* criterion (a must-keep line, the
call to action, a banned claim) is a Hold reason; the rest are warnings.
"""

from __future__ import annotations

import json

from reel.workspace import Workspace, atomic_write_json

FILE = ("plan", "rubric.json")


def build(brief, profile: dict | None) -> list[dict]:
    out: list[dict] = [{"id": "hook_2s", "text": "The first 2 seconds give a reason to keep watching (a claim, a question, a result or a surprise).",
                        "required": False}]
    if brief:
        for n, line in enumerate(brief.must_keep_lines, 1):
            out.append({"id": f"must_keep_{n}", "text": f"The reel says: “{line}” (or the same words).", "required": True})
        if brief.cta:
            out.append({"id": "cta", "text": f"The reel ends with the call to action: “{brief.cta}”.", "required": True})
        for n, claim in enumerate(brief.banned_claims, 1):
            out.append({"id": f"banned_{n}", "text": f"Nothing in the speech or on screen says or implies: “{claim}”.", "required": True})
        lo, hi = brief.target_length_s
        out.append({"id": "length", "text": f"The reel is about {lo:.0f}–{hi:.0f} s long.", "required": False})
        if brief.tone:
            out.append({"id": "tone", "text": f"The tone is {brief.tone}.", "required": False})
        if brief.genre_hint:
            out.append({"id": "genre", "text": f"It works as a {brief.genre_hint.removeprefix('genre.').replace('_', ' ')} reel.", "required": False})
        for n, name in enumerate(brief.product_names, 1):
            out.append({"id": f"product_{n}", "text": f"“{name}” is spelled right wherever it appears on screen.", "required": False})
    if profile:
        for n, s in enumerate(profile.get("recurring_settings", []), 1):
            out.append({"id": f"client_{n}", "text": f"Client habit: {s['kind'].replace('_', ' ')} is {json.dumps(s['value'], ensure_ascii=False)}.",
                        "required": False})
    return out


def write(ws: Workspace, brief, profile: dict | None) -> list[dict]:
    items = build(brief, profile)
    atomic_write_json(ws.path(*FILE), {"criteria": items})
    return items


def load(ws: Workspace) -> list[dict]:
    p = ws.path(*FILE)
    return json.loads(p.read_text()).get("criteria", []) if p.exists() else []


def md(items: list[dict]) -> list[str]:
    if not items:
        return []
    return ["", "## Rubric (fixed before the edit existed: score every criterion, add or drop none)", "",
            *[f"- `{c['id']}`{' **(required)**' if c['required'] else ''}: {c['text']}" for c in items]]


def check(review, items: list[dict]):
    """Issues when the Reviewer's rubric answers don't match the fixed criteria one for one."""
    from reel.validate import Issue

    want = [c["id"] for c in items]
    got = [r.id for r in review.rubric]
    if sorted(want) == sorted(got) and len(set(got)) == len(got):
        return []
    if not got:  # unanswered: the verdict says so; only a changed list is sent back
        return [Issue("rubric_unanswered", "rubric", "The Reviewer gave no rubric answers.", f"Answer these criteria: {want}.", "warning")]
    missing = [x for x in want if x not in got]
    extra = [x for x in got if x not in want]
    return [Issue("rubric_changed", "rubric", f"The rubric answers don't match the fixed criteria (missing {missing}, extra {extra}).",
                  f"Answer exactly these criteria, once each: {want}.")]


def verdict_effects(review, items: list[dict]) -> tuple[list[str], list[str]]:
    """(hold reasons, warnings) from the rubric answers."""
    req = {c["id"]: c for c in items}
    reasons, warnings = [], []
    if review is not None and items and not review.rubric:
        warnings.append("rubric: the Reviewer didn't score the fixed criteria")
    for r in (review.rubric if review else []):
        c = req.get(r.id)
        if c is None or r.met:
            continue
        line = f"rubric {r.id}: {c['text']}" + (f" — {r.evidence}" if r.evidence else "")
        (reasons if c["required"] else warnings).append(line)
    return reasons, warnings
