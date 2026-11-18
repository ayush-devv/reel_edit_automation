"""Score an edited reel against the owner's gold final (ADR-0014, ADR-0030 §2).

Gold side: the owner's final.mp4 is transcribed and aligned back to the raw word table, which
gives the words the owner kept, their order and the opening (hook) words. Cut rate on both
sides comes from the same scene detector, so the comparison is like for like.

Families: story (vs gold), captions (our caption text vs what is heard in our own render, plus
onset error), soft_gates (warn-level gate pass rate), reviewer (weighted by calibrated κ).
Vetoes: blocking gate failures and crashes.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from reel import script as sc
from reel import timebase as tb
from reel.evalh import metrics as m
from reel.perception.asr import RawWord
from reel.schemas.perception import WordTable

HOOK_S = 3.0  # the gold hook = raw words heard in the first 3 s of the owner's final
MIN_RUN = 2  # aligned runs shorter than this are treated as noise (common words)


@dataclass
class Gold:
    kept: set[int]  # raw word indices the owner kept
    order: list[int]  # raw word indices in the order they play in the final
    hook: set[int]
    cuts_per_min: float
    duration_s: float


def align(raw: WordTable, heard: list[RawWord]) -> list[tuple[int, float]]:
    """(raw word index, time in the final) for every heard word matched to the raw transcript.

    Greedy longest-common-run matching on script-agnostic keys, repeated until only runs shorter
    than MIN_RUN remain, so lines the owner re-ordered (or one take of a repeated line) are found
    wherever they are; matched words are masked so nothing is used twice."""
    hk = [sc.key(w.text) for w in heard]
    rk = [sc.key(w.text) for w in raw.words]
    clip_of = [w.clip for w in raw.words]
    out: dict[int, tuple[int, float]] = {}
    while True:
        sm = difflib.SequenceMatcher(a=hk, b=rk, autojunk=False)
        blk = sm.find_longest_match(0, len(hk), 0, len(rk))
        if blk.size < MIN_RUN:
            break
        for k in range(blk.size):
            if clip_of[blk.b + k] != clip_of[blk.b]:  # a run never spans two clips
                break
            out[blk.a + k] = (raw.words[blk.b + k].i, heard[blk.a + k].start_s)
            hk[blk.a + k] = f"\x00h{blk.a + k}"  # mask: unique tokens never match again
            rk[blk.b + k] = f"\x00r{blk.b + k}"
    return [out[k] for k in sorted(out)]


def gold_from_final(raw: WordTable, heard: list[RawWord], cuts: int, duration_s: float) -> Gold:
    pairs = align(raw, heard)
    order = [i for i, _ in pairs]
    return Gold(kept=set(order), order=order, hook={i for i, t in pairs if t < HOOK_S},
                cuts_per_min=cuts / max(duration_s, 1e-6) * 60, duration_s=duration_s)


def _segment_order(indices: list[int], seg_of: dict[int, str]) -> list[str]:
    out: list[str] = []
    for i in indices:
        s = seg_of.get(i)
        if s and (not out or out[-1] != s) and s not in out:
            out.append(s)
    return out


def our_hook(tl) -> set[int]:
    """Words that play in our first HOOK_S seconds — same definition as the gold hook."""
    fps = tb.parse_rate(tl.fps)
    return {w.i for p in (tl.captions.pages if tl.captions else []) for w in p.words if float(Fraction(w.start_f) / fps) < HOOK_S}


def story_family(story, raw: WordTable, gold: Gold, ours_cuts: int, ours_duration_s: float, seg_of: dict[int, str], hook: set[int]) -> dict:
    kept = [i for it in story.items for i in range(it.word_start, it.word_end + 1)]
    tau = m.kendall_tau(_segment_order(kept, seg_of), _segment_order(gold.order, seg_of))
    parts = {"hook_iou": m.hook_iou(hook, gold.hook), "word_f1": m.f1(set(kept), gold.kept), "tau": tau,
             "cut_rate": m.cut_rate_score(ours_cuts / max(ours_duration_s, 1e-6) * 60, gold.cuts_per_min)}
    return parts | {"score": m.story_score(parts["hook_iou"], parts["word_f1"], tau, parts["cut_rate"])}


def caption_family(tl, heard_ours: list[RawWord]) -> dict:
    """Our caption words vs the words actually heard in our render (text and onset)."""
    fps = tb.parse_rate(tl.fps)
    caps = [(w.text, float(Fraction(w.start_f) / fps)) for p in (tl.captions.pages if tl.captions else []) for w in p.words]
    ck = [sc.key(t) for t, _ in caps]
    hk = [sc.key(w.text) for w in heard_ours]
    wer = m.word_error_rate(hk, ck)
    pairs = []
    for blk in difflib.SequenceMatcher(a=ck, b=hk, autojunk=False).get_matching_blocks():
        pairs += [(caps[blk.a + k][1], heard_ours[blk.b + k].start_s) for k in range(blk.size)]
    err = m.median_timing_error_ms(pairs)
    return {"wer": round(wer, 4), "onset_ms": err, "score": m.caption_score(wer, err)}


def soft_gate_family(gates: list[dict]) -> tuple[float | None, list[str]]:
    warn = [g for g in gates if g.get("mode") == "warn"]
    vetoes = [f"gate {g['gate']}: {g.get('detail', '')}" for g in gates if g.get("mode") == "block" and not g.get("ok")]
    return (sum(g["ok"] for g in warn) / len(warn) if warn else None), vetoes


def reviewer_family(review: dict | None) -> float | None:
    if not review:
        return None
    if review.get("sendable"):
        return 1.0
    sev = [i.get("severity") for i in review.get("issues", [])]
    return max(0.0, 1 - 0.3 * sev.count("blocker") - 0.15 * sev.count("major") - 0.05 * sev.count("minor"))


def score_workspace(ws, gold: Gold, *, heard_ours: list[RawWord], ours_cuts: int, kappa: float | None = None) -> tuple[m.ReelScore, dict]:
    from reel import project
    from reel.schemas.plan import StoryPlan
    from reel.schemas.timeline import Timeline

    tl = Timeline.model_validate_json(ws.path("timeline", "timeline.json").read_text())
    story = project.load_json_model(StoryPlan, ws.path("plan", "story.json"))
    raw = project.word_table(ws)
    segs = json.loads(ws.path("perception", "segments.json").read_text()).get("segments", [])
    seg_of = {i: s["seg_id"] for s in segs for i in range(s["word_start"], s["word_end"] + 1)}
    fps = tb.parse_rate(tl.fps)
    detail = {"story": story_family(story, raw, gold, ours_cuts, float(Fraction(tl.duration_f) / fps), seg_of, our_hook(tl)),
              "captions": caption_family(tl, heard_ours)}
    gates = json.loads(ws.path("qa", "gates.json").read_text()) if ws.path("qa", "gates.json").exists() else []
    soft, vetoes = soft_gate_family(gates)
    review = json.loads(ws.path("qa", "review.json").read_text()) if ws.path("qa", "review.json").exists() else None
    score = m.ReelScore(reviewer_kappa=kappa, vetoes=vetoes)
    score.families["story"] = detail["story"]["score"]
    score.families["captions"] = detail["captions"]["score"]
    if soft is not None:
        score.families["soft_gates"] = soft
    rv = reviewer_family(review)
    if rv is not None:
        score.families["reviewer"] = rv
    return score, detail


def load_gold(final: Path, raw: WordTable, backend, cache: Path) -> Gold:
    """Transcribe + scene-detect the owner's final once (cached next to the eval run)."""
    from reel.perception import visual
    from reel.perception.audio import extract_wav
    from reel.probe import probe

    if cache.exists():
        d = json.loads(cache.read_text())
        return Gold(set(d["kept"]), d["order"], set(d["hook"]), d["cuts_per_min"], d["duration_s"])
    words, _ = backend.transcribe(extract_wav(final, cache.with_suffix(".wav")), None, None)
    g = gold_from_final(raw, words, len(visual.scene_cuts(final)), probe(final).duration_s)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"kept": sorted(g.kept), "order": g.order, "hook": sorted(g.hook), "cuts_per_min": g.cuts_per_min,
                                 "duration_s": g.duration_s}))
    return g
