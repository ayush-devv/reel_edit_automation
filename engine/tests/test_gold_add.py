"""3b.5 `reel gold add`: one command per pair, and a final that wasn't cut from the raw is refused."""

from __future__ import annotations

import json

import numpy as np
import pytest
import yaml

from reel.evalh import gold_add, harness


def test_the_final_lines_up_with_its_own_raw_above_chance():
    rng = np.random.default_rng(1)
    raw = np.abs(rng.normal(size=2400)).astype(np.float32)  # 2 min of envelope at 20 Hz
    # a pro-style final: 1.5 s pieces from all over the raw, quieter, with a music floor
    final = np.concatenate([raw[s:s + 30] for s in (700, 120, 1900, 400, 1500, 60, 2100, 900)]) * 0.8 + 0.05
    other = np.abs(rng.normal(size=600)).astype(np.float32)
    assert gold_add.best_match(final, raw) > 0.95
    assert gold_add.match_margin(final, raw) > gold_add.WEAK_MATCH
    assert gold_add.match_margin(other, raw) < gold_add.MIN_MATCH
    assert gold_add.best_match(final[:20], raw) == 0.0  # too short to judge


@pytest.fixture
def gold(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(harness, "MANIFEST", tmp_path / "eval" / "manifest.yaml")
    monkeypatch.setattr(harness.config, "EVAL_DIR", tmp_path / "eval")
    raw, final = tmp_path / "in" / "talk.mp4", tmp_path / "in" / "Reel Final.mp4"
    raw.parent.mkdir()
    raw.write_bytes(b"raw")
    final.write_bytes(b"final")
    rng = np.random.default_rng(2)
    env = {raw: np.abs(rng.normal(size=2400)).astype(np.float32)}
    env[final] = env[raw][100:600].copy()
    monkeypatch.setattr(gold_add, "envelope", lambda p: env[p])
    monkeypatch.setattr("reel.probe.probe", lambda p: type("P", (), {"duration_s": 25.0})())
    return tmp_path, raw, final, env


def test_add_pair_copies_writes_the_brief_and_refreshes_the_manifest(gold):
    tmp, raw, final, _env = gold
    r = gold_add.add_pair(raw, final, language="hinglish", split="holdout", genre="genre.podcast_clip", channel="@creator")
    assert r["id"] == "reel-final" and r["match"] > gold_add.WEAK_MATCH and "warning" not in r and r["hindi_hinglish"] == 1 and r["pairs"] == 1
    d = tmp / "gold" / "reel-final"
    assert (d / "raw" / "talk.mp4").exists() and (d / "final.mp4").read_bytes() == b"final"
    brief = json.loads((d / "brief.json").read_text())
    assert brief["language"] == "hinglish" and brief["target_length_s"] == [20.0, 30.0] and brief["genre_hint"] == "genre.podcast_clip"
    m = yaml.safe_load((tmp / "eval" / "manifest.yaml").read_text())
    assert m["reels"][0]["split"] == "holdout" and m["reels"][0]["language"] == "hinglish"
    with pytest.raises(gold_add.GoldError, match="already exists"):
        gold_add.add_pair(raw, final, language="hinglish")


def test_a_final_from_other_footage_is_refused(gold):
    _tmp, raw, final, env = gold
    env[final] = np.abs(np.random.default_rng(9).normal(size=500)).astype(np.float32)
    with pytest.raises(gold_add.GoldError, match="doesn't line up"):
        gold_add.add_pair(raw, final, language="hi")
    assert gold_add.add_pair(raw, final, language="hi", check=False)["match"] is None  # the owner can override knowingly
    with pytest.raises(gold_add.GoldError, match="language"):
        gold_add.add_pair(raw, final, language="fr")
