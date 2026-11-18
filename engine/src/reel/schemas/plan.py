"""What Claude writes (ADR-0016). Exported as JSON Schema for `claude -p --json-schema`.

Structured-output constraints (ADR-0030 / Claude docs): no recursion, no numeric bounds in
the schema (ranges are enforced by `reel validate`), `additionalProperties: false`, and as
few optional fields as possible. Every item has a stable `id` and a `reason`.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ pass 1: story


class HookOption(_Strict):
    id: str  # e.g. "h1"
    item: str  # story item id that would open the reel
    rank: int  # 1 = best
    reason: str


class KeepItem(_Strict):
    id: str  # stable, e.g. "k01"
    clip: str  # mezzanine clip id
    word_start: int  # global word index (inclusive)
    word_end: int  # global word index (inclusive)
    first_word: str  # quote of word_start — checked against the word table
    last_word: str  # quote of word_end — checked against the word table
    beat: str  # story beat name: hook, setup, point, proof, payoff, cta ...
    reason: str


class StoryPlan(_Strict):
    genre: str  # e.g. genre.testimonial
    summary: str  # one-line story of the reel
    hook_options: list[HookOption]
    hook: str  # id of the chosen hook option; its item must be items[0]
    items: list[KeepItem]  # in output order
    knowledge_used: list[str]  # knowledge node ids that drove decisions (failure attribution)


# ------------------------------------------------------------------ pass 2: finish


class Ease(str, Enum):
    hold = "hold"  # instant
    linear = "linear"
    ease_in = "ease_in"
    ease_out = "ease_out"
    ease_in_out = "ease_in_out"


class PunchIn(_Strict):
    id: str
    item: str  # story item id
    at_word: int  # word where the punch starts (inside the item)
    scale: float  # 1.0–2.0 (validated)
    ramp_frames: int  # 0 = instant punch
    ease: Ease
    reason: str


class Speed(_Strict):
    id: str
    item: str
    rate: float  # 0.25–4.0 (validated); never on speech (validated)
    reason: str


class TransitionType(str, Enum):
    cut = "cut"
    zoom = "zoom"
    whip = "whip"
    blur = "blur"
    flash = "flash"
    dip_to_black = "dip_to_black"


class Transition(_Strict):
    id: str
    after_item: str  # transition at the cut after this item
    type: TransitionType
    frames: int  # 2–15 (validated)
    reason: str


class Token(_Strict):
    key: str
    value: str


class CaptionPlan(_Strict):
    family: str  # caption style family id
    # Family token overrides (colour, font, zone …), validated against the family.
    # A list of key/value objects, not a dict: structured outputs allow additionalProperties=false only.
    tokens: list[Token]
    emphasis_words: list[int]  # global word indices to emphasise
    script: str  # "latin" | "devanagari" | "mixed"
    reason: str


class SfxAnchor(str, Enum):
    cut_after_item = "cut_after_item"
    word = "word"


class SfxCue(_Strict):
    id: str
    sfx: str  # id in assets/sfx/sfx_index.json
    anchor: SfxAnchor
    item: str  # story item (cut after it, or containing the word)
    word: int  # global word index when anchor == word, else -1
    gain_db: float  # -30 … 0 (validated)
    reason: str


class MusicPlan(_Strict):
    track: str  # id in assets/music/music_index.json, or "none"
    gain_db: float  # bed level before ducking, -30 … -6 (validated)
    duck_db: float  # extra attenuation under speech, 6 … 24 (validated)
    reason: str


class Broll(_Strict):
    id: str
    asset: str  # id in the owned b-roll library
    item: str
    from_word: int
    to_word: int
    mode: str  # "full" | "pip"
    reason: str


class HookTitle(_Strict):
    text: str  # on-screen title over the opening line; "" = none (≤ 42 chars, ≤ 7 words — validated)
    style: str  # "card" (boxed title, upper third) | "behind" (huge text behind the person's head; needs a visible person)
    reason: str


class GradePlan(_Strict):
    look: str  # id from the look list in context/finish_context.md, or "none"
    strength: float  # 0–1 (validated); 0.3–0.6 is typical
    reason: str


class FinishPlan(_Strict):
    hook_title: HookTitle
    grade: GradePlan
    punch_ins: list[PunchIn]
    speeds: list[Speed]
    transitions: list[Transition]
    captions: CaptionPlan
    sfx: list[SfxCue]
    music: MusicPlan
    broll: list[Broll]
    knowledge_used: list[str]


# ------------------------------------------------------------------ revisions


class PatchOpKind(str, Enum):
    insert = "insert"
    replace = "replace"
    delete = "delete"


class StoryPatchOp(_Strict):
    op: PatchOpKind
    target: str  # item id to replace/delete, or "" for insert
    after: str  # insert after this item id ("^" = at the start); "" otherwise
    item: KeepItem | None  # required for insert/replace


class StoryPatch(_Strict):
    request: str  # the user's revision request, verbatim
    ops: list[StoryPatchOp]
    reason: str


class Revision(_Strict):
    """A chat revision: story ops (possibly none) + the complete new finish plan."""

    story_patch: StoryPatch
    finish: FinishPlan
    reply: str  # one line for the owner: what changed
