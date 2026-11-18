"""Build step 8: script handling, bake-off scoring, smoke run on synthetic Hindi speech (macOS Lekha)."""

import shutil
import subprocess

import pytest

from reel import bakeoff, config
from reel import script as sc
from reel.perception.asr import RawWord


def test_romaniser_gives_casual_hinglish_spellings():
    assert sc.deva_to_roman("क्या है नहीं आज कल") == "kya hai nahin aaj kal"
    assert sc.deva_to_roman("बताऊँगा") == "bataaoonga"
    assert sc.deva_to_roman("आपको मतलब करना समझ") == "aapko matlab karna samajh"  # medial schwa deletion
    assert sc.deva_to_roman("save पैसे") == "save paise"  # Roman tokens untouched


def test_keys_fold_spelling_variants_across_scripts():
    same = [("क्या", "kyaa"), ("नहीं", "nahi"), ("अच्छा", "accha"), ("ज़रूर", "jaroor"), ("यह", "yeh"), ("बहुत", "bahut")]
    for a, b in same:
        assert sc.key(a) == sc.key(b), (a, b, sc.key(a), sc.key(b))
    assert sc.key("kal") != sc.key("kaam")


def test_script_detection_and_mix():
    assert sc.script_of("पैसे") == "devanagari" and sc.script_of("money") == "latin" and sc.script_of("10%") == "other"
    assert sc.mixed_ratio("आज मैं simple trick") == 0.5


def test_scoring_is_script_agnostic_and_counts_fillers():
    clip = bakeoff.Clip("c", None, "umm आज मैं आपको एक simple trick बताऊँगा",
                        ref_times=[("umm", 0.0, 0.3), ("आज", 0.5, 0.7), ("मैं", 0.7, 0.9)])
    roman = [RawWord(t, s, s + 0.2, 0.9) for t, s in (("aaj", 0.52), ("main", 0.72), ("aapko", 0.95), ("ek", 1.2),
                                                       ("simple", 1.4), ("trick", 1.7), ("bataunga", 2.0))]
    s = bakeoff.score("roman", clip, roman, runtime_s=1.0, duration_s=4.0)
    assert s.wer == pytest.approx(1 / 8)  # only the dropped "umm"
    assert s.fillers == 0.0 and s.onset_ms == pytest.approx(20, abs=1) and s.within_100ms == 1.0
    assert s.devanagari_share == 0.0 and s.rtf == 0.25
    bad = [RawWord("aaj", 1.0, 0.9, 0.9), RawWord("main", 0.5, 0.7, 0.9)]
    assert bakeoff.timing_sanity(bad) == 1.0


def test_dataset_loader(tmp_path):
    d = tmp_path / "hinglish" / "c1"
    d.mkdir(parents=True)
    (d / "clip.mp4").write_bytes(b"")
    (d / "transcript.txt").write_text("आज मैं\n")
    (d / "words.tsv").write_text("word\tstart\tend\nआज\t0.5\t0.7\n")
    (tmp_path / "hinglish" / "no_transcript").mkdir()
    (clip,) = bakeoff.load_dataset(tmp_path / "hinglish")
    assert clip.name == "c1" and clip.reference == "आज मैं" and clip.ref_times == [("आज", 0.5, 0.7)]


try:
    config.ffmpeg_path()
    import mlx_whisper  # noqa: F401

    READY = shutil.which("say") is not None
except Exception:  # noqa: BLE001
    READY = False

HINGLISH = "आज मैं आपको एक simple trick बताऊँगा, अपनी salary का दस प्रतिशत हर महीने अलग account में डालिए।"


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs ffmpeg, mlx-whisper and macOS say (Lekha)")
def test_bakeoff_smoke_on_synthetic_hindi(tmp_path):
    from reel.perception.asr import MlxWhisper

    d = tmp_path / "hinglish" / "lekha"
    d.mkdir(parents=True)
    r = subprocess.run(["say", "-v", "Lekha", "-o", str(d / "voice.aiff"), HINGLISH], capture_output=True)
    if r.returncode:
        pytest.skip("Lekha voice not installed")
    (d / "transcript.txt").write_text(HINGLISH)
    summary = bakeoff.run({"whisper-turbo": MlxWhisper()}, bakeoff.load_dataset(tmp_path / "hinglish"), tmp_path / "out")
    s = summary["engines"]["whisper-turbo"]
    assert summary["winner"] == "whisper-turbo" and (tmp_path / "out" / "results.md").exists()
    assert s["cer"] < 0.5 and s["bad_timing"] < 0.2, s


def test_captions_romanised_for_latin_script_and_phrase_fallback():
    from reel.compile import caption_text, compile_timeline, proof_list, unreliable_timing
    from reel.schemas.plan import CaptionPlan
    from test_plan_compile import CLIPS, FPS, IDX, WORDS, _finish, _story

    assert caption_text("पैसे", "latin") == "paise" and caption_text("पैसे", "mixed") == "पैसे" and caption_text("money", "latin") == "money"
    words = WORDS.model_copy(deep=True)
    tl = compile_timeline(_story(), _finish(), words, CLIPS, FPS, IDX)
    assert tl.captions.timing == "word" and proof_list(tl, _story(), words) == []
    for k in range(7, 14):  # smear the kept hook item's timings
        words.words[k] = words.words[k].model_copy(update={"suspect": True, "low_conf": k == 9})
    assert unreliable_timing([words.words[k] for k in range(7, 14)])
    tl2 = compile_timeline(_story(), _finish(), words, CLIPS, FPS, IDX)
    assert tl2.captions.timing == "phrase"
    proof = proof_list(tl2, _story(), words)
    assert [p["i"] for p in proof] == list(range(7, 14)) and proof[0]["frame"] == tl2.captions.pages[0].words[0].start_f and "low confidence" in proof[2]["why"]


def test_ctc_tokens_merge_into_words():
    from reel.hinglish_engines import merge_tokens

    words = merge_tokens(["▁मेरा", "▁ord", "er", "▁कब"], [0.10, 0.50, 0.62, 0.90])
    assert [(w.text, w.start_s) for w in words] == [("मेरा", 0.10), ("order", 0.50), ("कब", 0.90)]
    assert words[1].end_s == pytest.approx(0.66)


def test_engine_registry_lists_all_candidates():
    with pytest.raises(KeyError) as exc:
        bakeoff.engines(["nope"])  # unknown name → error lists every registered engine
    for name in ("whisper-turbo", "whisper-large-v3", "shruti", "oriserve-apex", "indicconformer"):
        assert name in str(exc.value)
