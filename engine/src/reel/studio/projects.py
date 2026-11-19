"""Read side of Reel Studio: project summaries and details built from the engine's workspace files.

Source of truth is the workspace the engine writes (state.json, plan/, qa/, render/, export/, log/).
Studio-only facts (display name, created, brand, footage length, delivered) live in studio.json.
Everything is read as plain JSON, so an older plan never breaks the dashboard.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from reel.studio import costs
from reel.workspace import _pid_alive, atomic_write_bytes, atomic_write_json

STAGES = ["ingest", "mezzanine", "perception", "tables", "broll", "reference", "story", "finish", "compile", "render",
          "overlay", "composite", "qa", "package", "variants"]
ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
MEDIA_PREFIXES = ("render/", "export/", "qa/sheets/", "qa/cuts/", "versions/")  # the NLE package is export/package/
COVER_RE = re.compile(r"^cover[^/]*\.jpg$")
STUDIO_FILE = "studio.json"
ATTENTION_ORDER = {"hold": 0, "failed": 1, "sendable": 2, "running": 3, "queued": 3, "draft": 4, "delivered": 5}


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def iso(t: float | None) -> str | None:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat() if t else None


# ------------------------------------------------------------------ locating projects


def is_project(path: Path) -> bool:
    return path.is_dir() and not path.name.startswith(".") and ((path / "state.json").exists() or (path / STUDIO_FILE).exists())


def project_dir(root: Path, pid: str) -> Path | None:
    """The workspace of project `pid`, or None (bad id, outside the root, or not a project)."""
    if not ID_RE.match(pid or ""):
        return None
    base = root.resolve()
    p = (base / pid).resolve()
    if p.parent != base or not is_project(p):
        return None
    return p


def list_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if ID_RE.match(p.name) and is_project(p)) if root.exists() else []


def studio_meta(ws: Path) -> dict:
    return read_json(ws / STUDIO_FILE, {}) or {}


def update_studio_meta(ws: Path, **fields) -> dict:
    meta = studio_meta(ws) | fields
    atomic_write_json(ws / STUDIO_FILE, meta)
    return meta


# ------------------------------------------------------------------ stages and status


def lock_alive(ws: Path) -> bool:
    info = read_json(ws / "run.lock", {}) or {}
    return _pid_alive(int(info.get("pid", 0) or 0))


def stages(ws: Path, job: str | None = None) -> list[dict]:
    """Stage list in display order. `job` = "queued" | "running" | None (the project's studio job)."""
    state = read_json(ws / "state.json", {}) or {}
    entries = state.get("stages", {})
    alive = job == "running" or lock_alive(ws)
    out = []
    for name in STAGES:
        e = entries.get(name)
        st = {"name": name, "status": "queued" if job == "queued" else "pending", "started": None, "finished": None, "meta": {}}
        if e:
            status = e.get("status", "pending")
            st.update(started=e.get("started"), finished=e.get("finished"), meta=e.get("meta") or {})
            if status == "done" and e.get("input_hash") == "none" and not e.get("outputs"):
                status = "skipped"  # optional stage with nothing to do (no b-roll folder, no reference reel)
            elif status == "running" and not alive:
                status = "failed"
                st["error"] = "Interrupted: the run stopped before this stage finished. Retry resumes from here."
            elif status == "failed":
                st["error"] = e.get("error") or "failed"
            st["status"] = status
        out.append(st)
    return out


def project_status(stage_list: list[dict], verdict: dict | None, job: str | None) -> tuple[str, str | None]:
    running = next((s["name"] for s in stage_list if s["status"] == "running"), None)
    failed = next((s["name"] for s in stage_list if s["status"] == "failed"), None)
    if job == "queued":
        return "queued", None
    if job == "running" or running:
        return "running", running
    if failed:
        return "failed", failed
    if verdict and verdict.get("status") in ("sendable", "hold"):
        return verdict["status"], None
    return "draft", None


def _reel_duration(ws: Path, state: dict) -> float | None:
    comp = (state.get("stages", {}).get("composite") or {}).get("meta") or {}
    if comp.get("video_s"):
        return round(float(comp["video_s"]), 2)
    tl = read_json(ws / "timeline" / "timeline.json")
    if tl and tl.get("duration_f") and tl.get("fps"):
        num, _, den = str(tl["fps"]).partition("/")
        return round(float(Fraction(tl["duration_f"]) / Fraction(int(num), int(den or 1))), 2)
    return None


def _created(ws: Path, meta: dict) -> float:
    if meta.get("created"):
        return float(meta["created"])
    st = ws.stat()
    return getattr(st, "st_birthtime", st.st_ctime)


def _updated(ws: Path) -> float:
    ts = [p.stat().st_mtime for p in (ws / "state.json", ws / STUDIO_FILE, ws / "qa" / "verdict.json", ws / "plan" / "finish.json") if p.exists()]
    return max(ts) if ts else ws.stat().st_mtime


def summary(ws: Path, job: str | None = None) -> dict:
    state = read_json(ws / "state.json", {}) or {}
    meta = studio_meta(ws)
    verdict = read_json(ws / "qa" / "verdict.json")
    st = stages(ws, job)
    status, stage = project_status(st, verdict, job)
    attention = []
    if status == "failed":
        attention.append(f"failed: {stage}")
    proof = (verdict or {}).get("proof_open") or []
    if proof and status not in ("running", "queued"):
        attention.append(f"{len(proof)} proof word{'s' if len(proof) != 1 else ''}")
    if status == "hold":
        other = [r for r in verdict.get("reasons", []) if not r.startswith("proof_words")]
        if other:
            attention.append(f"hold: {len(other)} reason{'s' if len(other) != 1 else ''}")
    done = sum(1 for s in st if s["status"] in ("done", "skipped"))
    return {"id": ws.name, "name": meta.get("name") or ws.name, "client": meta.get("client"),
            "created": iso(_created(ws, meta)), "updated": iso(_updated(ws)),
            "status": status, "stage": stage, "progress": round(done / len(STAGES), 3),
            "duration_s": _reel_duration(ws, state), "cost_usd": costs.project_total(ws / "log" / "runs.jsonl"),
            "verdict": (verdict or {}).get("status") if (verdict or {}).get("status") in ("sendable", "hold") else None,
            "needs_attention": attention, "thumb": "cover.jpg" if (ws / "cover.jpg").exists() else None,
            "delivered": iso(meta.get("delivered"))}


def attention_key(s: dict) -> tuple:
    group = "delivered" if s.get("delivered") and s["status"] == "sendable" else s["status"]
    return ATTENTION_ORDER.get(group, 9), -(datetime.fromisoformat(s["updated"]).timestamp() if s["updated"] else 0)


# ------------------------------------------------------------------ cover thumbnail (frame at 1 s of the latest render)

_cover_busy: set[str] = set()
_cover_lock = threading.Lock()


def ensure_cover(ws: Path) -> None:
    """Refresh cover.jpg in the background when the render is newer; never blocks a request."""
    final = ws / "render" / "final.mp4"
    cover = ws / "cover.jpg"
    if not final.exists() or (cover.exists() and cover.stat().st_mtime >= final.stat().st_mtime):
        return
    with _cover_lock:
        if str(ws) in _cover_busy:
            return
        _cover_busy.add(str(ws))

    def work():
        try:
            from reel import config

            tmp = ws / ".cover.tmp.jpg"
            subprocess.run([str(config.ffmpeg_path()), "-v", "error", "-y", "-ss", "1", "-i", str(final), "-frames:v", "1",
                            "-vf", "scale=360:-2", "-q:v", "4", str(tmp)], capture_output=True, timeout=30)
            if tmp.exists():
                os.replace(tmp, cover)
        except Exception:  # noqa: BLE001 — a missing thumbnail is cosmetic
            pass
        finally:
            with _cover_lock:
                _cover_busy.discard(str(ws))

    threading.Thread(target=work, daemon=True).start()


# ------------------------------------------------------------------ decisions (the Editor's reasons, the Reviewer, the verdict)

_cache: dict[str, tuple[tuple, object]] = {}


def _cached(key: str, files: list[Path], build):
    sig = tuple((str(f), f.stat().st_mtime_ns if f.exists() else 0) for f in files)
    hit = _cache.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    val = build()
    _cache[key] = (sig, val)
    return val


def words_text(ws: Path) -> dict[int, str]:
    def build():
        data = read_json(ws / "perception" / "words.json", {}) or {}
        return {int(w["i"]): w.get("text", "") for w in data.get("words", [])}
    return _cached(f"words:{ws}", [ws / "perception" / "words.json"], build)


def _line(words: dict[int, str], it: dict, limit: int = 140) -> str:
    text = " ".join(words.get(i, "") for i in range(int(it.get("word_start", 0)), int(it.get("word_end", -1)) + 1)).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _stage_time(state: dict, name: str, fallback: Path) -> float:
    t = (state.get("stages", {}).get(name) or {}).get("finished")
    return float(t) if t else (fallback.stat().st_mtime if fallback.exists() else 0.0)


def decisions(ws: Path) -> list[dict]:
    files = [ws / "state.json", ws / "plan" / "story.json", ws / "plan" / "finish.json", ws / "qa" / "review.json",
             ws / "qa" / "verdict.json", ws / "perception" / "words.json", ws / "plan" / "history"]
    return _cached(f"decisions:{ws}", files, lambda: _build_decisions(ws))


def _d(at: float, kind: str, title: str, detail: str, knowledge: list | None = None) -> dict:
    return {"at": at, "kind": kind, "title": title, "detail": detail or "", "knowledge": list(knowledge or [])}


def _build_decisions(ws: Path) -> list[dict]:
    state = read_json(ws / "state.json", {}) or {}
    words = words_text(ws)
    out: list[dict] = []
    story = read_json(ws / "plan" / "story.json")
    if story:
        at = _stage_time(state, "story", ws / "plan" / "story.json")
        items = story.get("items", [])
        hook = next((h for h in story.get("hook_options", []) if h.get("id") == story.get("hook")), None)
        if items:
            out.append(_d(at, "story", f"Hook: “{_line(words, items[0], 90)}”", (hook or {}).get("reason", ""), story.get("knowledge_used")))
        for it in items:
            out.append(_d(at, "story", f"Keep {it.get('id')} ({it.get('beat')}): “{_line(words, it, 90)}”", it.get("reason", "")))
    fin = read_json(ws / "plan" / "finish.json")
    if fin:
        at = _stage_time(state, "finish", ws / "plan" / "finish.json")
        cap, grade, music, ht = fin.get("captions") or {}, fin.get("grade") or {}, fin.get("music") or {}, fin.get("hook_title") or {}
        out.append(_d(at, "finish", f"Captions: {cap.get('family')}", cap.get("reason", ""), fin.get("knowledge_used")))
        if (ht.get("text") or "").strip():
            out.append(_d(at, "finish", f"Hook title “{ht['text']}” ({ht.get('style')})", ht.get("reason", "")))
        look = f"Look: {grade.get('look')} at {grade.get('strength')}"
        if grade.get("grain") or grade.get("vignette"):
            look += f" (grain {grade.get('grain', 0)}, vignette {grade.get('vignette', 0)})"
        out.append(_d(at, "finish", look, grade.get("reason", "")))
        out.append(_d(at, "finish", f"Music: {music.get('track')}", music.get("reason", "")))
        for p in fin.get("punch_ins", []):
            out.append(_d(at, "finish", f"Punch-in {p.get('id')} on {p.get('item')} → {p.get('scale')}×", p.get("reason", "")))
        for t in fin.get("transitions", []):
            out.append(_d(at, "finish", f"Transition {t.get('type')} after {t.get('after_item')}", t.get("reason", "")))
        for x in fin.get("sfx", []):
            out.append(_d(at, "finish", f"Sound effect {x.get('sfx')} on {x.get('item')}", x.get("reason", "")))
        for x in fin.get("speeds", []):
            out.append(_d(at, "finish", f"Speed {x.get('item')} {x.get('rate')}×", x.get("reason", "")))
        for x in fin.get("holds", []):
            out.append(_d(at, "finish", f"Freeze {x.get('item')} for {x.get('frames')} frames", x.get("reason", "")))
        for x in fin.get("effects", []):
            out.append(_d(at, "finish", f"Effect {x.get('type')} on {x.get('item')}", x.get("reason", "")))
        for x in fin.get("graphics", []):
            label = x.get("text") or x.get("emoji") or ""
            out.append(_d(at, "finish", f"Graphic {x.get('kind')} on {x.get('item')}" + (f": {label}" if label else ""), x.get("reason", "")))
        for x in fin.get("broll", []):
            out.append(_d(at, "finish", f"B-roll {x.get('asset')} over {x.get('item')}", x.get("reason", "")))
    hist = ws / "plan" / "history"
    for req in sorted(hist.glob("*_request.json")) if hist.exists() else []:
        r = read_json(req, {}) or {}
        out.append(_d(req.stat().st_mtime, "revision", f"Revision: {r.get('request', '')[:120]}", r.get("reply", "")))
    review = read_json(ws / "qa" / "review.json")
    qa_at = _stage_time(state, "qa", ws / "qa" / "verdict.json")
    if review:
        for i in review.get("issues", []):
            out.append(_d(qa_at, "review", f"{i.get('severity')} · {i.get('category')} at {i.get('at') or 'whole reel'}",
                          f"{i.get('problem', '')} Fix: {i.get('fix', '')}".strip()))
    verdict = read_json(ws / "qa" / "verdict.json")
    if verdict:
        out.append(_d(qa_at, "qa", f"Verdict: {verdict.get('status')}", "; ".join(verdict.get("reasons", [])) or "No blocking problems."))
    out.sort(key=lambda d: d["at"])
    return out


def decision_key(d: dict) -> str:
    return f"{d['kind']}|{d['title']}|{d['detail']}"


# ------------------------------------------------------------------ verdict, proof, review, media, versions


def verdict_detail(ws: Path) -> dict | None:
    v = read_json(ws / "qa" / "verdict.json")
    if not v:
        return None
    gates = []
    for g in read_json(ws / "qa" / "gates.json", []) or []:
        status = "pass" if g.get("ok") else ("fail" if g.get("mode") == "block" else "warn")
        gates.append({"name": g.get("gate"), "status": status, "detail": g.get("detail", ""), "measured": g.get("measured") or {}})
    return {"verdict": v.get("status"), "reasons": v.get("reasons", []), "warnings": v.get("warnings", []), "gates": gates}


def review_view(ws: Path) -> dict | None:
    r = read_json(ws / "qa" / "review.json")
    if not r:
        return None
    return {"summary": r.get("summary", ""), "sendable": r.get("sendable"), "strengths": r.get("strengths", []),
            "issues": [{"at": i.get("at") or "", "category": i.get("category", ""), "text": i.get("problem", ""),
                        "severity": i.get("severity"), "fix": i.get("fix", "")} for i in r.get("issues", [])]}


def media_view(ws: Path) -> dict:
    rel = lambda p: str(p.relative_to(ws))  # noqa: E731
    out: dict = {"sheets": [], "cut_strips": []}
    for key, p in (("final", ws / "render" / "final.mp4"), ("review_copy", ws / "export" / "review" / "review.mp4"), ("cover", ws / "cover.jpg")):
        if p.exists():
            out[key] = rel(p)
    if (ws / "qa" / "sheets").exists():
        out["sheets"] = sorted(rel(p) for p in (ws / "qa" / "sheets").rglob("*") if p.suffix.lower() in (".png", ".jpg") and p.is_file())
    if (ws / "qa" / "cuts").exists():
        out["cut_strips"] = sorted(rel(p) for p in (ws / "qa" / "cuts").rglob("*") if p.suffix.lower() in (".png", ".jpg") and p.is_file())
    variants = ws / "export" / "variants"
    out["variants"] = sorted(rel(p) for p in variants.glob("*.mp4")) if variants.exists() else []
    return out


def media_path(ws: Path, rel: str) -> Path | None:
    """A whitelisted file under the project, or None. No traversal, no absolute paths, no symlink escapes."""
    if not rel or "\\" in rel or "\x00" in rel or rel.startswith("/"):
        return None
    if any(part in ("", ".", "..") for part in rel.split("/")):
        return None
    if not (rel.startswith(MEDIA_PREFIXES) or COVER_RE.match(rel)):
        return None
    p = (ws / rel).resolve()
    if not p.is_relative_to(ws.resolve()) or not p.is_file():
        return None
    return p


def package_files(ws: Path) -> list[dict]:
    pkg = ws / "export" / "package"
    if not pkg.exists():
        return []
    return [{"path": str(p.relative_to(ws)), "name": str(p.relative_to(pkg)), "bytes": p.stat().st_size}
            for p in sorted(pkg.rglob("*")) if p.is_file()]


def versions(ws: Path) -> list[dict]:
    root = ws / "versions"
    out = []
    for d in sorted((d for d in root.iterdir() if d.is_dir() and d.name.isdigit()), key=lambda d: int(d.name)) if root.exists() else []:
        meta = read_json(d / "meta.json", {}) or {}
        v = {"n": int(d.name), "created": iso(meta.get("created") or d.stat().st_mtime), "label": meta.get("label", "")}
        if (d / "final.mp4").exists():
            v["final"] = f"versions/{d.name}/final.mp4"
        out.append(v)
    return out


VERSION_FILES = ("plan/story.json", "plan/finish.json", "plan/story_readback.txt", "timeline/timeline.json")


def snapshot(ws: Path, label: str) -> int:
    """Copy the plans, the timeline and the final render into versions/<n>/ (the render is hard-linked)."""
    existing = [int(d.name) for d in (ws / "versions").iterdir() if d.name.isdigit()] if (ws / "versions").exists() else []
    n = max(existing, default=0) + 1
    dst = ws / "versions" / str(n)
    for rel in VERSION_FILES:
        src = ws / rel
        if src.exists():
            atomic_write_bytes(dst / rel, src.read_bytes())
    final = ws / "render" / "final.mp4"
    if final.exists():
        dst.mkdir(parents=True, exist_ok=True)
        try:
            os.link(final, dst / "final.mp4")
        except OSError:
            shutil.copy2(final, dst / "final.mp4")
    atomic_write_json(dst / "meta.json", {"n": n, "created": time.time(), "label": label})
    return n


def restore_plans(ws: Path, n: int) -> bool:
    src = ws / "versions" / str(n)
    if not (src / "plan" / "story.json").exists():
        return False
    for rel in VERSION_FILES[:3]:
        if (src / rel).exists():
            atomic_write_bytes(ws / rel, (src / rel).read_bytes())
    return True


def last_revision(ws: Path) -> dict | None:
    hist = ws / "plan" / "history"
    reqs = sorted(hist.glob("*_request.json")) if hist.exists() else []
    return read_json(reqs[-1]) if reqs else None


# ------------------------------------------------------------------ the full project and the layers view


def brief_and_brand(ws: Path) -> tuple[dict | None, str | None]:
    opts = read_json(ws / "run_options.json", {}) or {}
    brief = read_json(Path(opts["brief"])) if opts.get("brief") else None
    brand = Path(opts["brand"]).stem if opts.get("brand") else studio_meta(ws).get("brand")
    return brief, brand


def detail(ws: Path, job: str | None = None) -> dict:
    s = summary(ws, job)
    brief, brand = brief_and_brand(ws)
    verdict = read_json(ws / "qa" / "verdict.json") or {}
    return s | {"brief": brief, "brand": brand, "stages": stages(ws, job), "decisions": decisions(ws),
                "verdict_detail": verdict_detail(ws), "proof": verdict.get("proof_open") or [], "review": review_view(ws),
                "media": media_view(ws), "versions": versions(ws), "calls": costs.calls(ws / "log" / "runs.jsonl"),
                "package": package_files(ws),
                "platform_notes": ((read_json(ws / "state.json", {}) or {}).get("stages", {}).get("variants") or {}).get("meta", {}).get("platform_notes", [])}


def timeline_view(ws: Path) -> dict | None:
    tl = read_json(ws / "timeline" / "timeline.json")
    if tl is None:
        return None
    words = words_text(ws)
    story = read_json(ws / "plan" / "story.json", {}) or {}
    fin = read_json(ws / "plan" / "finish.json", {}) or {}
    items = {it["id"]: {"beat": it.get("beat"), "reason": it.get("reason", ""), "text": _line(words, it, 10_000), "clip": it.get("clip"),
                        "word_start": it.get("word_start"), "word_end": it.get("word_end")} for it in story.get("items", [])}
    hook = next((h for h in story.get("hook_options", []) if h.get("id") == story.get("hook")), None)
    reasons: dict[str, dict] = {}
    for key in ("hook_title", "captions", "grade", "music"):
        if fin.get(key):
            reasons[key] = {"kind": key, **{k: v for k, v in fin[key].items() if k != "tokens"}}
    for kind in ("punch_ins", "speeds", "transitions", "sfx", "broll", "effects", "graphics", "holds"):
        for x in fin.get(kind, []):
            reasons[x["id"]] = {"kind": kind, **x}
    return {"timeline": tl, "story": items, "hook": hook, "finish": reasons}
