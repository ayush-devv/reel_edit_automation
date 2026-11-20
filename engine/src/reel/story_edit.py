"""Story-line edits by hand (UI plan C4, roadmap G2.4): drop or reorder the kept lines without asking the Editor.

Finish elements are bound to story item ids (punch-ins, SFX, b-roll, effects, graphics, holds, speeds,
transitions). Dropping a line orphans them, so code drops them too and says how many; a reorder keeps every binding.
Whole-reel graphics (progress bar, logo) move to the new first item. The result still goes through
`validate_story` (with a Clip Factory window) and `validate_finish`; when the finish no longer fits (for example a
CTA card that must sit on the last line), the caller refuses and suggests asking the Editor instead.
"""

from __future__ import annotations

from reel.schemas.plan import FinishPlan, StoryPlan

WHOLE_REEL_GRAPHICS = {"progress_bar", "logo_watermark"}


class StoryEditError(ValueError):
    pass


def reorder_story(story: StoryPlan, order: list[str]) -> tuple[StoryPlan, list[str]]:
    """The story half of `reorder` (no finish plan yet, e.g. at the story check-in): new order, hook follows the opener."""
    ids = [it.id for it in story.items]
    if not order:
        raise StoryEditError("keep at least one line")
    if len(set(order)) != len(order):
        raise StoryEditError("a line appears twice in the new order")
    unknown = [i for i in order if i not in ids]
    if unknown:
        raise StoryEditError(f"unknown line id(s): {', '.join(unknown)}")
    by = {it.id: it for it in story.items}
    items = [by[i] for i in order]
    keep = set(order)
    dropped = [i for i in ids if i not in keep]
    first = items[0].id
    chosen = next((h for h in story.hook_options if h.id == story.hook), None)
    opts = [h for h in story.hook_options if h.item in keep]
    if chosen is None or chosen.item != first:
        same = next((h for h in opts if h.item == first), None)
        if same is not None:
            hook = same.id
        else:
            hook = chosen.id if chosen else "h_manual"
            opts = [h for h in opts if h.id != hook] + [(chosen.model_copy(update={"item": first, "reason": "Owner reordered the lines."}) if chosen
                                                          else type(story.hook_options[0])(id=hook, item=first, rank=1, reason="Owner reordered the lines."))]
    else:
        hook = chosen.id
    return story.model_copy(update={"items": items, "hook": hook, "hook_options": opts}), dropped


def reorder(story: StoryPlan, fin: FinishPlan, order: list[str]) -> tuple[StoryPlan, FinishPlan, dict]:
    """`order` = the kept item ids in their new order; any id left out is dropped."""
    new_story, dropped = reorder_story(story, order)
    items = new_story.items
    keep = set(order)
    first = items[0].id

    kept_words = {w for it in items for w in range(it.word_start, it.word_end + 1)}
    counts: dict[str, int] = {}

    def keep_bound(name: str, elems: list, field: str = "item") -> list:
        out = [e for e in elems if getattr(e, field) in keep]
        if len(out) != len(elems):
            counts[name] = len(elems) - len(out)
        return out

    graphics = []
    for g in fin.graphics:
        if g.kind.value in WHOLE_REEL_GRAPHICS:
            graphics.append(g.model_copy(update={"item": first}) if g.item != first else g)
        elif g.item in keep:
            graphics.append(g)
        else:
            counts["graphics"] = counts.get("graphics", 0) + 1
    last = items[-1].id
    transitions = [t for t in fin.transitions if t.after_item in keep and t.after_item != last]
    if len(transitions) != len(fin.transitions):
        counts["transitions"] = len(fin.transitions) - len(transitions)
    emphasis = [w for w in fin.captions.emphasis_words if w in kept_words]
    new_fin = fin.model_copy(update={
        "punch_ins": keep_bound("punch_ins", fin.punch_ins), "speeds": keep_bound("speeds", fin.speeds),
        "holds": keep_bound("holds", fin.holds), "sfx": keep_bound("sfx", fin.sfx), "broll": keep_bound("broll", fin.broll),
        "effects": keep_bound("effects", fin.effects), "graphics": graphics, "transitions": transitions,
        "captions": fin.captions.model_copy(update={"emphasis_words": emphasis}),
    })
    return new_story, new_fin, {"dropped": dropped, "removed": counts}


def cut_words(story: StoryPlan, fin: FinishPlan, item_id: str, remove: list[list[int]], words) -> tuple[StoryPlan, FinishPlan, dict]:
    """3a.3: remove word ranges (global indices, inclusive) from one kept line. The line splits around them; the first
    part keeps the line's id (so the hook and whole-reel graphics stay bound), later parts get b, c… Finish elements
    follow the part that holds their words; one that spans a removed word is dropped and counted."""
    by = words.by_index()
    it = next((x for x in story.items if x.id == item_id), None)
    if it is None:
        raise StoryEditError(f"unknown line id: {item_id}")
    gone: set[int] = set()
    for r in remove:
        if len(r) != 2 or r[0] > r[1]:
            raise StoryEditError("each removal is [first word, last word]")
        if r[0] < it.word_start or r[1] > it.word_end:
            raise StoryEditError(f"words {r[0]}–{r[1]} are not all in line {item_id} ({it.word_start}–{it.word_end})")
        gone |= set(range(r[0], r[1] + 1))
    keep = [i for i in range(it.word_start, it.word_end + 1) if i not in gone]
    if not keep:
        raise StoryEditError("that removes the whole line: drop the line instead")
    parts: list[tuple[int, int]] = []
    for i in keep:
        if parts and i == parts[-1][1] + 1:
            parts[-1] = (parts[-1][0], i)
        else:
            parts.append((i, i))
    taken = {x.id for x in story.items}
    ids = [item_id]
    for n in range(1, len(parts)):
        sid = item_id + "bcdefghijklmnopqrstuvwxyz"[n - 1]
        while sid in taken:
            sid += "x"
        ids.append(sid)
        taken.add(sid)
    new_items = [it.model_copy(update={"id": pid, "word_start": a, "word_end": b, "first_word": by[a].text, "last_word": by[b].text})
                 for pid, (a, b) in zip(ids, parts)]
    pos = story.items.index(it)
    new_story = story.model_copy(update={"items": [*story.items[:pos], *new_items, *story.items[pos + 1:]]})

    def part_of(w: int) -> str | None:
        return next((pid for pid, (a, b) in zip(ids, parts) if a <= w <= b), None)

    counts: dict[str, int] = {}

    def rebind(name: str, elems: list, lo: str, hi: str | None = None) -> list:
        out = []
        for e in elems:
            if e.item != item_id:
                out.append(e)
                continue
            p1 = part_of(getattr(e, lo))
            p2 = part_of(getattr(e, hi)) if hi else p1
            if p1 and p1 == p2:
                out.append(e.model_copy(update={"item": p1}))
            else:
                counts[name] = counts.get(name, 0) + 1
        return out

    sfx = []
    for c in fin.sfx:
        if c.item != item_id:
            sfx.append(c)
        elif c.anchor.value == "cut_after_item":
            sfx.append(c.model_copy(update={"item": ids[-1]}))
        elif part_of(c.word):
            sfx.append(c.model_copy(update={"item": part_of(c.word)}))
        else:
            counts["sfx"] = counts.get("sfx", 0) + 1
    new_fin = fin.model_copy(update={
        "punch_ins": rebind("punch_ins", fin.punch_ins, "at_word"),
        "broll": rebind("broll", fin.broll, "from_word", "to_word"),
        "effects": rebind("effects", fin.effects, "from_word", "to_word"),
        # whole-reel graphics keep their item: the first part keeps the line's id
        "graphics": [g for g in fin.graphics if g.kind.value in WHOLE_REEL_GRAPHICS]
        + rebind("graphics", [g for g in fin.graphics if g.kind.value not in WHOLE_REEL_GRAPHICS], "from_word", "to_word"),
        "sfx": sfx,
        "holds": [h.model_copy(update={"item": ids[-1]}) if h.item == item_id else h for h in fin.holds],
        "transitions": [t.model_copy(update={"after_item": ids[-1]}) if t.after_item == item_id else t for t in fin.transitions],
        "captions": fin.captions.model_copy(update={"emphasis_words": [w for w in fin.captions.emphasis_words if w not in gone]}),
    })
    return new_story, new_fin, {"dropped": [], "removed": counts, "words_removed": len(gone), "parts": len(parts)}


def summary(meta: dict) -> str | None:
    parts = []
    if meta.get("words_removed"):
        parts.append(f"cut {meta['words_removed']} word(s)" + (f", the line is now {meta['parts']} parts" if meta.get("parts", 1) > 1 else ""))
    if meta["dropped"]:
        parts.append(f"dropped {len(meta['dropped'])} line(s)")
    removed = ", ".join(f"{n} {k.replace('_', '-')}" for k, n in meta["removed"].items())
    if removed:
        parts.append(f"removed what was attached to them: {removed}")
    return "; ".join(parts).capitalize() + "." if parts else None
