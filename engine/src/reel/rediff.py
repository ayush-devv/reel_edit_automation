"""Which overlay frames a revision changed (roadmap G1.5: partial re-render).

Compares the overlay props that produced the current `overlay.mov` (render/overlay.rendered.props.json, written only
after a successful render or splice) with the new props. Returns the frame ranges to re-render, or None for "render
everything" (a global change, no baseline, or so much changed that splicing would not save time).

- Elements with ids (titles, flashes, pips, graphics) match by id; caption pages (no id) match by content.
- An added, removed or changed element marks [start − PAD, end + PAD] (entry/exit animations).
- Closure: anything that overlaps a marked range joins it (graphics avoid each other; captions avoid graphics), and a
  changed caption page pulls in its neighbours (back-to-back pages shape each other's entry and exit).
"""

from __future__ import annotations

import json

PAD_F = 12
GLOBAL_KEYS = ("fps", "width", "height", "duration_f", "faces", "safe", "layer")
CAPTION_GLOBAL = ("family", "tokens", "script", "timing")
ID_LISTS = ("titles", "flashes", "pips", "graphics")
MAX_SHARE = 0.6  # re-rendering more than this share of the reel is not worth a splice


def _key(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


def _span(e: dict) -> tuple[int, int]:
    return int(e.get("start_f", 0)), int(e.get("end_f", e.get("start_f", 0)))


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def changed_elements(old: dict | None, new: dict) -> list[tuple[int, int]] | None:
    """The spans of overlay elements whose content changed (added, removed, edited), with no padding and no closure:
    what a revision actually changed, for the revision evals (3b.3). None = a global change (or no baseline)."""
    if not old or any(_key(old.get(k)) != _key(new.get(k)) for k in GLOBAL_KEYS):
        return None
    oc, nc = old.get("captions") or {}, new.get("captions") or {}
    if any(_key(oc.get(k)) != _key(nc.get(k)) for k in CAPTION_GLOBAL):
        return None
    out: list[tuple[int, int]] = []
    for lst in ID_LISTS:
        o = {e["id"]: e for e in old.get(lst) or []}
        n = {e["id"]: e for e in new.get(lst) or []}
        out += [_span(e) for eid in set(o) | set(n) if _key(o.get(eid)) != _key(n.get(eid)) for e in (o.get(eid), n.get(eid)) if e]
    op, np_ = oc.get("pages") or [], nc.get("pages") or []
    okeys, nkeys = {_key(p) for p in op}, {_key(p) for p in np_}
    out += [_span(p) for p in op if _key(p) not in nkeys] + [_span(p) for p in np_ if _key(p) not in okeys]
    return _merge(out)


def changed_ranges(old: dict | None, new: dict) -> list[tuple[int, int]] | None:
    """Inclusive frame ranges to re-render ([] = nothing changed), or None = render everything."""
    if not old:
        return None
    if any(_key(old.get(k)) != _key(new.get(k)) for k in GLOBAL_KEYS):
        return None
    oc, nc = old.get("captions") or {}, new.get("captions") or {}
    if any(_key(oc.get(k)) != _key(nc.get(k)) for k in CAPTION_GLOBAL):
        return None
    marked: list[tuple[int, int]] = []

    for lst in ID_LISTS:
        o = {e["id"]: e for e in old.get(lst) or []}
        n = {e["id"]: e for e in new.get(lst) or []}
        for eid in set(o) | set(n):
            if _key(o.get(eid)) != _key(n.get(eid)):
                marked += [_span(e) for e in (o.get(eid), n.get(eid)) if e]

    op, np_ = oc.get("pages") or [], nc.get("pages") or []
    okeys, nkeys = {_key(p) for p in op}, {_key(p) for p in np_}
    for pages, other in ((op, nkeys), (np_, okeys)):
        pages = sorted(pages, key=_span)
        for k, p in enumerate(pages):
            if _key(p) not in other:
                a, b = _span(p)
                marked.append((a, b))
                for q in pages[max(0, k - 1):k] + pages[k + 1:k + 2]:  # back-to-back neighbours (touching or nearly)
                    qa, qb = _span(q)
                    if qa - b <= PAD_F and a - qb <= PAD_F:
                        marked.append((qa, qb))

    if not marked:
        return []
    total = int(new.get("duration_f", 0))
    ranges = _merge([(max(0, a - PAD_F), min(total - 1, b + PAD_F)) for a, b in marked])
    items = [_span(e) for lst in ID_LISTS for e in (new.get(lst) or [])]
    pages = [_span(p) for p in np_]
    # Closure over titles, flashes, pips and graphics until nothing new joins (each joins padded: its animations).
    while True:
        grown = _merge(ranges + [(max(0, a - PAD_F), min(total - 1, b + PAD_F)) for a, b in items if any(a <= rb and b >= ra for ra, rb in ranges)])
        if grown == ranges:
            break
        ranges = grown
    # Caption pages under those ranges join padded in ONE pass. Iterating them chain-reacted through back-to-back
    # pages (each padded joiner reached the next page) and turned a one-page change into a full re-render
    # (found by the revision evals, roadmap 3b.3). A changed page's own neighbours are already marked above.
    ranges = _merge(ranges + [(max(0, a - PAD_F), min(total - 1, b + PAD_F)) for a, b in pages if any(a <= rb and b >= ra for ra, rb in ranges)])
    if sum(b - a + 1 for a, b in ranges) > MAX_SHARE * total:
        return None
    return ranges
