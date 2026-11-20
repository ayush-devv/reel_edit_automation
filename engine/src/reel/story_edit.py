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


def reorder(story: StoryPlan, fin: FinishPlan, order: list[str]) -> tuple[StoryPlan, FinishPlan, dict]:
    """`order` = the kept item ids in their new order; any id left out is dropped."""
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
    new_story = story.model_copy(update={"items": items, "hook": hook, "hook_options": opts})

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


def summary(meta: dict) -> str | None:
    parts = []
    if meta["dropped"]:
        parts.append(f"dropped {len(meta['dropped'])} line(s)")
    removed = ", ".join(f"{n} {k.replace('_', '-')}" for k, n in meta["removed"].items())
    if removed:
        parts.append(f"removed what was attached to them: {removed}")
    return "; ".join(parts).capitalize() + "." if parts else None
