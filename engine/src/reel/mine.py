"""Clip Factory, step 1: find standalone reels in one long recording (roadmap G2.2).

One Claude decision per transcript chunk proposes candidates; everything a prompt can only *ask* for is enforced
here in code (vidpipe and OpenMontage leave it to the prompt):
- word ranges that exist and quote the right words;
- spoken length inside the target;
- starts and ends on segment boundaries (no mid-sentence opening, no cut-off payoff);
- the speaker's face visible enough for a 9:16 crop;
- a score computed by the engine from the miner's 1–5 marks (never "viral"), then a greedy selection with a
  family quota, an overlap rule and a yield cap.

Candidate scores are the Editor's estimate. The owner's picks are logged (`mine/picks.jsonl`) so the scores can
be calibrated later.
"""

from __future__ import annotations

import json
import math
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reel import brief as brief_mod
from reel import claude_call, decide
from reel.schemas.perception import SegmentTable, WordTable
from reel.validate import Issue, _nearest_match, norm
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

PERSONA = Path(__file__).parent / "personas" / "clip_miner.md"
EFFORT = "high"
DEFAULT_TARGET_S = (20.0, 75.0)
MIN_SCORE = 3.0
MAX_OVERLAP = 0.20  # share of a candidate's words already used by a better-ranked selected one
MIN_FACE = 0.90
MINUTES_PER_REEL = 5.0  # yield target: about one reel per 4–6 min of source; never pad
MAX_REELS = 12
CHUNK_S = 15 * 60
CHUNK_OVERLAP_S = 60
CHUNK_IF_OVER_S = 20 * 60
WEIGHTS = {"hook": 3, "standalone": 3, "payoff": 2, "shareability": 2, "energy": 1}
BACK_REFERENCES = {"this", "that", "these", "those", "he", "she", "it", "they", "them", "so", "and", "but", "also",
                   "yeh", "ye", "woh", "wo", "isliye", "toh", "to", "aur", "phir", "isme", "usme", "inhone", "unhone"}
PROMPT = ("Find the standalone reels in this long recording. Read context/mine_brief.md first, then {script} and tables/summary.md "
          "(use tables/words.tsv for exact word indices and tables/segments.json for segment boundaries). Return the candidates.")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClipFamily(str, Enum):
    hook = "hook"
    story = "story"
    tip = "tip"
    hot_take = "hot_take"
    proof = "proof"
    myth = "myth"


class ClipRange(_Strict):
    clip: str
    word_start: int  # global word index, inclusive
    word_end: int
    first_word: str  # quote of word_start — checked against the word table
    last_word: str


class ClipScores(_Strict):
    hook: int  # 1–5: does the first line stop the scroll?
    standalone: int  # 1–5: understandable with no earlier context
    payoff: int  # 1–5: does it land a point, result or punchline?
    energy: int  # 1–5: delivery
    shareability: int  # 1–5: would someone send it to a friend?


class ClipCandidate(_Strict):
    id: str  # c01, c02 …
    title: str
    hook_text: str  # the opening line, as the viewer hears it
    ranges: list[ClipRange]  # 1–3, in output order (a payoff-first open is allowed)
    family: ClipFamily
    scores: ClipScores
    standalone_risks: list[str]  # what a viewer without context might miss
    reason: str


class ClipCandidates(_Strict):
    candidates: list[ClipCandidate]


# ------------------------------------------------------------------ measures


def spoken_s(rng: ClipRange, by: dict, edges: dict[int, tuple[int, int]] | None) -> float:
    a, b = by.get(rng.word_start), by.get(rng.word_end)
    if a is None or b is None:
        return 0.0
    start = (edges or {}).get(a.i, (a.start_us, a.end_us))[0]
    end = (edges or {}).get(b.i, (b.start_us, b.end_us))[1]
    return max(0.0, (end - start) / 1e6)


def face_share(rng: ClipRange, by: dict, faces: dict | None) -> float | None:
    """Share of face samples inside the range that see a face; None when faces were not measured."""
    samples = ((faces or {}).get(rng.clip) or {}).get("samples")
    a, b = by.get(rng.word_start), by.get(rng.word_end)
    if not samples or a is None or b is None:
        return None
    inside = [s for s in samples if a.start_us <= s["t_us"] <= b.end_us]
    return (sum(1 for s in inside if s.get("faces")) / len(inside)) if inside else None


def score(c: ClipCandidate) -> float:
    s = c.scores.model_dump()
    return round(sum(WEIGHTS[k] * s[k] for k in WEIGHTS) / sum(WEIGHTS.values()), 2)


def word_set(c: ClipCandidate) -> set[int]:
    return {i for r in c.ranges for i in range(r.word_start, r.word_end + 1)}


# ------------------------------------------------------------------ checks


def validate_candidates(plan: ClipCandidates, words: WordTable, segments: SegmentTable, *, edges=None, faces=None,
                        target_s: tuple[float, float] = DEFAULT_TARGET_S) -> list[Issue]:
    issues: list[Issue] = []
    by = words.by_index()
    clips = {w.clip for w in words.words}
    starts = {(s.clip, s.word_start) for s in segments.segments}
    ends = {(s.clip, s.word_end) for s in segments.segments}
    seg_starts = sorted(s.word_start for s in segments.segments)
    seg_ends = sorted(s.word_end for s in segments.segments)
    if not plan.candidates:
        issues.append(Issue("empty_plan", "candidates", "No candidates.", "Propose the standalone moments this recording has (or explain none in reason)."))
    seen: set[str] = set()
    for n, c in enumerate(plan.candidates):
        p = f"candidates[{n}]"
        if not c.id or c.id in seen:
            issues.append(Issue("duplicate_id", f"{p}.id", f"Candidate id '{c.id}' is empty or repeated.", "Use c01, c02, …"))
        seen.add(c.id)
        for k, v in c.scores.model_dump().items():
            if not 1 <= v <= 5:
                issues.append(Issue("out_of_range", f"{p}.scores.{k}", f"Score {v} is outside 1–5.", "Score each mark 1–5."))
        if not 1 <= len(c.ranges) <= 3:
            issues.append(Issue("range_count", f"{p}.ranges", f"{len(c.ranges)} ranges; a reel uses 1–3.", "Keep 1–3 ranges."))
            continue
        bad = False
        for r_n, r in enumerate(c.ranges):
            rp = f"{p}.ranges[{r_n}]"
            if r.clip not in clips:
                issues.append(Issue("unknown_clip", f"{rp}.clip", f"Clip '{r.clip}' does not exist.", f"Use one of {sorted(clips)}."))
                bad = True
                continue
            if r.word_start > r.word_end:
                issues.append(Issue("reversed_range", rp, f"word_start {r.word_start} > word_end {r.word_end}.", "Swap them."))
                bad = True
                continue
            for fname, idx, quote in (("word_start", r.word_start, r.first_word), ("word_end", r.word_end, r.last_word)):
                w = by.get(idx)
                if w is None:
                    issues.append(Issue("unknown_word", f"{rp}.{fname}", f"Word index {idx} does not exist.", "Use indices from tables/words.tsv."))
                    bad = True
                elif w.clip != r.clip:
                    issues.append(Issue("word_clip_mismatch", f"{rp}.{fname}", f"Word {idx} is in clip {w.clip}, not {r.clip}.", f"Set clip to {w.clip}."))
                    bad = True
                elif norm(w.text) != norm(quote):
                    near = _nearest_match(words, r.clip, idx, quote)
                    issues.append(Issue("quote_mismatch", f"{rp}.{fname}", f"Quoted '{quote}' but word {idx} is '{w.text}'.",
                                        f"Did you mean index {near}?" if near is not None else f"Quote the actual word: '{w.text}'."))
                    bad = True
            if bad:
                continue
            if (r.clip, r.word_start) not in starts:
                near = min(seg_starts, key=lambda s: abs(s - r.word_start)) if seg_starts else None
                issues.append(Issue("mid_sentence_start", f"{rp}.word_start", f"Word {r.word_start} does not start a segment: the reel would open mid-sentence.",
                                    f"Start at a segment start (nearest: word {near})."))
            if (r.clip, r.word_end) not in ends:
                near = min(seg_ends, key=lambda s: abs(s - r.word_end)) if seg_ends else None
                issues.append(Issue("ends_mid_thought", f"{rp}.word_end", f"Word {r.word_end} does not end a segment: the thought is cut off.",
                                    f"End at a segment end (nearest: word {near})."))
            fs = face_share(r, by, faces)
            if fs is not None and fs < MIN_FACE:
                issues.append(Issue("low_face", rp, f"The speaker's face is visible in only {fs:.0%} of this range; a 9:16 crop needs ≥ {MIN_FACE:.0%}.",
                                    "Drop this candidate or pick a stretch where the speaker is on camera."))
        if bad:
            continue
        spans = sorted((r.word_start, r.word_end) for r in c.ranges)
        if any(b0 <= a1 for (_a0, a1), (b0, _b1) in zip(spans, spans[1:])):
            issues.append(Issue("overlap", f"{p}.ranges", "Two ranges of this candidate share words.", "Make the ranges disjoint."))
        dur = sum(spoken_s(r, by, edges) for r in c.ranges)
        lo, hi = target_s
        if dur < lo:
            issues.append(Issue("too_short", p, f"{dur:.0f} s of speech; the target is {lo:.0f}–{hi:.0f} s.", "Widen it to a complete thought or drop it."))
        elif dur > hi:
            issues.append(Issue("too_long", p, f"{dur:.0f} s of speech; the target is {lo:.0f}–{hi:.0f} s.", "Tighten it to the strongest part."))
        first = by[c.ranges[0].word_start].text.strip(" ,.!?\"'“”").casefold()
        if first in BACK_REFERENCES:
            issues.append(Issue("opens_on_reference", f"{p}.ranges[0]", f"It opens on '{first}', which may refer to something said earlier.",
                                "Start where the thought starts, or say why it stands alone.", "warning"))
    return issues


# ------------------------------------------------------------------ selection


def yield_cap(source_s: float) -> int:
    return max(1, min(MAX_REELS, math.ceil(source_s / 60 / MINUTES_PER_REEL)))


def select(plan: ClipCandidates, source_s: float, *, words: WordTable, edges=None, warnings: list[Issue] | None = None) -> list[dict]:
    """Rank by the engine's score, then keep greedily: score floor, no more than half from one family, ≤ 20 % word
    overlap with anything already kept, and the yield cap. Every candidate is returned with its status and why."""
    by = words.by_index()
    cap = yield_cap(source_s)
    family_cap = max(1, math.ceil(cap / 2))
    warn_by: dict[str, list[str]] = {}
    for w in warnings or []:
        n = _index(w.path)
        if n is not None and n < len(plan.candidates):
            warn_by.setdefault(plan.candidates[n].id, []).append(f"{w.code}: {w.message}")
    rows = []
    for c in plan.candidates:
        rows.append({**c.model_dump(mode="json"), "score": score(c), "duration_s": round(sum(spoken_s(r, by, edges) for r in c.ranges), 1),
                     "warnings": warn_by.get(c.id, [])})
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    kept: list[dict] = []
    families: dict[str, int] = {}
    used: set[int] = set()
    for r in rows:
        ws_ = {i for rg in r["ranges"] for i in range(rg["word_start"], rg["word_end"] + 1)}
        share = len(ws_ & used) / max(1, len(ws_))
        if r["score"] < MIN_SCORE:
            r["status"], r["why"] = "rejected", f"score {r['score']} < {MIN_SCORE}"
        elif share > MAX_OVERLAP:
            r["status"], r["why"] = "rejected", f"{share:.0%} of its words are in a better-ranked pick"
        elif families.get(r["family"], 0) >= family_cap:
            r["status"], r["why"] = "rejected", f"already {family_cap} '{r['family']}' picks (variety)"
        elif len(kept) >= cap:
            r["status"], r["why"] = "rejected", f"yield cap {cap} for {source_s / 60:.0f} min of source"
        else:
            r["status"], r["why"] = "selected", ""
            kept.append(r)
            families[r["family"]] = families.get(r["family"], 0) + 1
            used |= ws_
    for rank, r in enumerate(rows, 1):
        r["rank"] = rank
    return rows


# ------------------------------------------------------------------ chunks and the pass


def chunks(segments: SegmentTable, total_s: float) -> list[tuple[float, float]]:
    """Time windows (s) for long sources: ~15 min with 1 min overlap; one window when short."""
    if total_s <= CHUNK_IF_OVER_S:
        return [(0.0, total_s)]
    out, t = [], 0.0
    while t < total_s:
        out.append((t, min(total_s, t + CHUNK_S)))
        t += CHUNK_S - CHUNK_OVERLAP_S
    return out


def target_for(brief: brief_mod.Brief | None, options: dict) -> tuple[float, float]:
    """Explicit run option, else a brief that changed the default length, else 20–75 s."""
    if options.get("clip_target_s"):
        lo, hi = options["clip_target_s"]
        return float(lo), float(hi)
    if brief and tuple(brief.target_length_s) != tuple(brief_mod.Brief.model_fields["target_length_s"].default):
        return tuple(brief.target_length_s)
    return DEFAULT_TARGET_S


def source_seconds(words: WordTable) -> float:
    by_clip: dict[str, int] = {}
    for w in words.words:
        by_clip[w.clip] = max(by_clip.get(w.clip, 0), w.end_us)
    return sum(by_clip.values()) / 1e6


def brief_md(brief: brief_mod.Brief | None, brand: brief_mod.Brand | None, target: tuple[float, float], cap: int, window: tuple[float, float] | None) -> str:
    lines = ["# What to find", "",
             f"Standalone reels of {target[0]:.0f}–{target[1]:.0f} s of speech each, for Instagram Reels. Aim for about {cap} strong ones "
             "across the whole recording; propose a few more than that so the engine can choose, but never pad with weak moments.", "",
             "Each candidate must make sense to someone who has not seen the rest of the recording, open on a line that stops the scroll, "
             "and end on its payoff. Use 1–3 ranges (a payoff-first open from later in the same thought is fine). Score each mark 1–5 honestly: "
             "the engine computes the ranking from your marks.", ""]
    if window:
        lines += [f"Only this part of the recording: {window[0] / 60:.1f}–{window[1] / 60:.1f} min (segments outside it belong to another pass).", ""]
    if brief:
        lines += ["# Client brief", "", json.dumps(brief.model_dump(exclude_none=True), ensure_ascii=False, indent=1), ""]
    if brand:
        lines += ["# Brand", "", json.dumps(brand.model_dump(exclude_none=True), ensure_ascii=False, indent=1), ""]
    return "\n".join(lines)


def _index(path: str) -> int | None:
    """Candidate number in an issue path like 'candidates[3].ranges[0]'."""
    if not path.startswith("candidates["):
        return None
    n = path[len("candidates["):].split("]", 1)[0]
    return int(n) if n.isdigit() else None


def _shift(w: Issue, offset: int) -> Issue:
    n = _index(w.path)
    if n is None or not offset:
        return w
    return Issue(w.code, w.path.replace(f"candidates[{n}]", f"candidates[{n + offset}]", 1), w.message, w.fix, w.severity)


def _chunk_script(ws: Workspace, segments: SegmentTable, window: tuple[float, float], n: int) -> str:
    """A script file holding only the segments that start inside the window (the full tables stay for indices)."""
    keep = {s.seg_id for s in segments.segments if window[0] * 1e6 <= s.start_us < window[1] * 1e6}
    out, take = [], True
    for line in ws.path("tables", "script.md").read_text().splitlines():
        if line.startswith("[s"):
            take = line[1:].split(" ", 1)[0] in keep
        elif line.startswith("## Clip") or not line.strip():
            take = True
        if take:
            out.append(line)
    rel = f"tables/mine_chunk_{n:02d}.md"
    atomic_write_bytes(ws.root / rel, ("\n".join(out) + "\n").encode())
    return rel


def mine_pass(ws: Workspace, options: dict, caller=claude_call.call) -> dict:
    from reel import project

    words = project.word_table(ws)
    segments = SegmentTable.model_validate_json(ws.path("perception", "segments.json").read_text())
    edges = project.edges(ws)
    faces_p = ws.path("perception", "faces.json")
    faces = json.loads(faces_p.read_text()) if faces_p.exists() else None
    brief = brief_mod.load_brief(options.get("brief"))
    brand = brief_mod.load_brand(options.get("brand"))
    target = target_for(brief, options)
    total = source_seconds(words)
    cap = yield_cap(total)
    windows = chunks(segments, total)
    found: list[ClipCandidate] = []
    warnings: list[Issue] = []
    calls, cost = 0, 0.0
    check = lambda plan: validate_candidates(plan, words, segments, edges=edges, faces=faces, target_s=target)  # noqa: E731
    for n, win in enumerate(windows, 1):
        script = "tables/script.md" if len(windows) == 1 else _chunk_script(ws, segments, win, n)
        atomic_write_bytes(ws.path("context", "mine_brief.md"),
                           brief_md(brief, brand, target, cap if len(windows) == 1 else max(1, math.ceil(cap / len(windows))),
                                    None if len(windows) == 1 else win).encode())
        d = decide.decide(caller, ws, label="mine" if len(windows) == 1 else f"mine_{n:02d}", prompt=PROMPT.format(script=script),
                          model=ClipCandidates, persona=PERSONA, effort=EFFORT, check=check)
        calls, cost = calls + d.calls, cost + d.cost_usd
        offset = len(found)
        for c in d.plan.candidates:  # ids are re-numbered across chunks so they stay unique
            found.append(c.model_copy(update={"id": f"c{len(found) + 1:02d}"}))
        warnings += [_shift(w, offset) for w in d.warnings]
    plan = ClipCandidates(candidates=found)
    rows = select(plan, total, words=words, edges=edges, warnings=warnings)
    out = {"source_s": round(total, 1), "yield_cap": cap, "target_s": list(target), "chunks": [list(w) for w in windows],
           "score_rule": f"({' + '.join(f'{k}×{v}' for k, v in WEIGHTS.items())}) / {sum(WEIGHTS.values())}; keep ≥ {MIN_SCORE}",
           "candidates": rows}
    atomic_write_json(ws.path("mine", "candidates.json"), out)
    atomic_write_bytes(ws.path("mine", "board.md"), board_md(out).encode())
    return {"candidates": len(rows), "selected": sum(r["status"] == "selected" for r in rows), "calls": calls, "cost_usd": round(cost, 4)}


def board_md(out: dict) -> str:
    lines = ["# Clips board", "", f"Source {out['source_s'] / 60:.1f} min · target {out['target_s'][0]:.0f}–{out['target_s'][1]:.0f} s · "
             f"up to {out['yield_cap']} reels · score = the Editor's estimate, {out['score_rule']}", ""]
    for r in out["candidates"]:
        mark = "✓" if r["status"] == "selected" else "·"
        lines.append(f"{mark} {r['rank']:>2}. **{r['title']}** ({r['id']}, {r['family']}, {r['duration_s']:.0f} s, score {r['score']})")
        lines.append(f"    hook: “{r['hook_text']}”")
        lines.append(f"    why: {r['reason']}" + (f" — not picked: {r['why']}" if r["why"] else ""))
        for w in r["warnings"]:
            lines.append(f"    ⚠ {w}")
    return "\n".join(lines) + "\n"


def load(ws: Workspace) -> dict | None:
    p = ws.path("mine", "candidates.json")
    return json.loads(p.read_text()) if p.exists() else None


def log_picks(ws: Workspace, picked: list[str]) -> None:
    """The owner's choice, picked and skipped, for calibrating the miner's marks later."""
    import time

    data = load(ws) or {"candidates": []}
    line = {"at": time.time(), "picked": picked,
            "shown": [{"id": r["id"], "score": r["score"], "status": r["status"], "family": r["family"]} for r in data["candidates"]]}
    f = ws.path("mine", "picks.jsonl")
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as fh:
        fh.write(json.dumps(line) + "\n")
