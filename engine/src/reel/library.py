"""Local asset libraries (build step 7): index an SFX folder and a music folder (ADR-0022). Files
stay where the owner keeps them; the index stores their path (relative to assets/ for files fetched
into it by `reel assets fetch`, so the committed index works in any checkout; absolute otherwise),
measured timing (SFX peak, music beats) and the licence of each source.
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

# first match wins; matched against "folder file" lower-cased, camelCase split ("impactPunch" → "impact punch")
SFX_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("riser", ("riser", "uplifter", "rise", "build up", "buildup", "swell", "sweep up")),
    ("whoosh", ("whoosh", "woosh", "swoosh", "swish", "pass by", "passby", "fly by", "flyby")),
    ("swipe", ("swipe", "slide", "page turn")),
    ("boom", ("boom", "sub drop", "subdrop", "bass drop", "downer")),
    ("hit", ("hit", "impact", "punch", "slam", "thud", "stinger", "smash")),
    ("glitch", ("glitch", "digital", "data", "error", "static", "zap")),
    ("pop", ("pop", "bubble", "pluck", "blip", "drop")),
    ("camera", ("shutter", "camera", "photo")),
    ("click", ("click", "tick", "tap", "button", "ui ", "interface", "switch", "toggle", "select", "mouse")),
    ("cash", ("cash", "coin", "register", "money", "kaching", "ka-ching")),
    ("ding", ("ding", "chime", "bell", "notification", "ping", "success", "confirmation", "bong", "two tone", "three tone")),
    ("typing", ("typing", "keyboard", "typewriter")),
]
SFX_MAX_S = 6.0
# typical length per category in short-form edits (craft playbook: whoosh ≈ transition, riser into a reveal)
TYPICAL_MS = {"riser": 2500, "whoosh": 700, "swipe": 400, "boom": 1500, "hit": 700, "glitch": 500, "pop": 200,
              "click": 120, "ding": 800, "cash": 900, "camera": 400, "typing": 1500}  # longer files are ambiences/music beds, not edit SFX


def _id(prefix: str, path: Path | str) -> str:
    return f"{prefix}_{hashlib.sha1(str(path).encode()).hexdigest()[:8]}"


def _stored_path(f: Path, rel_to: Path | None) -> str:
    """Path written to the index: relative (posix) under `rel_to` — portable across checkouts — else absolute."""
    f = f.resolve()
    if rel_to is not None and f.is_relative_to(rel_to.resolve()):
        return f.relative_to(rel_to.resolve()).as_posix()
    return str(f)


def sfx_category(path: Path) -> str | None:
    raw = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", f"{path.parent.name} {path.stem}")
    key = raw.lower().replace("_", " ").replace("-", " ")
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


def index_sfx(folder: Path, *, source: str, license_: str, rel_to: Path | None = None) -> list[dict]:
    check_licence(license_)
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
        stored = _stored_path(f, rel_to)
        out.append({"id": _id(cat, stored if rel_to is not None else f), "file": stored, "name": f.stem, "category": cat,
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


def index_music(folder: Path, *, source: str, license_: str, rel_to: Path | None = None) -> list[dict]:
    import librosa

    check_licence(license_)
    out = []
    for f in sorted(p for p in folder.rglob("*") if p.suffix.lower() in MUSIC_EXT and not p.name.startswith(".")):
        try:
            y, rate = librosa.load(str(f), sr=22050, mono=True)
        except Exception:  # noqa: BLE001
            continue
        bpm, beat_ms, down_ms = beats(y, rate)
        side = f.with_suffix(".json")
        meta = json.loads(side.read_text()) if side.exists() else {}
        if FORBIDDEN_LICENCE.search(str(meta.get("license", ""))):
            continue  # a per-track sidecar may not smuggle in a ShareAlike / NonCommercial track
        stored = _stored_path(f, rel_to)
        out.append({"id": _id("music", stored if rel_to is not None else f), "file": stored, "title": meta.get("title", f.stem),
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
    atomic_write_json(path, {**{k: v for k, v in data.items() if k != key}, key: sorted(by.values(), key=lambda e: e["id"])})
    return path


def sfx_menu(sfx: dict[str, dict], per_category: int = 6) -> dict[str, list[dict]]:
    """What the Editor sees: a few short, clean options per category (not thousands of files).
    Closest to the category's typical length first, alternating sources so one pack never fills a category."""
    by_cat: dict[str, dict[str, list[dict]]] = {}
    for e in sorted(sfx.values(), key=lambda e: (abs(e["duration_ms"] - TYPICAL_MS.get(e.get("category"), 700)), e["id"])):
        by_cat.setdefault(e.get("category", "other"), {}).setdefault(e.get("source", ""), []).append(e)
    menu: dict[str, list[dict]] = {}
    for cat in sorted(by_cat):
        queues = [by_cat[cat][s] for s in sorted(by_cat[cat])]
        picked: list[dict] = []
        while len(picked) < per_category and any(queues):
            for q in queues:
                if q and len(picked) < per_category:
                    picked.append(q.pop(0))
        menu[cat] = picked
    return menu


def credit_lines(tl, idx=None) -> list[str]:
    """Attribution the post must carry for the music/SFX a timeline uses (CC BY tracks); [] when all
    assets are owned, CC0 or royalty-free without attribution. One block per asset, in timeline order."""
    if idx is None:
        idx = assets_mod.load()
    out: list[str] = []
    used = [a.asset for a in tl.audio if a.role in ("music", "sfx")] + [c.asset for c in tl.video if c.id.startswith("br_")]
    for aid in used:
        snap = tl.assets.get(aid)
        meta = (idx.music.get(aid) or idx.sfx.get(aid) or idx.broll.get(aid) or {})
        # the compile-time snapshot wins: a library moved or not yet fetched must never drop a required credit
        for text in ((snap.attribution if snap else "") or meta.get("attribution") or "", (snap.credit if snap else "") or meta.get("credit") or ""):
            text = text.strip()
            if text and text not in out:
                out.append(text)
    return out


def unknown_licences(tl, idx=None) -> list[str]:
    """Library assets the timeline uses whose licence is unknown (neither snapshotted nor in the index)."""
    if idx is None:
        idx = assets_mod.load()
    bad = []
    for a in tl.audio:
        if a.role not in ("music", "sfx"):
            continue
        snap = tl.assets.get(a.asset)
        meta = idx.music.get(a.asset) or idx.sfx.get(a.asset) or {}
        if not ((snap and snap.license) or meta.get("license")):
            bad.append(a.asset)
    return sorted(set(bad))


FORBIDDEN_LICENCE = re.compile(r"(^|[-_\s])(SA|NC|ND)([-_\s.]|$)|share.?alike|non.?commercial|no.?deriv", re.I)


def check_licence(licence: str) -> None:
    """Never index ShareAlike, NonCommercial or NoDerivatives material: it cannot go into a paid client's reel."""
    if FORBIDDEN_LICENCE.search(licence or ""):
        raise ValueError(f"licence {licence!r} is ShareAlike / NonCommercial / NoDerivatives — not usable in client reels")
