"""Eval manifest, run bookkeeping and the scoreboard (ADR-0029/0030).

Step 1 scope: every reel in the chosen set is run through the stages that exist so far;
families that need later stages are simply absent (the primary score re-normalises).
The holdout set is refused unless explicitly requested (it is for release candidates only).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

import yaml

from reel import config
from reel.evalh.metrics import ReelScore
from reel.runner import run_pipeline
from reel.stages import PIPELINE
from reel.workspace import Workspace

MANIFEST = config.EVAL_DIR / "manifest.yaml"
SCOREBOARD = config.EVAL_DIR / "scoreboard.jsonl"
GOLD_DIR = config.REPO_ROOT / "samples" / "gold"


class HoldoutRefused(RuntimeError):
    pass


def init_manifest(holdout: int = 6) -> dict:
    """Create/refresh the manifest from samples/gold/<name>/ folders.

    Existing split assignments are kept; new reels default to 'tuning'. The owner marks
    the holdout explicitly (at least 2 Hinglish) — the harness never picks it silently.
    """
    existing = {}
    if MANIFEST.exists():
        existing = {r["id"]: r for r in (yaml.safe_load(MANIFEST.read_text()) or {}).get("reels", [])}
    reels = []
    if GOLD_DIR.exists():
        for d in sorted(p for p in GOLD_DIR.iterdir() if p.is_dir()):
            prev = existing.get(d.name, {})
            reels.append({
                "id": d.name,
                "raw": str((d / "raw").relative_to(config.REPO_ROOT)),
                "final": str((d / "final.mp4").relative_to(config.REPO_ROOT)) if (d / "final.mp4").exists() else None,
                "split": prev.get("split", "tuning"),
                "genre": prev.get("genre"),
                "language": prev.get("language"),
            })
    manifest = {"holdout_target": holdout, "reels": reels}
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=config.REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def knowledge_hash() -> str:
    h = hashlib.sha256()
    files = [config.KNOWLEDGE_DIR / "capabilities.yaml", *sorted((config.KNOWLEDGE_DIR / "graph").glob("*.yaml"))]
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


def run_eval(split: str = "tuning", *, allow_holdout: bool = False, work_root: Path | None = None) -> dict:
    if split == "holdout" and not allow_holdout:
        raise HoldoutRefused("The holdout set is for release candidates only. Pass --holdout to confirm.")
    if not MANIFEST.exists():
        init_manifest()
    manifest = yaml.safe_load(MANIFEST.read_text()) or {}
    reels = [r for r in manifest.get("reels", []) if r.get("split") == split]
    run_id = time.strftime("%Y%m%d-%H%M%S")
    work_root = work_root or (config.REPO_ROOT / "projects" / "_eval" / run_id)
    results = []
    for r in reels:
        ws = Workspace.create(work_root / r["id"])
        score = ReelScore()
        try:
            state = run_pipeline(ws, PIPELINE, options={"input": str(config.REPO_ROOT / r["raw"])})
            mezz = json.loads(ws.path("mezz", "report.json").read_text())
            checks = [c["ok"] for c in mezz.get("clips", [])]
            score.families["soft_gates"] = sum(checks) / len(checks) if checks else 0.0
            stages_done = [k for k, v in state["stages"].items() if v.get("status") == "done"]
        except Exception as exc:  # crash = veto (ADR-0030)
            score.vetoes.append(f"crash: {type(exc).__name__}: {exc}")
            stages_done = []
        results.append({"id": r["id"], "families": score.families, "vetoes": score.vetoes,
                        "primary": score.primary, "stages": stages_done})
    scored = [x["primary"] for x in results if x["primary"] is not None]
    row = {
        "run_id": run_id,
        "time": time.time(),
        "split": split,
        "commit": _git("rev-parse", "--short", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
        "knowledge": knowledge_hash(),
        "tools": tool_versions(),
        "reels": results,
        "mean_primary": round(sum(scored) / len(scored), 2) if scored else None,
        "vetoed": sum(1 for x in results if x["vetoes"]),
    }
    config.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCOREBOARD, "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return row
