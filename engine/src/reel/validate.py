"""`reel validate`: semantic checks the JSON Schema cannot express (ADR-0016, ADR-0030).

Every issue names the field (`path`), the rule (`code`), what is wrong (`message`) and a
concrete `fix`, so a resumed Claude call can correct the plan without guessing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass

from reel.assets import Indexes
from reel.schemas.perception import WordTable
from reel.schemas.plan import FinishPlan, PatchOpKind, SfxAnchor, StoryPatch, StoryPlan

SCRIPTS = {"latin", "devanagari", "mixed"}
BROLL_MODES = {"full", "pip"}
TITLE_MAX_CHARS = 42
TITLE_MAX_WORDS = 7


@dataclass
class Issue:
    code: str
    path: str
    message: str
    fix: str
    severity: str = "error"  # error | warning

    def as_dict(self) -> dict:
        return asdict(self)


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]


def norm(text: str) -> str:
    """Case/punctuation-insensitive comparison key (keeps Devanagari letters and marks)."""
    text = unicodedata.normalize("NFC", text).casefold()
    return re.sub(r"[^\wऀ-ॿ]+", "", text)


HEX = r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?"
TOKEN_RULES = {
    "stroke": (rf"true|false|{HEX}", '"true", "false" or a hex colour like #000000'),
    "box": (rf"true|false|{HEX}", '"true", "false" or a hex colour like #000000B3'),
    "case": ("upper|lower|sentence|title", "upper | lower | sentence | title"),
    "highlight": ("word|scale|none", "word | scale | none"),
    "anim": ("pop|fade|slide_fade", "pop | fade | slide_fade"),
    "zone": ("lower_middle|lower_third|beside_face", "lower_middle | lower_third | beside_face"),
    "weight": (r"[1-9]00", "a font weight 100–900"),
    "anim_ms": (r"\d{2,4}", "milliseconds, e.g. 150"),
    "emph_scale": (r"\d(\.\d+)?", "a number like 1.4"),
}


def token_rule(key: str) -> tuple[str, str] | None:
    """Value contract for caption tokens (the overlay renderer only understands these values)."""
    if key.endswith("_color") or key in ("speaker_a", "speaker_b"):
        return HEX, "a hex colour like #FFD400"
    return TOKEN_RULES.get(key)


def _range_check(issues: list[Issue], path: str, value: float, lo: float, hi: float, what: str) -> None:
    if not (lo <= value <= hi):
        issues.append(Issue("out_of_range", path, f"{what} {value} is outside {lo}–{hi}.", f"Set {path} between {lo} and {hi}."))


def _nearest_match(words: WordTable, clip: str, idx: int, quote: str, window: int = 8) -> int | None:
    target = norm(quote)
    if not target:
        return None
    by = words.by_index()
    for d in range(0, window + 1):
        for j in (idx - d, idx + d):
            w = by.get(j)
            if w and w.clip == clip and norm(w.text) == target:
                return j
    return None


# ------------------------------------------------------------------ story


def validate_story(plan: StoryPlan, words: WordTable, clips: set[str], knowledge_ids: set[str] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    by = words.by_index()
    if not plan.items:
        issues.append(Issue("empty_plan", "items", "The plan keeps no material.", "Add at least one keep item."))
        return issues

    seen: set[str] = set()
    for n, it in enumerate(plan.items):
        p = f"items[{n}]"
        if not it.id or it.id in seen:
            issues.append(Issue("duplicate_id", f"{p}.id", f"Item id '{it.id}' is empty or repeated.", "Give every item a unique id like 'k07'."))
        seen.add(it.id)
        if it.clip not in clips:
            issues.append(Issue("unknown_clip", f"{p}.clip", f"Clip '{it.clip}' does not exist.", f"Use one of: {sorted(clips)}."))
            continue
        if it.word_start > it.word_end:
            issues.append(Issue("reversed_range", p, f"word_start {it.word_start} > word_end {it.word_end}.", "Swap them or fix the indices."))
            continue
        for field_name, idx, quote in (("word_start", it.word_start, it.first_word), ("word_end", it.word_end, it.last_word)):
            w = by.get(idx)
            if w is None:
                issues.append(Issue("unknown_word", f"{p}.{field_name}", f"Word index {idx} does not exist.", "Use indices from the word table."))
                continue
            if w.clip != it.clip:
                issues.append(Issue("word_clip_mismatch", f"{p}.{field_name}", f"Word {idx} belongs to clip {w.clip}, not {it.clip}.", f"Set clip to {w.clip} or pick a word from {it.clip}."))
            if norm(w.text) != norm(quote):
                near = _nearest_match(words, it.clip, idx, quote)
                fix = (f"Did you mean index {near}? Set {field_name}={near}." if near is not None
                       else f"Quote the actual word at {idx}: '{w.text}', or fix the index.")
                issues.append(Issue("quote_mismatch", f"{p}.{field_name}", f"Quoted '{quote}' but word {idx} is '{w.text}'.", fix))

    # overlapping reuse of the same words
    spans = sorted(((it.clip, it.word_start, it.word_end, it.id) for it in plan.items if it.word_start <= it.word_end))
    for (c1, s1, e1, id1), (c2, s2, e2, id2) in zip(spans, spans[1:]):
        if c1 == c2 and s2 <= e1:
            issues.append(Issue("overlap", f"items[{id2}]", f"Items {id1} and {id2} both use words {s2}–{min(e1, e2)}.",
                                "Trim one item so no word is used twice (repeat a line only via a deliberate b-roll/callback)."))

    if plan.max_pause_ms and not 300 <= plan.max_pause_ms <= 3000:
        issues.append(Issue("out_of_range", "max_pause_ms", f"max_pause_ms {plan.max_pause_ms} is outside 300–3000.",
                            "Use 0 to keep every pause, or 300–3000 (400 is a tight talking-head default)."))

    # hooks
    opt_ids = [h.id for h in plan.hook_options]
    if len(set(opt_ids)) != len(opt_ids):
        issues.append(Issue("duplicate_id", "hook_options", "Hook option ids repeat.", "Give each hook option a unique id."))
    item_ids = {it.id for it in plan.items}
    for n, h in enumerate(plan.hook_options):
        if h.item not in item_ids:
            issues.append(Issue("unknown_item", f"hook_options[{n}].item", f"Hook option points at missing item '{h.item}'.", "Point it at a keep item id."))
    chosen = next((h for h in plan.hook_options if h.id == plan.hook), None)
    if chosen is None:
        issues.append(Issue("unknown_hook", "hook", f"Chosen hook '{plan.hook}' is not among hook_options.", f"Use one of {opt_ids}."))
    elif plan.items and chosen.item != plan.items[0].id:
        issues.append(Issue("hook_not_first", "items[0]", f"The chosen hook item '{chosen.item}' is not the first item.", f"Move item '{chosen.item}' to the start of items."))

    if knowledge_ids is not None:
        for k in plan.knowledge_used:
            if k not in knowledge_ids:
                issues.append(Issue("unknown_knowledge", "knowledge_used", f"'{k}' is not a knowledge node id.", "Cite ids from the provided playbook.", "warning"))
    return issues


# ------------------------------------------------------------------ finish


GRAPHIC_STYLES = {
    "emoji_pop": ({""}, {"", "upper_left", "upper_right", "beside_face"}),
    "keyword_card": ({"", "pill", "under", "marker", "box", "plain"}, {"", "upper", "center"}),
    "lower_third": ({"", "bar", "tag"}, {""}),
    "callout": ({"", "circle", "box", "underline", "arrow"}, {"", "face", "point"}),
    "counter": ({""}, {"", "upper", "center"}),
    "text_card": ({"", "dark", "light", "color"}, {""}),
    "cta_card": ({"", "bar", "card"}, {""}),
    "progress_bar": ({""}, {""}),
    "logo_watermark": ({""}, {"", "top_left", "top_right"}),
}
GRAPHIC_MAX_WORDS = {"keyword_card": 4, "lower_third": 6, "callout": 3, "counter": 4, "text_card": 8, "cta_card": 6}
GRAPHICS_MAX = 12


EFFECT_MAX_MS = {"shake": 1500, "rgb_split": 700, "light_leak": 3500, "exposure_pulse": 1500}
EFFECTS_MAX = 6


def validate_finish(fin: FinishPlan, story: StoryPlan, words: WordTable, idx: Indexes, knowledge_ids: set[str] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    items = {it.id: it for it in story.items}
    order = [it.id for it in story.items]
    by = words.by_index()
    ids: set[str] = set()

    def uid(path: str, value: str) -> None:
        if not value or value in ids:
            issues.append(Issue("duplicate_id", path, f"Id '{value}' is empty or repeated in the finish plan.", "Use unique ids (e.g. p01, s01, t01)."))
        ids.add(value)

    def need_item(path: str, item_id: str) -> bool:
        if item_id not in items:
            issues.append(Issue("unknown_item", path, f"Story item '{item_id}' does not exist.", f"Use one of {order}."))
            return False
        return True

    def in_item(path: str, item_id: str, word: int) -> None:
        it = items[item_id]
        if not (it.word_start <= word <= it.word_end):
            issues.append(Issue("word_outside_item", path, f"Word {word} is outside item {item_id} ({it.word_start}–{it.word_end}).",
                                f"Pick a word between {it.word_start} and {it.word_end}."))

    title = fin.hook_title.text.strip()
    if len(title) > TITLE_MAX_CHARS or len(title.split()) > TITLE_MAX_WORDS:
        issues.append(Issue("title_too_long", "hook_title.text", f"Hook title '{title}' has {len(title)} chars / {len(title.split())} words.",
                            f"Cut it to ≤ {TITLE_MAX_WORDS} words and ≤ {TITLE_MAX_CHARS} characters — a viewer reads it in under 2 s."))
    if fin.hook_title.style not in ("card", "behind"):
        issues.append(Issue("bad_title_style", "hook_title.style", f"Style '{fin.hook_title.style}' is not supported.", "Use card or behind."))
    unconfirmed = {norm(w.original_text or w.text) for w in words.words if w.vocab_suspect}
    if title and any(norm(tok) in unconfirmed for tok in title.split()):
        issues.append(Issue("title_unconfirmed_name", "hook_title.text", "The hook title uses a name the ASR could not confirm.",
                            "Use the confirmed spelling from the brief, or leave the name out."))

    from reel.color import LOOKS

    if fin.grade.look not in LOOKS:
        issues.append(Issue("unknown_look", "grade.look", f"Look '{fin.grade.look}' does not exist.", f"Use one of {sorted(LOOKS)}."))
    _range_check(issues, "grade.strength", fin.grade.strength, 0.0, 1.0, "Look strength")

    for n, p in enumerate(fin.punch_ins):
        path = f"punch_ins[{n}]"
        uid(f"{path}.id", p.id)
        if need_item(f"{path}.item", p.item):
            in_item(f"{path}.at_word", p.item, p.at_word)
        _range_check(issues, f"{path}.scale", p.scale, 1.0, 2.0, "Scale")
        _range_check(issues, f"{path}.ramp_frames", p.ramp_frames, 0, 120, "Ramp")

    for n, s in enumerate(fin.speeds):
        path = f"speeds[{n}]"
        uid(f"{path}.id", s.id)
        _range_check(issues, f"{path}.rate", s.rate, 0.25, 4.0, "Speed")
        if s.ramp_to:
            _range_check(issues, f"{path}.ramp_to", s.ramp_to, 0.25, 4.0, "Ramp target speed")
        if need_item(f"{path}.item", s.item):
            it = items[s.item]
            spoken = [w for i in range(it.word_start, it.word_end + 1) if (w := by.get(i)) and not w.filler]
            if spoken:
                issues.append(Issue("speed_on_speech", f"{path}.item", f"Item {s.item} contains speech; speech is never retimed (ADR-0015).",
                                    "Remove this speed change, or apply it to b-roll / non-speech action only."))

    for n, t in enumerate(fin.transitions):
        path = f"transitions[{n}]"
        uid(f"{path}.id", t.id)
        if need_item(f"{path}.after_item", t.after_item) and t.after_item == order[-1]:
            issues.append(Issue("transition_after_last", f"{path}.after_item", "There is no cut after the last item.", "Attach it to an earlier item."))
        _range_check(issues, f"{path}.frames", t.frames, 2, 15, "Transition length")

    cap = fin.captions
    fam = idx.caption_families.get(cap.family)
    if fam is None:
        issues.append(Issue("unknown_family", "captions.family", f"Caption family '{cap.family}' does not exist.", f"Use one of {sorted(idx.caption_families)}."))
    else:
        allowed = set((fam.get("tokens") or {}).keys())
        for n, tok in enumerate(cap.tokens):
            if tok.key not in allowed:
                issues.append(Issue("unknown_token", f"captions.tokens[{n}].key", f"Token '{tok.key}' is not part of family {cap.family}.", f"Use one of {sorted(allowed)}."))
                continue
            rule = token_rule(tok.key)
            if rule and not re.fullmatch(rule[0], tok.value):
                issues.append(Issue("bad_token_value", f"captions.tokens[{n}].value", f"Token '{tok.key}' = '{tok.value}' is not valid.", f"Use {rule[1]}."))
    if cap.script not in SCRIPTS:
        issues.append(Issue("bad_script", "captions.script", f"Script '{cap.script}' is not supported.", f"Use one of {sorted(SCRIPTS)}."))
    kept = {i for it in story.items for i in range(it.word_start, it.word_end + 1)}
    for n, w in enumerate(cap.emphasis_words):
        if w not in kept:
            issues.append(Issue("emphasis_not_kept", f"captions.emphasis_words[{n}]", f"Word {w} is not in the edit.", "Emphasise only words that are kept."))

    for n, c in enumerate(fin.sfx):
        path = f"sfx[{n}]"
        uid(f"{path}.id", c.id)
        if c.sfx not in idx.sfx:
            issues.append(Issue("unknown_sfx", f"{path}.sfx", f"SFX '{c.sfx}' is not in the library.", "Pick an id from the SFX index."))
        if need_item(f"{path}.item", c.item):
            if c.anchor == SfxAnchor.word:
                in_item(f"{path}.word", c.item, c.word)
            elif c.word != -1:
                issues.append(Issue("anchor_word_unused", f"{path}.word", "word must be -1 when anchor is cut_after_item.", "Set word to -1."))
        _range_check(issues, f"{path}.gain_db", c.gain_db, -30, 0, "SFX gain")

    m = fin.music
    if m.track != "none" and m.track not in idx.music:
        issues.append(Issue("unknown_music", "music.track", f"Track '{m.track}' is not in the music library.", "Pick an id from the music index or 'none'."))
    if m.track != "none":
        _range_check(issues, "music.gain_db", m.gain_db, -30, -6, "Music gain")
        _range_check(issues, "music.duck_db", m.duck_db, 6, 24, "Ducking depth")

    held = set()
    for n, h in enumerate(fin.holds):
        path = f"holds[{n}]"
        uid(f"{path}.id", h.id)
        need_item(f"{path}.item", h.item)
        _range_check(issues, f"{path}.frames", h.frames, 6, 45, "Hold")
        if h.item in held:
            issues.append(Issue("duplicate_hold", path, f"Item {h.item} already has a hold.", "Keep one hold per item."))
        held.add(h.item)
    _range_check(issues, "beat_pulse", fin.beat_pulse, 0.0, 0.08, "Beat pulse")
    if fin.beat_pulse > 0 and fin.music.track == "none":
        issues.append(Issue("pulse_without_music", "beat_pulse", "Beat pulses need a music bed.", "Set beat_pulse to 0 or pick a track."))
    _range_check(issues, "grade.grain", fin.grade.grain, 0.0, 0.6, "Grain")
    _range_check(issues, "grade.vignette", fin.grade.vignette, 0.0, 0.7, "Vignette")
    for n, e in enumerate(fin.effects):
        path = f"effects[{n}]"
        uid(f"{path}.id", e.id)
        _range_check(issues, f"{path}.intensity", e.intensity, 0.0, 1.0, "Effect intensity")
        if need_item(f"{path}.item", e.item):
            in_item(f"{path}.from_word", e.item, e.from_word)
            in_item(f"{path}.to_word", e.item, e.to_word)
            if e.from_word <= e.to_word and by.get(e.from_word) and by.get(e.to_word):
                dur_ms = (by[e.to_word].end_us - by[e.from_word].start_us) / 1000
                cap = EFFECT_MAX_MS[e.type.value]
                if dur_ms > cap:
                    issues.append(Issue("effect_too_long", path, f"{e.type.value} spans {dur_ms:.0f} ms; the limit is {cap} ms.",
                                        f"Shorten the word window — {e.type.value} only works as a short accent."))
        if e.from_word > e.to_word:
            issues.append(Issue("reversed_range", path, "from_word is after to_word.", "Swap them."))
    if len(fin.effects) > EFFECTS_MAX:
        issues.append(Issue("too_many_effects", "effects", f"{len(fin.effects)} effects in one reel.",
                            f"Keep at most {EFFECTS_MAX}: effects lose their punch when they are everywhere.", "warning"))

    issues += validate_graphics(fin, items, order, uid, need_item, in_item, idx)

    for n, b in enumerate(fin.broll):
        path = f"broll[{n}]"
        uid(f"{path}.id", b.id)
        if b.asset not in idx.broll:
            issues.append(Issue("unknown_broll", f"{path}.asset", f"B-roll '{b.asset}' is not in the library.", "Pick an id from the b-roll index."))
        if need_item(f"{path}.item", b.item):
            in_item(f"{path}.from_word", b.item, b.from_word)
            in_item(f"{path}.to_word", b.item, b.to_word)
        if b.from_word > b.to_word:
            issues.append(Issue("reversed_range", f"{path}", "from_word is after to_word.", "Swap them."))
        elif b.asset in idx.broll and need_item(f"{path}.item", b.item) and by.get(b.from_word) and by.get(b.to_word):
            need_us = by[b.to_word].end_us - by[b.from_word].start_us
            have_us = int(idx.broll[b.asset].get("duration_ms", 0)) * 1000
            if have_us and need_us > have_us:
                issues.append(Issue("broll_too_short", f"{path}", f"B-roll {b.asset} is {have_us / 1e6:.1f} s but the words span {need_us / 1e6:.1f} s.",
                                    "Cover fewer words, or pick a longer clip."))
        if b.mode not in BROLL_MODES:
            issues.append(Issue("bad_mode", f"{path}.mode", f"Mode '{b.mode}' is not supported.", f"Use one of {sorted(BROLL_MODES)}."))

    if knowledge_ids is not None:
        for k in fin.knowledge_used:
            if k not in knowledge_ids:
                issues.append(Issue("unknown_knowledge", "knowledge_used", f"'{k}' is not a knowledge node id.", "Cite ids from the provided playbook.", "warning"))
    return issues


# ------------------------------------------------------------------ patches


def apply_story_patch(plan: StoryPlan, patch: StoryPatch) -> tuple[StoryPlan, list[Issue]]:
    """Apply insert/replace/delete ops by item id. Untouched items are carried over unchanged."""
    items = list(plan.items)
    issues: list[Issue] = []

    def pos(item_id: str) -> int | None:
        return next((k for k, it in enumerate(items) if it.id == item_id), None)

    for n, op in enumerate(patch.ops):
        path = f"ops[{n}]"
        if op.op == PatchOpKind.delete:
            k = pos(op.target)
            if k is None:
                issues.append(Issue("unknown_item", f"{path}.target", f"Cannot delete missing item '{op.target}'.", "Use an existing item id."))
            else:
                items.pop(k)
        elif op.op == PatchOpKind.replace:
            k = pos(op.target)
            if k is None or op.item is None:
                issues.append(Issue("bad_replace", path, "replace needs an existing target and an item.", "Set target to an existing id and provide item."))
            else:
                items[k] = op.item
        elif op.op == PatchOpKind.insert:
            if op.item is None:
                issues.append(Issue("bad_insert", path, "insert needs an item.", "Provide the new item."))
                continue
            if op.after == "^":
                items.insert(0, op.item)
            else:
                k = pos(op.after)
                if k is None:
                    issues.append(Issue("unknown_item", f"{path}.after", f"Cannot insert after missing item '{op.after}'.", "Use an existing item id or '^'."))
                else:
                    items.insert(k + 1, op.item)
    return plan.model_copy(update={"items": items}), issues


def validate_graphics(fin, items, order, uid, need_item, in_item, idx, has_logo: bool | None = None) -> list[Issue]:
    issues: list[Issue] = []
    from reel.compile import WHOLE_REEL_GRAPHICS

    seen_whole: set[str] = set()
    for n, g in enumerate(fin.graphics):
        path, kind = f"graphics[{n}]", g.kind.value
        uid(f"{path}.id", g.id)
        styles, positions = GRAPHIC_STYLES[kind]
        if g.style not in styles:
            issues.append(Issue("bad_style", f"{path}.style", f"Style '{g.style}' is not valid for {kind}.", f"Use one of {sorted(styles)}."))
        if g.position not in positions:
            issues.append(Issue("bad_position", f"{path}.position", f"Position '{g.position}' is not valid for {kind}.", f"Use one of {sorted(positions)}."))
        if kind in WHOLE_REEL_GRAPHICS:
            if kind in seen_whole:
                issues.append(Issue("duplicate_graphic", path, f"Only one {kind} per reel.", "Remove the extra one."))
            seen_whole.add(kind)
        elif need_item(f"{path}.item", g.item):
            in_item(f"{path}.from_word", g.item, g.from_word)
            in_item(f"{path}.to_word", g.item, g.to_word)
            if g.from_word > g.to_word:
                issues.append(Issue("reversed_range", path, "from_word is after to_word.", "Swap them."))
        words = len(g.text.split())
        if kind in GRAPHIC_MAX_WORDS and words > GRAPHIC_MAX_WORDS[kind]:
            issues.append(Issue("graphic_text_too_long", f"{path}.text", f"{kind} text has {words} words.",
                                f"Cut it to ≤ {GRAPHIC_MAX_WORDS[kind]} words — on-screen text is read in a glance."))
        needs_text = {"keyword_card", "lower_third", "text_card", "cta_card", "counter"}
        if kind in needs_text and not g.text.strip():
            issues.append(Issue("graphic_needs_text", f"{path}.text", f"{kind} needs text.", "Write the on-screen text."))
        if kind == "emoji_pop":
            from reel import emoji as emoji_mod

            if not g.emoji.strip():
                issues.append(Issue("graphic_needs_emoji", f"{path}.emoji", "emoji_pop needs one emoji.", "Put a single emoji in `emoji`."))
            elif emoji_mod.ICON_SET.exists() and emoji_mod.name(g.emoji) is None:
                issues.append(Issue("unknown_emoji", f"{path}.emoji", f"'{g.emoji}' is not a single standard emoji.",
                                    "Use one standard emoji character (no text, no custom sequences)."))
        if kind == "counter":
            if "{n}" not in g.text:
                issues.append(Issue("counter_format", f"{path}.text", "Counter text must contain {n} where the number goes.", 'E.g. "{n}%" or "₹{n} crore".'))
            if g.value <= 0:
                issues.append(Issue("counter_value", f"{path}.value", "Counter value must be positive.", "Set the number it counts up to."))
        if kind == "callout" and g.position == "point" and not (0 <= g.x <= 1 and 0 <= g.y <= 1):
            issues.append(Issue("callout_point", path, "A point callout needs x and y between 0 and 1 (fractions of the source frame on the contact sheet).",
                                "Read the point off the contact sheet, or use position face."))
        if kind == "counter" and g.value > 0 and round(g.value, 2) != g.value:
            issues.append(Issue("counter_decimals", f"{path}.value", f"Counter value {g.value} has more than 2 decimals.",
                                "Round it the way it is said (the counter shows the exact number)."))
        if kind == "cta_card" and g.item != order[-1]:
            issues.append(Issue("cta_not_last", f"{path}.item", "The CTA card belongs on the last item.", f"Use item {order[-1]}."))
    issues += _top_band_clashes(fin, items, order)
    if len(fin.graphics) > GRAPHICS_MAX:
        issues.append(Issue("too_many_graphics", "graphics", f"{len(fin.graphics)} graphics in one reel.",
                            f"Keep at most {GRAPHICS_MAX}: graphics compete with the speaker.", "warning"))
    return issues


TOP_BAND = {("lower_third", ""), ("lower_third", "bar"), ("lower_third", "tag"), ("emoji_pop", ""), ("emoji_pop", "upper_left"),
            ("emoji_pop", "upper_right"), ("counter", ""), ("counter", "upper"), ("keyword_card", ""), ("keyword_card", "upper"),
            ("cta_card", ""), ("cta_card", "bar")}


def _band(g) -> bool:
    key = (g.kind.value, g.position if g.kind.value != "lower_third" else g.style)
    return (g.kind.value, g.position) in TOP_BAND or key in TOP_BAND


def _top_band_clashes(fin, items, order) -> list[Issue]:
    """Graphics placed in the top band must not share it in time: with each other, or with the hook title over
    the opening line (both would draw in the same place)."""
    from reel.compile import WHOLE_REEL_GRAPHICS

    issues = []
    tops = [(n, g) for n, g in enumerate(fin.graphics) if g.kind.value not in WHOLE_REEL_GRAPHICS and _band(g) and g.item in items]
    if fin.hook_title.text.strip() and order:
        for n, g in tops:
            if g.item == order[0]:
                issues.append(Issue("graphic_under_title", f"graphics[{n}]", f"{g.kind.value} sits in the top band during the opening line, "
                                    "where the hook title is.", "Move it to a later item, use position center/beside_face, or drop the hook title."))
    for (n1, a), (n2, b) in ((x, y) for i, x in enumerate(tops) for y in tops[i + 1:]):
        if a.item == b.item and a.from_word <= b.to_word and b.from_word <= a.to_word:
            issues.append(Issue("graphics_overlap", f"graphics[{n2}]", f"{b.kind.value} and {a.kind.value} (graphics[{n1}]) share the top band at the same time.",
                                "Give them different words, or move one to another position."))
    return issues
