"""Hindi sentence ends (। and ॥) count like full stops in captions (roadmap G1.3)."""

from __future__ import annotations

from reel.compile import _break_cost, balanced_pages, clean_caption_words
from reel.schemas.perception import Word


def _words(text: str, gap_us: int = 60_000) -> list[Word]:
    out, t = [], 0
    for i, tok in enumerate(text.split()):
        out.append(Word(i=i, clip="c01", text=tok, start_us=t, end_us=t + 280_000))
        t += 280_000 + gap_us  # tight speech: no pause hint, only punctuation tells where a sentence ends
    return out


def test_a_page_prefers_to_end_at_the_danda():
    ws = _words("मैंने रोज़ जूस पिया। फिर सब बदल गया")
    assert _break_cost(ws[3], ws[4]) == 0.0  # after "पिया।": free, like after a full stop
    pages = balanced_pages(ws, max_words=4)
    assert [w.text for w in pages[0]] == ["मैंने", "रोज़", "जूस", "पिया।"]


def test_double_danda_and_stutters():
    ws = _words("यह सच है॥ अब सुनो")
    assert _break_cost(ws[2], ws[3]) == 0.0
    cleaned = clean_caption_words(_words("जूस। जूस नहीं"))
    assert [w.text for w in cleaned] == ["जूस।", "नहीं"]  # "जूस। जूस" is a stutter once the danda is ignored
