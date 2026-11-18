"""Perception outputs the planner and compiler read (produced for real in build step 3).

All times are microseconds on the clip's **mezzanine** clock (ADR-0015).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Word(BaseModel):
    model_config = ConfigDict(extra="forbid")
    i: int  # global index across the project, stable
    clip: str  # clip id, e.g. "c01"
    text: str
    start_us: int
    end_us: int
    prob: float = 1.0
    speaker: str | None = None
    filler: bool = False  # non-lexical filler (um/uh/hmm) — safe to cut
    candidate_filler: bool = False  # lexical filler (matlab/toh/like…) — Claude judges in context
    suspect: bool = False  # word spans a pause or > 1.2 s — timing needs realignment
    low_conf: bool = False  # ASR probability < 0.5 — check against vocabulary / proof list
    original_text: str | None = None  # ASR text before vocabulary correction
    vocab_suspect: bool = False  # looks like a name/brand that is not confirmed by the vocabulary → proof list
    vocab_suggestion: str | None = None  # closest vocabulary term, if any


class WordTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str | None = None
    words: list[Word]

    def by_index(self) -> dict[int, Word]:
        return {w.i: w for w in self.words}

    def clip_words(self, clip: str) -> list[Word]:
        return [w for w in self.words if w.clip == clip]


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seg_id: str
    clip: str
    word_start: int
    word_end: int
    start_us: int
    end_us: int


class SegmentTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segments: list[Segment]
