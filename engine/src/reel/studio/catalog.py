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
        "unreadable": [],  # the indexer skips unreadable files without reporting them yet (engine gap)
    }


def library_file(kind: str, item_id: str) -> Path | None:
    """The audio / video file of one indexed library item (play buttons, FR-10). Only indexed items are served."""
    item = getattr(assets.load(), kind, {}).get(item_id)
    if not item or not item.get("file"):
        return None
    p = Path(item["file"]).expanduser()
    if not p.is_absolute():  # b-roll index entries are relative to the library folder
        p = next((c for c in (assets.ASSETS_DIR / "broll_owned" / p, assets.ASSETS_DIR / p, assets.config.REPO_ROOT / p) if c.exists()), p)
    return p if p.is_file() else None


# ------------------------------------------------------------------ brand kits (brands/<id>.json, validated with reel.brief.Brand)


class BrandError(ValueError):
    pass


def brand_slug(client: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", client.lower()).strip("-")[:64]
    return s or "brand"


def brand_path(root: Path, bid: str) -> Path | None:
    return root / f"{bid}.json" if BRAND_ID_RE.match(bid or "") else None


def brand_entry(bid: str, data: dict) -> dict:
    """`{id, brand}`: the id is the file name, never a Brand field (Brand is extra="forbid")."""
    try:
        brand = Brand.model_validate(data).model_dump(mode="json")
    except ValidationError:
        brand = data  # an invalid file still lists, so it can be fixed
    return {"id": bid, "brand": brand}


def list_brands(root: Path) -> list[dict]:
    out = []
    for p in sorted(root.glob("*.json")) if root.exists() else []:
        try:
            out.append(brand_entry(p.stem, json.loads(p.read_text())))
        except ValueError:
            continue
    return out


def validate_brand(body: dict) -> Brand:
    try:
        return Brand.model_validate(body)
    except ValidationError as exc:
        raise BrandError(json.loads(exc.json(include_url=False))) from exc


def save_brand(root: Path, bid: str, brand: Brand) -> dict:
    atomic_write_json(root / f"{bid}.json", brand.model_dump(mode="json", exclude_none=True))
    return brand_entry(bid, brand.model_dump(mode="json"))


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
            "reels": [{"id": r.get("id"), "split": r.get("split"), "language": r.get("language") or "", "source": r.get("channel") or r.get("source") or "",
                       "genre": r.get("genre"), "has_final": bool(r.get("final"))} for r in reels]}
    locked = len(hold) < HOLDOUT_SIZE or len(hold_hing) < HOLDOUT_MIN_HINGLISH
    reason = (f"Release check locked (ADR-0031): holdout has {len(hold)}/{HOLDOUT_SIZE} reels, "
              f"{len(hold_hing)}/{HOLDOUT_MIN_HINGLISH} Hinglish.") if locked else ""
    return locked, reason, gold


def _iso(t) -> str | None:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(float(t), tz=timezone.utc).isoformat() if isinstance(t, (int, float)) and t else None


def lab(settings) -> dict:
    """FR-11. Scores are 0–1 here (the engine's primary score is 0–100)."""
    locked, reason, gold = release_lock(settings.eval_manifest)
    pairs = gold.pop("reels")
    runs = [{"id": r.get("run_id") or f"run-{i}", "at": _iso(r.get("time")), "split": r.get("split") or "tuning",
             "primary": round(r["mean_primary"] / 100, 4), "families": _mean_families(r.get("reels", [])), "vetoed": r.get("vetoed") or 0,
             "reels": [{"id": x.get("id"), "primary": None if x.get("primary") is None else round(x["primary"] / 100, 4),
                        "verdict": x.get("verdict"), "vetoes": x.get("vetoes", [])} for x in r.get("reels", [])]}
            for i, r in enumerate(_jsonl(settings.scoreboard)) if isinstance(r.get("mean_primary"), (int, float))]
    return {"gold": gold, "gold_pairs": [{k: p[k] for k in ("id", "split", "language", "source")} for p in pairs],
            "release_locked": locked, "lock_reason": reason or None, "calibration": calibration(settings),
            "improve_history": [_improve_row(e) for e in _jsonl(settings.improve_log)], "runs": runs}


IMPROVE_OUTCOME = {"accepted": "accepted", "rejected": "rejected", "invalid proposal": "invalid", "dry-run": "dry_run"}


def _improve_row(e: dict) -> dict:
    decision = e.get("decision") or {}
    changes = "; ".join(f"{c.get('kind')} {c.get('node_id')}" for c in e.get("changes") or [])
    gain = decision.get("mean_gain")
    why = decision.get("reasons") or e.get("problems") or []
    return {"at": _iso(e.get("time")), "round": e.get("round"), "change": changes or (e.get("diagnosis") or "")[:200],
            "outcome": IMPROVE_OUTCOME.get(e.get("outcome"), "rejected"),
            "gain": round(gain / 100, 4) if isinstance(gain, (int, float)) else None,
            "reason": ("; ".join(map(str, why)) if isinstance(why, list) else str(why)) or None}


def calibration(settings) -> dict | None:
    """Reviewer agreement with the owner's labels (reel.calibrate) + per-gate false alarms: from owner-sendable renders
    when labels exist, else from the automatic calibration on pro finals (ADR-0033). None when neither exists."""
    from reel import calibrate, config

    try:
        rep = calibrate.report(calibrate.collect(settings.projects_root))
    except (OSError, ValueError, KeyError):
        rep = {"labels": 0, "reviewer": {}, "gates_failing_on_sendable": {}}
    auto = {}
    try:
        auto = json.loads(settings.calibration_report.read_text()) if settings.calibration_report.exists() else {}
    except (OSError, ValueError):
        auto = {}
    if not rep.get("labels") and not auto.get("gates"):
        return None
    gates: dict[str, dict] = {}
    for name, d in (auto.get("gates") or {}).items():
        fa, good = d.get("false_alarms"), d.get("known_good") or 0
        gates[name] = {"name": name, "mode": d.get("mode_now") or config.QA_GATES.get(name, "warn"),
                       "false_alarm_rate": round(fa / good, 3) if fa is not None and good else None,
                       "catch_rate": d.get("catch_rate"), "promote_to_block": bool(d.get("promote_to_block"))}
    for name, d in (rep.get("gates_failing_on_sendable") or {}).items():  # the owner's labels win over the automatic estimate
        gates.setdefault(name, {"name": name, "mode": config.QA_GATES.get(name, "warn"), "catch_rate": None, "promote_to_block": False})
        gates[name]["false_alarm_rate"] = d.get("fp_rate")
    reviewer = rep.get("reviewer") or {}
    return {"agreement": reviewer.get("accuracy"), "n_labels": rep.get("labels", 0), "trusted": bool(reviewer.get("trust_ready")),
            "gates": sorted(gates.values(), key=lambda g: g["name"]), "rule": auto.get("rule")}


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
