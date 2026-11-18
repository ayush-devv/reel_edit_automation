"""Client brief and brand kit (ADR-0017, ADR-0021). JSON files the owner fills in."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


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


class BrandColors(_Strict):
    primary: str | None = None
    secondary: str | None = None
    accent: str | None = None
    text: str | None = None


class Brand(_Strict):
    client: str
    fonts: dict[str, str] = Field(default_factory=dict)  # heading/body → font family or file
    colors: BrandColors = Field(default_factory=BrandColors)
    logo: str | None = None
    caption_family: str | None = None  # locks the family
    caption_tokens: dict[str, str] = Field(default_factory=dict)  # override palette-derived tokens
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
