"""Validate the knowledge base (knowledge/capabilities.yaml + knowledge/graph/*.yaml).

Checks: schema fields, unique ids, id prefix vs type, file routing, summary ≤ 60 words,
capability description ≤ 40 words, ≥ 1 source, all references resolve (genres, avoid_genres,
goals, conflicts_with, requires, uses_capabilities, platforms, example techniques), enums
(renderer_owner incl. engine, evidence_level, confidence, enforced_by), id_map integrity.

Usage: uv run --with pyyaml python knowledge/tools/validate_kb.py
Exit code 0 = pass (warnings allowed), 1 = errors.
"""
import collections
import pathlib
import re
import sys

import yaml

KB = pathlib.Path(__file__).resolve().parents[1]
GRAPH = KB / "graph"

RENDERER_OWNERS = {"ffmpeg", "remotion", "both", "engine", "unsupported"}
CAP_CATEGORIES = {"cut", "trim", "transition", "transform", "speed", "color", "audio", "text", "graphics",
                  "compositing", "effect", "export", "analysis"}
NODE_TYPES = {"principle": "principle.", "technique": "tech.", "anti_pattern": "anti.", "goal": "goal.",
              "genre": "genre.", "platform": "platform.", "example": "example."}
EVIDENCE = {"platform", "study", "practitioner", "theory", "single_opinion"}
CONFIDENCE = {"high", "medium", "low"}
ENFORCED_BY = {"compiler", "qa_gate", "qa_warning", "reviewer"}
FILE_TYPES = {
    "principles": {"principle"},
    "techniques_story_pacing": {"technique"},
    "techniques_sound_music": {"technique"},
    "techniques_color_type_motion": {"technique"},
    "anti_patterns": {"anti_pattern"},
    "genres": {"genre"},
    "platforms_goals": {"platform", "goal"},
    "examples": {"example"},
}
CAP_REQUIRED = ["id", "category", "name", "description", "parameters", "nle_names", "renderer_owner",
                "requires_pinned_ffmpeg", "sources"]
NODE_REQUIRED = ["id", "type", "name", "summary", "when_to_use", "how", "parameters", "avoid_when", "genres",
                 "goals", "uses_capabilities", "conflicts_with", "requires", "evidence_level", "confidence", "sources"]
LIST_FIELDS = ["how", "genres", "goals", "uses_capabilities", "conflicts_with", "requires"]
ADR_RE = re.compile(r"^ADR-\d{4}$")
CAP_ID_RE = re.compile(r"^cap\.([a-z]+)\.[a-z0-9_]+$")
NODE_ID_RE = re.compile(r"^[a-z_]+(\.[a-z0-9_]+)+$")

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def words(text):
    return len(str(text).split())


def check_sources(where, sources):
    if not isinstance(sources, list) or not sources:
        err(f"{where}: needs ≥ 1 source")
        return
    for s in sources:
        if not isinstance(s, dict) or not s.get("title") or not s.get("url"):
            err(f"{where}: source missing title/url: {s}")


def check_decided_by(where, item):
    for adr in item.get("decided_by") or []:
        if not ADR_RE.match(str(adr)):
            err(f"{where}: bad decided_by '{adr}'")


def validate_caps():
    data = yaml.safe_load((KB / "capabilities.yaml").read_text())
    caps = data.get("capabilities") or []
    ids = collections.Counter(c.get("id") for c in caps)
    for cid, k in ids.items():
        if k > 1:
            err(f"capability id duplicated: {cid}")
    for c in caps:
        cid = c.get("id", "<no id>")
        for f in CAP_REQUIRED:
            if f not in c:
                err(f"{cid}: missing field {f}")
        m = CAP_ID_RE.match(cid)
        if not m:
            err(f"{cid}: id must be cap.<category>.<snake_name>")
        elif m.group(1) != c.get("category"):
            err(f"{cid}: id category segment != category '{c.get('category')}'")
        if c.get("category") not in CAP_CATEGORIES:
            err(f"{cid}: bad category {c.get('category')}")
        owner = c.get("renderer_owner")
        if owner not in RENDERER_OWNERS:
            err(f"{cid}: renderer_owner '{owner}' not in {sorted(RENDERER_OWNERS)}")
        if not isinstance(c.get("requires_pinned_ffmpeg"), bool):
            err(f"{cid}: requires_pinned_ffmpeg must be true/false")
        if words(c.get("description", "")) > 40:
            err(f"{cid}: description {words(c['description'])} words > 40")
        if owner == "unsupported" and not (c.get("notes") or "").strip():
            err(f"{cid}: unsupported entries need notes giving the reason")
        if owner == "engine" and not (c.get("engine_tool") or "").strip():
            err(f"{cid}: engine entries need engine_tool")
        notes = (c.get("notes") or "").lower()
        if owner != "unsupported" and re.search(r"\(unsupported( in-stack| locally)?\)|outside the stack|absent in the local|lacks libass", notes):
            # mentioning *another* unsupported capability is fine; flag stale self-reasons
            warn(f"{cid}: owner '{owner}' but notes contain a stale 'unsupported/absent' reason")
        if not isinstance(c.get("parameters"), list):
            err(f"{cid}: parameters must be a list")
        check_sources(cid, c.get("sources"))
        check_decided_by(cid, c)
    return caps


def validate_graph(cap_ids):
    nodes, where = {}, {}
    for fname, allowed in FILE_TYPES.items():
        path = GRAPH / f"{fname}.yaml"
        if not path.exists():
            err(f"missing graph file {path.name}")
            continue
        data = yaml.safe_load(path.read_text()) or {}
        for n in data.get("nodes") or []:
            nid = n.get("id", "<no id>")
            if nid in nodes:
                err(f"node id duplicated: {nid} ({where[nid]} and {fname})")
            nodes[nid], where[nid] = n, fname
            if n.get("type") not in allowed:
                err(f"{nid}: type '{n.get('type')}' not allowed in {fname}.yaml")
    for nid, n in nodes.items():
        for f in NODE_REQUIRED:
            if f not in n:
                err(f"{nid}: missing field {f}")
        t = n.get("type")
        if t not in NODE_TYPES:
            err(f"{nid}: bad type {t}")
        elif not nid.startswith(NODE_TYPES[t]):
            err(f"{nid}: id prefix does not match type '{t}' (expected {NODE_TYPES[t]}*)")
        if not NODE_ID_RE.match(nid):
            err(f"{nid}: id must be lowercase dotted snake_case")
        if nid in cap_ids:
            err(f"{nid}: collides with a capability id")
        if words(n.get("summary", "")) > 60:
            err(f"{nid}: summary {words(n['summary'])} words > 60")
        if not str(n.get("summary", "")).strip():
            err(f"{nid}: empty summary")
        if n.get("evidence_level") not in EVIDENCE:
            err(f"{nid}: bad evidence_level {n.get('evidence_level')}")
        if n.get("confidence") not in CONFIDENCE:
            err(f"{nid}: bad confidence {n.get('confidence')}")
        for f in LIST_FIELDS:
            if f in n and not isinstance(n[f], list):
                err(f"{nid}: {f} must be a list")
        if not isinstance(n.get("parameters"), dict):
            err(f"{nid}: parameters must be a mapping")
        for e in n.get("enforced_by") or []:
            if e not in ENFORCED_BY:
                err(f"{nid}: bad enforced_by '{e}'")
        if "core" in n and not isinstance(n["core"], bool):
            err(f"{nid}: core must be true/false")
        if n.get("core") and t != "principle":
            err(f"{nid}: only principles can be core")
        check_decided_by(nid, n)
        check_sources(nid, n.get("sources"))

        def ref(field, target_types=None, values=None):
            for r in values if values is not None else (n.get(field) or []):
                if r not in nodes:
                    err(f"{nid}: {field} → unknown node '{r}'")
                elif target_types and nodes[r].get("type") not in target_types:
                    err(f"{nid}: {field} → '{r}' is type {nodes[r].get('type')}, expected {target_types}")
                elif r == nid:
                    err(f"{nid}: {field} references itself")

        ref("genres", {"genre"})
        ref("avoid_genres", {"genre"})
        ref("goals", {"goal"})
        ref("platforms", {"platform"})
        ref("conflicts_with")
        ref("requires")
        overlap = set(n.get("genres") or []) & set(n.get("avoid_genres") or [])
        if overlap:
            err(f"{nid}: genres and avoid_genres overlap {sorted(overlap)}")
        if t == "example":
            ref("techniques", None, [x.get("id") for x in n.get("techniques") or []])
        for c in n.get("uses_capabilities") or []:
            if c not in cap_ids:
                err(f"{nid}: uses_capabilities → unknown capability '{c}'")
    return nodes


ID_TOKEN = re.compile(r"\b(?:principle|tech|anti|goal|genre|platform|example|cap)(?:\.[a-z0-9_]+)+(?![a-z0-9_]*\*)(?!\.\*)")


def iter_strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from iter_strings(v, f"{path}[{i}]")
    elif isinstance(value, dict):
        for k, v in value.items():
            if k == "url":
                continue
            yield from iter_strings(v, f"{path}.{k}" if path else k)


def validate_prose_ids(caps, nodes):
    """Every id-shaped token in text must resolve (catches stale ids after merges)."""
    known = set(nodes) | {c["id"] for c in caps}
    items = [(c["id"], c) for c in caps] + list(nodes.items())
    for owner, item in items:
        for path, text in iter_strings({k: v for k, v in item.items() if k not in ("id", "merged_from", "drafts")}):
            for tok in ID_TOKEN.findall(text):
                if tok not in known:
                    err(f"{owner}: '{tok}' in {path} does not resolve to a node or capability")


def validate_local_sources(caps, nodes):
    root = KB.parent
    for owner, item in [(c["id"], c) for c in caps] + list(nodes.items()):
        for s in item.get("sources") or []:
            url = str(s.get("url", ""))
            if url and not url.startswith(("http://", "https://")) and not (root / url).exists():
                warn(f"{owner}: local source path not found: {url}")


def validate_id_map(nodes, cap_ids):
    path = GRAPH / "id_map.yaml"
    if not path.exists():
        err("missing graph/id_map.yaml")
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    node_map = data.get("nodes") or {}
    all_refs = set()
    for n in nodes.values():
        for f in ["genres", "avoid_genres", "goals", "conflicts_with", "requires", "platforms"]:
            all_refs.update(n.get(f) or [])
        all_refs.update(x.get("id") for x in n.get("techniques") or [])
    for old, new in node_map.items():
        if new not in nodes:
            err(f"id_map nodes: {old} → {new} target missing")
        if old in nodes:
            err(f"id_map nodes: old id {old} still present as a node")
        if old in all_refs:
            err(f"id_map nodes: old id {old} still referenced")
    for old, new in (data.get("capabilities") or {}).items():
        for t in new if isinstance(new, list) else [new]:
            if t not in cap_ids:
                err(f"id_map capabilities: {old} → {t} target missing")
    return node_map


def print_stats(caps, nodes):
    """Markdown tables for the README (counts are generated, never hand-typed)."""
    def table(title, counter, header):
        print(f"\n**{title}**\n\n| {header} | count |\n|---|---|")
        for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0]))):
            print(f"| {k} | {v} |")

    table("Nodes by type", collections.Counter(n["type"] for n in nodes.values()), "type")
    table("Nodes by evidence level", collections.Counter(n["evidence_level"] for n in nodes.values()), "evidence_level")
    table("Nodes by genre (genres field = applies_to)",
          collections.Counter(g for n in nodes.values() for g in n.get("genres") or []), "genre")
    table("Nodes by file", collections.Counter(
        f.stem for f in GRAPH.glob("*.yaml") if f.stem in FILE_TYPES
        for _ in (yaml.safe_load(f.read_text()) or {}).get("nodes") or []), "file")
    table("Capabilities by renderer_owner", collections.Counter(c["renderer_owner"] for c in caps), "renderer_owner")
    table("Capabilities by category", collections.Counter(c["category"] for c in caps), "category")


def main():
    caps = validate_caps()
    cap_ids = {c["id"] for c in caps}
    nodes = validate_graph(cap_ids)
    node_map = validate_id_map(nodes, cap_ids)
    validate_prose_ids(caps, nodes)
    validate_local_sources(caps, nodes)

    used_caps = {c for n in nodes.values() for c in n.get("uses_capabilities") or []}
    print("== knowledge base validation ==")
    print(f"capabilities: {len(caps)}  owners: {dict(sorted(collections.Counter(c['renderer_owner'] for c in caps).items()))}")
    print(f"  pinned-ffmpeg: {sum(c['requires_pinned_ffmpeg'] for c in caps)}  referenced by graph: {len(used_caps & cap_ids)}")
    print(f"nodes: {len(nodes)}  types: {dict(sorted(collections.Counter(n.get('type') for n in nodes.values()).items()))}")
    print(f"  evidence: {dict(sorted(collections.Counter(n.get('evidence_level') for n in nodes.values()).items()))}")
    print(f"  core principles: {sum(1 for n in nodes.values() if n.get('core'))}  id_map entries: {len(node_map)}")
    if "--stats" in sys.argv:
        print_stats(caps, nodes)
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"result: {'FAIL' if errors else 'PASS'} — {len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
