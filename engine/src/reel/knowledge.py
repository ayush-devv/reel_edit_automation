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


LEARNED = config.KNOWLEDGE_DIR / "learned" / "overrides.yaml"
EDITABLE_FIELDS = ("summary", "when_to_use", "avoid_when", "parameters", "core")


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
    return apply_overrides(out, load_overrides())


def load_overrides(path=None) -> dict:
    """Learned deltas (self-improvement loop, ADR-0029): {"edit": {id: {field: value}}, "add": [node, ...]}.
    Kept apart from the generated graph so build_kb.py never overwrites what was learned."""
    path = path or LEARNED
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def apply_overrides(graph: dict[str, dict], ov: dict) -> dict[str, dict]:
    out = dict(graph)
    for nid, fields in (ov.get("edit") or {}).items():
        if nid in out:
            out[nid] = {**out[nid], **{k: v for k, v in fields.items() if k in EDITABLE_FIELDS}, "learned": True}
    for n in ov.get("add") or []:
        if isinstance(n, dict) and n.get("id") and n["id"] not in out:
            out[n["id"]] = {**n, "learned": True}
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


# ------------------------------------------------------------------ full library on disk (the Editor reads on demand)

LIBRARY_DIR = ("context", "knowledge")


def _by_file() -> dict[str, list[dict]]:
    """All nodes (overrides applied) grouped by graph file; learned additions go under `learned`."""
    all_nodes, seen, out = nodes(), set(), {}
    for f in sorted((config.KNOWLEDGE_DIR / "graph").glob("*.yaml")):
        if f.name == "id_map.yaml":
            continue
        data = yaml.safe_load(f.read_text())
        items = data if isinstance(data, list) else (data or {}).get("nodes", [])
        ids = [n["id"] for n in items or [] if isinstance(n, dict) and n.get("id") in all_nodes]
        out[f.stem] = [all_nodes[i] for i in ids]
        seen.update(ids)
    learned = [n for i, n in all_nodes.items() if i not in seen]
    if learned:
        out["learned"] = learned
    return out


def _detail(n: dict) -> str:
    keep = {k: v for k, v in n.items() if k not in ("sources", "id_aliases") and v not in (None, "", [], {})}
    return f"### `{n['id']}`\n\n" + yaml.safe_dump(keep, sort_keys=False, allow_unicode=True, width=120).strip() + "\n"


def library_files() -> dict[str, str]:
    """Relative path under context/knowledge/ -> markdown. index.md lists every node in one line;
    <file>.md holds full node details; capabilities.md says what this build can render."""
    from reel import capability_status

    groups = _by_file()
    total = sum(len(v) for v in groups.values())
    idx = ["# Knowledge index (every node; read the file named in each heading for full details)", "",
           f"{total} nodes. Rules marked [code] are enforced by the engine — you need not apply them.", ""]
    files: dict[str, str] = {}
    for stem, items in groups.items():
        idx += [f"## {stem} → `context/knowledge/{stem}.md` ({len(items)})", ""]
        idx += [f"- `{n['id']}` ({n.get('type', '?')}, {n.get('evidence_level', '?')}){' [code]' if _code_enforced(n) else ''} — "
                f"{n.get('name', '')}: {' '.join(str(n.get('summary', '')).split())[:100]}" for n in items]
        idx.append("")
        files[f"{stem}.md"] = f"# {stem}\n\n" + "\n".join(_detail(n) for n in items)
    files["index.md"] = "\n".join(idx)
    caps = yaml.safe_load((config.KNOWLEDGE_DIR / "capabilities.yaml").read_text()).get("capabilities", [])
    cap = ["# Editing capabilities: what this build can do", "",
           "`yes` = you can ask for it in the plan; `auto` = the engine always does it; `partial` = limited form; "
           "`no` = not available yet — do not plan around it.", ""]
    for c in caps:
        st, how = capability_status.status(c["id"])
        cap.append(f"- `{c['id']}` **{st}** — {c.get('name', '')}{': ' + how if st != 'no' else ''}")
    files["capabilities.md"] = "\n".join(cap) + "\n"
    return files


def write_library(ws) -> None:
    from reel.workspace import atomic_write_bytes

    for rel, text in library_files().items():
        atomic_write_bytes(ws.path(*LIBRARY_DIR, rel), text.encode())


LIBRARY_POINTER = ("\n## Full knowledge library\n\nThe nodes above are a starting shortlist. Every node (313+) is listed in "
                   "`context/knowledge/index.md`; read the matching `context/knowledge/<file>.md` for full details of any node "
                   "you may use, and `context/knowledge/capabilities.md` for what the renderer can and cannot do. "
                   "Cite every node you relied on, from anywhere in the library.\n")
