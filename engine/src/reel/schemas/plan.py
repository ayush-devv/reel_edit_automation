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
    # Pauses inside an item longer than this are cut out (jump cut). 0 keeps every pause (a deliberate
    # dramatic beat); 300–3000 otherwise (validated). Default 400 ms: dead air is the clearest amateur tell.
    max_pause_ms: int = 400


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
    dip_to_white = "dip_to_white"
    glitch = "glitch"


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
    grain: float = 0.0  # film grain over the whole reel, 0–0.6 (validated); 0.15–0.3 reads as texture, not noise
    vignette: float = 0.0  # darkened corners, 0–0.7 (validated); pulls the eye to the centre


class EffectType(str, Enum):
    shake = "shake"  # camera shake that decays over the window (impact, punchline)
    rgb_split = "rgb_split"  # chromatic RGB split (tech / glitchy energy), short
    light_leak = "light_leak"  # warm light leak washing over the frame (nostalgic, dreamy, a reveal)
    exposure_pulse = "exposure_pulse"  # a bright flash-pulse on the first word (a hit, a beat)


class Effect(_Strict):
    id: str
    type: EffectType
    item: str  # story item
    from_word: int  # window starts at this word …
    to_word: int  # … and ends with this word (same item)
    intensity: float  # 0–1 (validated)
    reason: str


class GraphicKind(str, Enum):
    emoji_pop = "emoji_pop"  # an emoji pops in on a word (emoji); position upper_left | upper_right | beside_face
    keyword_card = "keyword_card"  # 1–4 big words animate in (text); style pill | under | marker | box | plain; position upper | center
    lower_third = "lower_third"  # name tag (text "Name · Role"); style bar | tag
    callout = "callout"  # hand-drawn mark: style circle | box | underline | arrow; position face (around the speaker) or point (x, y); text = optional label
    counter = "counter"  # a number counts up to `value`; text holds the format with {n}, e.g. "₹{n} crore", "{n}%"
    text_card = "text_card"  # full-screen card with kinetic text (≤ 8 words): a chapter / list beat; style dark | light | color
    cta_card = "cta_card"  # end card over the last line (text, e.g. "Follow for part 2"); style bar | card
    progress_bar = "progress_bar"  # thin bar filling across the top for the whole reel (words ignored)
    logo_watermark = "logo_watermark"  # the brand logo in a corner for the whole reel (needs a brand logo; words ignored)


class Graphic(_Strict):
    id: str
    kind: GraphicKind
    item: str  # story item (for whole-reel kinds: the first item)
    from_word: int  # appears on this word …
    to_word: int  # … and leaves after this word (same item)
    text: str  # "" when the kind has no text
    emoji: str  # one emoji for emoji_pop, else ""
    value: float  # counter target, else 0
    style: str  # per kind (see GraphicKind); "" = the kind's default
    position: str  # per kind (see GraphicKind); "" = the kind's default
    x: float  # callout point target, normalised output frame 0–1; -1 = not used
    y: float
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
    effects: list[Effect] = []  # footage effects on a word window (validated: limits per type)
    graphics: list[Graphic] = []  # motion graphics in the overlay (validated per kind)


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
