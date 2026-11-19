"""Client brief and brand kit (ADR-0017, ADR-0021). JSON files the owner fills in."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Brief(_Strict):
    project: str
    client: str | None = None
    platform: str = "platform.instagram_reels"
    goal: str | None = None  # e.g. goal.watch_through, goal.cta_conversion
    audience: str | None = None
    genre_hint: str | None = None  # e.g. genre.testimonial
    target_length_s: tuple[float, float] = (15.0, 60.0)
    language: str | None = None  # en | hi | hinglish (None = detect)
    caption_script: str = "latin"  # latin | devanagari | mixed
    must_keep_lines: list[str] = Field(default_factory=list)
    cta: str | None = None
    product_names: list[str] = Field(default_factory=list)
    banned_claims: list[str] = Field(default_factory=list)
    tone: str | None = None
    vocabulary: list[str] = Field(default_factory=list)  # names/terms to spell correctly
    notes: str | None = None
    deliverables: list[str] = Field(default_factory=list)  # extra aspect ratios: feed_4x5 | square (9:16 master always)
    # licence gate (reel.licences): what the reel is for decides which assets it may use
    use_categories: list[str] = Field(default_factory=list)  # political | dating | drugs | alcohol | gambling | religious | adult
    purpose: str = "promo"  # editorial | organic | promo | paid_ad
    accept_credits: bool = True  # False: the client won't carry credits, so CC BY music/SFX are left out

    @field_validator("use_categories")
    @classmethod
    def _categories(cls, v: list[str]) -> list[str]:
        from reel.licences import CATEGORIES

        bad = [c for c in v if c not in CATEGORIES]
        if bad:
            raise ValueError(f"unknown client categories {bad}; use {', '.join(CATEGORIES)}")
        return v

    @field_validator("purpose")
    @classmethod
    def _purpose(cls, v: str) -> str:
        from reel.licences import PURPOSES

        if v not in PURPOSES:
            raise ValueError(f"purpose {v!r} must be one of {', '.join(PURPOSES)}")
        return v


class BrandColors(_Strict):
    """#RRGGBB only: the overlay computes contrast from these (a name or #FFF would give NaN luminance)."""

    primary: str | None = None
    secondary: str | None = None
    accent: str | None = None
    text: str | None = None

    @field_validator("primary", "secondary", "accent", "text")
    @classmethod
    def _hex(cls, v: str | None) -> str | None:
        import re

        if v is None:
            return v
        v = v.strip()
        if re.fullmatch(r"#[0-9a-fA-F]{3}", v):
            v = "#" + "".join(ch * 2 for ch in v[1:])
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError(f"brand colour {v!r} must be #RRGGBB")
        return v.upper()


class BrandVoice(_Strict):
    """How the client's posts read (copy pack, reel.copy). Every field optional: old brand kits stay valid."""

    tone: str | None = None  # e.g. "warm, direct, no jargon"
    caption_language: str | None = None  # en | hinglish_latin | hi_deva (None = follow the brief / the talk)
    hashtags_always: list[str] = Field(default_factory=list)  # on every post (counts toward Instagram's cap)
    hashtags_pool: list[str] = Field(default_factory=list)  # pick from these first
    banned_words: list[str] = Field(default_factory=list)
    emoji: str = "light"  # none | light | heavy
    handles: list[str] = Field(default_factory=list)  # @mentions the client wants tagged
    cta_lines: list[str] = Field(default_factory=list)  # the client's own calls to action

    @field_validator("caption_language")
    @classmethod
    def _lang(cls, v: str | None) -> str | None:
        if v is not None and v not in ("en", "hinglish_latin", "hi_deva"):
            raise ValueError("caption_language must be en, hinglish_latin or hi_deva")
        return v

    @field_validator("emoji")
    @classmethod
    def _emoji(cls, v: str) -> str:
        if v not in ("none", "light", "heavy"):
            raise ValueError("emoji must be none, light or heavy")
        return v

    @field_validator("hashtags_always", "hashtags_pool")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        import re

        out = []
        for t in v:
            t = t.strip().lstrip("#")
            if not re.fullmatch(r"\w+", t):
                raise ValueError(f"hashtag {t!r} must be letters, digits or _ only")
            out.append(t)
        return out


class Brand(_Strict):
    client: str
    voice: BrandVoice = Field(default_factory=BrandVoice)
    fonts: dict[str, str] = Field(default_factory=dict)  # heading/body → font family or file
    colors: BrandColors = Field(default_factory=BrandColors)
    logo: str | None = None
    caption_family: str | None = None  # locks the family
    caption_tokens: dict[str, str] = Field(default_factory=dict)  # override palette-derived tokens
    look: str | None = None  # locks the colour look (reel.color.LOOKS)
    end_card: str | None = None
    cta_style: str | None = None


def load_brief(path: str | Path | None) -> Brief | None:
    return Brief.model_validate_json(Path(path).read_text()) if path else None


def load_brand(path: str | Path | None) -> Brand | None:
    return Brand.model_validate_json(Path(path).read_text()) if path else None


def vocabulary(brief: Brief | None, brand: Brand | None, ocr_texts: list[str] | None = None) -> list[str]:
    """Terms the ASR must spell right (ADR-0021): brief + brand + on-screen text."""
    terms: list[str] = []
    if brief:
        terms += brief.product_names + brief.vocabulary + ([brief.client] if brief.client else [])
    if brand:
        terms.append(brand.client)
    for t in ocr_texts or []:
        # keep capitalised tokens from on-screen text (names, brands), skip long sentences
        terms += [tok.strip(".,!?:;") for tok in t.split() if tok[:1].isupper() and len(tok) > 2][:5]
    return terms


def brand_caption_overrides(brand: Brand | None) -> tuple[str | None, dict[str, str]]:
    """Brand kit → (locked caption family or None, caption tokens). Brand always wins (ADR-0017)."""
    if not brand:
        return None, {}
    tokens: dict[str, str] = {}
    if brand.colors.text:
        tokens["base_color"] = brand.colors.text
    if brand.colors.accent or brand.colors.primary:
        tokens["emph_color"] = brand.colors.accent or brand.colors.primary
    if brand.fonts.get("heading"):
        tokens["font"] = brand.fonts["heading"]
    tokens.update(brand.caption_tokens)
    return brand.caption_family, tokens
