"""Hook preview in two looks (roadmap G1.6): the opening seconds rendered as A (the Editor's choice) and B (another
caption style and a contrasting colour look), so the client picks before the full render.

B costs no Claude call and no plan change: it is chosen here, deterministically, and a brand kit's locks always win.
"""

from __future__ import annotations

from reel import render, tools
from reel.schemas.plan import FinishPlan, StoryPlan
from reel.schemas.timeline import Timeline

# A contrasting look for each look (warm ↔ cool, plain ↔ punchy …)
CONTRAST = {"none": "punchy", "clean": "warm", "warm": "cool", "cool": "warm", "punchy": "film", "film": "punchy", "teal_orange": "clean"}
TAIL_S = 0.5  # the preview runs half a second past the hook's last word


def alternative(fin: FinishPlan, story: StoryPlan, families: dict[str, dict], brand=None) -> tuple[str | None, str | None]:
    """(caption family, look) for B — None where the brand kit locks it (or nothing else fits)."""
    fam_b = None
    if not (brand and brand.caption_family):
        others = [(-int(story.genre in (f.get("for") or [])), k, fid) for k, (fid, f) in enumerate(families.items()) if fid != fin.captions.family]
        fam_b = min(others)[2] if others else None
    look_b = None if (brand and brand.look) else CONTRAST.get(fin.grade.look, "clean")
    return fam_b, look_b


def variant(fin: FinishPlan, family: str | None, look: str | None) -> FinishPlan:
    """B's finish plan: the other caption family (its own default tokens) and/or the other look; everything else equal."""
    upd = {}
    if family:
        upd["captions"] = fin.captions.model_copy(update={"family": family, "tokens": []})
    if look:
        upd["grade"] = fin.grade.model_copy(update={"look": look})
    return fin.model_copy(update=upd)


def hook_end_f(tl: Timeline, story: StoryPlan) -> int:
    first = story.items[0].id if story.items else None
    ends = [c.at_f + c.dur_f for c in tl.video if c.id.startswith("v_") and c.src and c.src.item == first]
    return max(ends) if ends else tl.duration_f


def trim(tl: Timeline, n: int) -> Timeline:
    """The first n frames of a timeline, as a timeline the renderers accept (base clips still back to back)."""
    n = max(1, min(n, tl.duration_f))

    def cut(items, start="at_f", length="dur_f"):
        out = []
        for e in items:
            s = getattr(e, start)
            if s >= n:
                continue
            upd = {}
            if length == "dur_f" and s + e.dur_f > n:
                upd["dur_f"] = n - s
                if getattr(e, "hold_f", 0):
                    upd["hold_f"] = max(0, e.hold_f - (s + e.dur_f - n))
            elif length == "end_f" and e.end_f > n:
                upd["end_f"] = n
            out.append(e.model_copy(update=upd) if upd else e)
        return out

    caps = tl.captions
    if caps:
        pages = [p.model_copy(update={"end_f": min(p.end_f, n), "words": [w.model_copy(update={"end_f": min(w.end_f, n)}) for w in p.words if w.start_f < n]})
                 for p in caps.pages if p.start_f < n]
        caps = caps.model_copy(update={"pages": pages})
    ducking = [d.model_copy(update={"regions_f": [[a, min(b, n)] for a, b in d.regions_f if a < n]}) for d in tl.ducking]
    return tl.model_copy(update={
        "duration_f": n, "video": cut(tl.video), "audio": cut(tl.audio), "captions": caps, "ducking": ducking,
        "transitions": [t for t in tl.transitions if t.at_f + t.frames < n],
        "effects": cut(tl.effects, "start_f", "end_f"), "titles": cut(tl.titles, "start_f", "end_f"),
        "flashes": [f for f in tl.flashes if f.at_f + f.frames < n], "pips": cut(tl.pips, "start_f", "end_f"),
        "graphics": cut(tl.graphics, "start_f", "end_f")})


def choose(ws, option: str) -> dict:
    """Apply the client's pick: B rewrites the finish plan's caption family / look (validated by the next run's
    finish stage); A keeps the plan. preview.json records the choice. Returns preview.json."""
    import json

    from reel.workspace import atomic_write_json

    f = ws.path("export", "preview", "preview.json")
    if not f.exists():
        raise ValueError("no hook preview for this project")
    data = json.loads(f.read_text())
    if option not in data.get("options", {}):
        raise ValueError(f"option {option!r} is not one of {sorted(data.get('options', {}))}")
    plan = data["options"][option].get("plan") or {}
    if plan:
        fin_file = ws.path("plan", "finish.json")
        fin = FinishPlan.model_validate_json(fin_file.read_text())
        atomic_write_json(fin_file, variant(fin, plan.get("caption_family"), plan.get("look")).model_dump(mode="json"))
    data["chosen"] = option
    atomic_write_json(f, data)
    return data


def quick_composite(base, overlay_mov, out) -> None:
    """Base + overlay → a small MP4 to watch (no delivery loudness checks: it's a preview, not a deliverable)."""
    tools.ffmpeg(["-y", "-i", str(base), "-i", str(overlay_mov), "-filter_complex",
                  "[1:v]format=yuva444p10le[ov];[0:v][ov]overlay=0:0:format=auto:alpha=straight:eof_action=pass,format=yuv420p[v]",
                  "-map", "[v]", "-map", "0:a", *render.encode_args(out)])
