import json

import numpy as np

from reel.brief import Brief, Brand, vocabulary
from reel.perception.asr import RawWord, to_words, vocabulary_prompt
from reel.perception.prosody import rms_db, segment_stats
from reel.perception.segments import build_segments
from reel.perception.vad import filler_spans
from reel.perception.visual import kmeans
from reel.schemas.perception import Word, WordTable


def W(i, text, s, e, clip="c01", **kw):
    return Word(i=i, clip=clip, text=text, start_us=s, end_us=e, **kw)


def test_to_words_flags_and_monotonic():
    raw = [RawWord("Umm", 0.1, 0.4, 0.9), RawWord("this", 0.5, 0.7, 0.95), RawWord("DearMa", 0.65, 0.9, 0.3),
           RawWord("works", 0.95, 2.6, 0.9), RawWord("matlab", 2.7, 3.0, 0.9), RawWord("late", 9.0, 12.0, 0.9)]
    ws = to_words(raw, "c01", 10, duration_us=10_000_000)
    assert [w.i for w in ws] == list(range(10, 16))
    assert ws[0].filler and not ws[1].filler
    assert ws[2].low_conf and ws[2].start_us >= ws[1].start_us
    assert ws[3].suspect  # 1.65 s word
    assert ws[4].candidate_filler and not ws[4].filler
    assert ws[5].end_us == 10_000_000  # clamped to the clip


def test_vocabulary_correction_and_proof_flags():
    from reel.perception.asr import apply_vocabulary

    words = [W(0, "I", 0, 1), W(1, "am", 2, 3), W(2, "Mansa", 4, 5), W(3, "from", 6, 7), W(4, "Dioma.", 8, 9),
             W(5, "Wortam", 10, 11), W(6, "rocks", 12, 13)]
    out = apply_vocabulary(words, ["DearMa", "Wortham Studio"])
    assert out[5].text == "Wortham" and out[5].original_text == "Wortam"  # near-miss auto-corrected
    assert out[4].vocab_suspect and out[4].vocab_suggestion == "DearMa"  # name-like, close enough to suggest
    assert out[2].vocab_suspect and out[2].vocab_suggestion is None  # unknown name → proof list
    assert not out[6].vocab_suspect and out[0].text == "I"
    confirmed = apply_vocabulary([W(0, "hi", 0, 1), W(1, "DearMa", 2, 3)], ["DearMa"])
    assert not confirmed[1].vocab_suspect and confirmed[1].original_text is None


def test_vocabulary_prompt_dedupes():
    assert vocabulary_prompt(["DearMa", "dearma", "Wortham", " "]) == "Names: DearMa, Wortham."
    assert vocabulary_prompt([]) is None


def test_brief_brand_vocabulary():
    b = Brief(project="p", client="DearMa", product_names=["Wortham Studio"], vocabulary=["Mansa"])
    br = Brand(client="Wortham")
    v = vocabulary(b, br, ["Just come to Wortham", "the end"])
    assert {"Wortham Studio", "Mansa", "DearMa", "Wortham", "Just"} <= set(v)


def test_segments_split_rules():
    words = WordTable(words=[
        W(0, "hello", 0, 300_000), W(1, "there.", 350_000, 600_000),          # sentence end
        W(2, "next", 700_000, 900_000), W(3, "idea", 950_000, 1_200_000),
        W(4, "after", 2_000_000, 2_200_000),                                # pause ≥ 0.5 s
        W(5, "other", 0, 200_000, clip="c02"),                              # clip change
    ])
    segs = build_segments(words).segments
    assert [(s.word_start, s.word_end) for s in segs] == [(0, 1), (2, 3), (4, 4), (5, 5)]
    assert [s.seg_id for s in segs] == ["s001", "s002", "s003", "s004"]
    long = WordTable(words=[W(i, "w", i * 100_000, i * 100_000 + 50_000) for i in range(60)])
    assert max(s.word_end - s.word_start + 1 for s in build_segments(long).segments) <= 28


def test_filler_spans_from_uncovered_speech():
    regions = [(0, 2_000_000)]
    words = [W(0, "so", 0, 300_000), W(1, "today", 800_000, 1_100_000), W(2, "we", 1_150_000, 1_300_000)]
    spans = filler_spans(regions, words)
    assert spans == [(300_000, 800_000), (1_300_000, 2_000_000)]
    assert filler_spans([(0, 400_000)], [W(0, "a", 0, 300_000)]) == []  # 100 ms gap < 150 ms


def test_kmeans_finds_dominant_colours():
    img = np.zeros((40, 40, 3), np.uint8)
    img[:, :30] = (230, 120, 40)  # orange 75%
    img[:, 30:] = (20, 120, 110)  # teal 25%
    centres, weights = kmeans(img[None], k=2)
    assert abs(weights[0] - 0.75) < 0.01
    assert np.allclose(centres[0], (230, 120, 40), atol=2)


def test_rms_and_segment_stats():
    pcm = np.concatenate([np.zeros(16000, np.float32), 0.5 * np.ones(16000, np.float32)])
    db = rms_db(pcm)
    assert db[0] == -90.0 and abs(db[-1] - (-6.0)) < 0.2
    words = WordTable(words=[W(0, "a", 1_000_000, 1_300_000), W(1, "b", 1_400_000, 1_900_000, low_conf=True)])
    stats = segment_stats(words, build_segments(words), {"c01": db})
    s = stats[0]
    assert s["words"] == 2 and s["low_conf_words"] == [1] and s["loudness_db"] > -10
    json.dumps(stats)  # serialisable


def test_face_box_overlap_for_tile_merging():
    from reel.perception.visual import _iou

    a = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}
    assert abs(_iou(a, a) - 1.0) < 1e-9
    assert _iou(a, {"x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1}) == 0.0
    assert 0.3 < _iou(a, {"x": 0.15, "y": 0.1, "w": 0.2, "h": 0.2}) < 0.7  # the same face seen in two overlapping tiles
