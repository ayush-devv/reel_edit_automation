"""Local asset libraries (build step 7): index an SFX folder (owner: Sonniss GDC bundles) and an
owned music folder (ADR-0022). Files stay where the owner keeps them; the index stores absolute
paths, measured timing (SFX peak, music beats) and the licence of each source.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from reel import assets as assets_mod
from reel.workspace import atomic_write_json

AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac"}
MUSIC_EXT = AUDIO_EXT | {".mp3", ".m4a"}

# first match wins; matched against "folder/file" lower-cased
SFX_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("riser", ("riser", "uplifter", "rise", "build up", "buildup", "swell", "sweep up")),
    ("whoosh", ("whoosh", "woosh", "swoosh", "swish", "pass by", "passby", "fly by", "flyby")),
    ("swipe", ("swipe", "slide", "page turn")),
    ("boom", ("boom", "sub drop", "subdrop", "bass drop", "downer")),
    ("hit", ("hit", "impact", "punch", "slam", "thud", "stinger", "smash")),
    ("glitch", ("glitch", "digital", "data", "error", "static")),
    ("pop", ("pop", "bubble", "pluck", "blip")),
    ("click", ("click", "tick", "tap", "button", "ui ", "interface")),
    ("ding", ("ding", "chime", "bell", "notification", "ping", "success")),
    ("cash", ("cash", "coin", "register", "money", "kaching", "ka-ching")),
    ("camera", ("shutter", "camera", "photo")),
    ("typing", ("typing", "keyboard", "typewriter")),
]
SFX_MAX_S = 6.0
# typical length per category in short-form edits (craft playbook: whoosh ≈ transition, riser into a reveal)
TYPICAL_MS = {"riser": 2500, "whoosh": 700, "swipe": 400, "boom": 1500, "hit": 700, "glitch": 500, "pop": 200,
              "click": 120, "ding": 800, "cash": 900, "camera": 400, "typing": 1500}  # longer files are ambiences/music beds, not edit SFX


def _id(prefix: str, path: Path) -> str:
    return f"{prefix}_{hashlib.sha1(str(path).encode()).hexdigest()[:8]}"


def sfx_category(path: Path) -> str | None:
    key = f"{path.parent.name} {path.stem}".lower().replace("_", " ").replace("-", " ")
    for cat, words in SFX_CATEGORIES:
        if any(re.search(rf"\b{re.escape(w.strip())}", key) for w in words):
            return cat
    return None


def _mono(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return data.mean(axis=1), rate


def peak_ms(y: np.ndarray, rate: int, win_ms: int = 10) -> int:
    """Start of the loudest 10 ms window — the frame an SFX is aligned to (hit, pop, whoosh centre)."""
    n = max(1, int(rate * win_ms / 1000))
    usable = y[: (y.size // n) * n].reshape(-1, n) if y.size >= n else y.reshape(1, -1)
    return int(np.argmax(np.sqrt((usable.astype(np.float64) ** 2).mean(axis=1))) * win_ms)


def _peak_db(y: np.ndarray) -> float:
    return round(20 * np.log10(max(float(np.abs(y).max()) if y.size else 0.0, 1e-9)), 1)


def index_sfx(folder: Path, *, source: str, license_: str) -> list[dict]:
    out = []
    for f in sorted(p for p in folder.rglob("*") if p.suffix.lower() in AUDIO_EXT and not p.name.startswith(".")):
        cat = sfx_category(f.relative_to(folder))
        if cat is None:
            continue
        try:
            y, rate = _mono(f)
        except Exception:  # noqa: BLE001 — unreadable files are skipped, not fatal
            continue
        dur = y.size / rate
        if dur <= 0.02 or dur > SFX_MAX_S:
            continue
        out.append({"id": _id(cat, f), "file": str(f.resolve()), "name": f.stem, "category": cat,
                    "duration_ms": int(round(dur * 1000)), "peak_ms": peak_ms(y, rate), "peak_dbfs": _peak_db(y),
                    "source": source, "license": license_})
    return out


def beats(y: np.ndarray, rate: int) -> tuple[float, list[int], list[int]]:
    """(bpm, beat times ms, downbeat times ms). Downbeats: every 4th beat, phase with the strongest onsets."""
    import librosa

    tempo, frames = librosa.beat.beat_track(y=y, sr=rate, units="frames")
    onset = librosa.onset.onset_strength(y=y, sr=rate)
    times = librosa.frames_to_time(frames, sr=rate)
    beat_ms = [int(round(t * 1000)) for t in times]
    if len(frames) >= 4:
        strength = [float(np.sum(onset[frames[k::4][frames[k::4] < onset.size]])) for k in range(4)]
        phase = int(np.argmax(strength))
    else:
        phase = 0
    return round(float(np.atleast_1d(tempo)[0]), 1), beat_ms, beat_ms[phase::4]


def index_music(folder: Path, *, source: str, license_: str) -> list[dict]:
    import librosa

    out = []
    for f in sorted(p for p in folder.rglob("*") if p.suffix.lower() in MUSIC_EXT and not p.name.startswith(".")):
        try:
            y, rate = librosa.load(str(f), sr=22050, mono=True)
        except Exception:  # noqa: BLE001
            continue
        bpm, beat_ms, down_ms = beats(y, rate)
        side = f.with_suffix(".json")
        meta = json.loads(side.read_text()) if side.exists() else {}
        out.append({"id": _id("music", f), "file": str(f.resolve()), "title": meta.get("title", f.stem),
                    "duration_ms": int(round(y.size / rate * 1000)), "bpm": bpm, "beats_ms": beat_ms, "downbeats_ms": down_ms,
                    "mood": meta.get("mood") or f.parent.name.replace("_", " "), "energy": meta.get("energy"),
                    "source": meta.get("source", source), "license": meta.get("license", license_)})
    return out


def write_index(kind: str, entries: list[dict], *, replace: bool = False, root: Path = assets_mod.ASSETS_DIR) -> Path:
    """Merge into assets/<kind>/…index.json (by id); `replace` drops entries from the same source first."""
    path, key = {"sfx": (root / "sfx" / "sfx_index.json", "sfx"), "music": (root / "music" / "music_index.json", "tracks")}[kind]
    data = json.loads(path.read_text()) if path.exists() else {key: []}
    sources = {e["source"] for e in entries}
    items = [e for e in data.get(key, []) if not (replace and e.get("source") in sources)]
    by = {e["id"]: e for e in items}
    by.update({e["id"]: e for e in entries})
    atomic_write_json(path, {key: sorted(by.values(), key=lambda e: e["id"])})
    return path


def sfx_menu(sfx: dict[str, dict], per_category: int = 6) -> dict[str, list[dict]]:
    """What the Editor sees: a few short, clean options per category (not thousands of files)."""
    menu: dict[str, list[dict]] = {}
    for e in sorted(sfx.values(), key=lambda e: (e.get("category", ""), abs(e["duration_ms"] - TYPICAL_MS.get(e.get("category"), 700)), e["id"])):
        cat = e.get("category", "other")
        if len(menu.setdefault(cat, [])) < per_category:
            menu[cat].append(e)
    return menu
