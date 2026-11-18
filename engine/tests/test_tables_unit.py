from fractions import Fraction

import numpy as np

from reel import assets
from reel.compile import ClipInfo, compile_timeline
from reel.perception.edges import snap_word_edges
from reel.perception.segments import build_segments
from reel.schemas.perception import Word, WordTable
from reel.schemas.plan import HookOption, KeepItem, StoryPlan
from reel.selects import find_takes
from reel.tables import script_md, segment_rows, words_tsv

RATE = 16_000


def W(i, text, s, e, clip="c01", **kw):
    return Word(i=i, clip=clip, text=text, start_us=s, end_us=e, **kw)


def _tone(segments, total_s=3.0):
    pcm = np.random.default_rng(0).normal(0, 0.001, int(total_s * RATE)).astype(np.float32)  # noise floor
    for a, b in segments:
        t = np.arange(int(a * RATE), int(b * RATE))
        pcm[t] += 0.3 * np.sin(2 * np.pi * 220 * t / RATE)
    return pcm


def test_snap_moves_edges_to_heard_sound():
    pcm = _tone([(0.5, 1.5)])
    w = W(0, "hello", 600_000, 1_300_000)  # ASR late start, early end
    (s, e), = snap_word_edges([w], pcm).values()
    assert abs(s - 500_000) <= 20_000 and abs(e - 1_500_000) <= 20_000


def test_snap_never_crosses_neighbours():
    pcm = _tone([(0.5, 1.0), (1.05, 1.6)])
    a, b = W(0, "one", 550_000, 950_000), W(1, "two", 1_100_000, 1_550_000)
    edges = snap_word_edges([a, b], pcm)
    assert edges[0][1] <= b.start_us and edges[1][0] >= a.end_us


def test_snap_keeps_asr_edges_in_silence():
    pcm = np.zeros(RATE * 2, np.float32)
    w = W(0, "x", 500_000, 900_000)
    assert snap_word_edges([w], pcm)[0] == (500_000, 900_000)


def _retake_words():
    lines = [
        ("Today I will show you a", 0.0, False),             # restart (unfinished, short)
        ("Today I will show you one simple trick.", 3.0, False),
        ("Today I will show you one simple trick to save money.", 7.0, False),
        ("Put ten percent away every month.", 12.0, False),
    ]
    words, i = [], 0
    for text, t0, _ in lines:
        t = t0
        for tok in text.split():
            words.append(W(i, tok, int(t * 1e6), int((t + 0.25) * 1e6), prob=0.95))
            t += 0.3
            i += 1
    return WordTable(words=words)


def test_takes_grouped_and_ranked():
    wt = _retake_words()
    segs = build_segments(wt)
    takes = find_takes(wt, segs)
    assert len(takes["groups"]) == 1
    g = takes["groups"][0]
    assert [m["take"] for m in g["members"]] == [1, 2, 3]
    first = g["members"][0]
    assert "unfinished" in first["flags"] and "restart" in first["flags"]
    best = min(g["members"], key=lambda m: m["suggested_rank"])
    assert best["take"] in (2, 3)  # a complete take wins
    assert "s004" not in takes["by_segment"]  # the unrelated line is not a take


def test_script_markers_and_tsv():
    wt = WordTable(words=[
        W(0, "um", 0, 200_000, filler=True), W(1, "I", 300_000, 400_000), W(2, "love", 450_000, 700_000, low_conf=True),
        W(3, "Dioma.", 750_000, 1_100_000, vocab_suspect=True, vocab_suggestion="DearMa"),
        W(4, "Wortham", 2_000_000, 2_400_000, original_text="Wortam"),
    ])
    segs = build_segments(wt)
    rows = segment_rows(wt, segs, [], {"by_segment": {}}, {}, {}, {})
    md = script_md(wt, segs, rows)
    assert "{um}" in md and "love(?)" in md and "⚠Dioma.→DearMa" in md and "Wortham[asr:Wortam]" in md
    assert "(… 0.9 s)" in md
    tsv = words_tsv(wt, {3: (760_000, 1_150_000)})
    assert tsv.splitlines()[0].startswith("i\tclip") and "\t760\t1150\t" in tsv and "proof" in tsv


def test_compiler_uses_heard_edges():
    wt = WordTable(words=[W(0, "a", 1_000_000, 1_400_000), W(1, "b", 1_500_000, 1_900_000), W(2, "c", 3_000_000, 3_400_000)])
    story = StoryPlan(genre="g", summary="s", hook_options=[HookOption(id="h", item="k1", rank=1, reason="r")], hook="h",
                      items=[KeepItem(id="k1", clip="c01", word_start=0, word_end=1, first_word="a", last_word="b", beat="hook", reason="r")],
                      knowledge_used=[])
    clips = {"c01": ClipInfo("c01", "mezz/c01.mov", 5_000_000)}
    plain = compile_timeline(story, None, wt, clips, Fraction(30), assets.load())
    heard = compile_timeline(story, None, wt, clips, Fraction(30), assets.load(),
                             edges={0: (900_000, 1_400_000), 1: (1_500_000, 2_100_000), 2: (2_900_000, 3_400_000)})
    assert heard.video[0].src_in_us < plain.video[0].src_in_us  # earlier heard onset
    assert heard.video[0].src_out_us > plain.video[0].src_out_us  # later heard decay
    assert heard.video[0].src_out_us <= 2_900_000  # never into the next word's sound
