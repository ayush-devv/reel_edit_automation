"""The wrong-number check (reel.numbers, roadmap G1.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from reel import numbers


def vals(text: str, confident_only: bool = False) -> list[Decimal]:
    return [n.value for n in numbers.parse(text) if n.confident or not confident_only]


def test_hindi_tables_cover_1_to_99():
    assert len(numbers.HI_DEVA) == 99 and len(numbers.HI_LATIN) == 99
    assert numbers.WORD_UNITS["पच्चीस"] == 25 and numbers.WORD_UNITS["pachchis"] == 25 and numbers.WORD_UNITS["निन्यानबे"] == 99


@pytest.mark.parametrize("text,expected", [
    ("₹2.5 crore", [Decimal("25000000")]),
    ("Rs 5,00,000", [Decimal("500000")]),
    ("500,000 users", [Decimal("500000")]),
    ("50k followers", [Decimal("50000")]),
    ("10L views", [Decimal("1000000")]),
    ("1.2M", [Decimal("1200000")]),
    ("70%", [Decimal("70")]),
    ("seventy percent", [Decimal("70")]),
    ("twenty five thousand", [Decimal("25000")]),
    ("one hundred and five", [Decimal("105")]),
    ("five lakh fifty thousand", [Decimal("550000")]),
    ("5 crore 20 lakh", [Decimal("52000000")]),
    ("a thousand people", [Decimal("1000")]),
    ("25 लाख", [Decimal("2500000")]),
    ("पच्चीस हज़ार", [Decimal("25000")]),
    ("२५ लाख", [Decimal("2500000")]),
    ("paanch lakh rupaye", [Decimal("500000")]),
    ("dhai crore", [Decimal("25000000")]),
    ("saadhe teen lakh", [Decimal("350000")]),
    ("sawa do sau", [Decimal("225")]),
    ("8 teaspoons and 10 more", [Decimal("8"), Decimal("10")]),
    ("lakhs of people", []),
    ("hundreds of reasons", []),
    ("no numbers here", []),
])
def test_parse(text, expected):
    assert vals(text) == expected


@pytest.mark.parametrize("text", ["in 2026", "open 24/7", "at 5:30", "3-5 days", "the 1st step", "10x faster", "COVID-19", "5G phones"])
# "4K video" is not here on purpose: in writing it can't be told from "4k" = 4,000; an unclear case stays a warning
# only when nothing is said nearby, and a speaker who says "4K" matches it.
def test_unclear_forms_are_never_confident(text):
    assert vals(text, confident_only=True) == []


def test_words_that_double_as_ordinary_words_are_not_confident_alone():
    assert vals("one of them", True) == [] and vals("do it now", True) == [] and vals("saath mein", True) == []
    assert vals("one lakh", True) == [Decimal("100000")]  # with a scale they are numbers
    assert vals("दो", True) == [Decimal("2")]  # Devanagari is unambiguous


def test_rounding_tolerance_follows_the_shown_precision():
    shown = numbers.parse("₹5 crore")[0]
    assert numbers.matches(shown, numbers.parse("4.97 crore")[0])  # said precisely, shown rounded
    assert not numbers.matches(numbers.parse("4.97 crore")[0], numbers.parse("5 crore")[0])  # never the other way
    assert not numbers.matches(numbers.parse("5 lakh")[0], numbers.parse("4 lakh")[0])
    assert numbers.matches(numbers.parse("50k")[0], numbers.parse("fifty thousand")[0])
    assert numbers.matches(numbers.parse("2.5 crore")[0], numbers.parse("25 million")[0])


def test_compare_verdicts():
    assert numbers.compare("₹5 lakh", "isne paanch lakh kamaye")[0] == "ok"
    status, detail = numbers.compare("₹5 lakh", "she made fifty thousand in a month")
    assert status == "mismatch" and "50000" not in detail[0] and "fifty thousand" in detail[1]
    assert numbers.compare("70%", "only 17 percent of people")[0] == "mismatch"
    assert numbers.compare("Top 3 tips", "here are three things")[0] == "ok"
    assert numbers.compare("5 habits", "these habits change everything")[0] == "unspoken"  # a warning, not an error
    assert numbers.compare("Since 2019", "we started in twenty nineteen")[0] == "ok"  # a year on screen is never confident
    assert numbers.compare("Follow for more", "anything 5")[0] == "ok"


def _card(text: str, kind: str = "keyword_card", value: float = 0.0, item: str = "k02", a: int = 18, b: int = 19):
    from reel.schemas.plan import Graphic, GraphicKind

    return Graphic(id=f"g{abs(hash((text, kind))) % 1000}", kind=GraphicKind(kind), item=item, from_word=a, to_word=b, text=text,
                   emoji="", value=value, style="pill" if kind == "keyword_card" else "", position="upper" if kind == "keyword_card" else "",
                   x=-1, y=-1, reason="r")


def test_plan_check_sends_clear_mismatches_back_and_only_warns_otherwise():
    from test_plan_compile import IDX, WORDS, _finish, _story  # k02 says "put ten percent into a separate account …"

    from reel.schemas.plan import HookTitle
    from reel.validate import errors, validate_finish

    story = _story()
    ok = validate_finish(_finish(graphics=[_card("10% of salary")]), story, WORDS, IDX)
    assert not [i for i in ok if i.code.startswith("number_")]
    bad = validate_finish(_finish(graphics=[_card("70% of salary")]), story, WORDS, IDX)
    assert [i.code for i in errors(bad) if i.code.startswith("number_")] == ["number_mismatch"]
    mism = [i for i in bad if i.code == "number_mismatch"][0]
    assert mism.path == "graphics[0].text" and "“70% of salary”" in mism.message and "ten percent" in mism.message
    counter = validate_finish(_finish(graphics=[_card("{n}%", kind="counter", value=10.0)]), story, WORDS, IDX)
    assert not [i for i in counter if i.code.startswith("number_")]
    # k01 only says "the one trick": "one" is unclear on its own, so "3 tricks" is a warning, "1 trick" passes
    warn = validate_finish(_finish(hook_title=HookTitle(text="3 tricks", style="card", reason="r")), story, WORDS, IDX)
    assert [(i.code, i.severity) for i in warn if i.code.startswith("number_")] == [("number_unspoken", "warning")]
    assert not [i for i in validate_finish(_finish(hook_title=HookTitle(text="1 trick", style="card", reason="r")), story, WORDS, IDX)
                if i.code.startswith("number_")]


def test_numbers_gate_is_a_warning_by_default():
    from test_plan_compile import WORDS, _finish, _story

    from reel import config, qa

    assert config.QA_GATES["numbers"] == "warn"
    r = qa.numbers_match(_finish(graphics=[_card("70%")]), _story(), WORDS)
    assert not r.ok and "70%" in r.detail and r.fixable
    assert qa.numbers_match(None, _story(), WORDS).ok


def test_counter_text_shows_the_landing_value():
    assert numbers.counter_text("₹{n} crore", 2.5) == "₹2.5 crore"
    assert numbers.counter_text("{n}%", 70.0) == "70%"
    assert numbers.counter_text("", 12.0) == "12"
