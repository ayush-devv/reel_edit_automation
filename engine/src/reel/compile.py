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
    FlashEvent,
    Grade,
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
TITLE_MIN_US = 1_500_000  # hook title on screen at least this long …
TITLE_MAX_US = 3_000_000  # … and at most this long (or to the end of the first item, if sooner past the minimum)


@dataclass(frozen=True)
class ClipInfo:
    id: str
    uri: str  # mezzanine path relative to the workspace
    duration_us: int


class CompileError(ValueError):
    pass


def empty_finish(family: str = "bold_pop") -> FinishPlan:
    return FinishPlan(
        hook_title=HookTitle(text="", reason="default"), grade=GradePlan(look="none", strength=0.0, reason="default"), punch_ins=[], speeds=[], transitions=[],
        captions=CaptionPlan(family=family, tokens=[], emphasis_words=[], script="latin", reason="default"),
        sfx=[], music=MusicPlan(track="none", gain_db=-18, duck_db=12, reason="default"),
        broll=[], knowledge_used=[],
    )


def _digest(model) -> str:
    return hashlib.sha256(json.dumps(model.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()[:16]


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


def music_offset_us(meta: dict, cut_us: int, total_us: int) -> int:
    """Where to start the track so a beat (a downbeat if known) lands on the first cut, keeping
    enough track left to cover the reel when possible."""
    beats = [int(b) * 1000 for b in (meta.get("downbeats_ms") or meta.get("beats_ms") or [])]
    dur = int(meta.get("duration_ms", 0)) * 1000
    fits = [b - cut_us for b in beats if b >= cut_us and (not dur or dur - (b - cut_us) >= total_us)]
    if fits:
        return fits[0]
    later = [b - cut_us for b in beats if b >= cut_us]
    return later[0] if later else 0


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
) -> Timeline:
    """Brand kit (family lock + tokens) overrides the Editor's caption choices (ADR-0017)."""
    finish = finish or empty_finish()
    by = words.by_index()
    assets: dict[str, Asset] = {c.id: Asset(id=c.id, kind=AssetKind.video, uri=c.uri, duration_us=c.duration_us) for c in clips.values()}

    # ---- base clips: word ranges → mezzanine frames → output grid
    spans = []
    for it in story.items:
        clip = clips.get(it.clip)
        item_words = [by.get(i) for i in range(it.word_start, it.word_end + 1)]
        if clip is None or not item_words or any(w is None or w.clip != it.clip for w in item_words):
            raise CompileError(f"item {it.id}: invalid clip/word range — run `reel validate` first")
        start_us, end_us = _source_range(item_words, words.clip_words(it.clip), clip, edges)
        in_f = tb.us_to_frame(start_us, fps, mode="floor")
        out_f = min(tb.us_to_frame(end_us, fps, mode="ceil"), tb.us_to_frame(clip.duration_us, fps, mode="floor"))
        if out_f <= in_f:
            out_f = in_f + 1
        spans.append((it, in_f, out_f))
    rate = {sp.item: sp.rate for sp in finish.speeds}  # validator: non-speech items only, 0.25–4×
    segments = tb.layout_segments([max(1, round((out - inn) / rate.get(it.id, 1.0))) for it, inn, out in spans])

    video: list[VideoClip] = []
    audio: list[AudioClip] = []
    item_seg: dict[str, tuple[int, int, int]] = {}  # item id → (at_f, dur_f, in_f)
    for (it, in_f, out_f), seg in zip(spans, segments):
        prov = Provenance(item=it.id, words=[it.word_start, it.word_end])
        video.append(VideoClip(
            id=f"v_{it.id}", asset=it.clip, at_f=seg.out_start, dur_f=seg.out_frames,
            src_in_us=tb.frame_to_us(in_f, fps), src_out_us=tb.frame_to_us(out_f, fps), speed=rate.get(it.id, 1.0), src=prov,
        ))
        audio.append(AudioClip(
            id=f"a_{it.id}", asset=it.clip, at_f=seg.out_start, dur_f=seg.out_frames,
            src_in_us=tb.frame_to_us(in_f, fps), speed=rate.get(it.id, 1.0), role="voice", src=prov,
        ))
        item_seg[it.id] = (seg.out_start, seg.out_frames, in_f)
    total = segments[-1].out_end if segments else 0
    vclip = {c.src.item: c for c in video}

    def word_out_frame(w: Word, item_id: str, *, end: bool = False) -> int:
        at_f, dur_f, in_f = item_seg[item_id]
        f = tb.us_to_frame(w.end_us if end else w.start_us, fps, mode="ceil" if end else "floor") - in_f
        f = round(f / rate.get(item_id, 1.0))
        return at_f + max(0, min(f, dur_f))

    # ---- punch-ins (clip-relative keyframes)
    for p in sorted(finish.punch_ins, key=lambda p: (p.item, p.at_word)):
        clip = vclip[p.item]
        k = word_out_frame(by[p.at_word], p.item) - clip.at_f
        if not clip.scale:
            clip.scale.append(Keyframe(f=0, v=1.0, ease=Ease.hold))
        if p.ramp_frames == 0:
            clip.scale.append(Keyframe(f=k, v=p.scale, ease=Ease.hold))
        else:
            clip.scale.append(Keyframe(f=k, v=clip.scale[-1].v, ease=p.ease))
            clip.scale.append(Keyframe(f=min(k + p.ramp_frames, clip.dur_f), v=p.scale, ease=p.ease))

    # ---- transitions at cuts
    # ---- transitions at cuts: flashes are overlay events (Remotion), the rest need both shots (ffmpeg)
    transitions, flashes = [], []
    for t in finish.transitions:
        at_f, dur_f, _ = item_seg[t.after_item]
        if t.type == TransitionType.flash:
            flashes.append(FlashEvent(id=t.id, at_f=at_f + dur_f, frames=t.frames))
        else:
            transitions.append(TransitionEvent(id=t.id, at_f=at_f + dur_f, type=t.type, frames=t.frames))

    # ---- hook title over the opening line
    titles = []
    if finish.hook_title.text.strip() and story.items:
        first_end = item_seg[story.items[0].id][1]
        lo, hi = tb.us_to_frame(TITLE_MIN_US, fps, mode="ceil"), tb.us_to_frame(TITLE_MAX_US, fps)
        titles.append(TitleEvent(id="hook_title", text=finish.hook_title.text.strip(), start_f=0, end_f=min(max(first_end, lo), hi, total)))

    # ---- captions on output frames
    family = brand_family if brand_family in idx.caption_families else finish.captions.family
    fam = idx.caption_families.get(family, {})
    max_words = int(fam.get("max_words", 3))
    editor_tokens = {tok.key: tok.value for tok in finish.captions.tokens} if family == finish.captions.family else {}
    tokens = {**(fam.get("tokens") or {}), **editor_tokens, **(brand_tokens or {})}
    emph = set(finish.captions.emphasis_words)
    pages: list[CaptionPage] = []
    for it in story.items:
        ws = [by[i] for i in range(it.word_start, it.word_end + 1) if not by[i].filler]
        for k in range(0, len(ws), max_words):
            group = ws[k:k + max_words]
            cw = [CaptionWord(i=w.i, text=w.text, start_f=word_out_frame(w, it.id), end_f=word_out_frame(w, it.id, end=True), emph=w.i in emph)
                  for w in group]
            start_f = cw[0].start_f
            end_f = max(cw[-1].end_f, start_f + tb.us_to_frame(MIN_CAPTION_US, fps, mode="ceil"))
            pages.append(CaptionPage(start_f=start_f, end_f=end_f, words=cw))
    for a, b in zip(pages, pages[1:]):  # no overlapping pages
        if a.end_f > b.start_f:
            a.end_f = b.start_f
    captions = CaptionTrack(family=family, tokens=tokens, script=finish.captions.script, pages=pages)

    # ---- SFX, peak-aligned
    for c in finish.sfx:
        meta = idx.sfx[c.sfx]
        if c.anchor == SfxAnchor.cut_after_item:
            at_f, dur_f, _ = item_seg[c.item]
            anchor_f = at_f + dur_f
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
        offset_us = music_offset_us(meta, first_cut_us, tb.frame_to_us(total, fps))
        audio.append(AudioClip(id="music", asset=finish.music.track, at_f=0, dur_f=total, src_in_us=offset_us, gain_db=finish.music.gain_db, role="music"))
        ducking.append(Ducking(depth_db=finish.music.duck_db, regions_f=speech_regions(story, by, word_out_frame, fps)))

    # ---- b-roll over the base picture
    for b in finish.broll:
        meta = idx.broll[b.asset]
        start = word_out_frame(by[b.from_word], b.item)
        end = word_out_frame(by[b.to_word], b.item, end=True)
        assets.setdefault(b.asset, Asset(id=b.asset, kind=AssetKind.video, uri=meta.get("file", ""), duration_us=int(meta.get("duration_ms", 0)) * 1000))
        video.append(VideoClip(id=b.id, asset=b.asset, at_f=start, dur_f=max(1, end - start), src_in_us=0,
                               src_out_us=tb.frame_to_us(max(1, end - start), fps), src=Provenance(item=b.item, words=[b.from_word, b.to_word])))

    return Timeline(
        fps=f"{fps.numerator}/{fps.denominator}", width=width, height=height, duration_f=total,
        assets=assets, video=video, audio=audio, transitions=transitions, ducking=ducking, captions=captions,
        titles=titles, flashes=flashes,
        grade=Grade(look=brand_look or finish.grade.look, strength=finish.grade.strength if finish.grade.look != "none" or brand_look else 0.0),
        plan_ref={"story": _digest(story), "finish": _digest(finish)},
    )


def dry_run(story: StoryPlan, words: WordTable, clips: dict[str, ClipInfo], fps: Fraction, idx: Indexes,
            edges: dict[int, tuple[int, int]] | None = None) -> str:
    """Read-back script Claude sees before committing a story (ADR-0016)."""
    tl = compile_timeline(story, None, words, clips, fps, idx, edges=edges)
    by = words.by_index()
    lines = []
    for c, it in zip(tl.video, story.items):
        t0 = float(Fraction(c.at_f) / fps)
        dur = float(Fraction(c.dur_f) / fps)
        text = " ".join(by[i].text for i in range(it.word_start, it.word_end + 1))
        lines.append(f"[{t0:6.2f}s +{dur:5.2f}s] {it.id} ({it.beat}): {text}")
    total_s = float(Fraction(tl.duration_f) / fps)
    cuts = max(0, len(story.items) - 1)
    lines.append(f"TOTAL {total_s:.2f}s · {len(story.items)} items · {cuts} cuts · {cuts / total_s * 60 if total_s else 0:.1f} cuts/min")
    return "\n".join(lines)
