"""Selects: group repeated lines into takes and describe each take's delivery (ADR-0016).

The engine only *suggests* a ranking; Claude chooses takes in the story pass.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from reel.schemas.perception import SegmentTable, WordTable

SIMILAR = 0.6
MIN_TOKENS = 3


def _tokens(text_words: list[str]) -> list[str]:
    return [t for t in (re.sub(r"[^\wऀ-ॿ]", "", w.casefold()) for w in text_words) if t]


def find_takes(words: WordTable, segments: SegmentTable, prosody: list[dict] | None = None) -> dict:
    by = words.by_index()
    stats = {p["seg_id"]: p for p in (prosody or [])}
    segs = segments.segments
    toks = {s.seg_id: _tokens([by[i].text for i in range(s.word_start, s.word_end + 1) if not by[i].filler]) for s in segs}

    # union-find over similar segments
    parent = {s.seg_id: s.seg_id for s in segs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a_i, a in enumerate(segs):
        ta = toks[a.seg_id]
        if len(ta) < MIN_TOKENS:
            continue
        for b in segs[a_i + 1:]:
            tb = toks[b.seg_id]
            if len(tb) < MIN_TOKENS:
                continue
            if SequenceMatcher(None, ta, tb).ratio() >= SIMILAR:
                parent[find(b.seg_id)] = find(a.seg_id)

    groups: dict[str, list[str]] = {}
    for s in segs:
        groups.setdefault(find(s.seg_id), []).append(s.seg_id)
    multi = [m for m in groups.values() if len(m) > 1]
    multi.sort(key=lambda m: [s.seg_id for s in segs].index(m[0]))

    seg_by = {s.seg_id: s for s in segs}
    out_groups, seg_take = [], {}
    for g, members in enumerate(multi, 1):
        gid = f"T{g:02d}"
        rows = []
        for order, sid in enumerate(members):
            s = seg_by[sid]
            ws = [by[i] for i in range(s.word_start, s.word_end + 1)]
            t = toks[sid]
            flags = []
            if any(a == b for a, b in zip(t, t[1:])):
                flags.append("stumble")  # repeated word
            if not ws[-1].text.endswith((".", "?", "!", "।")):
                flags.append("unfinished")
            if any(w.filler for w in ws):
                flags.append("filler")
            if any(w.low_conf for w in ws):
                flags.append("low_confidence")
            if len(t) < 0.7 * max(len(toks[m]) for m in members):
                flags.append("restart")  # noticeably shorter than the fullest take
            st = stats.get(sid, {})
            conf = st.get("asr_conf", sum(w.prob for w in ws) / len(ws))
            score = (0.4 * conf + 0.2 * (1 - min(1, sum(w.filler for w in ws) / max(1, len(ws))))
                     + 0.2 * ("unfinished" not in flags) + 0.1 * ("restart" not in flags and "stumble" not in flags)
                     + 0.1 * (order / max(1, len(members) - 1)))  # later takes are usually the keeper
            rows.append({"seg_id": sid, "take": order + 1, "flags": flags, "score": round(score, 3),
                         "words_per_s": st.get("words_per_s"), "loudness_db": st.get("loudness_db"), "asr_conf": round(conf, 3)})
        for rank, r in enumerate(sorted(rows, key=lambda r: -r["score"]), 1):
            r["suggested_rank"] = rank
        for r in rows:
            seg_take[r["seg_id"]] = {"group": gid, "take": r["take"], "of": len(rows), "suggested_rank": r["suggested_rank"]}
        out_groups.append({"group": gid, "members": rows})
    return {"groups": out_groups, "by_segment": seg_take}
