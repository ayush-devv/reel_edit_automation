"""Licence registry, the licence gate and the per-render licence manifest (docs/product/asset-library-plan.md).

Code decides whether an asset may go into a reel; Claude never does.
- The registry (`assets/licenses/registry.yaml`) holds one row per licence, carrying that licence's rules.
- An index entry links an asset to its licence and adds facts about that one file (editorial only,
  registrations, sha256).
- `refused()` drops ineligible assets before the Editor sees its menus.
- `gate()` checks a compiled timeline before render and again at package.
- `write_manifest()` leaves proof of licence beside the deliverable.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from reel import assets as assets_mod
from reel.library import FORBIDDEN_LICENCE
from reel.workspace import atomic_write_json

LICENCE_DIR = assets_mod.ASSETS_DIR / "licenses"
REGISTRY = LICENCE_DIR / "registry.yaml"
CATEGORIES = ("political", "dating", "drugs", "alcohol", "gambling", "religious", "adult")
PURPOSES = ("editorial", "organic", "promo", "paid_ad")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Licence(_Strict):
    id: str
    title: str
    family: str
    url: str = ""
    text: str | None = None  # file in assets/licenses/
    text_kind: Literal["official", "pack-notice", "summary", "missing"] = "missing"
    retrieved: str = ""
    aliases: list[str] = Field(default_factory=list)
    notes: str = ""
    commercial_ok: bool = True
    attribution_required: bool = False
    client_transfer: Literal["sublicense", "single_client", "none"] = "sublicense"
    sensitive_use: list[str] = Field(default_factory=list)
    allowed_platforms: list[str] = Field(default_factory=lambda: ["*"])
    subscription: str | None = None
    per_project_registration: bool = False
    deliver_source_files: bool = True
    ml_indexing_ok: bool = False
    blocked: str = ""


class SourceRef(_Strict):
    licence: str
    notice: str | None = None  # the licence file shipped inside the pack


@dataclass
class Registry:
    licences: dict[str, Licence]
    sources: dict[str, SourceRef]
    root: Path
    sha256: str = ""

    def resolve(self, meta: dict) -> Licence | None:
        """Explicit `licence_id`, else the `license` text by alias, else the pack (`source`). None = no licence on record."""
        lid = str(meta.get("licence_id") or "").strip()
        if lid:
            return self.licences.get(lid)  # a wrong explicit id is an error, never a fall-through
        text = str(meta.get("license") or "").strip()
        if text:
            for lic in self.licences.values():
                if any(re.search(a, text, re.I) for a in lic.aliases):
                    return lic
        src = self.sources.get(str(meta.get("source") or ""))
        return self.licences.get(src.licence) if src else None

    def notice(self, meta: dict) -> str | None:
        src = self.sources.get(str(meta.get("source") or ""))
        return src.notice if src else None

    def path(self, name: str | None) -> Path | None:
        return self.root / name if name else None


def load_registry(path: Path | None = None) -> Registry:
    path = path or REGISTRY
    raw = path.read_bytes()
    data = yaml.safe_load(raw) or {}
    lics: dict[str, Licence] = {}
    for row in data.get("licences", []):
        lic = Licence.model_validate(row)
        if lic.id in lics:
            raise ValueError(f"{path.name}: licence {lic.id!r} listed twice")
        for a in lic.aliases:
            re.compile(a)
        if FORBIDDEN_LICENCE.search(lic.title) and not lic.blocked:
            lic.blocked = "ShareAlike / NonCommercial / NoDerivatives: not usable in client reels"
        if lic.text and not (path.parent / lic.text).is_file():
            raise ValueError(f"{path.name}: licence text {lic.text!r} of {lic.id!r} is missing")
        lics[lic.id] = lic
    sources = {k: SourceRef.model_validate(v) for k, v in (data.get("sources") or {}).items()}
    for name, s in sources.items():
        if s.licence not in lics:
            raise ValueError(f"{path.name}: source {name!r} points at unknown licence {s.licence!r}")
        if s.notice and not (path.parent / s.notice).is_file():
            raise ValueError(f"{path.name}: notice {s.notice!r} of {name!r} is missing")
    return Registry(lics, sources, path.parent, hashlib.sha256(raw).hexdigest())


# ------------------------------------------------------------------ account state (never in git)


def config_dir() -> Path:
    """~/.config/reel, or $REEL_CONFIG_DIR (tests point it at a temp folder)."""
    return Path(os.environ.get("REEL_CONFIG_DIR") or Path.home() / ".config" / "reel")


def subscriptions_file() -> Path:
    return config_dir() / "subscriptions.json"


def ledger_file() -> Path:
    return config_dir() / "licence_ledger.jsonl"


def load_subscriptions() -> dict[str, dict]:
    """{"epidemic": {"active_until": "2027-11-30"}} — what the owner pays for now."""
    f = subscriptions_file()
    return json.loads(f.read_text()) if f.exists() else {}


def subscription_active(name: str, subs: dict[str, dict], today: dt.date) -> bool:
    s = subs.get(name) or {}
    if not s:
        return False
    until = s.get("active_until")
    return bool(s.get("active", True)) if not until else dt.date.fromisoformat(str(until)) >= today


def asset_key(aid: str, meta: dict) -> str:
    return str(meta.get("sha256") or aid)


def load_ledger() -> dict[str, set[str]]:
    """Asset key → every client it was delivered to ("" = no client named)."""
    out: dict[str, set[str]] = {}
    f = ledger_file()
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                out.setdefault(e["key"], set()).add(e.get("client") or "")
    return out


def record_use(items: list[dict], use: UseContext) -> int:
    """Append (asset, client, project) once: repackaging the same project never counts as a new use."""
    f = ledger_file()
    seen = set()
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                seen.add((e["key"], e.get("client") or "", e.get("project", "")))
    new = [{"key": i["key"], "asset": i["id"], "licence": i["licence_id"], "client": use.client or "", "project": use.project,
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
           for i in items if (i["key"], use.client or "", use.project) not in seen]
    if new:
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a") as fh:
            fh.writelines(json.dumps(e) + "\n" for e in new)
    return len(new)


# ------------------------------------------------------------------ use context (from the brief)


@dataclass(frozen=True)
class UseContext:
    client: str | None = None
    platform: str = "platform.instagram_reels"
    categories: frozenset[str] = frozenset()
    purpose: str = "promo"
    accept_credits: bool = True
    project: str = ""
    today: dt.date = field(default_factory=dt.date.today)

    @classmethod
    def from_brief(cls, brief, project: str = "", fallback_client: str | None = None) -> UseContext:
        """`fallback_client`: the Studio's client label (rename / set client), used when the brief names none — otherwise
        the single-client rule would never see the client of a project made from the command line."""
        if brief is None:
            return cls(project=project, client=fallback_client or None)
        return cls(client=brief.client or fallback_client or None, platform=brief.platform, categories=frozenset(brief.use_categories),
                   purpose=brief.purpose, accept_credits=brief.accept_credits, project=project)


Refusal = tuple[str, str]  # (code, message)


def refusals(aid: str, meta: dict, reg: Registry, use: UseContext, *, subs: dict | None = None,
             ledger: dict[str, set[str]] | None = None) -> list[Refusal]:
    """Why this asset may not go into this reel ([] = it may)."""
    text = str(meta.get("license") or "")
    if FORBIDDEN_LICENCE.search(text):
        return [("blocked_licence", f"licence {text!r} is ShareAlike / NonCommercial / NoDerivatives")]
    lic = reg.resolve(meta)
    if lic is None:
        why = f"unknown licence id {meta['licence_id']!r}" if meta.get("licence_id") else f"no licence on record ({text or 'none'})"
        return [("no_licence", f"{why}: add it to assets/licenses/registry.yaml")]
    if lic.blocked:
        return [("blocked_licence", f"{lic.title}: {lic.blocked}")]
    if not lic.commercial_ok:
        return [("blocked_licence", f"{lic.title} does not allow commercial use")]
    out: list[Refusal] = []
    if meta.get("editorial_only") and use.purpose != "editorial":
        out.append(("editorial_only", f"editorial use only; this reel is {use.purpose}"))
    hit = use.categories & (set(lic.sensitive_use) | set(meta.get("sensitive_use") or []))
    if hit:
        out.append(("sensitive_use", f"{lic.title} forbids {', '.join(sorted(hit))} use"))
    platforms = meta.get("allowed_platforms") or lic.allowed_platforms
    if "*" not in platforms and use.platform not in platforms:
        out.append(("platform_not_allowed", f"{lic.title} covers {', '.join(platforms)}, not {use.platform}"))
    if lic.subscription and not subscription_active(lic.subscription, load_subscriptions() if subs is None else subs, use.today):
        out.append(("subscription_inactive", f"needs an active {lic.subscription} subscription (~/.config/reel/subscriptions.json)"))
    if lic.per_project_registration and not any(r.get("project") == use.project for r in meta.get("registrations") or []):
        out.append(("registration_missing", f"{lic.title} needs this project registered with the vendor first"))
    if lic.client_transfer == "single_client" or meta.get("single_client"):
        others = (load_ledger() if ledger is None else ledger).get(asset_key(aid, meta), set()) - {use.client or "", ""}
        if others:
            out.append(("single_client", f"already delivered to another client; {lic.title} covers one client"))
    if lic.attribution_required:
        if not use.accept_credits:
            out.append(("credit_refused", f"{lic.title} needs a credit in the post, and the brief says the client won't carry credits"))
        elif not str(meta.get("attribution") or "").strip():
            out.append(("attribution_missing", f"{lic.title} needs a credit, but this asset has no attribution text"))
    return out


def refused(idx, use: UseContext, reg: Registry | None = None) -> dict[str, list[Refusal]]:
    """Every library asset this reel may not use, with the reasons (the Editor's menus leave them out)."""
    reg = reg or load_registry()
    subs, ledger = load_subscriptions(), load_ledger()
    out: dict[str, list[Refusal]] = {}
    for kind in ("sfx", "music", "broll", "lottie"):
        for aid, meta in getattr(idx, kind, {}).items():
            r = refusals(aid, meta, reg, use, subs=subs, ledger=ledger)
            if r:
                out[aid] = r
    return out


def reason(rs: list[Refusal]) -> str:
    return "; ".join(m for _c, m in rs)


# ------------------------------------------------------------------ the gate (timeline) and the manifest


def used_assets(tl, idx) -> list[dict]:
    """Library assets a compiled timeline uses, in timeline order: music/SFX, full-frame b-roll, pip b-roll, Lottie.
    Index metadata (current) is merged over the compile-time snapshot (kept even when the library moved)."""
    by: dict[str, dict] = {}

    def add(aid: str, kind: str, where: str, meta: dict) -> None:
        e = by.setdefault(aid, {"id": aid, "kind": kind, "where": [], "meta": meta})
        e["where"].append(where)

    def snap(aid: str) -> dict:
        a = tl.assets.get(aid)
        if not a:
            return {}
        return {k: v for k, v in {"license": a.license, "attribution": a.attribution, "credit": a.credit, "restrictions": a.restrictions,
                                   "file": a.uri}.items() if v}

    def merged(aid: str, lib: dict) -> dict:
        return {**snap(aid), **{k: v for k, v in (lib.get(aid) or {}).items() if v not in (None, "", [])}}

    for a in tl.audio:
        if a.role in ("music", "sfx"):
            add(a.asset, a.role, a.id, merged(a.asset, idx.music if a.role == "music" else idx.sfx))
    for c in tl.video:
        if c.id.startswith("br_"):
            add(c.asset, "broll", c.id, merged(c.asset, idx.broll))
    by_file = {m.get("file"): k for k, m in idx.broll.items()}
    for p in tl.pips:
        bid = by_file.get(p.uri)
        add(bid or f"pip:{p.uri}", "broll", p.id, dict(idx.broll.get(bid) or {"file": p.uri}))
    for g in tl.graphics:
        if g.kind == "lottie":
            add(g.uri or f"lottie:{g.id}", "lottie", g.id, dict(idx.lottie.get(g.uri) or {}))
    return list(by.values())


@dataclass
class GateResult:
    use: UseContext
    items: list[dict]  # id, kind, where, meta, licence_id, key, refusals

    @property
    def ok(self) -> bool:
        return not any(i["refusals"] for i in self.items)

    def problems(self) -> list[str]:
        return [f"{i['id']} ({i['kind']}, {', '.join(i['where'])}): {m}" for i in self.items for _c, m in i["refusals"]]


class LicenceRefused(ValueError):
    def __init__(self, result: GateResult):
        self.result = result
        super().__init__("licence gate refused this reel:\n- " + "\n- ".join(result.problems()))


def gate(tl, idx, use: UseContext, reg: Registry | None = None) -> GateResult:
    reg = reg or load_registry()
    subs, ledger = load_subscriptions(), load_ledger()
    items = []
    for u in used_assets(tl, idx):
        lic = reg.resolve(u["meta"])
        items.append({**u, "licence_id": lic.id if lic else None, "key": asset_key(u["id"], u["meta"]),
                      "refusals": refusals(u["id"], u["meta"], reg, use, subs=subs, ledger=ledger)})
    return GateResult(use, items)


def fingerprint(brief_path: str | Path | None) -> str:
    """Everything the gate decides from besides the timeline: a changed brief, registry or subscription re-runs package."""
    h = hashlib.sha256()
    for p in (REGISTRY, subscriptions_file(), Path(brief_path) if brief_path else None):
        h.update(p.read_bytes() if p and p.is_file() else b"-")
    return h.hexdigest()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_sha(meta: dict, ws_root: Path) -> str | None:
    if meta.get("sha256"):
        return meta["sha256"]
    f = meta.get("file")
    if not f:
        return None
    p = Path(f) if Path(f).is_absolute() else ws_root / f
    return _sha256(p) if p.is_file() else None


def write_manifest(pkg: Path, result: GateResult, ws_root: Path, *, reg: Registry | None = None, reel: Path | None = None,
                   credits: list[str] | None = None) -> Path:
    """export/package/licences/: manifest.json (asset → licence → text hash) and the licence texts themselves.
    The client's proof of licence and the dispute packet."""
    reg = reg or load_registry()
    out = pkg / "licences"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    licences: dict[str, dict] = {}
    notices: set[str] = set()
    assets = []
    for i in result.items:
        m = i["meta"]
        lic = reg.licences.get(i["licence_id"] or "")
        if lic and lic.id not in licences:
            text = reg.path(lic.text)
            if text:
                shutil.copyfile(text, out / text.name)
            licences[lic.id] = {"title": lic.title, "family": lic.family, "url": lic.url, "text": text.name if text else None,
                                "text_kind": lic.text_kind, "text_sha256": _sha256(text) if text else None,
                                "retrieved": lic.retrieved or None, "notes": lic.notes or None}
        notice = reg.notice(m)
        if notice and notice not in notices:
            notices.add(notice)
            shutil.copyfile(reg.root / notice, out / notice)
        assets.append({"id": i["id"], "kind": i["kind"], "used_in": i["where"], "licence": i["licence_id"],
                       "source": m.get("source"), "source_url": m.get("source_url") or m.get("page") or m.get("download_url"),
                       "author": m.get("author") or m.get("credit"), "file_sha256": _file_sha(m, ws_root),
                       "licence_as_recorded": m.get("license"), "pack_notice": notice, "attribution": m.get("attribution") or None,
                       "restrictions": m.get("restrictions") or None, "registrations": m.get("registrations") or None,
                       "content_id_registered": m.get("content_id_registered"), "editorial_only": bool(m.get("editorial_only")),
                       "downloaded_at": m.get("downloaded_at") or m.get("fetched")})
    use = result.use
    manifest = {
        "schema": 1,
        "written_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": use.project, "client": use.client, "platform": use.platform, "purpose": use.purpose,
        "client_categories": sorted(use.categories), "credits_accepted": use.accept_credits,
        "reel": {"file": "reel.mp4", "sha256": _sha256(reel) if reel and reel.is_file() else None},
        "credits_required": credits or [],
        "registry_sha256": reg.sha256,
        "licences": licences,
        "assets": assets,
    }
    atomic_write_json(out / "manifest.json", manifest)
    return out / "manifest.json"


# ------------------------------------------------------------------ backfill / census

INDEX_FILES = (("sfx", "sfx/sfx_index.json", "sfx"), ("music", "music/music_index.json", "tracks"),
               ("lottie", "lottie/index.json", "animations"), ("broll", "broll_owned/index.json", "clips"))


def census(root: Path = assets_mod.ASSETS_DIR, *, write: bool = False, reg: Registry | None = None) -> dict:
    """Licence of every indexed library asset (the raw index files, so assets not fetched on this machine count too).
    `write`: stamp `licence_id` (and a missing sha256 when the file is here) into the committed indexes."""
    reg = reg or load_registry()
    out: dict = {"by_licence": {}, "unresolved": [], "blocked": [], "stamped": 0}
    for kind, rel, key in INDEX_FILES:
        path = root / rel
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        changed = 0
        for e in data.get(key, []):
            lic = reg.resolve(e)
            if lic is None or FORBIDDEN_LICENCE.search(str(e.get("license") or "")):
                out["unresolved"].append(f"{kind}:{e.get('id')} ({e.get('license') or 'no licence'})")
                continue
            if lic.blocked:
                out["blocked"].append(f"{kind}:{e.get('id')} ({lic.id}: {lic.blocked})")
            out["by_licence"].setdefault(lic.id, {}).setdefault(kind, 0)
            out["by_licence"][lic.id][kind] += 1
            if not e.get("licence_id"):
                e["licence_id"] = lic.id
                changed += 1
            f = Path(e.get("file") or "")
            f = f if f.is_absolute() else root / f
            if not e.get("sha256") and e.get("file") and f.is_file():
                e["sha256"] = _sha256(f)
                changed += 1
        if write and changed:
            atomic_write_json(path, data)
        out["stamped"] += changed
    return out


def stamp(entries: list[dict], reg: Registry | None = None) -> int:
    """Write `licence_id` into index entries that resolve and lack one; returns how many changed."""
    reg = reg or load_registry()
    n = 0
    for e in entries:
        if not e.get("licence_id"):
            lic = reg.resolve(e)
            if lic:
                e["licence_id"] = lic.id
                n += 1
    return n
