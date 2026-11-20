"""B-roll by meaning (roadmap G2.3, asset-library phase D scoped down).

Ranks the b-roll pool against each kept line so the finish Editor sees the best cutaways per line first, with
near-duplicates folded together and clips already used by sibling reels (Clip Factory) pushed down.

**Text only, by licence.** `ml_indexing_ok` is true only for owned / CC0 / CC BY / MIT assets
(assets/licenses/registry.yaml); Pexels, Pixabay and client footage are unset, so nothing is computed from those
files. What is ranked is text the engine already holds: the Claude-written description, name, shot, mood and tags.

**Lexical by default.** Okapi BM25 in memory: the pool is tens to a few hundred clips per project, so an on-disk
index (SQLite/FTS5) would add a file and no speed. An optional `embed` function (a local multilingual sentence
model, once its licence and Hinglish quality are verified; roadmap G2.3) adds a cosine term; without it, Hinglish
lines match English descriptions only through shared words, which is the known limit.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable, Iterable

PER_ITEM = 3  # cutaways offered per kept line
SHOW_ALL_UNDER = 12  # small pools are shown whole (ranked), so nothing useful is hidden
MAX_MENU = 24
NEAR_DUPLICATE = 0.9  # cosine of description term vectors (or embeddings)
BATCH_PENALTY = 0.5  # score multiplier for a clip a sibling reel already uses
K1, B = 1.5, 0.75
STOP = set("""a an the and or but of to in on at for with from by is are was were be been it this that these those
i you he she we they me my your our their his her its as so if then than too very just not no do does did have has had
can will would should could about into over under up down out off again more most some any all each other such only own
same here there when where why how what which who whom ke ki ka ko se me hai hain tha thi the aur bhi toh to ye yeh woh wo""".split())

Embed = Callable[[list[str]], list[list[float]]]


def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[\w']+", (text or "").casefold()):
        t = t.strip("'")
        if len(t) < 2 or t in STOP or t.isdigit():
            continue
        if len(t) > 4 and t.endswith("ies"):
            t = t[:-3] + "y"
        elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def doc_text(meta: dict) -> str:
    parts = [meta.get("description", ""), meta.get("name", ""), meta.get("shot", ""), meta.get("motion", ""), meta.get("mood", ""),
             " ".join(meta.get("tags", []) or []), meta.get("subject", "")]
    return " ".join(p for p in parts if p)


class BM25:
    def __init__(self, docs: dict[str, str]):
        self.tf = {k: Counter(tokens(v)) for k, v in docs.items()}
        self.len = {k: sum(c.values()) for k, c in self.tf.items()}
        n = len(docs)
        self.avg = (sum(self.len.values()) / n) if n else 0.0
        df = Counter(t for c in self.tf.values() for t in c)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> dict[str, float]:
        q = set(tokens(query))
        out = {}
        for k, c in self.tf.items():
            s = 0.0
            for t in q & c.keys():
                f = c[t]
                s += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[k] / (self.avg or 1)))
            out[k] = s
        return out


def cosine(a: Counter | list[float], b: Counter | list[float]) -> float:
    if isinstance(a, Counter):
        dot = sum(a[t] * b.get(t, 0) for t in a)
        na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    else:
        dot = sum(x * y for x, y in zip(a, b))
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def near_duplicates(pool: dict[str, dict], threshold: float = NEAR_DUPLICATE) -> list[tuple[str, str, float]]:
    """Pairs of clips whose descriptions say nearly the same thing."""
    vec = {k: Counter(tokens(doc_text(m))) for k, m in pool.items()}
    ids = sorted(vec)
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            c = cosine(vec[a], vec[b])
            if c >= threshold:
                out.append((a, b, round(c, 3)))
    return out


def rank_broll(pool: dict[str, dict], lines: list[tuple[str, str]], *, batch_used: Iterable[str] = (), embed: Embed | None = None,
               per_item: int = PER_ITEM) -> list[dict]:
    """The b-roll menu in order: each clip with the kept lines it suits best (`for`), its best score and whether a
    sibling reel already uses it. Near-duplicates of a better-ranked clip are folded into it (`same_as`)."""
    if not pool:
        return []
    bm = BM25({k: doc_text(m) for k, m in pool.items()})
    emb_docs = dict(zip(pool, embed([doc_text(m) for m in pool.values()]))) if embed else {}
    emb_lines = dict(zip((i for i, _ in lines), embed([t for _, t in lines]))) if embed and lines else {}
    used = set(batch_used)
    best: dict[str, float] = {k: 0.0 for k in pool}
    suits: dict[str, list[str]] = {k: [] for k in pool}
    for item_id, text in lines:
        s = bm.scores(text)
        top = max(s.values(), default=0.0) or 1.0
        combined = {k: s[k] / top + (cosine(emb_lines[item_id], emb_docs[k]) if embed else 0.0) for k in pool}
        for k in pool:
            if k in used:
                combined[k] *= BATCH_PENALTY
        for k in sorted(combined, key=lambda x: -combined[x])[:per_item]:
            if combined[k] > 0:
                suits[k].append(item_id)
                best[k] = max(best[k], combined[k])
    order = sorted(pool, key=lambda k: (-best[k], k))
    dup_of: dict[str, str] = {}
    vec = {k: Counter(tokens(doc_text(pool[k]))) for k in pool}
    kept: list[str] = []
    for k in order:
        twin = next((x for x in kept if cosine(vec[k], vec[x]) >= NEAR_DUPLICATE), None)
        if twin:
            dup_of[k] = twin
        kept.append(k)
    rows = [{"id": k, "for": suits[k], "score": round(best[k], 3), "batch_used": k in used, "same_as": dup_of.get(k)} for k in order]
    # Never hide the pool: matched clips first, then the rest, capped. A Hindi (Devanagari) or Hinglish line shares
    # few or no words with English descriptions, so "only what matched" could leave the Editor an empty menu.
    return rows[:max(MAX_MENU, SHOW_ALL_UNDER)]
