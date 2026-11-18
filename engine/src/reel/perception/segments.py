"""Phrase segmentation of the word table (the units Claude references as `seg_id`)."""

from __future__ import annotations

from reel.schemas.perception import Segment, SegmentTable, WordTable

PAUSE_US = 500_000
MAX_WORDS = 28
SENTENCE_END = (".", "?", "!", "।", "…")


def build_segments(words: WordTable, pause_us: int = PAUSE_US, max_words: int = MAX_WORDS) -> SegmentTable:
    segs: list[Segment] = []
    current: list = []

    def flush() -> None:
        if current:
            segs.append(Segment(
                seg_id=f"s{len(segs) + 1:03d}", clip=current[0].clip,
                word_start=current[0].i, word_end=current[-1].i,
                start_us=current[0].start_us, end_us=current[-1].end_us,
            ))
            current.clear()

    for w in words.words:
        if current:
            prev = current[-1]
            if (w.clip != prev.clip or w.start_us - prev.end_us >= pause_us or prev.text.endswith(SENTENCE_END)
                    or (w.speaker and prev.speaker and w.speaker != prev.speaker) or len(current) >= max_words):
                flush()
        current.append(w)
    flush()
    return SegmentTable(segments=segs)
