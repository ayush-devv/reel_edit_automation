"""Knowledge base access and compilation into Claude context (ADR-0027, ADR-0016).

Core principles are always loaded; the genre playbook (techniques + anti-patterns that apply
to the reel's genre, strongest evidence first) is loaded per reel. Rules enforced by the
compiler/QA (`enforced_by`) are omitted from Claude's context — code applies them.
"""

from __future__ import annotations

from functools import lru_cache

import yaml

from reel import config

EVIDENCE_RANK = {"platform": 0, "study": 1, "practitioner": 2, "theory": 3, "single_opinion": 4}


@lru_cache(maxsize=1)
def nodes() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted((config.KNOWLEDGE_DIR / "graph").glob("*.yaml")):
        if f.name == "id_map.yaml":
            continue
        data = yaml.safe_load(f.read_text())
        items = data if isinstance(data, list) else (data or {}).get("nodes", [])
        for n in items or []:
            if isinstance(n, dict) and "id" in n:
                out[n["id"]] = n
    return out


def node_ids() -> frozenset[str]:
    return frozenset(nodes())


def _line(n: dict) -> str:
    params = n.get("parameters") or {}
    p = ("; params " + ", ".join(f"{k}={v}" for k, v in list(params.items())[:4])) if params else ""
    when = f" When: {n['when_to_use']}" if n.get("when_to_use") else ""
    avoid = f" Avoid: {n['avoid_when']}" if n.get("avoid_when") else ""
    return f"- `{n['id']}` **{n.get('name', '')}** [{n.get('evidence_level', '?')}] — {n.get('summary', '').strip()}{when}{avoid}{p}"


def _code_enforced(n: dict) -> bool:
    return bool(set(n.get("enforced_by") or []) & {"compiler", "qa", "renderer"})


def core_principles() -> list[dict]:
    return [n for n in nodes().values() if n.get("core") and not _code_enforced(n)]


def genres() -> list[dict]:
    return [n for n in nodes().values() if n.get("type") == "genre"]


def playbook(genre: str | None, *, types=("technique", "anti_pattern"), limit: int = 40) -> list[dict]:
    """Nodes applying to a genre (or genre-agnostic ones), strongest evidence first."""
    pick = []
    for n in nodes().values():
        if n.get("type") not in types or _code_enforced(n):
            continue
        gs = n.get("genres") or []
        if genre and gs and genre not in gs:
            continue
        pick.append(n)
    pick.sort(key=lambda n: (EVIDENCE_RANK.get(n.get("evidence_level"), 9), 0 if genre in (n.get("genres") or []) else 1, n["id"]))
    return pick[:limit]


def story_context(genre_hint: str | None) -> str:
    """Markdown knowledge pack for the story pass."""
    lines = ["# Editing knowledge (cite node ids you rely on in `knowledge_used`)", "", "## Core principles"]
    lines += [_line(n) for n in core_principles()]
    lines += ["", "## Genres (pick the one that fits; each has a structure)"]
    for g in genres():
        lines.append(f"- `{g['id']}` — {g.get('summary', '').strip()}")
    lines += ["", f"## Playbook{' for ' + genre_hint if genre_hint else ''} (story, hooks, pacing)"]
    lines += [_line(n) for n in playbook(genre_hint, limit=35)
              if any(k in n["id"] for k in ("hook", "story", "pace", "pacing", "cut", "loop", "payoff", "structure", "open", "cta", "jump", "take"))
              or n.get("type") == "anti_pattern"]
    return "\n".join(lines) + "\n"


def finish_context(genre: str | None) -> str:
    """Markdown knowledge pack for the finish pass (emphasis, captions, SFX, music, motion)."""
    lines = ["# Finishing knowledge (cite node ids you rely on in `knowledge_used`)", ""]
    lines += [_line(n) for n in playbook(genre, limit=45)
              if any(k in n["id"] for k in ("punch", "zoom", "caption", "type", "sfx", "music", "duck", "broll", "b_roll", "transition", "emph", "motion", "color", "colour"))]
    return "\n".join(lines) + "\n"
