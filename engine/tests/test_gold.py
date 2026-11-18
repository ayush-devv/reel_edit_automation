"""Build step 11a: gold alignment + family scores, and an end-to-end self-gold eval run."""

import json
import shutil
import subprocess

import pytest

from reel import config
from reel.claude_call import CallResult
from reel.evalh import gold
from reel.perception.asr import RawWord
from reel.schemas.perception import Word, WordTable

RAW = "so today i will show you one simple trick to save money put ten percent of your salary into a separate account".split()


def _raw():
    return WordTable(words=[Word(i=k, clip="c01", text=t, start_us=k * 300_000, end_us=k * 300_000 + 250_000) for k, t in enumerate(RAW)])


def _heard(indices, t0=0.0):
    return [RawWord(RAW[i], t0 + n * 0.3, t0 + n * 0.3 + 0.25, 0.9) for n, i in enumerate(indices)]


def test_alignment_recovers_kept_words_order_and_hook():
    raw = _raw()
    order = list(range(12, 22)) + list(range(1, 11))  # owner opened with the tip, then the promise
    g = gold.gold_from_final(raw, _heard(order), cuts=1, duration_s=6.0)
    assert g.order == order and g.kept == set(order)
    assert g.hook == set(range(12, 22))  # first 3 s of the final = the tip
    assert g.cuts_per_min == pytest.approx(10.0)


def test_single_word_coincidences_are_ignored():
    g = gold.gold_from_final(_raw(), [RawWord("money", 0, 0.2, 0.9), RawWord("banana", 0.3, 0.5, 0.9)], cuts=0, duration_s=1.0)
    assert g.kept == set()


def test_families():
    assert gold.reviewer_family({"sendable": True}) == 1.0
    assert gold.reviewer_family({"sendable": False, "issues": [{"severity": "major"}, {"severity": "minor"}]}) == pytest.approx(0.8)
    soft, vetoes = gold.soft_gate_family([{"gate": "loudness", "mode": "block", "ok": False, "detail": "-20 LUFS"},
                                          {"gate": "dead_air", "mode": "warn", "ok": True}, {"gate": "black", "mode": "warn", "ok": False}])
    assert soft == 0.5 and vetoes == ["gate loudness: -20 LUFS"]


# ------------------------------------------------------------------ end to end: our own render as the gold

try:
    config.ffmpeg_path()
    import mlx_whisper  # noqa: F401

    READY = shutil.which("say") is not None
except Exception:  # noqa: BLE001
    READY = False

SCRIPT = "Hi everyone. Today I will show you one simple trick to save money. Put ten percent of your salary into a separate account every month, and never touch it."


class DeterministicEditor:
    """Stands in for Claude: keeps everything after the greeting, finishes plainly, reviews as sendable."""

    def __call__(self, prompt, schema, *, cwd, label="", **kw):
        words = json.loads((cwd / "perception" / "words.json").read_text())["words"]
        keep = [w for w in words if w["i"] >= 2]
        if label.startswith("story"):
            data = {"genre": "genre.talking_head", "summary": "tip", "hook": "h1",
                    "hook_options": [{"id": "h1", "item": "k1", "rank": 1, "reason": "r"}],
                    "items": [{"id": "k1", "clip": "c01", "word_start": keep[0]["i"], "word_end": keep[-1]["i"],
                               "first_word": keep[0]["text"], "last_word": keep[-1]["text"], "beat": "hook", "reason": "r"}],
                    "knowledge_used": []}
        elif label.startswith("finish"):
            data = {"hook_title": {"text": "", "style": "card", "reason": "r"}, "grade": {"look": "none", "strength": 0.0, "reason": "r"},
                    "punch_ins": [], "speeds": [], "transitions": [], "sfx": [], "broll": [], "knowledge_used": [],
                    "captions": {"family": "bold_pop", "tokens": [], "emphasis_words": [], "script": "latin", "reason": "r"},
                    "music": {"track": "none", "gain_db": -18, "duck_db": 12, "reason": "r"}}
        else:  # review
            data = {"sendable": True, "summary": "fine", "issues": [], "strengths": ["clean"]}
        return CallResult(data=data, session_id="s", num_turns=1, cost_usd=0.0, usage={}, duration_s=0.0)


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs ffmpeg, mlx-whisper, macOS say")
def test_self_gold_eval_scores_high(tmp_path, monkeypatch):
    from reel import tools
    from reel.evalh import harness

    gold_dir = tmp_path / "samples" / "gold" / "talk"
    (gold_dir / "raw").mkdir(parents=True)
    aiff = tmp_path / "voice.aiff"
    subprocess.run(["say", "-o", str(aiff), SCRIPT], check=True)
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30", "-i", str(aiff), "-shortest", "-c:v", "libx264",
                  "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(gold_dir / "raw" / "talk.mp4")])
    monkeypatch.setattr(harness, "GOLD_DIR", tmp_path / "samples" / "gold")
    monkeypatch.setattr(harness, "MANIFEST", tmp_path / "eval" / "manifest.yaml")
    monkeypatch.setattr(harness, "SCOREBOARD", tmp_path / "eval" / "scoreboard.jsonl")
    monkeypatch.setattr(config, "EVAL_DIR", tmp_path / "eval")
    harness.init_manifest()
    # produce our edit once, then declare it the owner's "final"
    import yaml

    from reel import autofix
    from reel.stages import EDIT_PIPELINE
    from reel.workspace import Workspace

    ws = Workspace.create(tmp_path / "seed")
    autofix.run(ws, EDIT_PIPELINE, {"input": str(gold_dir / "raw"), "language": "en"}, caller=DeterministicEditor())
    shutil.copy(ws.path("render", "final.mp4"), gold_dir / "final.mp4")
    harness.init_manifest()
    m = yaml.safe_load(harness.MANIFEST.read_text())
    assert m["reels"][0]["final"].endswith("final.mp4")
    row = harness.run_eval(work_root=tmp_path / "run2", caller=DeterministicEditor())
    (reel,) = row["reels"]
    assert not reel["vetoes"], reel["vetoes"]
    st = reel["detail"]["story"]
    assert st["word_f1"] > 0.9 and st["hook_iou"] > 0.6 and st["cut_rate"] >= 0.0
    assert reel["detail"]["captions"]["wer"] < 0.25
    assert reel["primary"] > 75, reel
    assert json.loads(harness.SCOREBOARD.read_text().splitlines()[-1])["mean_primary"] == reel["primary"]
