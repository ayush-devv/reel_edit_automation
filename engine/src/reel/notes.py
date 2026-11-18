"""Client-note importer (build step 10d): timestamped notes on the review copy → one revision.

Accepts lines like "0:12 make this faster", "00:00:12 - remove the um", "12s: bigger captions",
"1:02.5 swap this line" and untimed lines (whole-reel notes). Each timed note is anchored to the
story item and the words on screen at that output time, so the Editor knows exactly what the
client is pointing at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from reel import timebase as tb
from reel.schemas.plan import StoryPlan
from reel.schemas.timeline import Timeline

_TC = re.compile(r"^\s*[\[(]?\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\s*[\])]?\s*[-–:,]?\s*(.+)$")
_SECS = re.compile(r"^\s*[\[(]?\s*(\d+(?:\.\d+)?)\s*s(?:ec)?\s*[\])]?\s*[-–:,]?\s*(.+)$", re.I)


@dataclass
class Note:
    t: float | None  # seconds into the reel; None = whole reel
    text: str


def parse(text: str) -> list[Note]:
    notes = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•*").strip()
        if not line:
            continue
        m = _TC.match(line)
        if m:
            h, mnt, sec, body = m.groups()
            notes.append(Note(int(h or 0) * 3600 + int(mnt) * 60 + float(sec), body.strip()))
            continue
        m = _SECS.match(line)
        if m:
            notes.append(Note(float(m.group(1)), m.group(2).strip()))
            continue
        notes.append(Note(None, line))
    return notes


def anchor(note: Note, tl: Timeline, story: StoryPlan, words) -> str:
    if note.t is None:
        return f"- (whole reel) {note.text}"
    fps = tb.parse_rate(tl.fps)
    f = int(Fraction(note.t).limit_denominator(1000) * fps)
    clip = next((c for c in tl.video if c.id.startswith("v_") and c.at_f <= f < c.at_f + c.dur_f), None)
    if clip is None:
        return f"- at {note.t:.2f}s (after the end) {note.text}"
    item = next(it for it in story.items if it.id == clip.src.item)
    by = words.by_index()
    on_screen = next((" ".join(w.text for w in p.words) for p in (tl.captions.pages if tl.captions else []) if p.start_f <= f < p.end_f), "")
    line = " ".join(by[i].text for i in range(item.word_start, item.word_end + 1))
    return (f"- at {note.t:.2f}s — item {item.id} ({item.beat}: “{line}”)"
            + (f", caption on screen “{on_screen}”" if on_screen else "") + f": {note.text}")


def revision_request(notes: list[Note], tl: Timeline, story: StoryPlan, words) -> str:
    body = "\n".join(anchor(n, tl, story, words) for n in notes)
    return ("The client reviewed the review copy and sent these notes (timecodes are reel time). "
            "Apply all of them in one revision; change nothing they did not ask for:\n" + body)
