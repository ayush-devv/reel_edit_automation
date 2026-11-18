"""Access to the knowledge base (ADR-0027)."""

from __future__ import annotations

from functools import lru_cache

import yaml

from reel import config


@lru_cache(maxsize=1)
def node_ids() -> frozenset[str]:
    ids: set[str] = set()
    graph = config.KNOWLEDGE_DIR / "graph"
    for f in graph.glob("*.yaml"):
        if f.name == "id_map.yaml":
            continue
        data = yaml.safe_load(f.read_text()) or {}
        for node in data.get("nodes", []) or []:
            if isinstance(node, dict) and "id" in node:
                ids.add(node["id"])
    return frozenset(ids)
