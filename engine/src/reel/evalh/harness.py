"""Eval manifest, run bookkeeping and the scoreboard (ADR-0029/0030).

Every gold reel of a split runs through the full edit (fix loop included, as in real use) and
is scored against the owner's final (evalh/gold.py). The holdout set is refused unless
explicitly requested (release candidates only).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

import yaml

from reel import config
from reel.workspace import Workspace

MANIFEST = config.EVAL_DIR / "manifest.yaml"
SCOREBOARD = config.EVAL_DIR / "scoreboard.jsonl"
GOLD_DIR = config.REPO_ROOT / "samples" / "gold"


HOLDOUT_SIZE = 6
HOLDOUT_MIN_HINGLISH = 2


class HoldoutRefused(RuntimeError):
    pass


def _rel(p: Path) -> str:
    """Repo-relative when inside the repo (portable manifest), absolute otherwise."""
    try:
        return str(p.relative_to(config.REPO_ROOT))
    except ValueError:
        return str(p)


def _abs(s: str) -> Path:
    return Path(s) if Path(s).is_absolute() else config.REPO_ROOT / s


def init_manifest(holdout: int = 6, *, auto_holdout: bool = False, seed: int = 7) -> dict:
    """Create/refresh the manifest from samples/gold/<name>/ folders.

    Existing split assignments are kept; new reels default to 'tuning'. Language/genre come from
    the pair's brief.json. `auto_holdout` (owner is not an editor, so the tool picks): a seeded,
    stratified holdout of `holdout` reels with ≥ 2 Hinglish and as many channels as possible —
    picked once and then frozen (existing assignments are never changed).
    """
    import random

    existing = {}
    if MANIFEST.exists():
        existing = {r["id"]: r for r in (yaml.safe_load(MANIFEST.read_text()) or {}).get("reels", [])}
    reels = []
    if GOLD_DIR.exists():
        for d in sorted(p for p in GOLD_DIR.iterdir() if p.is_dir()):
            prev = existing.get(d.name, {})
            brief = json.loads((d / "brief.json").read_text()) if (d / "brief.json").exists() else {}
            src = json.loads((d / "source.json").read_text()) if (d / "source.json").exists() else {}
            reels.append({
                "id": d.name,
                "raw": _rel(d / "raw"),
                "final": _rel(d / "final.mp4") if (d / "final.mp4").exists() else None,
                "split": prev.get("split", "tuning"),
                "genre": prev.get("genre") or brief.get("genre_hint"),
                "language": prev.get("language") or brief.get("language"),
                "channel": prev.get("channel") or src.get("channel"),
            })
    if auto_holdout and not any(r["split"] == "holdout" for r in reels):
        rng = random.Random(seed)
        pool = [r for r in reels if r["final"]]
        rng.shuffle(pool)
        hing = [r for r in pool if r["language"] in ("hi", "hinglish")]
        pick = hing[:2]
        seen = {r["channel"] for r in pick}
        for r in pool:  # then spread across channels
            if len(pick) >= holdout:
                break
            if r not in pick and r["channel"] not in seen:
                pick.append(r)
                seen.add(r["channel"])
        for r in pool:
            if len(pick) >= holdout:
                break
            if r not in pick:
                pick.append(r)
        for r in pick:
            r["split"] = "holdout"
    manifest = {"holdout_target": holdout, "reels": reels}
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    return manifest


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=config.REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def knowledge_hash() -> str:
    h = hashlib.sha256()
    files = [config.KNOWLEDGE_DIR / "capabilities.yaml", *sorted((config.KNOWLEDGE_DIR / "graph").glob("*.yaml")),
             *sorted((config.KNOWLEDGE_DIR / "learned").glob("*.yaml"))]
    for f in files:
        if f.exists():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def tool_versions() -> dict:
    out = {}
    try:
        line = subprocess.run([str(config.ffmpeg_path()), "-version"], capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
        out["ffmpeg"] = line
    except Exception as exc:  # noqa: BLE001 — record, don't fail bookkeeping
        out["ffmpeg"] = f"unavailable: {exc}"
    try:
        out["claude"] = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        out["claude"] = "not found"
    return out


def score_reel(r: dict, ws: Workspace, *, asr_backend, kappa: float | None, style_lib: dict | None = None) -> dict:
    """Score one finished gold-set reel against the owner's final (ADR-0030 §2)."""
    from reel import project
    from reel.evalh import gold
    from reel.perception import visual
    from reel.perception.audio import extract_wav

    final_ours = ws.path("render", "final.mp4")
    heard, _ = asr_backend.transcribe(extract_wav(final_ours, ws.path("eval", "ours.wav")), r.get("language"), None)
    raw = project.word_table(ws)
    g = gold.load_gold(_abs(r["final"]), raw, asr_backend, config.EVAL_DIR / "cache" / f"{r['id']}.gold.json")
    score, detail = gold.score_workspace(ws, g, heard_ours=heard, ours_cuts=len(visual.scene_cuts(final_ours)), kappa=kappa)
    if style_lib:
        from reel.evalh import style

        ours = style.cached_vector(final_ours, ws.path("eval", "style.json"))
        lib = style_lib.get(r.get("genre") or "any") or style_lib.get("any", {})
        st, parts = style.style_score(ours, lib)
        if st is not None:
            score.families["style"] = st
            detail["style"] = parts
    verdict = json.loads(ws.path("qa", "verdict.json").read_text()).get("status") if ws.path("qa", "verdict.json").exists() else None
    review = json.loads(ws.path("qa", "review.json").read_text()) if ws.path("qa", "review.json").exists() else {}
    used = []
    for plan in ("story", "finish"):
        f = ws.path("plan", f"{plan}.json")
        if f.exists():
            used += json.loads(f.read_text()).get("knowledge_used", [])
    return {"families": score.families, "vetoes": score.vetoes, "primary": score.primary, "detail": detail, "verdict": verdict,
            "review_issues": [f"{i['severity']} {i['category']}: {i['problem']}" for i in review.get("issues", [])],
            "knowledge_used": sorted(set(used))}


def run_eval(split: str = "tuning", *, allow_holdout: bool = False, work_root: Path | None = None, caller=None,
             reels_filter: list[str] | None = None, label: str = "", fresh_decisions: bool = False) -> dict:
    """Run the full edit (with the fix loop) on every gold reel of `split` and score it vs the owner's final."""
    from reel import autofix, bakeoff, calibrate
    from reel.stages import EDIT_PIPELINE

    if split == "holdout" and not allow_holdout:
        raise HoldoutRefused("The holdout set is for release candidates only. Pass --holdout to confirm.")
    if not MANIFEST.exists():
        init_manifest()
    manifest = yaml.safe_load(MANIFEST.read_text()) or {}
    if split == "holdout":  # ADR-0031: the release check is locked until the holdout is complete
        hold = [r for r in manifest.get("reels", []) if r.get("split") == "holdout"]
        hing = [r for r in hold if r.get("language") in ("hi", "hinglish")]
        if len(hold) < HOLDOUT_SIZE or len(hing) < HOLDOUT_MIN_HINGLISH:
            raise HoldoutRefused(f"Release check locked (ADR-0031): holdout has {len(hold)}/{HOLDOUT_SIZE} reels, "
                                 f"{len(hing)}/{HOLDOUT_MIN_HINGLISH} Hinglish.")
    reels = [r for r in manifest.get("reels", []) if r.get("split") == split and (not reels_filter or r["id"] in reels_filter)]
    run_id = time.strftime("%Y%m%d-%H%M%S") + (f"-{label}" if label else "")
    work_root = work_root or (config.REPO_ROOT / "projects" / "_eval" / run_id)
    kappa = calibrate.report(calibrate.collect(config.REPO_ROOT / "projects"))["reviewer"]["kappa"]
    from reel.evalh import style

    style_lib = style.library(manifest.get("reels", []), _abs)
    asr = None
    results = []
    for r in reels:
        ws = Workspace.create(work_root / r["id"])
        gold_dir = GOLD_DIR / r["id"]
        brief = gold_dir / "brief.json"
        options = {"input": str(_abs(r["raw"])), "language": r.get("language"), "brief": str(brief) if brief.exists() else None}
        try:
            if not r.get("final"):
                raise FileNotFoundError(f"{r['id']}: no final.mp4 (gold edit) to score against")
            # fresh_decisions: re-ask the Editor even if inputs are unchanged (repeat runs measure decision variance)
            autofix.run(ws, EDIT_PIPELINE, options, caller=caller, force={"story", "finish"} if fresh_decisions else None)
            if asr is None:
                eng = config.ASR_ENGINES.get(r.get("language") or "en", config.ASR_ENGINES["en"])
                asr = bakeoff.engines([eng])[eng]
            results.append({"id": r["id"], "language": r.get("language"), **score_reel(r, ws, asr_backend=asr, kappa=kappa, style_lib=style_lib)})
        except Exception as exc:  # crash = veto (ADR-0030)
            results.append({"id": r["id"], "language": r.get("language"), "families": {}, "primary": None,
                            "vetoes": [f"crash: {type(exc).__name__}: {exc}"]})
    scored = [x["primary"] for x in results if x["primary"] is not None]
    row = {
        "run_id": run_id,
        "time": time.time(),
        "split": split,
        "commit": _git("rev-parse", "--short", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
        "knowledge": knowledge_hash(),
        "tools": tool_versions(),
        "reviewer_kappa": kappa,
        "reels": results,
        "mean_primary": round(sum(scored) / len(scored), 2) if scored else None,
        "vetoed": sum(1 for x in results if x["vetoes"]),
    }
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCOREBOARD, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return row
