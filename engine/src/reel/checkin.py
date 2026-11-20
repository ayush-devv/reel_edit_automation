"""Story check-in (roadmap 3a.1): stop after the story pass, show the plan in plain words, ask at most 3 questions.

The run stops before the finish pass and the render are paid for. The questions are built by code from what the
story pass and the tables already hold, with no Claude call and no schema change:
- the Editor's 2nd/3rd hook options ("open with this instead?");
- a kept line whose take is not the one the engine suggested ("use the suggested take?");
- a kept line longer than LONG_LINE_S ("drop it?").
A must-keep line the story left out is a warning, not a question. Answers change only plan/story.json (no finish
plan exists yet); a free-text note is one story revision on the story session. Then the run continues.
"""

from __future__ import annotations

import json
import time

from reel import decide, project
from reel.schemas.plan import KeepItem, StoryPlan
from reel.story_edit import reorder_story
from reel.validate import errors, norm
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

FILE = ("plan", "checkin.json")
MAX_QUESTIONS = 3
LONG_LINE_S = 8.0
NOTE_PROMPT = ("The owner read your story before the finish pass and asks:\n\n\"{note}\"\n\nCurrent read-back:\n{readback}\n\n"
               "Return the complete revised story plan (unchanged where the note doesn't ask for a change).")


class CheckinError(ValueError):
    pass


def _seconds(it: KeepItem, by: dict) -> float:
    a, b = by.get(it.word_start), by.get(it.word_end)
    return round((b.end_us - a.start_us) / 1e6, 1) if a and b else 0.0


def _text(it: KeepItem, by: dict, limit: int = 140) -> str:
    t = " ".join(by[i].text for i in range(it.word_start, it.word_end + 1) if i in by)
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"


def build(ws: Workspace, inp: decide.Inputs) -> dict:
    """Write plan/checkin.json for the current story plan."""
    story = project.load_json_model(StoryPlan, ws.path("plan", "story.json"))
    by = inp.words.by_index()
    lines = [{"id": it.id, "beat": it.beat, "seconds": _seconds(it, by), "text": _text(it, by)} for it in story.items]
    kept = {i for it in story.items for i in range(it.word_start, it.word_end + 1)}
    segs = (json.loads(ws.path("tables", "segments.json").read_text()).get("segments", [])
            if ws.path("tables", "segments.json").exists() else [])
    left = [s for s in segs if not any(w in kept for w in range(s["words"][0], s["words"][1] + 1))]
    left_out = [{"seg_id": s["seg_id"], "seconds": round(s["t1"] - s["t0"], 1), "text": s.get("text", "")[:140]}
                for s in sorted(left, key=lambda s: -(s["t1"] - s["t0"]))[:6]]

    questions: list[dict] = []
    items = {it.id: it for it in story.items}
    for h in sorted(story.hook_options, key=lambda h: h.rank):
        if h.id != story.hook and h.item in items and h.item != story.items[0].id:
            questions.append({"id": f"q{len(questions) + 1}", "kind": "hook", "option": h.id, "item": h.item,
                              "text": f"Open with “{_text(items[h.item], by, 80)}” instead?", "why": h.reason})
            break
    seg_by_id = {s["seg_id"]: s for s in segs}
    takes = json.loads(ws.path("tables", "takes.json").read_text()) if ws.path("tables", "takes.json").exists() else {"groups": []}
    best_of = {g["group"]: next((m["seg_id"] for m in g["members"] if m.get("suggested_rank") == 1), None) for g in takes.get("groups", [])}
    for it in story.items:
        seg = next((s for s in segs if s["clip"] == it.clip and s["words"] == [it.word_start, it.word_end]), None)
        tk = (seg or {}).get("take")
        if not tk or tk.get("suggested_rank") == 1:
            continue
        best = seg_by_id.get(best_of.get(tk["group"]) or "")
        if best and not any(w in kept for w in range(best["words"][0], best["words"][1] + 1)):
            questions.append({"id": f"q{len(questions) + 1}", "kind": "take", "item": it.id, "segment": best["seg_id"],
                              "text": f"Use the engine's suggested take of “{_text(it, by, 60)}” (take {seg_take_no(takes, best['seg_id'])} "
                                      f"of {tk['of']}) instead of take {tk['take']}?", "why": "fewer stumbles or fillers by the engine's take score"})
            break
    for it in sorted(story.items[1:], key=lambda it: -_seconds(it, by)):
        if _seconds(it, by) > LONG_LINE_S and len(questions) < MAX_QUESTIONS:
            questions.append({"id": f"q{len(questions) + 1}", "kind": "drop", "item": it.id,
                              "text": f"Drop this {_seconds(it, by):.0f} s line: “{_text(it, by, 80)}”?", "why": "long lines slow a reel down"})
            break
    warnings = []
    kept_text = norm(" ".join(by[i].text for i in sorted(kept) if i in by))
    for line in (inp.brief.must_keep_lines if inp.brief else []):
        if norm(line) and norm(line) not in kept_text:
            warnings.append(f"The brief's must-keep line “{line}” isn't in the story.")
    hook_item = items.get(next((h.item for h in story.hook_options if h.id == story.hook), ""), story.items[0])
    data = {"status": "open", "created": time.time(), "story_fp": _fp(ws), "summary": story.summary, "genre": story.genre,
            "hook": {"item": hook_item.id, "text": _text(hook_item, by)}, "lines": lines,
            "total_s": round(sum(x["seconds"] for x in lines), 1), "left_out": left_out,
            "questions": questions[:MAX_QUESTIONS], "warnings": warnings}
    atomic_write_json(ws.path(*FILE), data)
    return {"questions": len(data["questions"]), "warnings": len(warnings)}


def seg_take_no(takes: dict, seg_id: str) -> int | None:
    for g in takes.get("groups", []):
        for m in g["members"]:
            if m["seg_id"] == seg_id:
                return m["take"]
    return None


def _fp(ws: Workspace) -> str:
    import hashlib

    return hashlib.sha256(ws.path("plan", "story.json").read_bytes()).hexdigest()[:16]


def load(ws: Workspace) -> dict | None:
    p = ws.path(*FILE)
    return json.loads(p.read_text()) if p.exists() else None


def is_open(ws: Workspace) -> bool:
    c = load(ws)
    return bool(c) and c.get("status") == "open"


def answer(ws: Workspace, inp: decide.Inputs, yes: list[str], note: str | None = None, caller=None) -> dict:
    """Apply the accepted questions (and an optional free-text note: one Claude call), re-validate, approve."""
    c = load(ws)
    if not c or c.get("status") != "open":
        raise CheckinError("there is no open story check-in for this project")
    if c.get("story_fp") != _fp(ws):
        raise CheckinError("the story changed since the check-in was written: run the project again to refresh it")
    qs = {q["id"]: q for q in c["questions"]}
    unknown = [q for q in yes if q not in qs]
    if unknown:
        raise CheckinError(f"unknown question(s): {', '.join(unknown)}")
    story = project.load_json_model(StoryPlan, ws.path("plan", "story.json"))
    by = inp.words.by_index()
    done = []
    for qid in yes:
        q = qs[qid]
        ids = [it.id for it in story.items]
        if q["kind"] == "hook" and q["item"] in ids:
            story, _ = reorder_story(story, [q["item"], *[i for i in ids if i != q["item"]]])
            story = story.model_copy(update={"hook": q["option"]}) if any(h.id == q["option"] and h.item == q["item"] for h in story.hook_options) else story
        elif q["kind"] == "drop" and q["item"] in ids:
            story, _ = reorder_story(story, [i for i in ids if i != q["item"]])
        elif q["kind"] == "take" and q["item"] in ids:
            segs = json.loads(ws.path("tables", "segments.json").read_text()).get("segments", [])
            best = next(s for s in segs if s["seg_id"] == q["segment"])
            a, b = best["words"]
            story = story.model_copy(update={"items": [it.model_copy(update={"clip": best["clip"], "word_start": a, "word_end": b,
                                                                              "first_word": by[a].text, "last_word": by[b].text,
                                                                              "reason": it.reason + " (owner: the suggested take)"})
                                                       if it.id == q["item"] else it for it in story.items]})
        done.append(q["kind"])
    issues = inp.story_issues(story)
    if errors(issues):
        raise CheckinError("the engine's validator refused these answers: " + "; ".join(i.message for i in errors(issues)))
    calls = 0
    if note and note.strip():
        atomic_write_json(ws.path("plan", "story.json"), story.model_dump(mode="json"))
        session = json.loads(ws.path("plan", "sessions.json").read_text()).get("story") if ws.path("plan", "sessions.json").exists() else None
        d = decide.decide(caller or decide.claude_call.call, ws, label="story_checkin",
                          prompt=NOTE_PROMPT.format(note=note.strip(), readback=decide.readback(inp, story)), model=StoryPlan,
                          persona=decide.STORY_PERSONA, effort=decide.STORY_EFFORT, check=inp.story_issues, resume=session)
        story, calls = d.plan, d.calls
        done.append("note")
    atomic_write_json(ws.path("plan", "story.json"), story.model_dump(mode="json"))
    atomic_write_bytes(ws.path("plan", "story_readback.txt"), decide.readback(inp, story).encode())
    c.update(status="approved", approved=time.time(), answers={"yes": yes, "note": note or ""}, applied=done)
    atomic_write_json(ws.path(*FILE), c)
    return {"applied": done, "calls": calls}
