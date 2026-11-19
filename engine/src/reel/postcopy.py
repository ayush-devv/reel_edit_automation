"""Post copy pack (roadmap G1.1): Instagram caption, hashtags, first comment, YouTube Shorts title and description.

One small Claude call per edit (persona `personas/copywriter.md`), checked in code; one re-ask with the problems
listed, then the pack is kept as `needs_review` with its problems (copy never blocks a delivery).
Credits a licence requires are added by code at package time (`credited`), never by Claude.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

PERSONA = Path(__file__).parent / "personas" / "copywriter.md"
IG_CAPTION_MAX = 2200
# Instagram cap on hashtags per post/Reel, caption + comments together (reported from Dec 2025; not confirmed on
# Instagram's Help Center as of 2026-11-20 — one constant to change)
IG_HASHTAG_MAX = 5
YT_TITLE_MAX = 100
YT_DESC_MAX = 5000
GENERIC_TAGS = {"viral", "fyp", "foryou", "foryoupage", "trending", "explore", "explorepage", "reels", "reel", "instagood"}
_TAG = re.compile(r"#(\w+)")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U0001F900-\U0001F9FF]")


class CopyPack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ig_caption: str
    hashtags: list[str]
    first_comment: str
    yt_title: str
    yt_description: str


def schema() -> dict:
    s = {"type": "string"}
    return {"type": "object", "additionalProperties": False,
            "required": ["ig_caption", "hashtags", "first_comment", "yt_title", "yt_description"],
            "properties": {"ig_caption": {**s, "maxLength": IG_CAPTION_MAX}, "first_comment": {**s, "maxLength": 300},
                           "hashtags": {"type": "array", "maxItems": IG_HASHTAG_MAX, "items": {**s, "maxLength": 40}},
                           "yt_title": {**s, "maxLength": YT_TITLE_MAX}, "yt_description": {**s, "maxLength": YT_DESC_MAX}}}


def language(brief, brand) -> str:
    """Which language and script the copy is written in: the brand's choice, else the brief's."""
    if brand and brand.voice.caption_language:
        return brand.voice.caption_language
    if brief and brief.caption_script == "devanagari":
        return "hi_deva"
    if brief and brief.language in ("hi", "hinglish"):
        return "hinglish_latin"
    return "en"


LANGUAGE_TEXT = {"en": "English", "hinglish_latin": "Hinglish written in Latin (English) letters",
                 "hi_deva": "Hindi in Devanagari script (English words the speaker uses may stay in Latin letters)"}


def prompt(kept_text: str, summary: str, brief, brand, problems: list[str] | None = None) -> str:
    v = brand.voice if brand else None
    lines = ["Write the post copy for this reel.", "",
             f"Language and script: {LANGUAGE_TEXT[language(brief, brand)]}.", "",
             "## Words kept in the reel", "", kept_text.strip() or "(none)", "",
             "## What the talk is about", "", summary.strip() or "(no summary)", ""]
    if brief:
        b = {k: val for k, val in brief.model_dump(exclude_none=True).items()
             if k in ("client", "goal", "audience", "cta", "tone", "product_names", "banned_claims", "notes") and val}
        lines += ["## Client brief", "", json.dumps(b, ensure_ascii=False, indent=1), ""]
    if v:
        lines += ["## Brand voice", "", json.dumps({"client": brand.client, **v.model_dump(exclude_defaults=False)}, ensure_ascii=False, indent=1), "",
                  f"Hashtags: always include {', '.join(v.hashtags_always) or 'none'}; at most {IG_HASHTAG_MAX} in total.", ""]
    if problems:
        lines += ["## Your previous answer had these problems — fix every one", "", *(f"- {p}" for p in problems), ""]
    return "\n".join(lines)


def _norm_tag(t: str) -> str:
    return t.strip().lstrip("#")


def problems(pack: CopyPack, brief, brand, credits: list[str] | None = None) -> list[str]:
    """Hard rules the copy must meet; [] = good. Checked on the credited caption, which is what gets posted."""
    out: list[str] = []
    v = brand.voice if brand else None
    tags = [_norm_tag(t) for t in pack.hashtags]
    inline = _TAG.findall(pack.ig_caption) + _TAG.findall(pack.first_comment)
    total = {t.casefold() for t in tags + inline}
    if len(total) > IG_HASHTAG_MAX:
        out.append(f"{len(total)} hashtags in caption + first comment; Instagram allows {IG_HASHTAG_MAX}")
    if inline:
        out.append("hashtags belong in `hashtags`, not inside the caption or first comment")
    bad = [t for t in tags if not re.fullmatch(r"\w+", t)]
    if bad:
        out.append(f"hashtags must be letters, digits or _ only: {bad}")
    if len({t.casefold() for t in tags}) != len(tags):
        out.append("a hashtag is repeated")
    generic = sorted({t for t in tags if t.casefold() in GENERIC_TAGS})
    if generic:
        out.append(f"generic hashtags add nothing: {generic}")
    if v:
        missing = [t for t in v.hashtags_always if t.casefold() not in {x.casefold() for x in tags}]
        if missing:
            out.append(f"the brand's always-on hashtags are missing: {missing}")
    caption = credited_caption(pack.ig_caption, tags, credits or [])
    if len(caption) > IG_CAPTION_MAX:
        out.append(f"the caption is {len(caption)} characters with hashtags and credits; Instagram allows {IG_CAPTION_MAX} — shorten it")
    if len(pack.yt_title) > YT_TITLE_MAX:
        out.append(f"the YouTube title is over {YT_TITLE_MAX} characters")
    if len(pack.yt_description) > YT_DESC_MAX:
        out.append(f"the YouTube description is over {YT_DESC_MAX} characters")
    text = "\n".join([pack.ig_caption, pack.first_comment, pack.yt_title, pack.yt_description])
    low = text.casefold()
    for w in (v.banned_words if v else []):
        if re.search(rf"(?<!\w){re.escape(w.casefold())}(?!\w)", low):
            out.append(f"banned word used: {w!r}")
    for claim in (brief.banned_claims if brief else []):
        if claim.strip() and claim.casefold() in low:
            out.append(f"banned claim used: {claim!r}")
    if v and v.emoji == "none" and _EMOJI.search(text):
        out.append("the brand uses no emoji")
    if brief and brief.cta:
        words = [w for w in re.findall(r"\w+", brief.cta.casefold()) if len(w) >= 4]
        if words and sum(w in pack.ig_caption.casefold() for w in words) < max(1, len(words) // 2):
            out.append(f"the caption should end with the brief's call to action: {brief.cta!r}")
    return out


def credited_caption(caption: str, tags: list[str], credits: list[str]) -> str:
    parts = [caption.strip()]
    if tags:
        parts.append(" ".join(f"#{_norm_tag(t)}" for t in tags))
    if credits:
        parts.append("\n\n".join(credits))
    return "\n\n".join(parts)


def credited(pack: dict, credits: list[str]) -> dict:
    """What gets posted: hashtags and the licence credits appended by code (Claude never writes credits)."""
    p = CopyPack.model_validate({k: pack[k] for k in CopyPack.model_fields})
    desc = p.yt_description.strip() + ("\n\n" + "\n\n".join(credits) if credits else "")
    return {"ig_caption": credited_caption(p.ig_caption, p.hashtags, credits), "first_comment": p.first_comment.strip(),
            "hashtags": [_norm_tag(t) for t in p.hashtags], "yt_title": p.yt_title.strip(), "yt_description": desc,
            "credits": credits, "status": pack.get("status", "ok"), "problems": pack.get("problems", [])}


def markdown(c: dict) -> str:
    warn = ""
    if c.get("problems"):
        warn = "> **Check before posting** — the copywriter's answer still had problems:\n" + "".join(f"> - {p}\n" for p in c["problems"]) + "\n"
    return (f"# Post copy\n\n{warn}## Instagram caption\n\n{c['ig_caption']}\n\n## First comment\n\n{c['first_comment']}\n\n"
            f"## YouTube Shorts title\n\n{c['yt_title']}\n\n## YouTube Shorts description\n\n{c['yt_description']}\n")


def write(ws_root: Path, caller, *, kept_text: str, summary: str, brief, brand, credits: list[str] | None = None,
          log_file: Path | None = None) -> dict:
    """Claude's draft + its check. Never raises: a failed call is recorded as status `failed`."""
    issues: list[str] | None = None
    pack = None
    for attempt in range(2):
        try:
            res = caller(prompt(kept_text, summary, brief, brand, issues), schema(), cwd=ws_root, persona_file=PERSONA,
                         effort="low", log_file=log_file, label="copy" if attempt == 0 else "copy_retry")
            pack = CopyPack.model_validate(res.data)
        except Exception as exc:  # noqa: BLE001 — copy is a convenience; the reel is delivered without it
            if pack is None:
                return {"status": "failed", "reason": str(exc)[:300]}
            break
        issues = problems(pack, brief, brand, credits)
        if not issues:
            return {**pack.model_dump(), "status": "ok", "problems": []}
    return {**pack.model_dump(), "status": "needs_review", "problems": issues or []}
