"""Libraries (FR-10), brand kits, the quality lab (FR-11) and health (FR-12)."""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from pathlib import Path

import yaml
from pydantic import ValidationError

from reel import assets
from reel.brief import Brand
from reel.workspace import atomic_write_json

BRAND_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


# ------------------------------------------------------------------ libraries


def libraries() -> dict:
    idx = assets.load()
    lic = lambda m: m.get("license") or m.get("licence") or m.get("rights")  # noqa: E731
    return {
        "sfx": [{"id": k, "category": m.get("category"), "duration_ms": m.get("duration_ms"), "source": m.get("source"),
                 "license": lic(m), "file": m.get("file")} for k, m in sorted(idx.sfx.items())],
        "music": [{"id": k, "title": m.get("title") or m.get("name") or k, "mood": m.get("mood"), "bpm": m.get("bpm"),
                   "duration_ms": m.get("duration_ms"), "source": m.get("source"), "license": lic(m),
                   "attribution": m.get("attribution") or m.get("credit")} for k, m in sorted(idx.music.items())],
        "broll": [{"id": k, "description": m.get("description"), "shot": m.get("shot") or m.get("shot_type"), "tags": m.get("tags", []),
                   "duration_ms": m.get("duration_ms"), "source": m.get("source"), "license": lic(m), "file": m.get("file")}
                  for k, m in sorted(idx.broll.items())],
        "caption_families": [{"id": k, "for": m.get("for", []), "mood": m.get("mood"), "max_words": m.get("max_words"),
                              "tokens": m.get("tokens", {})} for k, m in idx.caption_families.items()],
    }


# ------------------------------------------------------------------ brand kits (brands/<id>.json, validated with reel.brief.Brand)


class BrandError(ValueError):
    pass


def brand_slug(client: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", client.lower()).strip("-")[:64]
    return s or "brand"


def brand_path(root: Path, bid: str) -> Path | None:
    return root / f"{bid}.json" if BRAND_ID_RE.match(bid or "") else None


def list_brands(root: Path) -> list[dict]:
    out = []
    for p in sorted(root.glob("*.json")) if root.exists() else []:
        try:
            out.append({"id": p.stem, **json.loads(p.read_text())})
        except ValueError:
            continue
    return out


def validate_brand(body: dict) -> Brand:
    try:
        return Brand.model_validate({k: v for k, v in body.items() if k != "id"})
    except ValidationError as exc:
        raise BrandError(json.loads(exc.json(include_url=False))) from exc


def save_brand(root: Path, bid: str, brand: Brand) -> dict:
    atomic_write_json(root / f"{bid}.json", brand.model_dump(mode="json", exclude_none=True))
    return {"id": bid, **brand.model_dump(mode="json", exclude_none=True)}


# ------------------------------------------------------------------ quality lab


def _jsonl(path: Path, limit: int = 200) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def release_lock(manifest: Path) -> tuple[bool, str, dict]:
    """ADR-0031: the release check (holdout eval) is locked until the holdout set is complete."""
    from reel.evalh.harness import HOLDOUT_MIN_HINGLISH, HOLDOUT_SIZE

    reels = ((yaml.safe_load(manifest.read_text()) or {}).get("reels", []) if manifest.exists() else [])
    hold = [r for r in reels if r.get("split") == "holdout"]
    hing = [r for r in reels if r.get("language") in ("hi", "hinglish")]
    hold_hing = [r for r in hold if r.get("language") in ("hi", "hinglish")]
    gold = {"pairs": len(reels), "tuning": sum(1 for r in reels if r.get("split") == "tuning"), "holdout": len(hold), "hinglish": len(hing),
            "reels": [{"id": r.get("id"), "split": r.get("split"), "language": r.get("language"), "genre": r.get("genre"),
                       "channel": r.get("channel"), "has_final": bool(r.get("final"))} for r in reels]}
    locked = len(hold) < HOLDOUT_SIZE or len(hold_hing) < HOLDOUT_MIN_HINGLISH
    reason = (f"Release check locked (ADR-0031): holdout has {len(hold)}/{HOLDOUT_SIZE} reels, "
              f"{len(hold_hing)}/{HOLDOUT_MIN_HINGLISH} Hinglish.") if locked else ""
    return locked, reason, gold


def lab(settings) -> dict:
    from reel import calibrate

    locked, reason, gold = release_lock(settings.eval_manifest)
    try:
        calibration = calibrate.report(calibrate.collect(settings.projects_root))
    except (OSError, ValueError, KeyError):
        calibration = None
    scores = [{"run_id": r.get("run_id"), "time": r.get("time"), "split": r.get("split"), "mean_primary": r.get("mean_primary"),
               "vetoed": r.get("vetoed"), "commit": r.get("commit"), "knowledge": r.get("knowledge"),
               "families": _mean_families(r.get("reels", [])),
               "reels": [{"id": x.get("id"), "primary": x.get("primary"), "verdict": x.get("verdict"), "vetoes": x.get("vetoes", [])}
                         for x in r.get("reels", [])]}
              for r in _jsonl(settings.scoreboard)]
    return {"gold": gold, "release_locked": locked, "lock_reason": reason, "calibration": calibration,
            "improve_history": _jsonl(settings.improve_log), "scores": scores}


def _mean_families(reels: list[dict]) -> dict:
    acc: dict[str, list[float]] = {}
    for r in reels:
        for k, v in (r.get("families") or {}).items():
            if isinstance(v, (int, float)):
                acc.setdefault(k, []).append(float(v))
    return {k: round(sum(v) / len(v), 3) for k, v in acc.items()}


# ------------------------------------------------------------------ health


class _Doctor:
    """doctor.check() runs ffmpeg and `claude --version`: cached for a minute, never called per poll."""

    def __init__(self, check=None, ttl_s: float = 60.0):
        self.check = check
        self.ttl = ttl_s
        self.value: dict | None = None
        self.at = 0.0
        self.lock = threading.Lock()

    def get(self) -> dict:
        with self.lock:
            if self.value is None or time.monotonic() - self.at > self.ttl:
                if self.check is None:
                    from reel import doctor

                    self.check = doctor.check
                try:
                    self.value = self.check()
                except Exception as exc:  # noqa: BLE001
                    self.value = {"ok": False, "items": [{"name": "doctor", "ok": False, "detail": str(exc), "required": True}]}
                self.at = time.monotonic()
            return self.value


def health(settings, doctor: _Doctor, mgr) -> dict:
    from importlib import metadata

    from reel.studio import jobs

    rep = doctor.get()
    try:
        version = metadata.version("reel")
    except metadata.PackageNotFoundError:
        version = "0.1.0"
    disk = shutil.disk_usage(settings.projects_root if settings.projects_root.exists() else Path.home())
    claude = shutil.which("claude") is not None
    return {"engine": "ok", "version": version, "toolchain_ok": bool(rep.get("ok")),
            "tools": [{"name": i["name"], "ok": i["ok"], "detail": i["detail"], "required": i.get("required", True)} for i in rep.get("items", [])],
            "claude": claude, "disk_free_gb": round(disk.free / 2**30, 1),
            "jobs": {"running": len(mgr.running()), "queued": len(mgr.queued()), "limit": settings.max_jobs},
            "memory_gb": {"used": mgr.used_gb(), "budget": settings.memory_budget_gb, "system": jobs.system_memory()},
            "projects_root": str(settings.projects_root)}
