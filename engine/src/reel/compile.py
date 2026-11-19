"""Plan → timeline compiler (ADR-0002, ADR-0003, ADR-0015).

Deterministic: the same plans + word table + clip info always give the same timeline.
Claude never supplies a timestamp; every frame comes from word edges via the shared
time-map (reel.timebase).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction

from reel import timebase as tb
from reel.assets import Indexes
from reel.schemas.perception import Word, WordTable
from reel.schemas.plan import CaptionPlan, Ease, FinishPlan, GradePlan, HookTitle, MusicPlan, SfxAnchor, StoryPlan, TransitionType
from reel.schemas.timeline import (
    Asset,
    AssetKind,
    AudioClip,
    CaptionPage,
    CaptionTrack,
    CaptionWord,
    Ducking,
    EffectEvent,
    FlashEvent,
    GraphicEvent,
    Grade,
    PipEvent,
    Keyframe,
    Provenance,
    Timeline,
    TitleEvent,
    TransitionEvent,
    VideoClip,
)

BREATH_PAD_US = 80_000  # breath around a kept range when only ASR edges are known
HEARD_PAD_US = 100_000  # breath around heard (snapped) edges (ADR-0002)
MIN_CAPTION_US = 350_000  # a caption page stays at least this long
PAGE_HOLD_US = 600_000  # bridge pauses up to this between pages (no blinking)
PAGE_MIN_US = 600_000  # a page stays readable at least this long (unless the next page starts sooner)
TITLE_MIN_US = 1_500_000  # hook title on screen at least this long …
TITLE_MAX_US = 3_000_000
GRAPHIC_MIN_US = 1_200_000  # a graphic stays at least this long (it has to be read)
TEXT_CARD_MIN_US = 2_000_000  # a full-screen card needs its word entrance plus a beat to read
# entrance animation + time to read before the 0.3 s exit (counter: 1.3 s count-up; keyword marks draw after the words)
GRAPHIC_MIN_US_BY_KIND = {"text_card": TEXT_CARD_MIN_US, "counter": 2_200_000, "keyword_card": 2_000_000, "callout": 1_600_000}
WHOLE_REEL_GRAPHICS = {"progress_bar", "logo_watermark"}  # … and at most this long (or to the end of the first item, if sooner past the minimum)


@dataclass(frozen=True)
class ClipInfo:
    id: str
    uri: str  # mezzanine path relative to the workspace
    duration_us: int


class CompileError(ValueError):
    pass


def empty_finish(family: str = "bold_pop") -> FinishPlan:
    return FinishPlan(
        hook_title=HookTitle(text="", style="card", reason="default"), grade=GradePlan(look="none", strength=0.0, reason="default"), punch_ins=[], speeds=[], transitions=[],
        captions=CaptionPlan(family=family, tokens=[], emphasis_words=[], script="latin", reason="default"),
        sfx=[], music=MusicPlan(track="none", gain_db=-18, duck_db=12, reason="default"),
        broll=[], knowledge_used=[],
    )


def _digest(model) -> str:
    return hashlib.sha256(json.dumps(model.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()[:16]


def pause_groups(item_words: list[Word], max_pause_us: int, edges: dict[int, tuple[int, int]] | None = None) -> list[list[Word]]:
    """Split a kept line at pauses longer than `max_pause_us` (heard edges when known): each group
    becomes its own shot, so dead air inside a line is cut out (a jump cut). 0 keeps every pause."""
    edges = edges or {}
    groups = [[item_words[0]]]
    for a, b in zip(item_words, item_words[1:]):
        gap = edges.get(b.i, (b.start_us, b.end_us))[0] - edges.get(a.i, (a.start_us, a.end_us))[1]
        if max_pause_us and gap > max_pause_us:
            groups.append([b])
        else:
            groups[-1].append(b)
    return groups


def _source_range(item_words: list[Word], clip_words: list[Word], clip: ClipInfo,
                  edges: dict[int, tuple[int, int]] | None = None) -> tuple[int, int]:
    """Cut points: heard speech edges (step 4 snapping) when known, else ASR edges; plus a breath,
    never crossing into the neighbouring words' heard sound."""
    edges = edges or {}

    def heard(w: Word) -> tuple[int, int]:
        return edges.get(w.i, (w.start_us, w.end_us))

    first, last = item_words[0], item_words[-1]
    pos = {w.i: k for k, w in enumerate(clip_words)}
    prev = clip_words[pos[first.i] - 1] if pos[first.i] > 0 else None
    nxt = clip_words[pos[last.i] + 1] if pos[last.i] + 1 < len(clip_words) else None
    pad = BREATH_PAD_US if not edges else HEARD_PAD_US
    start = max(heard(first)[0] - pad, heard(prev)[1] if prev else 0, 0)
    end = min(heard(last)[1] + pad, heard(nxt)[0] if nxt else clip.duration_us, clip.duration_us)
    if end <= start:
        raise CompileError(f"empty source range for words {first.i}-{last.i}")
    return start, end


UNRELIABLE_SHARE = 0.15  # above this share of suspect/zero-length kept words, captions fall back to phrases


def clean_caption_words(ws: list) -> list:
    """Captions read like writing, not raw ASR: stutters ("i i thought") drop the repeat, "i" → "I",
    and a line starts with a capital. The audio is unchanged; only the on-screen text is tidied."""
    out = []
    for w in ws:
        key = w.text.strip(".,!?;:").casefold()
        if out and key and key == out[-1].text.strip(".,!?;:").casefold():
            continue
        t = w.text
        core = t.strip(".,!?;:")
        if len(core) > 4 and core.isupper():  # ASR writes shouted words in caps ("ORANGE."); acronyms (≤ 4) stay
            t = t.replace(core, core.lower())
        if key in ("i", "i'm", "i've", "i'll", "i'd"):
            t = "I" + t[1:]
        if (not out or out[-1].text.rstrip()[-1:] in ".?!") and t[:1].islower():
            t = t[:1].upper() + t[1:]
        out.append(w.model_copy(update={"text": t}) if t != w.text else w)
    return out


def caption_text(text: str, script: str) -> str:
    """Caption script (brief): latin → Devanagari words romanised; devanagari/mixed → as transcribed."""
    from reel import script as sc

    return sc.deva_to_roman(text) if script == "latin" and sc.script_of(text) == "devanagari" else text


# English words that should not end a caption page (they lean on the next word) and Hindi
# postpositions/auxiliaries that should not start one (they lean on the previous word).
LEANS_FORWARD = {"a", "an", "the", "to", "of", "into", "in", "on", "at", "for", "with", "from", "by", "and", "or", "but",
                 "your", "my", "our", "their", "his", "her", "its", "this", "that", "these", "those", "will", "can", "is",
                 "are", "was", "were", "be", "i", "you", "we", "they", "not", "very", "so", "just", "more", "most",
                 "one", "two", "three", "some", "any", "every", "each", "no", "all", "few", "many"}
LEANS_BACK = {"ka", "ki", "ke", "ko", "se", "me", "mein", "par", "ne", "tak", "hai", "hain", "tha", "thi", "the", "hi", "bhi",
              "का", "की", "के", "को", "से", "में", "पर", "ने", "तक", "है", "हैं", "था", "थी", "थे", "ही", "भी"}


def _bare(text: str) -> str:
    return text.strip(".,!?;:—\"'“”").casefold()


def _break_cost(w, nxt) -> float:
    """Cost of ending a caption page after word `w`: free after punctuation, cheap at a pause,
    expensive inside a phrase (after a word that leans forward, or before one that leans back)."""
    if nxt is None or w.text.rstrip()[-1:] in ".,!?;:—":
        return 0.0
    gap_ms = (nxt.start_us - w.end_us) / 1000
    cost = 0.5 if gap_ms >= 250 else 2.0 if gap_ms >= 120 else 3.0
    if _bare(w.text) in LEANS_FORWARD:
        cost += 3.0
    if _bare(nxt.text) in LEANS_BACK:
        cost += 3.0
    if _bare(nxt.text) in LEANS_FORWARD:
        cost -= 1.0  # breaking before "to save…", "and never…" keeps the phrase together
    return max(cost, 0.25)


def page_char_budget(tokens: dict) -> int:
    """Characters that fit one caption line at the family's size (mirrors the overlay's estimate)."""
    if tokens.get("case") == "upper":
        return 14
    return 16 if int(tokens.get("weight", "700") or 700) >= 800 else 20


PAGE_SHORT_US = 600_000  # pages shorter than this flash by: the paging pays a penalty for them


def balanced_pages(ws: list, max_words: int, max_chars: int = 999) -> list[list]:
    """Caption pages of ≤ max_words that break at phrase boundaries (punctuation, pauses), with
    as few pages as possible and no one-word orphan page (dynamic programming over break points)."""
    n = len(ws)
    if n == 0:
        return []
    best = [0.0] + [float("inf")] * n  # best[k] = cost of paging ws[:k]
    prev = [0] * (n + 1)
    for k in range(1, n + 1):
        for size in range(1, min(max_words, k) + 1):
            j = k - size
            if size > 1 and sum(len(w.text) + 1 for w in ws[j:k]) - 1 > max_chars:
                continue  # would need a smaller font: re-page instead of shrinking
            cost = best[j] + _break_cost(ws[k - 1], ws[k] if k < n else None) + 1.0  # +1 per page: prefer fewer pages
            dur = ws[k - 1].end_us - ws[j].start_us
            if dur < PAGE_SHORT_US:
                cost += 3.0 * (PAGE_SHORT_US - dur) / PAGE_SHORT_US  # fast talkers: fuller pages instead of flicker
            if size == 1 and n > 1:
                cost += 3.0  # orphan word
            if cost < best[k]:
                best[k], prev[k] = cost, j
    pages, k = [], n
    while k > 0:
        pages.append(ws[prev[k]:k])
        k = prev[k]
    return pages[::-1]


def unreliable_timing(words: list[Word]) -> bool:
    """Word-by-word highlighting needs trustworthy word times; Hinglish ASR sometimes smears them."""
    if not words:
        return False
    bad = sum(1 for w in words if w.suspect or w.end_us - w.start_us <= 20_000)
    return bad / len(words) > UNRELIABLE_SHARE


def proof_list(tl: Timeline, story: StoryPlan, words: WordTable) -> list[dict]:
    """Kept words the ASR was unsure of, with output timecodes, for the owner's ~30 s check (ADR-0021).
    Uses the same word → output-frame mapping as the compiler."""
    fps = tb.parse_rate(tl.fps)
    by = words.by_index()
    shots = [c for c in tl.video if c.id.startswith("v_")]
    out = []
    for it in story.items:
        for i in range(it.word_start, it.word_end + 1):
            w = by[i]
            c = next((s for s in shots if s.src.item == it.id and s.src.words[0] <= i <= s.src.words[1]), None)
            if c is None:
                continue
            in_f = tb.us_to_frame(c.src_in_us, fps)
            if w.filler or not (w.low_conf or w.vocab_suspect or w.suspect):
                continue
            f = c.at_f + max(0, min(round((tb.us_to_frame(w.start_us, fps, mode="floor") - in_f) / c.speed), c.dur_f))
            t = float(Fraction(f) / fps)
            why = ", ".join(r for r, flag in (("unconfirmed name", w.vocab_suspect), ("low confidence", w.low_conf), ("timing", w.suspect)) if flag)
            out.append({"i": w.i, "text": w.text, "suggestion": w.vocab_suggestion, "frame": f, "at": f"{int(t // 60)}:{t % 60:05.2f}", "why": why})
    return out


BEAT_TOL_US = 45_000  # a cut within this of a beat reads as "on the beat"


def ramp_factor(r0: float, r1: float) -> float:
    """Output length / source length for a speed easing linearly (in source time) from r0 to r1."""
    import math

    if not r1 or abs(r1 - r0) < 1e-6:
        return 1.0 / r0
    return math.log(r1 / r0) / (r1 - r0)


def music_offset_us(meta: dict, cut_us: int, total_us: int, cuts_us: list[int] | None = None) -> int:
    """Where to start the track: a downbeat (a beat if none known) lands on the first cut, keeping
    enough track to cover the reel when possible. With all the cut times given, among the offsets
    that do that, pick the one that puts the most other cuts on a beat (cut-to-beat without ever
    moving a speech cut)."""
    beats = [int(b) * 1000 for b in (meta.get("downbeats_ms") or meta.get("beats_ms") or [])]
    every = sorted(int(b) * 1000 for b in (meta.get("beats_ms") or meta.get("downbeats_ms") or []))
    dur = int(meta.get("duration_ms", 0)) * 1000
    fits = [b - cut_us for b in beats if b >= cut_us and (not dur or dur - (b - cut_us) >= total_us)]
    if not fits:
        later = [b - cut_us for b in beats if b >= cut_us]
        return later[0] if later else 0
    if not cuts_us or len(cuts_us) < 2:
        return fits[0]
    import bisect

    def on_beat(off: int) -> int:
        n = 0
        for c in cuts_us:
            t = c + off
            k = bisect.bisect_left(every, t)
            n += any(0 <= j < len(every) and abs(every[j] - t) <= BEAT_TOL_US for j in (k - 1, k))
        return n

    return max(fits[:64], key=lambda off: (on_beat(off), -off))


PULSE_UP_F, PULSE_DOWN_F = 2, 7  # a pulse snaps in on the beat and settles over a quarter second


def add_beat_pulses(video: list[VideoClip], meta: dict, offset_us: int, total_f: int, fps: Fraction, strength: float) -> int:
    """A short zoom pulse on every downbeat of the bed, on top of whatever scale the shot has.
    Skipped where a punch-in is animating or a shot is too short to hold it. Returns pulses added."""
    downs = [int(b) * 1000 - offset_us for b in (meta.get("downbeats_ms") or [])]
    base = sorted((c for c in video if c.id.startswith("v_")), key=lambda c: c.at_f)
    added = 0
    for t in downs:
        f = tb.us_to_frame(t, fps)
        if not 0 < f < total_f:
            continue
        clip = next((c for c in base if c.at_f <= f < c.at_f + c.dur_f), None)
        if clip is None:
            continue
        k = f - clip.at_f
        if k + PULSE_UP_F + PULSE_DOWN_F >= clip.dur_f - clip.hold_f:
            continue
        if any(k - 2 <= kf.f <= k + PULSE_UP_F + PULSE_DOWN_F + 2 for kf in clip.scale):
            continue
        ks = sorted(clip.scale, key=lambda kf: kf.f)
        if any(a.f < k < b.f and b.ease != Ease.hold and a.v != b.v for a, b in zip(ks, ks[1:])):
            continue  # a punch-in is ramping here: a pulse would bend its curve
        v = 1.0
        for kf in sorted(clip.scale, key=lambda kf: kf.f):
            if kf.f <= k:
                v = kf.v
        if not clip.scale:
            clip.scale.append(Keyframe(f=0, v=1.0, ease=Ease.hold))
        clip.scale += [Keyframe(f=k, v=v, ease=Ease.hold), Keyframe(f=k + PULSE_UP_F, v=round(v * (1 + strength), 4), ease=Ease.ease_out),
                       Keyframe(f=k + PULSE_UP_F + PULSE_DOWN_F, v=v, ease=Ease.ease_in_out)]
        clip.scale.sort(key=lambda kf: kf.f)
        added += 1
    return added


def speech_regions(story: StoryPlan, by: dict[int, Word], word_out_frame, fps: Fraction, merge_us: int = 300_000) -> list[list[int]]:
    """Kept speech as merged [start, end) output-frame spans (for ducking)."""
    spans = sorted((word_out_frame(by[i], it.id), word_out_frame(by[i], it.id, end=True))
                   for it in story.items for i in range(it.word_start, it.word_end + 1))
    gap = tb.us_to_frame(merge_us, fps)
    out: list[list[int]] = []
    for s, e in spans:
        if out and s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def compile_timeline(
    story: StoryPlan,
    finish: FinishPlan | None,
    words: WordTable,
    clips: dict[str, ClipInfo],
    fps: Fraction,
    idx: Indexes,
    *,
    width: int = 1080,
    height: int = 1920,
    edges: dict[int, tuple[int, int]] | None = None,
    brand_family: str | None = None,
    brand_tokens: dict[str, str] | None = None,
    brand_look: str | None = None,
    word_fixes: dict[int, str] | None = None,
    brand_accent: str | None = None,
    brand_logo: str | None = None,
) -> Timeline:
    """Brand kit (family lock + tokens) overrides the Editor's caption choices (ADR-0017)."""
    finish = finish or empty_finish()
    by = words.by_index()
    assets: dict[str, Asset] = {c.id: Asset(id=c.id, kind=AssetKind.video, uri=c.uri, duration_us=c.duration_us) for c in clips.values()}

    # ---- base clips: word ranges → mezzanine frames → output grid. A line with long inner pauses
    # becomes several shots (pause tightening); every shot keeps its own words for provenance.
    max_pause_us = max(0, story.max_pause_ms) * 1000
    spans = []  # (item, shot no., in_f, out_f, first word, last word)
    for it in story.items:
        clip = clips.get(it.clip)
        item_words = [by.get(i) for i in range(it.word_start, it.word_end + 1)]
        if clip is None or not item_words or any(w is None or w.clip != it.clip for w in item_words):
            raise CompileError(f"item {it.id}: invalid clip/word range — run `reel validate` first")
        shots: list[list] = []
        for group in pause_groups(item_words, max_pause_us, edges):
            start_us, end_us = _source_range(group, words.clip_words(it.clip), clip, edges)
            in_f = tb.us_to_frame(start_us, fps, mode="floor")
            out_f = min(tb.us_to_frame(end_us, fps, mode="ceil"), tb.us_to_frame(clip.duration_us, fps, mode="floor"))
            if out_f <= in_f:
                out_f = in_f + 1
            if shots and in_f <= shots[-1][1]:  # the pause is shorter than a frame after padding: no cut
                shots[-1][1], shots[-1][3] = max(out_f, shots[-1][1]), group[-1].i
            else:
                shots.append([in_f, out_f, group[0].i, group[-1].i])
        spans += [(it, n, a, b, w0, w1) for n, (a, b, w0, w1) in enumerate(shots)]
    # validator: non-speech items only, 0.25–4×; a ramp uses its average rate for the length and word mapping
    rate = {sp.item: 1.0 / ramp_factor(sp.rate, sp.ramp_to) for sp in finish.speeds}
    ramp = {sp.item: (sp.rate, sp.ramp_to) for sp in finish.speeds if sp.ramp_to}
    hold = {h.item: h.frames for h in finish.holds}
    last_shot = {it.id: max(n for (i2, n, *_r) in spans if i2.id == it.id) for it in story.items}
    segments = tb.layout_segments([max(1, round((out - inn) / rate.get(it.id, 1.0))) + (hold.get(it.id, 0) if n == last_shot[it.id] else 0)
                                   for it, n, inn, out, _a, _b in spans])

    video: list[VideoClip] = []
    audio: list[AudioClip] = []
    item_seg: dict[str, list[tuple[int, int, int, int, int]]] = {}  # item id → shots (at_f, dur_f, in_f, first word, last word)
    vclips: dict[str, list[VideoClip]] = {}
    for (it, n, in_f, out_f, w0, w1), seg in zip(spans, segments):
        prov = Provenance(item=it.id, words=[w0, w1])
        sid = it.id if n == 0 else f"{it.id}.{n + 1}"
        r0, r1 = ramp.get(it.id, (rate.get(it.id, 1.0), 0.0))
        v = VideoClip(id=f"v_{sid}", asset=it.clip, at_f=seg.out_start, dur_f=seg.out_frames,
                      src_in_us=tb.frame_to_us(in_f, fps), src_out_us=tb.frame_to_us(out_f, fps), speed=r0, speed_to=r1,
                      hold_f=hold.get(it.id, 0) if n == last_shot[it.id] else 0, src=prov)
        video.append(v)
        audio.append(AudioClip(
            id=f"a_{sid}", asset=it.clip, at_f=seg.out_start, dur_f=seg.out_frames,
            src_in_us=tb.frame_to_us(in_f, fps), speed=rate.get(it.id, 1.0), role="voice", src=prov,
        ))
        item_seg.setdefault(it.id, []).append((seg.out_start, seg.out_frames, in_f, w0, w1))
        vclips.setdefault(it.id, []).append(v)
    total = segments[-1].out_end if segments else 0

    def shot_of(item_id: str, wi: int) -> int:
        shots = item_seg[item_id]
        return next((k for k, s in enumerate(shots) if s[3] <= wi <= s[4]), len(shots) - 1)

    def item_end(item_id: str) -> int:
        at_f, dur_f, *_ = item_seg[item_id][-1]
        return at_f + dur_f

    def word_out_frame(w: Word, item_id: str, *, end: bool = False) -> int:
        at_f, dur_f, in_f, _w0, _w1 = item_seg[item_id][shot_of(item_id, w.i)]
        f = tb.us_to_frame(w.end_us if end else w.start_us, fps, mode="ceil" if end else "floor") - in_f
        f = round(f / rate.get(item_id, 1.0))
        return at_f + max(0, min(f, dur_f))

    # ---- punch-ins (clip-relative keyframes); a punch holds through the rest of its line, across
    # the jump cuts that pause tightening made inside it
    by_shot: dict[tuple[str, int], list] = {}
    for p in finish.punch_ins:
        by_shot.setdefault((p.item, shot_of(p.item, p.at_word)), []).append(p)
    for item_id, shots in vclips.items():
        carried = 1.0
        for n, clip in enumerate(shots):
            ps = sorted(by_shot.get((item_id, n), []), key=lambda p: p.at_word)
            if ps or carried != 1.0:
                clip.scale.append(Keyframe(f=0, v=carried, ease=Ease.hold))
            for p in ps:
                k = word_out_frame(by[p.at_word], p.item) - clip.at_f
                if p.ramp_frames == 0:
                    clip.scale.append(Keyframe(f=k, v=p.scale, ease=Ease.hold))
                else:
                    clip.scale.append(Keyframe(f=k, v=clip.scale[-1].v, ease=p.ease))
                    clip.scale.append(Keyframe(f=min(k + p.ramp_frames, clip.dur_f), v=p.scale, ease=p.ease))
            if clip.scale:
                carried = clip.scale[-1].v

    # ---- transitions at cuts
    # ---- transitions at cuts: flashes are overlay events (Remotion), the rest need both shots (ffmpeg)
    transitions, flashes = [], []
    for t in finish.transitions:
        if t.type == TransitionType.flash:
            flashes.append(FlashEvent(id=t.id, at_f=item_end(t.after_item), frames=t.frames))
        else:
            transitions.append(TransitionEvent(id=t.id, at_f=item_end(t.after_item), type=t.type, frames=t.frames))

    # ---- hook title over the opening line
    titles = []
    if finish.hook_title.text.strip() and story.items:
        first_end = item_end(story.items[0].id)
        lo, hi = tb.us_to_frame(TITLE_MIN_US, fps, mode="ceil"), tb.us_to_frame(TITLE_MAX_US, fps)
        titles.append(TitleEvent(id="hook_title", text=finish.hook_title.text.strip(), start_f=0, end_f=min(max(first_end, lo), hi, total),
                                 layer="behind" if finish.hook_title.style == "behind" else "front"))

    # ---- captions on output frames
    family = brand_family if brand_family in idx.caption_families else finish.captions.family
    fam = idx.caption_families.get(family, {})
    max_words = int(fam.get("max_words", 3))
    editor_tokens = {tok.key: tok.value for tok in finish.captions.tokens} if family == finish.captions.family else {}
    tokens = {**(fam.get("tokens") or {}), **editor_tokens, **(brand_tokens or {})}
    emph = set(finish.captions.emphasis_words)
    cap_script = finish.captions.script
    kept = [by[i] for it in story.items for i in range(it.word_start, it.word_end + 1) if not by[i].filler]
    timing = "phrase" if unreliable_timing(kept) else "word"
    pages: list[CaptionPage] = []
    for it in story.items:
        ws = clean_caption_words([by[i] for i in range(it.word_start, it.word_end + 1) if not by[i].filler])
        # one line per page (pro reference: 1–3 word pages on a fixed line); fuller pages only when speech is fast
        for group in balanced_pages(ws, max_words, page_char_budget(tokens)):
            cw = [CaptionWord(i=w.i, text=caption_text((word_fixes or {}).get(w.i, w.text), cap_script), start_f=word_out_frame(w, it.id),
                              end_f=word_out_frame(w, it.id, end=True), emph=w.i in emph)
                  for w in group]
            start_f = cw[0].start_f
            end_f = max(cw[-1].end_f, start_f + tb.us_to_frame(MIN_CAPTION_US, fps, mode="ceil"))
            pages.append(CaptionPage(start_f=start_f, end_f=end_f, words=cw))
    # captions must not blink: a page holds through short pauses until the next page starts, and
    # stays at least PAGE_MIN_US (found on a real podcast: 0.2 s pages and gaps read as flicker)
    hold = tb.us_to_frame(PAGE_HOLD_US, fps)
    min_f = tb.us_to_frame(PAGE_MIN_US, fps, mode="ceil")
    for a, b in zip(pages, pages[1:]):
        if 0 < b.start_f - a.end_f <= hold:
            a.end_f = b.start_f
        a.end_f = max(a.end_f, min(a.start_f + min_f, b.start_f))
        if a.end_f > b.start_f:  # no overlapping pages
            a.end_f = b.start_f
    if pages:
        pages[-1].end_f = min(max(pages[-1].end_f, pages[-1].start_f + min_f), total)
    captions = CaptionTrack(family=family, tokens=tokens, script=cap_script, timing=timing, pages=pages)

    # ---- SFX, peak-aligned
    for c in finish.sfx:
        meta = idx.sfx[c.sfx]
        if c.anchor == SfxAnchor.cut_after_item:
            anchor_f = item_end(c.item)
        else:
            anchor_f = word_out_frame(by[c.word], c.item)
        peak_f = tb.us_to_frame(int(meta.get("peak_ms", 0)) * 1000, fps)
        dur_sfx = max(1, tb.us_to_frame(int(meta.get("duration_ms", 500)) * 1000, fps, mode="ceil"))
        start = anchor_f - peak_f
        skip_f = max(0, -start)  # anchor earlier than the sound's lead-in: drop the head so the peak still lands
        start = max(0, start)
        dur_sfx = min(dur_sfx - skip_f, total - start)
        if dur_sfx <= 0:
            continue
        assets.setdefault(c.sfx, Asset(id=c.sfx, kind=AssetKind.sfx, uri=meta.get("file", ""), duration_us=int(meta.get("duration_ms", 0)) * 1000))
        audio.append(AudioClip(id=c.id, asset=c.sfx, at_f=start, dur_f=dur_sfx, src_in_us=tb.frame_to_us(skip_f, fps), gain_db=c.gain_db, role="sfx"))

    # ---- music bed: a beat lands on the first cut; ducked under every kept speech span
    ducking = []
    if finish.music.track != "none":
        meta = idx.music[finish.music.track]
        assets.setdefault(finish.music.track, Asset(id=finish.music.track, kind=AssetKind.music, uri=meta.get("file", ""), duration_us=int(meta.get("duration_ms", 0)) * 1000))
        first_cut_us = tb.frame_to_us(segments[0].out_end, fps) if len(segments) > 1 else 0
        cuts_us = [tb.frame_to_us(sg.out_end, fps) for sg in segments[:-1]]
        offset_us = music_offset_us(meta, first_cut_us, tb.frame_to_us(total, fps), cuts_us)
        audio.append(AudioClip(id="music", asset=finish.music.track, at_f=0, dur_f=total, src_in_us=offset_us, gain_db=finish.music.gain_db, role="music"))
        ducking.append(Ducking(depth_db=finish.music.duck_db, regions_f=speech_regions(story, by, word_out_frame, fps)))
        if finish.beat_pulse > 0:
            add_beat_pulses(video, meta, offset_us, total, fps, finish.beat_pulse)

    # ---- b-roll: `full` replaces the base picture (ffmpeg), `pip` is a card in the overlay (Remotion)
    pips = []
    for b in finish.broll:
        from reel.broll import best_src_in_us

        meta = idx.broll[b.asset]
        start = word_out_frame(by[b.from_word], b.item)
        end = max(start + 1, word_out_frame(by[b.to_word], b.item, end=True))
        src_in = best_src_in_us(meta, tb.frame_to_us(end - start, fps))
        if b.mode == "pip":
            pips.append(PipEvent(id=b.id, uri=meta.get("file", ""), start_f=start, end_f=end, src_in_us=src_in))
            continue
        assets.setdefault(b.asset, Asset(id=b.asset, kind=AssetKind.video, uri=meta.get("file", ""), duration_us=int(meta.get("duration_ms", 0)) * 1000))
        video.append(VideoClip(id=f"br_{b.id}", asset=b.asset, at_f=start, dur_f=end - start, src_in_us=src_in,
                               src_out_us=src_in + tb.frame_to_us(end - start, fps), src=Provenance(item=b.item, words=[b.from_word, b.to_word])))

    # ---- footage effects on word windows (ffmpeg, after the cut)
    effects = []
    for e in finish.effects:
        start = word_out_frame(by[e.from_word], e.item)
        end = max(start + 2, word_out_frame(by[e.to_word], e.item, end=True))
        effects.append(EffectEvent(id=e.id, type=e.type.value, start_f=start, end_f=min(end, total), intensity=e.intensity))

    # ---- motion graphics (overlay): word windows; progress bar and logo span the whole reel
    accent = brand_accent or tokens.get("emph_color") or "#FFD400"
    graphics = []
    for g in finish.graphics:
        if g.kind.value in WHOLE_REEL_GRAPHICS:
            start, end = 0, total
        else:
            start = word_out_frame(by[g.from_word], g.item)
            min_us = GRAPHIC_MIN_US_BY_KIND.get(g.kind.value, GRAPHIC_MIN_US)
            end = max(start + tb.us_to_frame(min_us, fps, mode="ceil"), word_out_frame(by[g.to_word], g.item, end=True))
        if g.kind.value == "cta_card":
            end = total  # an end card stays to the last frame
        if g.kind.value == "logo_watermark" and not brand_logo:
            continue  # validated upstream; never draw an empty logo
        graphics.append(GraphicEvent(id=g.id, kind=g.kind.value, start_f=start, end_f=min(end, total), text=g.text.strip(), emoji=g.emoji.strip(),
                                     value=g.value, style=g.style, position=g.position, x=g.x, y=g.y, accent=accent,
                                     uri=brand_logo if g.kind.value == "logo_watermark" else ""))

    return Timeline(
        fps=f"{fps.numerator}/{fps.denominator}", width=width, height=height, duration_f=total,
        assets=assets, video=video, audio=audio, transitions=transitions, ducking=ducking, captions=captions,
        titles=titles, flashes=flashes, pips=pips, effects=effects, graphics=graphics,
        grade=Grade(look=brand_look or finish.grade.look, strength=finish.grade.strength if finish.grade.look != "none" or brand_look else 0.0,
                    grain=finish.grade.grain, vignette=finish.grade.vignette),
        plan_ref={"story": _digest(story), "finish": _digest(finish)},
    )


def dry_run(story: StoryPlan, words: WordTable, clips: dict[str, ClipInfo], fps: Fraction, idx: Indexes,
            edges: dict[int, tuple[int, int]] | None = None) -> str:
    """Read-back script Claude sees before committing a story (ADR-0016)."""
    tl = compile_timeline(story, None, words, clips, fps, idx, edges=edges)
    by = words.by_index()
    lines = []
    tightened = 0
    for it in story.items:
        shots = [c for c in tl.video if c.src.item == it.id]
        t0 = float(Fraction(shots[0].at_f) / fps)
        dur = float(Fraction(sum(c.dur_f for c in shots)) / fps)
        text = " ".join(by[i].text for i in range(it.word_start, it.word_end + 1))
        tightened += len(shots) - 1
        cut = f" [{len(shots) - 1} pause(s) cut]" if len(shots) > 1 else ""
        lines.append(f"[{t0:6.2f}s +{dur:5.2f}s] {it.id} ({it.beat}): {text}{cut}")
    total_s = float(Fraction(tl.duration_f) / fps)
    cuts = max(0, len(story.items) - 1)
    lines.append(f"TOTAL {total_s:.2f}s · {len(story.items)} items · {cuts} cuts + {tightened} pause cuts (max_pause_ms={story.max_pause_ms}) · "
                 f"{(cuts + tightened) / total_s * 60 if total_s else 0:.1f} cuts/min")
    return "\n".join(lines)
