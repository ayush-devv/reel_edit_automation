"""Editor decision calls: story pass, finish pass, revisions (ADR-0016, ADR-0019, ADR-0030).

Each pass is one headless Claude Code session that reads workspace files and returns a plan
as structured output. The engine validates it; on errors it resumes the same session with
the issue list (code, path, message, fix) — at most MAX_RETRIES times — and fails the stage
with plan/<pass>_issues.json if the plan still does not validate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ValidationError

from reel import assets, claude_call, knowledge, library, project
from reel import brief as brief_mod
from reel.compile import ClipInfo, dry_run
from reel.schemas.perception import WordTable
from reel.schemas.plan import FinishPlan, Revision, StoryPlan
from reel.validate import Issue, apply_story_patch, errors, validate_finish, validate_story
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

PERSONAS = Path(__file__).parent / "personas"
STORY_PERSONA = PERSONAS / "editor_story.md"
FINISH_PERSONA = PERSONAS / "editor_finish.md"
MAX_RETRIES = 2
STORY_EFFORT = "high"
FINISH_EFFORT = "medium"

# What the step-5 renderer can draw (render.unsupported rejects the rest). Grows in steps 6–7.
RENDERABLE_TRANSITIONS = {"cut", "flash", "zoom", "whip", "blur", "dip_to_black", "dip_to_white", "glitch"}

Caller = Callable[..., claude_call.CallResult]


class DecisionError(RuntimeError):
    pass


@dataclass
class Inputs:
    ws: Workspace
    words: WordTable
    clips: dict[str, ClipInfo]
    fps: Fraction
    idx: assets.Indexes
    kids: frozenset[str]
    edges: dict[int, tuple[int, int]] | None
    brief: brief_mod.Brief | None
    brand: brief_mod.Brand | None
    vad: dict[str, list[list[int]]] | None = None
    scenes: dict[str, list[int]] | None = None

    @property
    def source_s(self) -> float:
        return sum(c.duration_us for c in self.clips.values()) / 1e6


def load_inputs(ws: Workspace, brief_path: str | None = None, brand_path: str | None = None) -> Inputs:
    return Inputs(ws=ws, words=project.word_table(ws), clips=project.clip_infos(ws), fps=project.project_fps(ws),
                  idx=project.indexes(ws), kids=knowledge.node_ids(), edges=project.edges(ws),
                  brief=brief_mod.load_brief(brief_path), brand=brief_mod.load_brand(brand_path),
                  vad=project.vad_speech(ws), scenes=project.scene_cuts(ws))


def all_required(node):
    """Every property of every object is required in what Claude must return: a field with a default is
    optional in pydantic's schema, and a revision that omits it would silently reset it (graphics, effects,
    holds … dropped). Defaults stay on the models only to load plans written before a field existed."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"])
            for prop in node["properties"].values():
                prop.pop("default", None)
        for v in node.values():
            all_required(v)
    elif isinstance(node, list):
        for v in node:
            all_required(v)
    return node


def schema(model: type[BaseModel]) -> dict:
    return all_required(model.model_json_schema())


# ------------------------------------------------------------------ context packs


def effective_target(brief: brief_mod.Brief | None, source_s: float) -> tuple[float, float]:
    lo, hi = brief.target_length_s if brief else (15.0, 60.0)
    if source_s < lo:  # short footage: the brief's range is unreachable, aim for a tight cut of what exists
        return round(source_s * 0.5, 1), round(source_s, 1)
    return lo, min(hi, source_s)


def story_pack(inp: Inputs) -> str:
    lo, hi = effective_target(inp.brief, inp.source_s)
    b = inp.brief
    lines = ["# Brief", ""]
    lines.append(json.dumps(b.model_dump(exclude_none=True), indent=1, ensure_ascii=False) if b else "No client brief: make the strongest reel the footage allows.")
    if inp.brand:
        lines += ["", "# Brand kit", "", json.dumps(inp.brand.model_dump(exclude_none=True), indent=1, ensure_ascii=False)]
    lines += ["", "# Length", "",
              f"Source footage: {inp.source_s:.1f} s in {len(inp.clips)} clip(s). Target for this reel: {lo:.0f}–{hi:.0f} s "
              f"(brief target capped to the footage). Length is a goal, not a rule: a tight reel beats a padded one.", ""]
    ref = inp.ws.path("context", "reference_style.md")
    if ref.exists():
        lines += [ref.read_text(), ""]
    lines.append(knowledge.story_context(b.genre_hint if b else None))
    lines.append(knowledge.library_pointer())
    return "\n".join(lines)


def _library(name: str, items: dict[str, dict], fields: tuple[str, ...]) -> list[str]:
    if not items:
        return [f"## {name}", "", "Empty — use none.", ""]
    return [f"## {name}", "", *(f"- `{k}` " + ", ".join(f"{f}={v[f]}" for f in fields if f in v) for k, v in items.items()), ""]


def finish_pack(inp: Inputs, story: StoryPlan) -> str:
    lines = ["# What the renderer can do in this build", "",
             "- Colour: pick a look + strength (0.3–0.6 typical; `none` keeps the corrected footage).",
             "- Speed: 0.25–4× on items with no speech only (validator rejects speech); `ramp_to` eases the speed to a second value by the item's end (a speed ramp; 0 = constant).",
             "- Holds (`holds`): freeze an item's last frame for 6–45 frames — lets a punchline land, or ends the reel on a clean frame (sound stops under it; music carries on).",
             "- Beat pulse (`beat_pulse` 0.02–0.06, needs music): a short zoom pulse on every downbeat — energetic/music-led reels only; 0 for calm or talky ones. "
             "The engine already starts the music so the most cuts land on beats.",
             "- Music: bed from the library (starts on a beat at the first cut, ducked under speech), or none.",
             "- Transitions: hard cut (default, nothing to add); `flash`, `zoom`, `whip`, `blur`, `dip_to_black`, `dip_to_white` (bright reset), `glitch` (RGB split + noise; tech/energy) — 2–15 frames, centred on the cut. Use rarely, on a real beat change.",
             "- Hook title: a short on-screen title over the opening line (≤ 7 words, ≤ 42 chars), or \"\" for none; style `card` or `behind` (behind the speaker's head — needs a clearly visible person).",
             "- Punch-ins: yes (scale 1.0–2.0, instant or ramped).",
             "- Texture (whole reel, in `grade`): `grain` 0–0.6 (0.15–0.3 = filmic texture), `vignette` 0–0.7 (darker corners, eye to centre). 0 = off.",
             "- Footage effects (`effects`, on a word window inside one item, intensity 0–1): `shake` (decaying camera shake, ≤ 1.5 s — impact or punchline), "
             "`rgb_split` (≤ 0.7 s — glitchy/tech energy), `exposure_pulse` (bright hit peaking on the first word — a beat or reveal), "
             "`light_leak` (warm wash, ≤ 3.5 s — nostalgic, dreamy, a soft reveal). Accents only: 0–3 per reel is typical, ≤ 6.",
             "- Pauses inside lines were already tightened in the story pass (jump cuts); a punch-in on the shot after a jump cut hides the jump.",
             "- Motion graphics (`graphics`, on a word window; text is read in a glance — keep it short):",
             "  - `emoji_pop` (one emoji; upper_left | upper_right | beside_face) — a reaction on a punchline, 0–3 per reel;",
             "  - `keyword_card` (1–4 words; style pill | under | marker | box | plain; upper | center) — the one idea of a beat, not a caption copy;",
             "  - `lower_third` (\"Name · Role\"; bar | tag) — first time a person is introduced;",
             "  - `callout` (circle | box | underline | arrow; position face, or point with x,y = fractions (0–1) of the SOURCE frame as seen on the contact sheet — the engine maps them through the crop; optional ≤ 3-word label);",
             "  - `counter` (value + text with {n}, e.g. \"₹{n} crore\", \"{n}%\") — when a number is the story; it appears on from_word and reaches the value exactly on to_word, so put to_word on the word that SAYS the number. Never use it to mirror a count the speaker does out loud (\"five, six, seven\");",
             "  - `text_card` (full screen, ≤ 8 words; dark | light | color) — a chapter or list beat; it hides the speaker, so use 0–2;",
             "  - `cta_card` (last item only; bar | card) — the brief's call to action;",
             "  - `progress_bar` and `logo_watermark` (whole reel; the logo needs a brand logo; top_right | top_left).",
             "  Top band = lower_third, emoji_pop upper_*, counter/keyword_card upper, cta bar: one at a time, never during the hook title (opening line). "
             "Emoji: one standard emoji (country flags and keycaps are not available).",
             "  Rules (pro motion design): sentence case, short claims without a full stop; two cards in a row never share size, entry and position; "
             "one style direction per creator — keep the same graphic styles across a reel; graphics never sit on the face or the captions.",
             "- Captions: kinetic captions in the family you choose, with your emphasis words; a brand kit overrides family/tokens.", ""]
    if inp.brand:
        lines += ["# Brand kit (overrides your token choices)", "", json.dumps(inp.brand.model_dump(exclude_none=True), indent=1, ensure_ascii=False), ""]
    from reel.color import LOOKS

    lines += ["# Colour looks (each clip is first corrected toward neutral; the look is applied on top at `strength`)", ""]
    lines += [f"- `{k}` — {d}" for k, (_, d) in LOOKS.items()]
    lines += ["", "# Caption families", ""]
    for fid, f in inp.idx.caption_families.items():
        lines.append(f"- `{fid}` — for {', '.join(f.get('for', []))}; mood: {f.get('mood', '')}; max {f.get('max_words')} words/page; "
                     f"tokens you may override: {', '.join(sorted((f.get('tokens') or {}).keys()))}")
    lines.append("")
    lines += ["## SFX library (pick by id; a handful per reel — ~8 reads as designed, ~20 as generic)", ""]
    menu = library.sfx_menu(inp.idx.sfx)
    if not menu:
        lines += ["Empty — use none.", ""]
    for cat, items in menu.items():
        lines.append(f"- **{cat}**: " + ", ".join(f"`{e['id']}` {e.get('name', '')} ({e['duration_ms']} ms, peak at {e['peak_ms']} ms)" for e in items))
    lines.append("")
    lines += _library("Music library (bed starts so a beat lands on the first cut; ducked under speech)", inp.idx.music, ("title", "mood", "energy", "bpm", "feel", "duration_ms"))
    lines += ["## B-roll (cutaways over the voice; `full` replaces the picture, `pip` = picture-in-picture card)", ""]
    if not inp.idx.broll:
        lines += ["Empty — use none.", ""]
    for bid, b in inp.idx.broll.items():
        lines.append(f"- `{bid}` {b.get('duration_ms', 0) / 1000:.1f} s · {b.get('shot', '?')}, {b.get('motion', '?')}, {b.get('mood', '')} — "
                     f"{b.get('description', b.get('name', ''))} ({b.get('source', 'library')})")
    lines.append("")
    ref = inp.ws.path("context", "reference_style.md")
    if ref.exists():
        lines += [ref.read_text(), ""]
    lines.append(knowledge.finish_context(story.genre))
    lines.append(knowledge.library_pointer())
    return "\n".join(lines)


# ------------------------------------------------------------------ validate → resume loop


def _issues_json(issues: list[Issue]) -> str:
    return json.dumps([i.as_dict() for i in issues], indent=1, ensure_ascii=False)


def _parse(model: type[BaseModel], data: dict) -> tuple[BaseModel | None, list[Issue]]:
    try:
        return model.model_validate(data), []
    except ValidationError as exc:
        return None, [Issue("schema", ".".join(str(p) for p in e["loc"]), e["msg"], "Return data matching the schema.") for e in exc.errors()]


@dataclass
class Decision:
    plan: BaseModel
    session_id: str | None
    calls: int
    cost_usd: float
    warnings: list[Issue]


def decide(caller: Caller, ws: Workspace, *, label: str, prompt: str, model: type[BaseModel], persona: Path, effort: str,
           check: Callable[[BaseModel], list[Issue]], resume: str | None = None) -> Decision:
    sch = schema(model)
    log_file = ws.path("log", "runs.jsonl")
    res = caller(prompt, sch, cwd=ws.root, persona_file=persona, effort=effort, resume=resume, log_file=log_file, label=label)
    calls, cost = 1, res.cost_usd or 0.0
    for attempt in range(MAX_RETRIES + 1):
        plan, issues = _parse(model, res.data)
        if plan is not None:
            issues = check(plan)
        if plan is not None and not errors(issues):
            return Decision(plan, res.session_id, calls, round(cost, 4), issues)
        if attempt == MAX_RETRIES:
            atomic_write_json(ws.path("plan", f"{label}_issues.json"), {"data": res.data, "issues": [i.as_dict() for i in issues]})
            raise DecisionError(f"{label}: plan still invalid after {MAX_RETRIES} fixes — see plan/{label}_issues.json")
        fix = ("The engine rejected your plan. Fix every error below (each has a `fix`) and return the complete corrected plan.\n\n"
               + _issues_json(errors(issues)))
        res = caller(fix, sch, cwd=ws.root, persona_file=persona, effort=effort, resume=res.session_id, log_file=log_file,
                     label=f"{label}:fix{attempt + 1}", meta={"fixing": [f"{i.code}@{i.path}" for i in errors(issues)]})
        calls, cost = calls + 1, cost + (res.cost_usd or 0.0)
    raise AssertionError("unreachable")


def _sessions(ws: Workspace) -> dict:
    p = ws.path("plan", "sessions.json")
    return json.loads(p.read_text()) if p.exists() else {}


def _save_session(ws: Workspace, key: str, session_id: str | None) -> None:
    s = _sessions(ws)
    s[key] = session_id
    atomic_write_json(ws.path("plan", "sessions.json"), s)


# ------------------------------------------------------------------ passes

STORY_PROMPT = ("Edit this reel: story pass. Read context/brief_and_knowledge.md, tables/summary.md and tables/script.md first, then "
                "whatever else you need from tables/ (words.tsv for exact indices, takes.json, segments.json, the contact sheets in "
                "sheets.json). Return the story plan.")
READBACK_PROMPT = ("Here is the read-back of your cut as the engine will assemble it (times are output times):\n\n{readback}\n\n"
                   "Check it like a viewer: does the first line hook within 1–2 s, does every line follow from the one before, is "
                   "any thought cut off, is anything repeated or slow? Return the final story plan — unchanged if it is right.")
FINISH_PROMPT = ("Finish pass. Read context/finish_context.md, plan/story.json and plan/story_readback.txt, plus tables/summary.md "
                 "and the contact sheets as needed. Return the finish plan.")
REVISION_PROMPT = ("The owner asked for a revision:\n\n\"{request}\"\n\nCurrent story read-back:\n{readback}\n\n"
                   "Return a revision: `story_patch` (ops on story items by id — empty ops if the story stays), the complete new "
                   "`finish` plan (copy unchanged parts), and a one-line `reply` saying what you changed.")


def _check_story(inp: Inputs):
    return lambda plan: validate_story(plan, inp.words, set(inp.clips), inp.kids)


def _check_finish(inp: Inputs, story: StoryPlan):
    def check(fin: FinishPlan) -> list[Issue]:
        issues = validate_finish(fin, story, inp.words, inp.idx, inp.kids)
        if fin.hook_title.style == "behind" and fin.hook_title.text.strip() and story.items:
            faces_p = inp.ws.path("perception", "faces.json")
            faces = json.loads(faces_p.read_text()) if faces_p.exists() else {}
            presence = (faces.get(story.items[0].clip) or {}).get("presence", 0.0)
            if presence < 0.5:
                issues.append(Issue("no_person_for_behind", "hook_title.style", f"A person is visible in only {presence:.0%} of the opening clip.",
                                    "Use style card — text behind the subject needs a clearly visible person."))
        for n, g in enumerate(fin.graphics):
            if g.kind.value == "logo_watermark" and not (inp.brand and inp.brand.logo):
                issues.append(Issue("no_brand_logo", f"graphics[{n}]", "There is no brand logo for this client.", "Remove the logo_watermark."))
        for n, t in enumerate(fin.transitions):
            if t.type.value not in RENDERABLE_TRANSITIONS:
                issues.append(Issue("not_renderable", f"transitions[{n}].type", f"'{t.type.value}' transitions are not available in this build.",
                                    "Remove it; use a hard cut (empty transitions)."))
        return issues
    return check


def cut_signature(story: StoryPlan) -> tuple:
    """What the viewer sees: hook + ordered word ranges (ignores reworded reasons/summary)."""
    return story.hook, tuple((it.clip, it.word_start, it.word_end) for it in story.items)


def readback(inp: Inputs, story: StoryPlan) -> str:
    return dry_run(story, inp.words, inp.clips, inp.fps, inp.idx, edges=inp.edges, vad=inp.vad, scene_cuts=inp.scenes)


def story_pass(inp: Inputs, caller: Caller = claude_call.call) -> dict:
    ws = inp.ws
    knowledge.write_library(ws)
    atomic_write_bytes(ws.path("context", "brief_and_knowledge.md"), story_pack(inp).encode())
    d1 = decide(caller, ws, label="story", prompt=STORY_PROMPT, model=StoryPlan, persona=STORY_PERSONA, effort=STORY_EFFORT,
                check=_check_story(inp))
    rb = readback(inp, d1.plan)
    d2 = decide(caller, ws, label="story_readback", prompt=READBACK_PROMPT.format(readback=rb), model=StoryPlan,
                persona=STORY_PERSONA, effort=STORY_EFFORT, check=_check_story(inp), resume=d1.session_id)
    story: StoryPlan = d2.plan
    atomic_write_json(ws.path("plan", "story.json"), story.model_dump(mode="json"))
    atomic_write_bytes(ws.path("plan", "story_readback.txt"), readback(inp, story).encode())
    _save_session(ws, "story", d2.session_id)
    return {"items": len(story.items), "genre": story.genre, "calls": d1.calls + d2.calls, "cost_usd": round(d1.cost_usd + d2.cost_usd, 4),
            "changed_on_readback": cut_signature(story) != cut_signature(d1.plan), "warnings": len(d1.warnings) + len(d2.warnings)}


def finish_pass(inp: Inputs, caller: Caller = claude_call.call) -> dict:
    ws = inp.ws
    story = project.load_json_model(StoryPlan, ws.path("plan", "story.json"))
    knowledge.write_library(ws)
    atomic_write_bytes(ws.path("context", "finish_context.md"), finish_pack(inp, story).encode())
    d = decide(caller, ws, label="finish", prompt=FINISH_PROMPT, model=FinishPlan, persona=FINISH_PERSONA, effort=FINISH_EFFORT,
               check=_check_finish(inp, story))
    fin: FinishPlan = d.plan
    atomic_write_json(ws.path("plan", "finish.json"), fin.model_dump(mode="json"))
    _save_session(ws, "finish", d.session_id)
    return {"punch_ins": len(fin.punch_ins), "caption_family": fin.captions.family, "calls": d.calls, "cost_usd": d.cost_usd}


def _patched(story: StoryPlan, rev: Revision) -> tuple[StoryPlan, list[Issue]]:
    """Apply the story ops; the opener is by definition items[0], so the chosen hook follows it
    (a patch cannot edit hook_options — without this every re-ordered opening fails once)."""
    new, issues = apply_story_patch(story, rev.story_patch)
    if new.items and not errors(issues):
        first = new.items[0].id
        opts = [h.model_copy(update={"item": first, "reason": f"Revision: {rev.story_patch.request}"}) if h.id == new.hook else h
                for h in new.hook_options if h.id == new.hook or h.item in {it.id for it in new.items}]
        new = new.model_copy(update={"hook_options": opts})
    return new, issues


def revise(inp: Inputs, request: str, caller: Caller = claude_call.call) -> dict:
    """Chat revision on the finish session (it has seen the story, the read-back and the finish context)."""
    ws = inp.ws
    session = _sessions(ws).get("finish")
    story = project.load_json_model(StoryPlan, ws.path("plan", "story.json"))

    def check(rev: Revision) -> list[Issue]:
        new_story, issues = _patched(story, rev)
        issues = [Issue(i.code, f"story_patch.{i.path}", i.message, i.fix, i.severity) for i in issues]
        if errors(issues):
            return issues
        issues += [Issue(i.code, f"story_patch→{i.path}", i.message, i.fix, i.severity) for i in validate_story(new_story, inp.words, set(inp.clips), inp.kids)]
        if errors(issues):
            return issues
        return issues + [Issue(i.code, f"finish.{i.path}", i.message, i.fix, i.severity) for i in _check_finish(inp, new_story)(rev.finish)]

    d = decide(caller, ws, label="revision", prompt=REVISION_PROMPT.format(request=request, readback=readback(inp, story)),
               model=Revision, persona=FINISH_PERSONA, effort=FINISH_EFFORT, check=check, resume=session)
    rev: Revision = d.plan
    new_story, _ = _patched(story, rev)
    hist = ws.path("plan", "history")
    n = len(list(hist.glob("*_story.json"))) + 1 if hist.exists() else 1
    for name in ("story", "finish"):
        src = ws.path("plan", f"{name}.json")
        if src.exists():
            atomic_write_bytes(hist / f"{n:03d}_{name}.json", src.read_bytes())
    atomic_write_json(hist / f"{n:03d}_request.json", {"request": request, "reply": rev.reply})
    atomic_write_json(ws.path("plan", "story.json"), new_story.model_dump(mode="json"))
    atomic_write_bytes(ws.path("plan", "story_readback.txt"), readback(inp, new_story).encode())
    atomic_write_json(ws.path("plan", "finish.json"), rev.finish.model_dump(mode="json"))
    _save_session(ws, "finish", d.session_id)
    return {"reply": rev.reply, "ops": len(rev.story_patch.ops), "calls": d.calls, "cost_usd": d.cost_usd}
