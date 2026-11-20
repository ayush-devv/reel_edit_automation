"""Which overlay frames a revision changed (reel.rediff, roadmap G1.5)."""

from __future__ import annotations

import copy

from reel.rediff import PAD_F, changed_ranges


def _page(a: int, b: int, *words: str) -> dict:
    return {"start_f": a, "end_f": b, "words": [{"i": k, "text": w, "start_f": a, "end_f": b, "emph": False} for k, w in enumerate(words)]}


def _props() -> dict:
    return {"fps": 30.0, "width": 1080, "height": 1920, "duration_f": 900, "faces": [], "safe": {"top": 0.1},
            "captions": {"family": "bold_pop", "tokens": {}, "script": "latin", "timing": "word",
                         "pages": [_page(0, 40, "so"), _page(40, 80, "today"), _page(200, 240, "money"), _page(240, 280, "every"),
                                   _page(600, 640, "end")]},
            "titles": [{"id": "t1", "text": "Hook", "start_f": 0, "end_f": 60, "role": "hook", "layer": "front"}],
            "flashes": [], "pips": [],
            "graphics": [{"id": "g1", "kind": "keyword_card", "start_f": 400, "end_f": 460, "text": "10%"},
                         {"id": "g2", "kind": "emoji_pop", "start_f": 450, "end_f": 500, "text": ""}]}


def test_no_baseline_or_a_global_change_renders_everything():
    new = _props()
    assert changed_ranges(None, new) is None
    for mutate in (lambda p: p["captions"].update(family="clean_phrase"), lambda p: p.update(faces=[{"start_f": 0}]),
                   lambda p: p.update(duration_f=901), lambda p: p.update(layer="behind")):
        old = _props()
        mutate(new := _props())
        assert changed_ranges(old, new) is None


def test_nothing_changed():
    assert changed_ranges(_props(), _props()) == []


def test_one_caption_word_takes_its_page_and_back_to_back_neighbours():
    old, new = _props(), _props()
    new["captions"]["pages"][2] = _page(200, 240, "MONEY")
    # page 200–240 changed; 240–280 touches it and joins; 40–80 is 120 frames earlier and stays
    assert changed_ranges(old, new) == [(200 - PAD_F, 280 + PAD_F)]


def test_a_graphic_change_pulls_in_what_overlaps_it():
    old, new = _props(), _props()
    new["graphics"][0]["text"] = "17%"
    assert changed_ranges(old, new) == [(400 - PAD_F, 500 + PAD_F)]  # g2 overlaps g1, so its frames re-render too


def test_added_and_removed_elements():
    old, new = _props(), _props()
    new["titles"] = []
    new["flashes"] = [{"id": "f1", "start_f": 700, "end_f": 704}]
    assert changed_ranges(old, new) == [(0, 80 + PAD_F), (700 - PAD_F, 704 + PAD_F)]


def test_back_to_back_pages_do_not_chain_into_a_full_render():
    """A long run of touching caption pages (normal in a talking-head reel): one changed page re-renders itself, its
    neighbours and at most one more page each side, never the whole reel (the chain reaction fixed in 3b.3)."""
    pages = [_page(k * 40, k * 40 + 40, f"w{k}") for k in range(22)]  # 0–880, all touching
    old = _props() | {"captions": _props()["captions"] | {"pages": pages}, "titles": [], "graphics": []}
    new = copy.deepcopy(old)
    new["captions"]["pages"][10] = _page(400, 440, "CHANGED")
    r = changed_ranges(old, new)
    assert r is not None and len(r) == 1 and r[0][0] >= 320 - PAD_F and r[0][1] <= 520 + PAD_F


def test_too_much_change_is_a_full_render():
    old, new = _props(), copy.deepcopy(_props())
    new["graphics"].append({"id": "g9", "kind": "text_card", "start_f": 0, "end_f": 899, "text": "x"})
    assert changed_ranges(old, new) is None
