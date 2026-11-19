"""Post copy pack (reel.postcopy, roadmap G1.1). No network: the Claude caller is a fake."""

from __future__ import annotations

import json

import pytest

from reel import postcopy
from reel.brief import Brand, BrandVoice, Brief
from reel.claude_call import CallResult

CREDIT = '"Carefree" Kevin MacLeod (incompetech.com)\nLicensed under Creative Commons: By Attribution 4.0 License'


def _pack(**kw) -> dict:
    return {"ig_caption": "Sugar hides in your juice.\n\nTry this swap tomorrow. Comment JUICE for the list.",
            "hashtags": ["nutrition", "healthyhabits", "sugar"], "first_comment": "Which drink surprised you?",
            "yt_title": "The juice myth nobody told you", "yt_description": "Why juice isn't the healthy choice.", **kw}


def _brand(**voice) -> Brand:
    return Brand(client="Acme", voice=BrandVoice(**voice))


def _probs(pack: dict, brief=None, brand=None, credits=None) -> list[str]:
    return postcopy.problems(postcopy.CopyPack(**pack), brief, brand, credits)


def test_old_brand_kits_stay_valid_and_voice_validates():
    b = Brand.model_validate({"client": "Acme"})
    assert b.voice.emoji == "light" and b.voice.hashtags_always == []
    assert BrandVoice(hashtags_always=["#Acme", "acme_india"]).hashtags_always == ["Acme", "acme_india"]
    for bad in ({"emoji": "lots"}, {"caption_language": "fr"}, {"hashtags_pool": ["two words"]}):
        with pytest.raises(ValueError):
            BrandVoice(**bad)


def test_a_good_pack_passes():
    assert _probs(_pack()) == []


def test_hashtag_rules():
    assert any("Instagram allows 5" in p for p in _probs(_pack(hashtags=["a1", "b2", "c3", "d4", "e5", "f6"])))
    # caption + first comment share the cap, and tags belong in the list
    probs = _probs(_pack(hashtags=["a1", "b2", "c3", "d4"], first_comment="Thoughts? #e5 #f6"))
    assert any("6 hashtags" in p for p in probs) and any("not inside" in p for p in probs)
    assert any("repeated" in p for p in _probs(_pack(hashtags=["Sugar", "sugar"])))
    assert any("generic" in p for p in _probs(_pack(hashtags=["fyp", "sugar"])))
    assert any("always-on" in p for p in _probs(_pack(), brand=_brand(hashtags_always=["AcmeFoods"])))


def test_voice_and_brief_rules():
    brand = _brand(banned_words=["cheap"], emoji="none")
    probs = _probs(_pack(ig_caption="A cheap trick 🍊. Comment JUICE."), brand=brand)
    assert any("banned word" in p for p in probs) and any("no emoji" in p for p in probs)
    assert _probs(_pack(ig_caption="Cheaper than you think"), brand=_brand(banned_words=["cheap"])) == []  # whole words only
    brief = Brief(project="x", banned_claims=["cures diabetes"], cta="Follow for daily nutrition tips")
    probs = _probs(_pack(ig_caption="This cures diabetes!"), brief=brief)
    assert any("banned claim" in p for p in probs) and any("call to action" in p for p in probs)
    assert _probs(_pack(ig_caption="Sugar hides in juice. Follow for daily nutrition tips."), brief=brief) == []


def test_length_counts_credits_and_hashtags():
    long = "x" * (postcopy.IG_CAPTION_MAX - 60) + " Comment JUICE."
    assert _probs(_pack(ig_caption=long, hashtags=["sugar"])) == []  # fits on its own …
    probs = _probs(_pack(ig_caption=long, hashtags=["sugar"]), credits=[CREDIT])
    assert any("characters with hashtags and credits" in p for p in probs)  # … but not once the credit is added


def test_credits_are_added_by_code_once():
    final = postcopy.credited({**_pack(), "status": "ok"}, [CREDIT])
    assert final["ig_caption"].endswith(CREDIT) and final["ig_caption"].count("Kevin MacLeod") == 1
    assert "#nutrition #healthyhabits #sugar" in final["ig_caption"] and final["yt_description"].endswith(CREDIT)
    md = postcopy.markdown(final)
    assert "## Instagram caption" in md and "Check before posting" not in md
    assert "Check before posting" in postcopy.markdown(postcopy.credited({**_pack(), "status": "needs_review", "problems": ["x"]}, []))


def _caller(*answers):
    calls = []

    def call(prompt, schema, **kw):
        calls.append((prompt, kw))
        a = answers[min(len(calls) - 1, len(answers) - 1)]
        if isinstance(a, Exception):
            raise a
        return CallResult(data=a, session_id="s", num_turns=1, cost_usd=0.001, usage={}, duration_s=0.0)

    return call, calls


def test_write_reasks_once_with_the_problems(tmp_path):
    call, calls = _caller(_pack(hashtags=["fyp", "sugar"]), _pack())
    out = postcopy.write(tmp_path, call, kept_text="sugar in juice", summary="talk", brief=None, brand=None)
    assert out["status"] == "ok" and len(calls) == 2
    assert "generic hashtags" in calls[1][0] and calls[1][1]["label"] == "copy_retry" and calls[1][1]["effort"] == "low"


def test_write_keeps_a_still_bad_pack_for_review_and_never_raises(tmp_path):
    call, calls = _caller(_pack(hashtags=["fyp"]))
    out = postcopy.write(tmp_path, call, kept_text="k", summary="s", brief=None, brand=None)
    assert out["status"] == "needs_review" and out["problems"] and len(calls) == 2
    call, _ = _caller(RuntimeError("claude unavailable"))
    assert postcopy.write(tmp_path, call, kept_text="k", summary="s", brief=None, brand=None)["status"] == "failed"
    call, _ = _caller(_pack(hashtags=["fyp"]), RuntimeError("down"))  # the retry fails: keep the first draft
    assert postcopy.write(tmp_path, call, kept_text="k", summary="s", brief=None, brand=None)["status"] == "needs_review"


def test_language_follows_brand_then_brief():
    assert postcopy.language(None, None) == "en"
    assert postcopy.language(Brief(project="x", language="hinglish"), None) == "hinglish_latin"
    assert postcopy.language(Brief(project="x", caption_script="devanagari"), None) == "hi_deva"
    assert postcopy.language(Brief(project="x", language="hinglish"), _brand(caption_language="en")) == "en"
    p = postcopy.prompt("kept", "sum", Brief(project="x", cta="Follow"), _brand(hashtags_always=["Acme"]))
    assert "Hashtags: always include Acme" in p and '"cta": "Follow"' in p


def test_package_writes_only_the_credited_version(tmp_path):
    from reel import package
    from reel.workspace import Workspace

    ws = Workspace.create(tmp_path / "p")
    pkg = ws.path("export", "package")
    pkg.mkdir(parents=True)
    (ws.path("plan")).mkdir(parents=True, exist_ok=True)
    ws.path("plan", "copy.json").write_text(json.dumps({**_pack(), "status": "ok", "problems": []}))
    package._copy_pack(ws, pkg, [CREDIT])
    served = json.loads((pkg / "copy.json").read_text())
    assert served["ig_caption"].endswith(CREDIT) and (pkg / "COPY.md").exists()
    ws.path("plan", "copy.json").write_text(json.dumps({"status": "failed", "reason": "x"}))
    package._copy_pack(ws, pkg, [])
    assert not (pkg / "copy.json").exists() and not (pkg / "COPY.md").exists()  # never a stale copy


def test_copy_stage_hash_ignores_renders(tmp_path):
    from reel.runner import StageContext
    from reel.stages import edit
    from reel.workspace import Workspace

    ws = Workspace.create(tmp_path / "p")
    ctx = StageContext(ws=ws, options={})
    h = edit.COPY.input_hash(ctx)
    ws.path("render").mkdir(parents=True, exist_ok=True)
    ws.path("render", "final.mp4").write_bytes(b"x")
    assert edit.COPY.input_hash(ctx) == h
    ws.path("tables").mkdir(parents=True, exist_ok=True)
    ws.path("tables", "summary.md").write_text("new summary")
    assert edit.COPY.input_hash(ctx) != h
