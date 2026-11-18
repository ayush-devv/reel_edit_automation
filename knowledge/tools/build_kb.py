"""Build the validated knowledge base from knowledge/drafts/* + knowledge/tools/merge_plan.yaml.

Outputs (all generated — edit merge_plan.yaml, not these):
  knowledge/capabilities.yaml
  knowledge/graph/{principles,techniques_story_pacing,techniques_sound_music,
                   techniques_color_type_motion,anti_patterns,genres,platforms_goals,examples}.yaml
  knowledge/graph/id_map.yaml

Usage: uv run --with pyyaml python knowledge/tools/build_kb.py
"""
import collections
import copy
import pathlib
import re
import sys

import yaml

KB = pathlib.Path(__file__).resolve().parents[1]
DRAFTS = KB / "drafts"
GRAPH = KB / "graph"
PLAN = KB / "tools" / "merge_plan.yaml"
GRAPH_DRAFTS = ["graph_editing_theory", "graph_shortform_craft", "graph_sound_music", "graph_color_type_motion"]

EVIDENCE_RANK = {"platform": 5, "study": 4, "practitioner": 3, "theory": 2, "single_opinion": 1}
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
CORE_NODE_FIELDS = ["id", "type", "name", "summary", "when_to_use", "how", "parameters", "avoid_when",
                    "genres", "avoid_genres", "goals", "uses_capabilities", "conflicts_with", "requires",
                    "evidence_level", "confidence", "core", "enforced_by", "decided_by", "sources", "merged_from", "drafts"]
LIST_FIELDS = ["how", "genres", "avoid_genres", "goals", "uses_capabilities", "conflicts_with", "requires",
               "enforced_by", "decided_by", "merged_from", "drafts"]
CAP_FIELDS = ["id", "category", "name", "description", "parameters", "nle_names", "renderer_owner",
              "engine_tool", "requires_pinned_ffmpeg", "notes", "decided_by", "sources"]

# Routing: by type; techniques by the id's domain segment (tech.<domain>.<name>).
SOUND_DOMAINS = {"audio", "split", "loudness", "dialogue", "repair", "voice", "duck", "music", "sfx", "silence", "mix", "beat"}
VISUAL_DOMAINS = {"color", "type", "caption", "motion", "transition", "punch_in"}
VISUAL_OVERRIDES = {"tech.india.devanagari_text", "tech.india.romanised_hinglish_captions"}
FILES = {
    "principles": "Principles — why and when, across genres",
    "techniques_story_pacing": "Techniques — story, hooks, structure, cutting and pacing",
    "techniques_sound_music": "Techniques — dialogue, sound design, music and loudness",
    "techniques_color_type_motion": "Techniques — colour, typography/captions, motion graphics and transitions",
    "anti_patterns": "Anti-patterns — what to detect and avoid",
    "genres": "Genres — playbook entry points (genres field on other nodes = applies_to edge)",
    "platforms_goals": "Platforms and goals",
    "examples": "Annotated examples (films and reference reels)",
}


def route(node):
    t = node["type"]
    if t == "principle":
        return "principles"
    if t == "anti_pattern":
        return "anti_patterns"
    if t == "genre":
        return "genres"
    if t in ("platform", "goal"):
        return "platforms_goals"
    if t == "example":
        return "examples"
    if node["id"] in VISUAL_OVERRIDES:
        return "techniques_color_type_motion"
    domain = node["id"].split(".")[1]
    if domain in SOUND_DOMAINS:
        return "techniques_sound_music"
    if domain in VISUAL_DOMAINS:
        return "techniques_color_type_motion"
    return "techniques_story_pacing"


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def dedupe(seq):
    seen, out = set(), []
    for x in seq:
        key = yaml.safe_dump(x, sort_keys=True) if isinstance(x, (dict, list)) else x
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


def dedupe_sources(sources):
    seen, out = set(), []
    for s in sources:
        key = (s.get("url"), s.get("locator"))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def ordered(node, fields):
    out = {k: node[k] for k in fields if k in node}
    out.update({k: v for k, v in node.items() if k not in out})
    return out


# ───────────────────────── capabilities ─────────────────────────
def build_capabilities(plan):
    caps = load_yaml(DRAFTS / "capabilities.yaml")["capabilities"]
    by_id = {c["id"]: c for c in caps}
    relabelled = collections.defaultdict(list)
    for cid, patch in (plan.get("cap_patches") or {}).items():
        if cid not in by_id:
            sys.exit(f"cap_patches: unknown capability {cid}")
        cap = by_id[cid]
        for k, v in patch.items():
            if k == "pinned":
                cap["requires_pinned_ffmpeg"] = bool(v)
            else:
                if k == "renderer_owner" and v != cap.get("renderer_owner"):
                    relabelled[f"{cap.get('renderer_owner')}->{v}"].append(cid)
                cap[k] = v
    for c in caps:
        c.setdefault("requires_pinned_ffmpeg", False)
    # insert new caps after the last entry of their category
    for new in plan.get("new_caps") or []:
        if new["id"] in by_id:
            sys.exit(f"new_caps: duplicate id {new['id']}")
        new = dict(new)
        new.setdefault("requires_pinned_ffmpeg", False)
        idx = max((i for i, c in enumerate(caps) if c["category"] == new["category"]), default=len(caps) - 1)
        caps.insert(idx + 1, new)
        by_id[new["id"]] = new
    caps = [ordered(c, CAP_FIELDS) for c in caps]
    return caps, relabelled


def resolve_cap_map(plan, cap_ids):
    cmap = {}
    for old, new in (plan.get("cap_id_map") or {}).items():
        targets = new if isinstance(new, list) else [new]
        for t in targets:
            if t not in cap_ids:
                sys.exit(f"cap_id_map: {old} -> {t} does not exist in catalog")
        cmap[old] = new
    return cmap


# ───────────────────────── graph ─────────────────────────
def merge_into(base, others, override, from_new):
    """Merge `others` into `base` (in place). Stronger evidence wins parameter clashes."""
    group = [base] + others
    strongest = sorted(group, key=lambda n: -EVIDENCE_RANK.get(n.get("evidence_level"), 0))
    params = {}
    for n in strongest:
        for k, v in (n.get("parameters") or {}).items():
            params.setdefault(k, v)
    base["parameters"] = params
    base["evidence_level"] = strongest[0]["evidence_level"]
    base["confidence"] = max((n.get("confidence", "low") for n in group), key=lambda c: CONFIDENCE_RANK.get(c, 0))
    list_fields = ["genres", "goals", "uses_capabilities", "conflicts_with", "requires", "drafts"]
    if not from_new:  # a hand-written canonical node keeps its own steps
        list_fields.insert(0, "how")
    for fld in list_fields:
        merged = []
        for n in group:
            merged.extend(n.get(fld) or [])
        base[fld] = dedupe(merged)
    if not from_new:
        for fld in ["when_to_use", "avoid_when"]:
            parts = [n.get(fld) for n in group if n.get(fld)]
            base[fld] = " | ".join(dedupe(parts))
    srcs = []
    for n in group:
        srcs.extend(n.get("sources") or [])
    base["sources"] = dedupe_sources(srcs)
    base["merged_from"] = dedupe((base.get("merged_from") or []) + [n["id"] for n in others])
    for k in ("name", "summary", "when_to_use", "avoid_when", "how"):
        if k in override:
            base[k] = override[k]
    if "parameters_add" in override:
        base["parameters"].update(override["parameters_add"])


ID_TOKEN = re.compile(r"\b(?:principle|tech|anti|goal|genre|platform|example|cap)(?:\.[a-z0-9_]+)+")


def rewrite_text_ids(value, mapping):
    """Recursively replace old ids inside strings (exact token match)."""
    if isinstance(value, str):
        return ID_TOKEN.sub(lambda m: mapping.get(m.group(0), m.group(0)), value)
    if isinstance(value, list):
        return [rewrite_text_ids(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: rewrite_text_ids(v, mapping) for k, v in value.items()}
    return value


def apply_patch(node, patch):
    for k, v in (patch.get("set") or {}).items():
        node[k] = v
    for k, v in (patch.get("add") or {}).items():
        if k == "parameters":
            node.setdefault("parameters", {})
            node["parameters"] = {**(node["parameters"] or {}), **v}
        elif k == "sources":
            node["sources"] = dedupe_sources((node.get("sources") or []) + v)
        else:
            node[k] = dedupe((node.get(k) or []) + v)
    for k, v in (patch.get("remove") or {}).items():
        node[k] = [x for x in node.get(k) or [] if x not in v]


def build_graph(plan, cap_ids, cap_map):
    nodes = {}
    for g in GRAPH_DRAFTS:
        for n in load_yaml(DRAFTS / f"{g}.yaml")["nodes"]:
            if n["id"] in nodes:
                sys.exit(f"duplicate draft id {n['id']}")
            n = dict(n)
            n["drafts"] = [f"drafts/{g}.yaml"]
            nodes[n["id"]] = n
    draft_count = len(nodes)

    new_nodes = {n["id"]: dict(n) for n in plan.get("new_nodes") or []}
    for nid, n in new_nodes.items():
        n.setdefault("drafts", [])
        if nid == "example.testimonial.dearma_wortham":
            n["drafts"] = ["drafts/reference_reels_plan.md"]
        if nid in nodes:
            sys.exit(f"new node collides with draft id {nid}")

    id_map = {}
    groups = 0
    for m in plan.get("merges") or []:
        canon = m["canonical"]
        absorbed = [nodes.pop(a) for a in m["absorb"]]
        from_new = bool(m.get("from_new"))
        if from_new:
            base = new_nodes.pop(canon)
        elif canon in nodes:
            base = nodes.pop(canon)
        else:  # new id built from the first absorbed node
            base = copy.deepcopy(absorbed[0])
            base["id"] = canon
            absorbed_ids = [a["id"] for a in absorbed]
            base["merged_from"] = []
            absorbed = [dict(a) for a in absorbed]
            base_src = absorbed.pop(0)
            base["merged_from"].append(base_src["id"])
            assert base_src["id"] == absorbed_ids[0]
        merge_into(base, absorbed, m, from_new)
        nodes[canon] = base
        for old in base.get("merged_from") or []:
            id_map[old] = canon
        groups += 1
    for nid, n in new_nodes.items():
        nodes[nid] = n

    def remap_node_ref(r):
        return id_map.get(r, r)

    # remap references
    for n in nodes.values():
        for fld in ["genres", "avoid_genres", "goals", "conflicts_with", "requires", "platforms"]:
            if n.get(fld):
                n[fld] = dedupe([remap_node_ref(r) for r in n[fld] if remap_node_ref(r) != n["id"]])
        for t in n.get("techniques") or []:
            t["id"] = remap_node_ref(t["id"])
        caps = []
        for c in n.get("uses_capabilities") or []:
            new = cap_map.get(c, c)
            caps.extend(new if isinstance(new, list) else [new])
        n["uses_capabilities"] = dedupe(caps)

    # rewrite ids mentioned in prose (summary, how, notes, parameter values…), never in urls
    text_map = dict(id_map)
    text_map.update({old: new for old, new in cap_map.items() if isinstance(new, str)})
    for n in nodes.values():
        for k, v in list(n.items()):
            if k not in ("id", "sources", "merged_from", "drafts"):
                n[k] = rewrite_text_ids(v, text_map)

    # patches
    for nid, patch in (plan.get("node_patches") or {}).items():
        if nid not in nodes:
            sys.exit(f"node_patches: unknown node {nid}")
        apply_patch(nodes[nid], patch)
    for nid in plan.get("core_principles") or []:
        nodes[nid]["core"] = True
    for nid, params in (plan.get("platform_params") or {}).items():
        nodes[nid]["parameters"] = {**(nodes[nid].get("parameters") or {}), **params}

    # source_from for new nodes
    for n in nodes.values():
        src_from = n.pop("source_from", None)
        if src_from:
            extra = []
            for ref in src_from:
                extra.extend((nodes[ref].get("sources") or [])[:2])
            n["sources"] = dedupe_sources((n.get("sources") or []) + extra)
        if n["id"].startswith("goal.") or n["id"] == "genre.interview":
            n["sources"] = dedupe_sources(n["sources"] + [
                {"title": "ADR-0027 Expert knowledge system", "url": "docs/adr/0027-expert-knowledge-system-and-learning-loop.md",
                 "locator": "Decision §2 (Goal/Genre node types)"},
                {"title": "Knowledge base schema — canonical IDs", "url": "knowledge/SCHEMA.md", "locator": "Canonical IDs to reuse"},
            ])

    # normalise
    out = {}
    for nid, n in nodes.items():
        for fld in LIST_FIELDS:
            if fld in ("avoid_genres", "enforced_by", "decided_by", "merged_from"):
                continue
            n.setdefault(fld, [])
        n.setdefault("parameters", {})
        n.setdefault("when_to_use", "")
        n.setdefault("avoid_when", "")
        if n.get("parameters") is None:
            n["parameters"] = {}
        for opt in ("avoid_genres", "enforced_by", "decided_by", "merged_from"):
            if opt in n and not n[opt]:
                del n[opt]
        out[nid] = ordered(n, CORE_NODE_FIELDS)
    return out, id_map, groups, draft_count


class Dumper(yaml.SafeDumper):
    pass


def _str_repr(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


Dumper.add_representer(str, _str_repr)


def dump(data, path, header):
    text = yaml.dump(data, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=140, default_flow_style=None)
    path.write_text(header + text)


def main():
    plan = load_yaml(PLAN)
    caps, relabelled = build_capabilities(plan)
    cap_ids = {c["id"] for c in caps}
    if len(cap_ids) != len(caps):
        sys.exit("duplicate capability ids")
    cap_map = resolve_cap_map(plan, cap_ids)
    nodes, id_map, groups, draft_count = build_graph(plan, cap_ids, cap_map)

    GRAPH.mkdir(exist_ok=True)
    dump({"capabilities": caps}, KB / "capabilities.yaml",
         "# GENERATED by knowledge/tools/build_kb.py from knowledge/drafts/capabilities.yaml + tools/merge_plan.yaml.\n"
         "# Do not edit by hand. Schema: knowledge/SCHEMA.md §1 (+ engine owner, engine_tool, requires_pinned_ffmpeg, decided_by).\n"
         "# renderer_owner: ffmpeg | remotion | both | engine | unsupported (see knowledge/README.md).\n")
    by_file = collections.defaultdict(list)
    for n in nodes.values():
        by_file[route(n)].append(n)
    for fname, title in FILES.items():
        items = sorted(by_file.get(fname, []), key=lambda n: (n["type"], n["id"]))
        dump({"nodes": items}, GRAPH / f"{fname}.yaml",
             f"# {title}\n# GENERATED by knowledge/tools/build_kb.py — do not edit by hand. Schema: knowledge/SCHEMA.md §2 + README.\n")
    dump({"nodes": dict(sorted(id_map.items())), "capabilities": dict(sorted(cap_map.items()))}, GRAPH / "id_map.yaml",
         "# Old id → new id. nodes: draft graph ids merged into a canonical node.\n"
         "# capabilities: guessed cap ids used in graph drafts → catalog id(s) in knowledge/capabilities.yaml.\n")

    print(f"capabilities: {len(caps)} (draft 196 + {len(plan.get('new_caps') or [])} new)")
    print("owners:", dict(collections.Counter(c["renderer_owner"] for c in caps)))
    print("relabelled:", {k: len(v) for k, v in relabelled.items()})
    for k, v in relabelled.items():
        print(f"  {k}: {', '.join(v)}")
    print("pinned-ffmpeg caps:", [c["id"] for c in caps if c["requires_pinned_ffmpeg"]])
    print(f"nodes: {len(nodes)} (drafts {draft_count}; merge groups {groups}; absorbed {len(id_map)})")
    print("by file:", {f: len(v) for f, v in sorted(by_file.items())})
    print("by type:", dict(collections.Counter(n["type"] for n in nodes.values())))


if __name__ == "__main__":
    main()
