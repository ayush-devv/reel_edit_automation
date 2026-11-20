"""3c.4a dub spike: lines, the translation check, timing fit, intelligibility QA, captions, the voice/consent gate, and the
job end to end (fake Claude, fake voice, fake ASR; no video render)."""

from __future__ import annotations

import json
import wave
from fractions import Fraction
from pathlib import Path

import pytest

from reel import dub, licences
from reel.claude_call import CallResult
from reel.perception.asr import RawWord
from reel.schemas.timeline import CaptionPage, CaptionTrack, CaptionWord, Timeline

FPS = Fraction(25)


def _tl(pages: list[tuple[int, int, str]], duration_f: int = 250) -> Timeline:
    cps, i = [], 0
    for s, e, text in pages:
        ws = text.split()
        step = (e - s) / len(ws)
        cws = []
        for k, w in enumerate(ws):
            cws.append(CaptionWord(i=i, text=w, start_f=s + int(k * step), end_f=s + int((k + 1) * step)))
            i += 1
        cps.append(CaptionPage(start_f=s, end_f=e, words=cws))
    return Timeline(fps="25/1", width=1080, height=1920, duration_f=duration_f, assets={}, video=[], audio=[],
                    captions=CaptionTrack(family="x", pages=cps))


PAGES = [(0, 20, "Today I will"), (21, 40, "show you one trick."), (60, 80, "Put ten percent"), (81, 100, "of your salary aside"),
         (101, 120, "every month")]


def test_lines_break_at_pauses_and_sentence_ends():
    ls = dub.lines(_tl(PAGES))
    assert [x.text for x in ls] == ["Today I will show you one trick.", "Put ten percent of your salary aside every month"]
    assert (ls[0].start_f, ls[0].end_f, ls[1].start_f) == (0, 40, 60)
    with pytest.raises(dub.DubError):
        dub.lines(Timeline(fps="25/1", width=1080, height=1920, duration_f=10, assets={}, video=[], audio=[]))


def test_long_runs_are_split_at_the_cap():
    pages = [(k * 20, k * 20 + 19, "and then more") for k in range(10)]  # 8 s without a pause
    assert all((x.end_f - x.start_f) / 25 <= dub.LINE_MAX_S + 1 for x in dub.lines(_tl(pages)))
    assert len(dub.lines(_tl(pages))) >= 2


def _plan(**lines):
    return dub.DubPlan(lines=[dub.DubLine(id=k, caption=c, tts=t) for k, (c, t) in lines.items()])


def test_the_plan_check_wants_every_line_and_the_right_script():
    ls = dub.lines(_tl(PAGES))
    good = _plan(L01=("आज मैं एक ट्रिक बताऊँगा।", "आज मैं एक ट्रिक बताऊँगा।"), L02=("हर महीने 10% अलग रखो।", "हर महीने दस प्रतिशत अलग रखो।"))
    assert dub.check_plan(good, ls, "hi") == []
    latin = _plan(L01=("aaj main ek trick bataunga", "aaj main ek trick bataunga"), L02=good.lines[1].caption and ("हर", "हर"))
    assert {i.code for i in dub.check_plan(latin, ls, "hi")} == {"wrong_script"}
    missing = _plan(L01=good.lines[0].caption and ("आज", "आज"))
    assert "lines_changed" in {i.code for i in dub.check_plan(missing, ls, "hi")}
    deva_in_en = _plan(L01=("Today", "आज"), L02=("Ten", "Ten"))
    assert {i.path for i in dub.check_plan(deva_in_en, ls, "en")} == {"lines.L01.tts"}


def test_fit_speeds_up_within_the_cap_and_slides_the_rest():
    ls = dub.lines(_tl(PAGES))  # slots: L01 0→2.4 s, L02 2.4→10 s
    p = dub.fit(ls, {"L01": 2.6, "L02": 3.0}, FPS, 250)
    assert p[0].tempo == pytest.approx(2.6 / 2.4, abs=1e-3) and not p[0].over and p[1].drift_s == 0
    p = dub.fit(ls, {"L01": 3.6, "L02": 3.0}, FPS, 250)  # needs 1.5×: capped at 1.15, still over, L02 slides
    assert p[0].tempo == dub.OVER and p[0].over
    assert p[1].start_s == pytest.approx(3.6 / 1.15 + dub.SLIDE_GAP_S, abs=1e-3) and p[1].drift_s > 0
    p = dub.fit(ls, {"L01": 1.0, "L02": 1.0}, FPS, 250)  # short lines are never slowed down
    assert all(x.tempo == 1.0 for x in p)
    assert dub.over_ratios(ls, {"L01": 3.6, "L02": 3.0}, FPS, 250) == {"L01": pytest.approx(1.5)}


def test_line_error_compares_numbers_as_values():
    sent = "देखो, अगर आप हर महीने सिर्फ़ पाँच हज़ार भी इन्वेस्ट करते हो, तो दस साल में ये एक लाख से ज़्यादा बन जाता है।"
    good = "देखो अगर आप हर महीने सिरफ 5000 भी इंवेस्ट करते हो तो 10 साल में ये 1 लाग से ज़्यादा बन जाता है।"  # G2.5, Devanagari
    bad = "देखो, अदर आप हर महाएन सर्फ पांच हजार भी इन्वेस्ट का थो, तो 10 साल महाएन यह गलाग से जाया दा बान जाता है."  # Latin-script input
    assert dub.line_error(sent, good) < 0.15
    assert dub.line_error(sent, bad) > dub.MAX_LINE_ERROR
    assert dub.line_error("Put ten percent aside.", "Put 10% aside.") == 0.0
    assert dub.line_error("Put ten percent aside.", "Put five percent aside.") > 0


def test_captions_use_heard_word_times_and_never_overlap():
    plan = _plan(L01=("आज एक ट्रिक", "आज एक ट्रिक"), L02=("हर महीने अलग रखो", "हर महीने अलग रखो"))
    placed = [dub.Placed("L01", 0.0, 1.0, 1.0, 0.0), dub.Placed("L02", 1.0, 2.0, 1.0, 0.0)]
    heard = {"L01": [RawWord("आज", 0.1, 0.3, 1), RawWord("एक", 0.3, 0.5, 1), RawWord("ट्रिक", 0.5, 0.9, 1)], "L02": []}
    pages = dub.caption_pages(placed, plan, heard, FPS)
    assert [w["text"] for w in pages[0]["words"]] == ["आज", "एक", "ट्रिक"]
    assert pages[0]["words"][0]["start_f"] == round(0.1 * 25)
    assert [len(p["words"]) for p in pages] == [3, 3, 1]  # ≤ 3 words a page
    assert all(a["end_f"] <= b["start_f"] for a, b in zip(pages, pages[1:]))
    CaptionPage.model_validate(pages[0])


VOICE = {"set": "voice", "licence_id": "mit", "cmd": ["gen"], "source": "Chatterbox (Resemble AI)"}


def test_the_voice_needs_a_licence_row_and_consent_to_clone(tmp_path):
    reg = licences.load_registry()
    with pytest.raises(dub.DubError, match="no voice generator"):
        dub.voice(None, {"x": {"set": "sfx", "licence_id": "mit"}}, reg)
    with pytest.raises(dub.DubError, match="no row"):
        dub.voice(None, {"v": {**VOICE, "licence_id": "nope"}}, reg)
    assert dub.voice(None, {"v": VOICE}, reg)[0] == "v"
    from reel.workspace import Workspace

    ws = Workspace(tmp_path)
    with pytest.raises(dub.DubError, match="consent"):
        dub.voice("v", {"v": {**VOICE, "clones": True}}, reg, ws)
    (tmp_path / "dub").mkdir()
    (tmp_path / "dub" / "consent.json").write_text(json.dumps({k: "x" for k in dub.CONSENT_FIELDS}))
    assert dub.voice("v", {"v": {**VOICE, "clones": True}}, reg, ws)[0] == "v"


# ------------------------------------------------------------------ the job, end to end (no video render)


def _wav(path: Path, seconds: float, rate: int = 24000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x01" * int(seconds * rate))


class FakeClaude:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt, schema, **kw):
        self.calls.append(kw["label"])
        long = "आज मैं आपको एक बहुत ही आसान और काम की ट्रिक बताने वाला हूँ।"
        first = "आज एक ट्रिक।" if "shorten" in kw["label"] else long
        data = {"lines": [{"id": "L01", "caption": first, "tts": first},
                          {"id": "L02", "caption": "हर महीने 10% अलग रखो।", "tts": "हर महीने दस प्रतिशत अलग रखो।"}]}
        return CallResult(data=data, session_id="s", num_turns=1, cost_usd=0.01, usage={}, duration_s=0.0)


class FakeASR:
    name = "fake"

    def transcribe(self, wav, language, prompt):
        text = {"L01": "आज एक ट्रिक", "L02": "हर महीने 10% अलग रखो"}[Path(wav).stem]
        return [RawWord(w, 0.1 * k, 0.1 * k + 0.1, 1.0) for k, w in enumerate(text.split())], "hi"


def _project(tmp_path: Path) -> Path:
    import subprocess

    from reel import config

    root = tmp_path / "p"
    for d in ("timeline", "render/stems"):
        (root / d).mkdir(parents=True)
    (root / "timeline" / "timeline.json").write_text(_tl(PAGES).model_dump_json())
    (root / "render" / "base.mov").write_bytes(b"not used without render")
    for stem in ("dialogue", "music", "sfx"):
        subprocess.run([str(config.ffmpeg_path()), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                        "-t", "10", str(root / "render" / "stems" / f"{stem}.wav")], check=True)
    return root


def test_a_dub_job_end_to_end(tmp_path):
    root = _project(tmp_path)
    spoken = []

    def synth(spec, jobs, work):
        work.mkdir(parents=True, exist_ok=True)
        for j in jobs:
            spoken.append(j["text"])
            _wav(Path(j["out"]), 0.09 * len(j["text"]))  # the long first L01 overruns its 2.4 s slot

    caller = FakeClaude()
    r = dub.run(root, dub.Options(lang="hi", render=False), caller=caller, gens={"v": VOICE}, synth=synth, asr=FakeASR())
    assert caller.calls == ["dub_hi", "dub_hi_shorten"] and r["rewritten"] == ["L01"]
    assert spoken[-1] == "आज एक ट्रिक।"  # only the rewritten line is spoken again
    assert r["status"] == "ok" and r["for_delivery"] is False and r["voice"]["source"] == "Chatterbox (Resemble AI)"
    assert all(q["error"] == 0.0 for q in r["lines"])
    assert (root / "dub" / "hi" / "dialogue.wav").exists() and (root / "dub" / "hi" / "dub.json").exists()
    assert dub.wav_seconds(root / "dub" / "hi" / "dialogue.wav") == pytest.approx(10.0, abs=0.05)
    assert r["disclosure"] and "timeline" not in {p.name for p in (root / "dub").iterdir()}


def test_a_dub_needs_a_finished_project(tmp_path):
    with pytest.raises(dub.DubError, match="run the edit"):
        dub.run(tmp_path, dub.Options(lang="hi"), gens={"v": VOICE})
    with pytest.raises(dub.DubError, match="not supported"):
        dub.run(tmp_path, dub.Options(lang="ta"), gens={"v": VOICE})
