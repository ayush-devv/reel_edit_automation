"""Free-model listening test (roadmap G2.5): blind A/B of generated SFX, music and voice against what we have today.

Group 3 (generated SFX, scored music, Indic voice) waits on this. The question each set answers is not "is the model
impressive" but **"is it better than today's fallback, and usable in a client reel?"**:
- **sfx** and **music**: candidates against our current library (the nearest indexed file by name and mood);
- **voice**: candidates against each other. macOS `say` is a reference point only: its voices may not be
  used in client work, so it can never be adopted.

Models are not bundled. The owner installs one, reads its licence at the pinned commit, and declares it in
`~/.config/reel/generators.json`:
    {"stable-audio-3-small-sfx": {"set": "sfx", "licence_id": "stability-community",
                                   "cmd": ["/path/python", "/path/gen.py", "--prompt", "{prompt}", "--seconds", "{seconds}", "--out", "{out}"],
                                   "commit": "…", "weights_sha256": "…", "paid": false}}
A generator whose `licence_id` has no row in assets/licenses/registry.yaml (or a blocked one) is **refused**: no
generated file may reach a reel before its licence is on record. Voice cloning is tested on the owner's own voice
only, with the written self-consent file in the set folder.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import time
from pathlib import Path

from reel import config
from reel.workspace import atomic_write_json

ROOT = config.REPO_ROOT / "eval" / "listening"
ADOPT_USABLE = 0.70  # share of a model's outputs the owner would put in a client reel
ADOPT_WIN = 0.50  # and it must beat the fallback in more than half of its comparisons
GENERATE_TIMEOUT_S = 900

PROMPTS: dict[str, list[dict]] = {
    "sfx": [
        {"id": "cooker", "text": "pressure cooker whistle in an Indian kitchen", "seconds": 4, "match": "whistle steam kitchen"},
        {"id": "rickshaw", "text": "auto-rickshaw horn on a busy street", "seconds": 3, "match": "horn street traffic"},
        {"id": "wah", "text": "small crowd cheering 'wah!' indoors", "seconds": 3, "match": "crowd cheer applause"},
        {"id": "ding", "text": "cash register ding, clean and short", "seconds": 2, "match": "cash register ding coin"},
        {"id": "dhol", "text": "single dhol drum hit, punchy", "seconds": 2, "match": "drum hit impact"},
        {"id": "notify", "text": "phone notification chime", "seconds": 2, "match": "notification chime ping"},
        {"id": "whoosh", "text": "fast whoosh transition", "seconds": 1, "match": "whoosh swish transition"},
    ],
    "music": [
        {"id": "bollypop", "text": "upbeat Bollywood-pop instrumental bed, 100 bpm, no vocals", "seconds": 30, "match": "upbeat happy pop energetic"},
        {"id": "chai_lofi", "text": "lo-fi chai-shop beat, warm, relaxed, no vocals", "seconds": 30, "match": "lofi chill calm relaxed"},
        {"id": "corporate", "text": "corporate motivational build, piano and strings", "seconds": 30, "match": "inspiring corporate motivational"},
        {"id": "devotional", "text": "calm devotional bed, tanpura drone and soft flute", "seconds": 30, "match": "calm peaceful ambient"},
    ],
    "voice": [
        {"id": "hi_number", "text": "आपकी सैलरी का दस प्रतिशत, यानी पच्चीस हज़ार रुपये, हर महीने अलग रखिए।", "seconds": 0, "lang": "hi"},
        {"id": "hinglish", "text": "Dekho, agar aap har mahine sirf paanch hazaar bhi invest karte ho, toh das saal mein yeh ek lakh se zyada ban jaata hai.", "seconds": 0, "lang": "hinglish"},
        {"id": "hi_crore", "text": "पिछले साल हमारी कंपनी ने ढाई करोड़ का टर्नओवर किया।", "seconds": 0, "lang": "hi"},
        {"id": "ta_cta", "text": "இந்த வீடியோவை உங்கள் நண்பர்களுடன் பகிருங்கள்.", "seconds": 0, "lang": "ta"},
        {"id": "en_cta", "text": "Follow for part two, where I show you the exact spreadsheet.", "seconds": 0, "lang": "en"},
    ],
}
FALLBACK = {"sfx": "library", "music": "library"}  # built in; voice has no fallback we may ship
REFERENCE_ONLY = {"macos_say"}  # may be listened to, never adopted


class ListenError(ValueError):
    pass


def generators_file() -> Path:
    return Path(os.environ.get("REEL_CONFIG_DIR") or Path.home() / ".config" / "reel") / "generators.json"


def declared() -> dict[str, dict]:
    f = generators_file()
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except (OSError, ValueError) as exc:
        raise ListenError(f"{f} is not valid JSON: {exc}") from exc


def check_licence(gen_id: str, spec: dict, reg=None) -> None:
    from reel import licences

    reg = reg or licences.load_registry()
    lid = spec.get("licence_id")
    lic = reg.licences.get(lid or "")
    if lic is None:
        raise ListenError(f"{gen_id}: licence {lid!r} has no row in assets/licenses/registry.yaml. Read the model's licence at its pinned "
                          f"commit and add the row first: no generated file may reach a reel before its licence is on record.")
    if lic.blocked or not lic.commercial_ok:
        raise ListenError(f"{gen_id}: licence {lid!r} is not usable for client work ({lic.blocked or 'not commercial'}).")


def _library_pick(kind: str, match: str) -> Path | None:
    from reel import asset_search, assets

    idx = assets.load()
    pool = idx.sfx if kind == "sfx" else idx.music
    if not pool:
        return None
    docs = {k: " ".join(str(v.get(f, "")) for f in ("name", "title", "category", "mood", "feel", "tags")) for k, v in pool.items()}
    scores = asset_search.BM25(docs).scores(match)
    best = max(scores, key=lambda k: (scores[k], k))
    return Path(pool[best]["file"])


def _run(cmd: list[str], prompt: dict, out: Path) -> None:
    args = [a.replace("{prompt}", prompt["text"]).replace("{seconds}", str(prompt.get("seconds") or 0)).replace("{out}", str(out))
            .replace("{lang}", prompt.get("lang", "")) for a in cmd]
    subprocess.run(args, check=True, capture_output=True, timeout=GENERATE_TIMEOUT_S)
    if not out.exists() or out.stat().st_size == 0:
        raise ListenError(f"the generator wrote nothing to {out.name}")


def _say(prompt: dict, out: Path) -> None:
    voice = {"hi": "Lekha", "hinglish": "Lekha", "en": "Samantha", "ta": "Vani"}.get(prompt.get("lang", "en"), "Samantha")
    subprocess.run(["say", "-v", voice, "-o", str(out.with_suffix(".aiff")), prompt["text"]], check=True, capture_output=True, timeout=120)
    subprocess.run([str(config.ffmpeg_path()), "-y", "-loglevel", "error", "-i", str(out.with_suffix(".aiff")), str(out)], check=True)
    out.with_suffix(".aiff").unlink(missing_ok=True)


def _root(root: Path | None) -> Path:
    return root or ROOT  # resolved at call time (tests and the Studio patch ROOT)


def _blind_name(model: str, prompt: str, suffix: str) -> str:
    """File names must not give the model away on the listening page."""
    import hashlib

    return hashlib.sha1(f"{model}|{prompt}".encode()).hexdigest()[:12] + suffix


def prepare(kind: str, root: Path | None = None, *, gens: dict[str, dict] | None = None, reg=None, runner=None) -> dict:
    """Render every prompt with every declared generator of this set plus the fallback. Refused or failing
    generators are recorded with the reason; nothing silently passes."""
    root = _root(root)
    if kind not in PROMPTS:
        raise ListenError(f"unknown set {kind!r}: use one of {', '.join(PROMPTS)}")
    gens = declared() if gens is None else gens
    out_dir = root / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"set": kind, "created": time.time(), "outputs": [], "generators": {}}
    mine = {g: s for g, s in gens.items() if s.get("set") == kind}
    for gid, spec in mine.items():
        try:
            check_licence(gid, spec, reg)
            manifest["generators"][gid] = {"status": "ok", **{k: spec.get(k) for k in ("licence_id", "commit", "weights_sha256", "paid")}}
        except ListenError as exc:
            manifest["generators"][gid] = {"status": "refused", "why": str(exc)}
    run = runner or _run
    for p in PROMPTS[kind]:
        pdir = out_dir / p["id"]
        pdir.mkdir(parents=True, exist_ok=True)
        if kind in FALLBACK:
            src = _library_pick(kind, p["match"])
            if src and src.exists():
                dst = pdir / _blind_name("library", p["id"], src.suffix)
                shutil.copy2(src, dst)
                manifest["outputs"].append({"prompt": p["id"], "model": "library", "file": str(dst.relative_to(root)), "seconds": 0.0})
        elif kind == "voice" and shutil.which("say"):
            dst = pdir / _blind_name("macos_say", p["id"], ".wav")
            try:
                _say(p, dst)
                manifest["outputs"].append({"prompt": p["id"], "model": "macos_say", "file": str(dst.relative_to(root)), "seconds": 0.0})
            except (subprocess.SubprocessError, OSError):
                pass
        for gid, spec in mine.items():
            if manifest["generators"][gid]["status"] != "ok":
                continue
            dst = pdir / _blind_name(gid, p["id"], ".wav")
            t0 = time.time()
            try:
                run(spec["cmd"], p, dst)
                manifest["outputs"].append({"prompt": p["id"], "model": gid, "file": str(dst.relative_to(root)), "seconds": round(time.time() - t0, 1)})
            except (subprocess.SubprocessError, OSError, ListenError, KeyError) as exc:
                manifest["generators"][gid].setdefault("failures", []).append(f"{p['id']}: {type(exc).__name__}: {exc}"[:300])
    atomic_write_json(out_dir / "manifest.json", manifest)
    pairs(kind, root, seed=int(manifest["created"]))
    return manifest


def pairs(kind: str, root: Path | None = None, *, seed: int = 0) -> list[dict]:
    """Blind pairs per prompt: every candidate against the fallback (sfx, music) or every two candidates (voice),
    sides randomised. The key (which side is which model) stays in pairs.json, never in what the page shows."""
    root = _root(root)
    m = json.loads((root / kind / "manifest.json").read_text())
    by_prompt: dict[str, list[dict]] = {}
    for o in m["outputs"]:
        by_prompt.setdefault(o["prompt"], []).append(o)
    rng = random.Random(seed)
    out = []
    for prompt, outs in by_prompt.items():
        base = FALLBACK.get(kind)
        if base:
            ref = next((o for o in outs if o["model"] == base), None)
            combos = [(ref, o) for o in outs if ref and o["model"] != base]
        else:
            combos = [(a, b) for i, a in enumerate(outs) for b in outs[i + 1:]]
        for a, b in combos:
            if rng.random() < 0.5:
                a, b = b, a
            out.append({"id": f"{prompt}:{len(out):03d}", "prompt": prompt, "A": a, "B": b})
    rng.shuffle(out)
    atomic_write_json(root / kind / "pairs.json", out)
    return out


def blind(kind: str, root: Path | None = None) -> list[dict]:
    """What the listening page may show: prompt text and two files, no model names."""
    root = _root(root)
    p = root / kind / "pairs.json"
    if not p.exists():
        return []
    text = {x["id"]: x["text"] for x in PROMPTS[kind]}
    done = {v["pair"] for v in _votes(kind, root)}
    return [{"id": x["id"], "prompt": text.get(x["prompt"], x["prompt"]), "A": x["A"]["file"], "B": x["B"]["file"], "done": x["id"] in done}
            for x in json.loads(p.read_text())]


def _votes(kind: str, root: Path) -> list[dict]:
    f = root / kind / "results.json"
    return json.loads(f.read_text()).get("votes", []) if f.exists() else []


def vote(kind: str, pair_id: str, choice: str, usable_a: bool, usable_b: bool, root: Path | None = None) -> None:
    root = _root(root)
    if choice not in ("A", "B", "tie"):
        raise ListenError("choice must be A, B or tie")
    known = {x["id"] for x in json.loads((root / kind / "pairs.json").read_text())}
    if pair_id not in known:
        raise ListenError(f"unknown pair {pair_id!r}")
    votes = [v for v in _votes(kind, root) if v["pair"] != pair_id]  # a re-vote replaces the earlier one
    votes.append({"pair": pair_id, "choice": choice, "usable_a": bool(usable_a), "usable_b": bool(usable_b), "at": time.time()})
    atomic_write_json(root / kind / "results.json", {"votes": votes})


def summary(kind: str, root: Path | None = None) -> dict:
    """Per model: comparisons, win rate (ties count half), usable rate, mean generation time, and the decision."""
    root = _root(root)
    pairs_ = {x["id"]: x for x in json.loads((root / kind / "pairs.json").read_text())}
    m = json.loads((root / kind / "manifest.json").read_text())
    gen_s: dict[str, list[float]] = {}
    for o in m["outputs"]:
        gen_s.setdefault(o["model"], []).append(o.get("seconds") or 0.0)
    stats: dict[str, dict] = {}
    for v in _votes(kind, root):
        pr = pairs_.get(v["pair"])
        if not pr:
            continue
        for side, other in (("A", "B"), ("B", "A")):
            model = pr[side]["model"]
            s = stats.setdefault(model, {"n": 0, "wins": 0.0, "usable": 0})
            s["n"] += 1
            s["wins"] += 1.0 if v["choice"] == side else 0.5 if v["choice"] == "tie" else 0.0
            s["usable"] += int(v[f"usable_{side.lower()}"])
    rows = {}
    for model, s in stats.items():
        win, usable = s["wins"] / s["n"], s["usable"] / s["n"]
        paid = bool((m["generators"].get(model) or {}).get("paid"))
        if model in REFERENCE_ONLY or model == FALLBACK.get(kind):
            decision = "reference"
        elif usable >= ADOPT_USABLE and win > ADOPT_WIN:
            decision = "adopt" + (" (paid)" if paid else "")
        else:
            decision = "not yet"
        rows[model] = {"comparisons": s["n"], "win_rate": round(win, 3), "usable_rate": round(usable, 3),
                       "mean_generation_s": round(sum(gen_s.get(model, [0])) / max(1, len(gen_s.get(model, []))), 1), "decision": decision}
    return {"set": kind, "votes": len(_votes(kind, root)), "pairs": len(pairs_), "rule": f"adopt when usable ≥ {ADOPT_USABLE:.0%} and it beats the "
            f"{'fallback' if kind in FALLBACK else 'other voices'} in more than {ADOPT_WIN:.0%} of comparisons", "models": rows,
            "generators": m["generators"]}
