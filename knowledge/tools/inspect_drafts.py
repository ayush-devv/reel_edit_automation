"""Inspect draft YAML files: counts, field usage, id lists, referenced capability ids.

Usage: uv run --with pyyaml python knowledge/tools/inspect_drafts.py [section]
"""
import collections
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / "drafts"
GRAPHS = ["graph_editing_theory", "graph_shortform_craft", "graph_sound_music", "graph_color_type_motion"]


def load(name):
    with open(D / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def main():
    section = sys.argv[1] if len(sys.argv) > 1 else "summary"
    caps = load("capabilities")
    cap_list = caps["capabilities"]
    cap_ids = {c["id"] for c in cap_list}
    if section == "summary":
        print("top keys caps:", list(caps.keys()))
        print("caps:", len(cap_list), "unique:", len(cap_ids))
        print("owners:", collections.Counter(c.get("renderer_owner") for c in cap_list))
        print("cat:", collections.Counter(c.get("category") for c in cap_list))
        fields = collections.Counter(k for c in cap_list for k in c)
        print("cap fields:", fields)
        for g in GRAPHS:
            data = load(g)
            nodes = data["nodes"]
            print("==", g, "top keys", list(data.keys()), "nodes", len(nodes))
            print("  types", collections.Counter(n.get("type") for n in nodes))
            print("  ev", collections.Counter(n.get("evidence_level") for n in nodes))
            print("  fields", dict(collections.Counter(k for n in nodes for k in n)))
    elif section == "caps":
        for c in cap_list:
            print(c["id"], "|", c.get("renderer_owner"), "|", c["name"], "|", (c.get("notes") or "")[:110])
    elif section == "ids":
        for g in GRAPHS:
            for n in load(g)["nodes"]:
                print(g.split("_", 1)[1][:6], n["id"], "|", n.get("type"), "|", n.get("name"), "|", n.get("evidence_level"))
    elif section == "refs":
        missing = collections.Counter()
        where = collections.defaultdict(set)
        for g in GRAPHS:
            for n in load(g)["nodes"]:
                for r in n.get("uses_capabilities") or []:
                    if r not in cap_ids:
                        missing[r] += 1
                        where[r].add(g.split("_", 1)[1][:6])
        print("missing cap refs:", len(missing))
        for r, k in sorted(missing.items()):
            print(r, k, sorted(where[r]))
    elif section == "noderefs":
        all_ids = set()
        for g in GRAPHS:
            all_ids |= {n["id"] for n in load(g)["nodes"]}
        miss = collections.Counter()
        for g in GRAPHS:
            for n in load(g)["nodes"]:
                for fld in ("genres", "goals", "conflicts_with", "requires"):
                    for r in n.get(fld) or []:
                        if r not in all_ids:
                            miss[(fld, r)] += 1
        for (fld, r), k in sorted(miss.items()):
            print(fld, r, k)
    elif section == "similar":
        import re
        stop = set("the a an and or of to in on for with is it as at by be that this from are not but its it's into than so".split())
        nodes = []
        for g in GRAPHS:
            for n in load(g)["nodes"]:
                toks = set(re.findall(r"[a-z]+", (n["name"] + " " + n["summary"]).lower())) - stop
                nodes.append((g[6:12], n["id"], toks))
        pairs = []
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                inter = len(a[2] & b[2])
                score = inter / max(1, min(len(a[2]), len(b[2])))
                if score > 0.33 and inter >= 5:
                    pairs.append((round(score, 2), a[0], a[1], b[0], b[1]))
        for p in sorted(pairs, reverse=True)[:70]:
            print(*p)
    elif section.startswith("brief:"):
        wanted = section.split(":", 1)[1].split(",")
        for g in GRAPHS:
            for n in load(g)["nodes"]:
                if n["id"] in wanted:
                    print(f"## {n['id']} [{g[6:12]}] ev={n.get('evidence_level')}/{n.get('confidence')}")
                    print("  S:", n.get("summary"))
                    print("  P:", n.get("parameters"))
                    print("  W:", n.get("when_to_use"), "| AVOID:", n.get("avoid_when"))
                    print("  G:", n.get("genres"), "C:", n.get("conflicts_with"), "R:", n.get("requires"))
                    print("  SRC:", [s.get("title") for s in n.get("sources") or []])
    elif section.startswith("node:"):
        target = section.split(":", 1)[1]
        for g in GRAPHS:
            for n in load(g)["nodes"]:
                if target in n["id"]:
                    print("#", g)
                    print(yaml.safe_dump(n, sort_keys=False, allow_unicode=True, width=140))


if __name__ == "__main__":
    main()
