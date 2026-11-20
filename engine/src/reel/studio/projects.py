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

STAGES = ["ingest", "mezzanine", "perception", "tables", "stock", "broll", "reference", "story", "finish", "compile", "render",
          "overlay", "composite", "qa", "package", "variants"]
ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
MEDIA_PREFIXES = ("render/", "export/", "qa/sheets/", "qa/cuts/", "versions/")  # the NLE package is export/package/
COVER_RE = re.compile(r"^cover[^/]*\.jpg$")
STUDIO_FILE = "studio.json"
ATTENTION_ORDER = {"hold": 0, "awaiting_choice": 0, "awaiting_story": 0, "source": 1, "failed": 1, "sendable": 2, "running": 3, "queued": 4, "draft": 5, "delivered": 6}
ANALYSIS_STAGES = ("ingest", "mezzanine", "perception", "tables")
SOURCE_STAGES = [*ANALYSIS_STAGES, "mine"]  # a Clip Factory source: analysed once, then mined (G2.2)


def is_source(ws: Path) -> bool:
    return (read_json(ws / "run_options.json", {}) or {}).get("mine") is True or (ws / "mine" / "candidates.json").exists()


def is_child(ws: Path) -> bool:
    return (ws / "window.json").exists()


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
    child = is_child(ws)
    for name in (SOURCE_STAGES if is_source(ws) else STAGES):
        e = entries.get(name)
        st = {"name": name, "status": "queued" if job == "queued" else "pending", "started": None, "finished": None, "meta": {}}
        if child and name in ANALYSIS_STAGES:  # a Clip Factory reel shares the source's analysis
            st.update(status="skipped", meta={"shared_from": (read_json(ws / "window.json", {}) or {}).get("parent")})
            out.append(st)
            continue
        if e:
            status = e.get("status", "pending")
            st.update(started=e.get("started"), finished=e.get("finished"), meta=e.get("meta") or {})
            if status == "done" and e.get("input_hash") in ("none", "off") and not e.get("outputs"):
                status = "skipped"  # optional stage with nothing to do (no b-roll folder, no reference reel, stock b-roll off)
            elif status == "running" and not alive:
                status = "failed"
                st["error"] = "Interrupted: the run stopped before this stage finished. Retry resumes from here."
            elif status == "failed":
                st["error"] = e.get("error") or "failed"
            st["status"] = status
        out.append(st)
    # A stage the project's run never had (added to the engine later, e.g. `stock`) is skipped once any later stage ran.
    for n, st in enumerate(out):
        if st["name"] not in entries and st["status"] == "pending" and any(o["name"] in entries for o in out[n + 1:]):
            st["status"] = "skipped"
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
    pv = read_json(ws / "export" / "preview" / "preview.json")
    if status == "draft" and pv and not pv.get("chosen"):  # a --preview-first run ended at the hook previews (G1.6)
        status = "awaiting_choice"
        attention.append("pick the hook look (A/B)")
    ci = read_json(ws / "plan" / "checkin.json")
    if status == "draft" and ci and ci.get("status") == "open":  # a --story-checkin run ended after the story pass (3a.1)
        status = "awaiting_story"
        attention.append("check the story")
    source = is_source(ws)
    if source and status == "draft" and (ws / "mine" / "candidates.json").exists():
        status = "source"
        if not (ws / "mine" / "children.json").exists():
            attention.append("pick the reels to make")
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
            "kind": "source" if source else ("clip" if is_child(ws) else "reel"), "parent": meta.get("parent"),
            "status": status, "stage": stage, "progress": round(done / max(1, len(st)), 3),
            "duration_s": _reel_duration(ws, state), "cost_usd": costs.project_total(ws / "log" / "runs.jsonl"),
            "verdict": (verdict or {}).get("status") if (verdict or {}).get("status") in ("sendable", "hold") else None,
            "needs_attention": attention, "thumb": "cover.jpg" if (ws / "cover.jpg").exists() else None,
            "delivered_at": iso(meta.get("delivered"))}


def clips_view(ws: Path, root: Path, job_state) -> dict:
    """The Clips board (G2.2): every candidate with the engine's score, why it was or wasn't picked, the transcript
    excerpt, and the reel project made from it (with its status). Scores are labelled as the Editor's estimate."""
    data = read_json(ws / "mine" / "candidates.json")
    if not data:
        raise FileNotFoundError("no candidates")
    text = words_text(ws)
    made = {Path(p).name.rsplit("__", 1)[-1]: ws.parent / Path(p).name for p in (read_json(ws / "mine" / "children.json", {}) or {}).get("children", [])}
    out = []
    for c in data["candidates"]:
        excerpt = " … ".join(" ".join(text.get(i, "") for i in range(r["word_start"], r["word_end"] + 1)) for r in c["ranges"])
        child = made.get(c["id"])
        row = {k: c[k] for k in ("id", "rank", "title", "hook_text", "family", "scores", "score", "duration_s", "status", "why", "reason",
                                  "standalone_risks", "warnings")}
        row["excerpt"] = excerpt[:600] + ("…" if len(excerpt) > 600 else "")
        row["project"] = None
        if child is not None and child.exists():
            row["project"] = {"id": child.name, "status": summary(child, job_state(child.name))["status"]}
        out.append(row)
    return {"source_s": data["source_s"], "yield_cap": data["yield_cap"], "target_s": data["target_s"],
            "score_label": "Editor's estimate", "score_rule": data["score_rule"], "candidates": out,
            "estimate_per_reel": costs.per_reel_estimate(root)}


def is_delivered(s: dict) -> bool:
    """The "Delivered" group: marked delivered and finished (a delivered reel that is re-editing shows as editing)."""
    return bool(s.get("delivered_at")) and s["status"] in ("sendable", "hold")


def attention_key(s: dict) -> tuple:
    group = "delivered" if is_delivered(s) else s["status"]
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
             ws / "qa" / "verdict.json", ws / "perception" / "words.json", ws / "plan" / "history", ws / "log" / "runs.jsonl"]
    return _cached(f"decisions:{ws}", files, lambda: _build_decisions(ws))


def _d(at: float, kind: str, title: str, detail: str, knowledge: list | None = None, cost: float | None = None) -> dict:
    d = {"at": at, "kind": kind, "title": title, "detail": detail or "", "knowledge": list(knowledge or [])}
    if cost:
        d["cost_usd"] = round(cost, 4)
    return d


def _call_cost(calls: list[dict], prefix: str) -> float:
    """AI cost of the Editor / Reviewer calls behind a group of decisions (labels: story, story_readback, story:fix1, …)."""
    return sum(c["cost_usd"] for c in calls if str(c.get("label", "")).startswith(prefix))


def _build_decisions(ws: Path) -> list[dict]:
    state = read_json(ws / "state.json", {}) or {}
    words = words_text(ws)
    calls = costs.calls(ws / "log" / "runs.jsonl")
    out: list[dict] = []
    story = read_json(ws / "plan" / "story.json")
    if story:
        at = _stage_time(state, "story", ws / "plan" / "story.json")
        items = story.get("items", [])
        hook = next((h for h in story.get("hook_options", []) if h.get("id") == story.get("hook")), None)
        if items:
            out.append(_d(at, "story", f"Hook: “{_line(words, items[0], 90)}”", (hook or {}).get("reason", ""), story.get("knowledge_used"),
                          _call_cost(calls, "story")))
        for it in items:
            out.append(_d(at, "story", f"Keep {it.get('id')} ({it.get('beat')}): “{_line(words, it, 90)}”", it.get("reason", "")))
    fin = read_json(ws / "plan" / "finish.json")
    if fin:
        at = _stage_time(state, "finish", ws / "plan" / "finish.json")
        cap, grade, music, ht = fin.get("captions") or {}, fin.get("grade") or {}, fin.get("music") or {}, fin.get("hook_title") or {}
        out.append(_d(at, "finish", f"Captions: {cap.get('family')}", cap.get("reason", ""), fin.get("knowledge_used"), _call_cost(calls, "finish")))
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
        out.append(_d(qa_at, "review", f"Reviewer: {'sendable' if review.get('sendable') else 'hold'}", review.get("summary", ""),
                      cost=_call_cost(calls, "review")))
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
    from reel import verdict_plain

    gates = []
    raw = read_json(ws / "qa" / "gates.json", []) or []
    for g in raw:
        status = "pass" if g.get("ok") else ("fail" if g.get("mode") == "block" else "warn")
        gates.append({"name": g.get("gate"), "status": status, "detail": g.get("detail", ""), "measured": g.get("measured") or {}})
    from reel import coverage

    return {"verdict": v.get("status"), "reasons": v.get("reasons", []), "warnings": v.get("warnings", []), "gates": gates,
            "plain": verdict_plain.explain(raw),  # one plain sentence per check that didn't pass (UI plan A1)
            "coverage": coverage.report(ws)}  # 4.2: what wasn't (or couldn't be) checked


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


PACKAGE_KINDS = {  # export/package/<name> → (kind, label)
    ".fcpxml": ("timeline", "Final Cut Pro timeline"), ".otio": ("timeline", "OpenTimelineIO timeline"),
    ".srt": ("captions", "Captions · SRT"), ".vtt": ("captions", "Captions · WebVTT"),
    "overlay.mov": ("overlay", "Overlay with transparency (captions, titles, graphics)"),
    "edit_list.md": ("edit_list", "Edit list with reasons"), "README.md": ("other", "Read me"),
}
VARIANT_LABEL = {"feed_4x5": "Feed · 4:5 · 1080×1350", "square": "Square · 1:1 · 1080×1080"}


def _bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size


def package_listing(ws: Path) -> dict:
    """FR-9: what there is to hand over. Every `path` is relative to the project folder (a media path for files)."""
    rel = lambda p: str(p.relative_to(ws))  # noqa: E731
    pkg = ws / "export" / "package"
    tl = read_json(ws / "timeline" / "timeline.json", {}) or {}
    size = f" · {tl['width']}×{tl['height']}" if tl.get("width") and tl.get("height") else ""
    cover = "cover.jpg" if (ws / "cover.jpg").exists() else None
    files: list[dict] = []
    final = next((p for p in (pkg / "reel.mp4", ws / "export" / "reel.mp4", ws / "render" / "final.mp4") if p.exists()), None)
    if final:
        files.append({"path": rel(final), "label": f"Final reel · 9:16{size}", "kind": "final", "bytes": _bytes(final), "thumb": cover})
    variants = ws / "export" / "variants"
    for p in sorted(variants.glob("*.mp4")) if variants.exists() else []:
        name = p.stem.removeprefix("reel_")
        files.append({"path": rel(p), "label": VARIANT_LABEL.get(name, name.replace("_", " ")), "kind": "variant", "bytes": _bytes(p), "thumb": None})
    review = ws / "export" / "review" / "review.mp4"
    if review.exists():
        files.append({"path": rel(review), "label": "Review copy · small, watermarked", "kind": "review_copy", "bytes": _bytes(review), "thumb": None})
    for p in sorted(pkg.iterdir()) if pkg.exists() else []:
        if p.name.startswith(".") or p == final:
            continue
        if p.is_dir():
            kind, label = ("stems", "Audio stems · dialogue, music, effects") if p.name == "stems" else ("other", p.name)
            files.append({"path": rel(p) + "/", "label": label, "kind": kind, "bytes": _bytes(p), "thumb": None})
            continue
        kind, label = PACKAGE_KINDS.get(p.name) or PACKAGE_KINDS.get(p.suffix.lower()) or ("other", p.name)
        files.append({"path": rel(p), "label": label, "kind": kind, "bytes": _bytes(p), "thumb": None})
    return {"files": files, "warnings": [*platform_notes(ws), *_credit_lines(ws)]}


def platform_notes(ws: Path) -> list[str]:
    stages_ = (read_json(ws / "state.json", {}) or {}).get("stages", {})
    return list(((stages_.get("variants") or {}).get("meta") or {}).get("platform_notes") or [])


def _credit_lines(ws: Path) -> list[str]:
    """Licences that ask for a credit line in the post (music bed, sound effects used)."""
    fin = read_json(ws / "plan" / "finish.json", {}) or {}
    track = (fin.get("music") or {}).get("track")
    if not track or track == "none":
        return []
    try:
        from reel import assets

        meta = assets.load().music.get(track) or {}
    except Exception:  # noqa: BLE001 — a missing library only loses the hint
        return []
    credit = meta.get("attribution") or meta.get("credit")
    return [f"Music “{meta.get('title') or track}” needs a credit line in the post: “{credit}”."] if credit else []


def versions(ws: Path) -> list[dict]:
    """Version history, oldest first. Before the first change the finished edit is a virtual version 1
    ("Original edit", final = render/final.mp4); the first change snapshots it into versions/1/."""
    root = ws / "versions"
    out = []
    for d in sorted((d for d in root.iterdir() if d.is_dir() and d.name.isdigit()), key=lambda d: int(d.name)) if root.exists() else []:
        meta = read_json(d / "meta.json", {}) or {}
        v = {"n": int(d.name), "created": iso(meta.get("created") or d.stat().st_mtime), "label": meta.get("label", ""),
             "reply": meta.get("reply") or "", "cost_usd": meta.get("cost_usd")}
        if (d / "final.mp4").exists():
            v["final"] = f"versions/{d.name}/final.mp4"
        out.append(v)
    final = ws / "render" / "final.mp4"
    if not out and final.exists():
        out.append({"n": 1, "created": iso(final.stat().st_mtime), "label": "Original edit", "reply": "", "cost_usd": None,
                    "final": "render/final.mp4"})
    return out


def with_measured_verdict(ws: Path, reply: str) -> str:
    """3b.4: an Editor reply ("Fixed the caption") is a claim made before the re-render. Append what QA measured after
    it, so the owner never reads a success the checks didn't confirm (Timeline-Bench: agents claimed success in 93 %
    of runs, including 95.5 % of failed ones)."""
    v = read_json(ws / "qa" / "verdict.json")
    if not v or v.get("status") not in ("sendable", "hold"):
        return reply
    from reel import coverage

    if v["status"] == "sendable":
        tail = "QA after the change: Sendable" + (f" ({len(v.get('warnings', []))} warning(s))" if v.get("warnings") else "")
    else:
        reasons = v.get("reasons", [])
        tail = f"QA after the change: Hold, {len(reasons)} reason(s): " + "; ".join(r.split(":")[0] for r in reasons[:3])
    tail += coverage.reply_tail(ws)  # 4.2: a pass never hides a check that couldn't run
    return f"{reply} · {tail}" if reply else tail


VERSION_FILES = ("plan/story.json", "plan/finish.json", "plan/story_readback.txt", "timeline/timeline.json")


def snapshot(ws: Path, label: str, *, reply: str = "", cost_usd: float | None = None) -> int:
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
    atomic_write_json(dst / "meta.json", {"n": n, "created": time.time(), "label": label, "reply": reply, "cost_usd": cost_usd})
    return n


def has_snapshots(ws: Path) -> bool:
    root = ws / "versions"
    return root.exists() and any(d.name.isdigit() for d in root.iterdir())


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


ETA_MIN_SAMPLES = 3


def stage_rates(root: Path) -> dict[str, list[float]]:
    """Seconds each stage took per second of footage, across this Mac's finished projects (UI plan B1)."""
    rates: dict[str, list[float]] = {}
    for ws in list_dirs(root):
        footage = float(studio_meta(ws).get("footage_s") or 0)
        if footage <= 0:
            continue
        for name, e in ((read_json(ws / "state.json", {}) or {}).get("stages") or {}).items():
            if e.get("status") == "done" and e.get("started") and e.get("finished") and e.get("input_hash") not in ("none", "off"):
                dur = float(e["finished"]) - float(e["started"])
                if dur > 0:
                    rates.setdefault(name, []).append(dur / footage)
    return rates


def eta_s(ws: Path, stage_list: list[dict], now: float | None = None) -> int | None:
    """Seconds left: the median time of every stage still to run, scaled by this project's footage length, minus
    the time the running stage has already spent. None until every remaining stage has ≥ 3 finished samples."""
    import statistics
    import time as _time

    footage = float(studio_meta(ws).get("footage_s") or 0)
    left = [st for st in stage_list if st["status"] in ("pending", "queued", "running")]
    if footage <= 0 or not left:
        return None
    rates = stage_rates(ws.parent)
    total = 0.0
    for st in left:
        r = rates.get(st["name"], [])
        if len(r) < ETA_MIN_SAMPLES:
            return None
        need = statistics.median(r) * footage
        if st["status"] == "running" and st.get("started"):
            need = max(need * 0.1, need - ((now or _time.time()) - float(st["started"])))  # never "0 s left" while it runs
        total += need
    return int(round(total))


def detail(ws: Path, job: str | None = None) -> dict:
    s = summary(ws, job)
    brief, brand = brief_and_brand(ws)
    verdict = read_json(ws / "qa" / "verdict.json") or {}
    st = stages(ws, job)
    return s | {"brief": brief, "brand": brand, "stages": st, "decisions": decisions(ws),
                "verdict_detail": verdict_detail(ws), "proof": verdict.get("proof_open") or [], "review": review_view(ws),
                "media": media_view(ws), "versions": versions(ws), "calls": costs.calls(ws / "log" / "runs.jsonl"),
                "platform_notes": platform_notes(ws), "eta_s": eta_s(ws, st) if s.get("status") in ("running", "queued") else None,
                "preview": read_json(ws / "export" / "preview" / "preview.json")}


TIMELINE_LISTS = ("video", "audio", "transitions", "ducking", "titles", "flashes", "pips", "effects", "graphics")


def normalized_timeline(raw: dict) -> dict:
    """The timeline with every default filled in: older timeline.json files omit defaulted keys (effects, graphics,
    grade.grain, …), and the web app reads them all."""
    from reel.schemas.timeline import Timeline

    try:
        return Timeline.model_validate(raw).model_dump(mode="json")
    except Exception:  # noqa: BLE001 — an older or hand-edited timeline still shows, with the list keys filled in
        out = dict(raw)
        for key in TIMELINE_LISTS:
            if not isinstance(out.get(key), list):
                out[key] = []
        out["grade"] = {"look": "none", "strength": 0.0, "correct": True, "grain": 0.0, "vignette": 0.0, **(raw.get("grade") or {})}
        return out


def timeline_view(ws: Path) -> dict | None:
    """FR-5 layers: the timeline, the Editor's reason for every block (keyed like the blocks), the kept lines, and the
    current value of every guided adjustment (FR-8)."""
    raw = read_json(ws / "timeline" / "timeline.json")
    if raw is None:
        return None
    tl = normalized_timeline(raw)
    words = words_text(ws)
    story = read_json(ws / "plan" / "story.json", {}) or {}
    fin = read_json(ws / "plan" / "finish.json", {}) or {}
    items = {it["id"]: {"beat": it.get("beat") or "", "text": _line(words, it, 10_000),  # words: 3a.3 word-level edits
                        "words": [[i, words.get(i, "")] for i in range(it["word_start"], it["word_end"] + 1)]}
             for it in story.get("items", [])}

    reasons: dict[str, str] = {}

    def add(key: str, text: str | None) -> None:
        if text:
            reasons[key] = f"{reasons[key]} {text}" if key in reasons else text

    hook = next((h for h in story.get("hook_options", []) if h.get("id") == story.get("hook")), None)
    for it in story.get("items", []):
        add(it["id"], it.get("reason"))
    if hook and hook.get("item"):
        add(hook["item"], f"Hook: {hook.get('reason', '')}".strip())
    for key in ("hook_title", "captions", "grade", "music"):
        add(key, (fin.get(key) or {}).get("reason"))
    clips_of: dict[str, list[str]] = {}
    for c in tl.get("video", []):
        clips_of.setdefault((c.get("src") or {}).get("item", ""), []).append(c["id"])
    for c in tl.get("audio", []):  # dialogue blocks carry their line's reason
        if c.get("role") == "voice" and (c.get("src") or {}).get("item") in items:
            add(c["id"], next((it.get("reason") for it in story.get("items", []) if it["id"] == c["src"]["item"]), None))
    for kind, word in (("punch_ins", "Punch-in"), ("speeds", "Speed"), ("holds", "Freeze")):
        for x in fin.get(kind, []):  # placed on the item's video clip(s): the punch-in block is the clip
            for cid in clips_of.get(x.get("item", ""), []):
                if cid.startswith("v_"):
                    add(cid, f"{word}: {x.get('reason', '')}".strip())
            add(x["id"], x.get("reason"))
    for kind in ("transitions", "sfx", "effects", "graphics", "broll"):
        for x in fin.get(kind, []):  # same id on the timeline (sfx audio clip, pip, effect, graphic, transition)
            add(x["id"], x.get("reason"))
            if kind == "broll":
                add(f"br_{x['id']}", x.get("reason"))  # full-frame b-roll is a video clip

    grade, cap, music = fin.get("grade") or {}, fin.get("captions") or {}, fin.get("music") or {}
    tgrade = tl.get("grade") or {}
    adjust = {
        "caption_family": cap.get("family") or (tl.get("captions") or {}).get("family"),
        "caption_tokens": {t["key"]: t["value"] for t in cap.get("tokens") or [] if "key" in t},
        "look": grade.get("look", tgrade.get("look", "none")), "look_strength": grade.get("strength", tgrade.get("strength", 0.0)),
        "grain": grade.get("grain", tgrade.get("grain", 0.0)), "vignette": grade.get("vignette", tgrade.get("vignette", 0.0)),
        "music_track": music.get("track", "none"), "music_gain_db": music.get("gain_db", -18.0),
        "max_pause_ms": story.get("max_pause_ms"), "sfx": len(fin.get("sfx") or []), "punch_ins": len(fin.get("punch_ins") or []),
        "beauty": "light" if (ws / "render" / "beauty.json").exists() else "off",  # what the last render applied (3c.1)
    }
    return {"timeline": tl, "reasons": reasons, "story": items, "adjust": adjust}
