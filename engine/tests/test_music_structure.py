"""Song structure for the music bed (reel.music_structure, roadmap G1.4)."""

from __future__ import annotations

import numpy as np
import pytest

from reel import music_structure
from reel.compile import music_offset_us

SR = 22050


def _track(seconds: float = 30.0, step_at: float | None = 12.0, quiet: float = 0.05, loud: float = 0.5) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    y = quiet * np.sin(2 * np.pi * 220 * t)
    if step_at is not None:
        y[t >= step_at] = loud * np.sin(2 * np.pi * 220 * t[t >= step_at])
    return y.astype(np.float32)


def test_drop_found_on_the_downbeat_where_energy_steps_up():
    downs = [k * 2000 for k in range(15)]  # a downbeat every 2 s
    d = music_structure.find_drop(_track(), SR, downs)
    assert d is not None and d["drop_ms"] == 12_000 and d["rise_db"] >= 15


def test_no_drop_in_a_flat_track_or_a_small_swell():
    downs = [k * 2000 for k in range(15)]
    assert music_structure.find_drop(_track(step_at=None), SR, downs) is None
    assert music_structure.find_drop(_track(quiet=0.3, loud=0.45), SR, downs) is None  # ~3.5 dB: a swell
    assert music_structure.find_drop(_track(quiet=0.0005, loud=0.005), SR, downs) is None  # loud-ish only relative to silence


def test_beats_fall_back_to_librosa_without_beat_this(monkeypatch):
    def missing():
        raise ImportError("no beat_this")

    monkeypatch.setattr(music_structure, "_model", missing)
    clicks = np.zeros(SR * 10, dtype=np.float32)
    for k in range(20):
        clicks[int(k * 0.5 * SR):int(k * 0.5 * SR) + 300] = 0.8
    bpm, beats, downs, tracker = music_structure.beats(clicks, SR)
    assert tracker == "librosa" and 110 <= bpm <= 130 and beats and downs


def test_offset_lands_the_drop_on_the_hook_end():
    meta = {"duration_ms": 60_000, "beats_ms": list(range(0, 60_000, 500)), "downbeats_ms": list(range(0, 60_000, 2000)),
            "drop_ms": 24_000}
    off = music_offset_us(meta, cut_us=2_000_000, total_us=20_000_000, cuts_us=[2_000_000, 5_000_000], hook_end_us=5_000_000)
    assert off == 19_000_000  # 24 s drop − 5 s hook end
    # a drop too early (before the hook ends) or too late (not enough track left) falls back to the beat rule
    early = {**meta, "drop_ms": 3_000}
    assert music_offset_us(early, 2_000_000, 20_000_000, [2_000_000], hook_end_us=5_000_000) != -2_000_000
    late = {**meta, "drop_ms": 58_000}
    assert music_offset_us(late, 2_000_000, 20_000_000, [2_000_000], hook_end_us=5_000_000) != 53_000_000
    # a one-item reel (the hook is the whole reel) never jumps to the drop
    assert music_offset_us(meta, 2_000_000, 20_000_000, [2_000_000], hook_end_us=20_000_000) != 4_000_000


@pytest.mark.skipif(not music_structure.tracker_name().startswith("beat_this"), reason="beat-this not installed")
def test_committed_music_index_was_measured_with_beat_this():
    import json

    from reel import assets

    tracks = json.loads((assets.ASSETS_DIR / "music" / "music_index.json").read_text())["tracks"]
    assert all(t.get("beats_by", "").startswith("beat_this") for t in tracks)
    assert all(t["drop_ms"] > 0 and t["rise_db"] >= music_structure.DROP_MIN_RISE_DB for t in tracks if "drop_ms" in t)
