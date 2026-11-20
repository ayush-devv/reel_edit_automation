"""Clip Factory, step 2: turn picked candidates into reel projects (roadmap G2.2).

A reel project ("child") reuses the long recording's analysis instead of re-running ASR, faces and voice:
- `mezz/` files are **hard links** (no disk cost; Studio's media_path refuses symlink escapes; Claude Code reads
  inside the project folder; deleting or re-analysing the source never breaks a child, which keeps its inodes);
- `perception/*.json` and `source/manifest.json` are copies (small);
- `tables/` are regenerated for the child's window only, with **global** word indices, so story plans stay valid
  against the full word table;
- `window.json` holds the candidate's ranges and the allowed margin. The story validator, revisions and autofix
  all enforce it (decide.Inputs.window), and the child runs only the edit stages (stages.CLIP_PIPELINE).
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from reel import mine
from reel.schemas.perception import SegmentTable, WordTable
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

MARGIN_S = 20.0  # context either side of the candidate the Editor may use to find a better first line
OVERVIEW_EVERY_S = 2.0


def load_window(ws: Workspace) -> list[tuple[str, int, int]] | None:
    p = ws.path("window.json")
    if not p.exists():
        return None
    return [(c, int(a), int(b)) for c, a, b in json.loads(p.read_text())["allowed"]]


def is_child(ws: Workspace) -> bool:
    return ws.path("window.json").exists()


def window_seconds(words: WordTable, window: list[tuple[str, int, int]]) -> float:
    by = words.by_index()
    total = 0.0
    for _clip, a, b in window:
        if a in by and b in by:
            total += max(0.0, (by[b].end_us - by[a].start_us) / 1e6)
    return total


def in_window(clip: str, a: int, b: int, window: list[tuple[str, int, int]]) -> bool:
    return any(c == clip and lo <= a and b <= hi for c, lo, hi in window)


def allowed_ranges(cand: dict, words: WordTable, segments: SegmentTable, margin_s: float = MARGIN_S) -> list[tuple[str, int, int]]:
    """The candidate's ranges widened by `margin_s` either side to whole segments of the same clip, merged."""
    by = words.by_index()
    segs = sorted(segments.segments, key=lambda s: (s.clip, s.word_start))
    out: list[tuple[str, int, int]] = []
    for r in cand["ranges"]:
        t0 = by[r["word_start"]].start_us - margin_s * 1e6
        t1 = by[r["word_end"]].end_us + margin_s * 1e6
        inside = [s for s in segs if s.clip == r["clip"] and s.end_us >= t0 and s.start_us <= t1]
        lo = min([r["word_start"], *(s.word_start for s in inside)])
        hi = max([r["word_end"], *(s.word_end for s in inside)])
        out.append((r["clip"], lo, hi))
    out.sort()
    merged: list[tuple[str, int, int]] = []
    for c, lo, hi in out:
        if merged and merged[-1][0] == c and lo <= merged[-1][2] + 1:
            merged[-1] = (c, merged[-1][1], max(hi, merged[-1][2]))
        else:
            merged.append((c, lo, hi))
    return merged


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:  # another volume: a copy
        shutil.copy2(src, dst)


def _read(ws: Workspace, name: str) -> dict:
    p = ws.path("perception", f"{name}.json")
    return json.loads(p.read_text()) if p.exists() else {}


def window_tables(child: Workspace, window: list[tuple[str, int, int]], brief, *, make_sheets: bool = True) -> dict:
    """The tables stage's outputs for the window only (global indices kept), plus contact sheets of it."""
    from reel import selects, sheets, tables

    words = WordTable.model_validate(_read(child, "words"))
    segs = SegmentTable.model_validate(_read(child, "segments"))
    keep_w = [w for w in words.words if any(w.clip == c and lo <= w.i <= hi for c, lo, hi in window)]
    keep_s = [s for s in segs.segments if in_window(s.clip, s.word_start, s.word_end, window)]
    w_tab = WordTable(language=words.language, words=keep_w)
    s_tab = SegmentTable(segments=keep_s)
    prosody = _read(child, "prosody").get("segments", [])
    faces, energy, scenes, palette, ocr = (_read(child, n) for n in ("faces", "energy", "scenes", "palette", "ocr"))
    edges = {int(k): (int(v[0]), int(v[1])) for k, v in _read(child, "edges").items()}
    manifest = json.loads(child.path("source", "manifest.json").read_text())
    takes = selects.find_takes(w_tab, s_tab, prosody)
    rows = tables.segment_rows(w_tab, s_tab, prosody, takes, faces, energy, scenes)
    atomic_write_json(child.path("tables", "segments.json"), {"segments": rows})
    atomic_write_json(child.path("tables", "takes.json"), takes)
    atomic_write_bytes(child.path("tables", "script.md"), tables.script_md(w_tab, s_tab, rows).encode())
    atomic_write_bytes(child.path("tables", "words.tsv"), tables.words_tsv(w_tab, edges).encode())
    summary = tables.summary_md(manifest, w_tab, rows, takes, palette, ocr, brief)
    summary += ("\nThis reel is one part of a longer recording. Only the words in these tables are available: "
                "word indices are the recording's own (they do not start at 0).\n")
    atomic_write_bytes(child.path("tables", "summary.md"), summary.encode())
    sheet_index: dict[str, list[str]] = {}
    for c in manifest["clips"]:
        cid = c["id"]
        mezz = child.path("mezz", f"{cid}.mov")
        spans = [(lo, hi) for cc, lo, hi in window if cc == cid]
        if not make_sheets or not spans or not mezz.exists():
            continue
        by = w_tab.by_index()
        seg_stamps = [((r["t0"] + r["t1"]) / 2, f"{r['seg_id']} {r['t0']:.1f}s") for r in rows if r["clip"] == cid]
        overview = []
        for lo, hi in spans:
            t, t_end = by[lo].start_us / 1e6, by[hi].end_us / 1e6
            while t < t_end:
                overview.append((t, f"{t:.1f}s"))
                t += OVERVIEW_EVERY_S
        made = []
        if seg_stamps:
            made += sheets.make_sheets(mezz, seg_stamps, child.path("tables", "sheets", f"{cid}_segments"))
        if overview:
            made += sheets.make_sheets(mezz, overview, child.path("tables", "sheets", f"{cid}_overview"))
        sheet_index[cid] = [str(p.relative_to(child.root)) for p in made]
    atomic_write_json(child.path("tables", "sheets.json"), sheet_index)
    return {"words": len(keep_w), "segments": len(keep_s)}


def child_dir(parent: Workspace, cand_id: str) -> Path:
    return parent.root.parent / f"{parent.root.name}__{cand_id}"


def children(parent: Workspace) -> list[Path]:
    """Reel projects made from this source. Stored by name, so moving the projects folder keeps the board working."""
    p = parent.path("mine", "children.json")
    if not p.exists():
        return []
    return [parent.root.parent / Path(x).name for x in json.loads(p.read_text()).get("children", [])]


def spawn(parent: Workspace, cand_ids: list[str], *, make_sheets: bool = True) -> list[Path]:
    """Create one reel project per picked candidate. Re-spawning an existing child refreshes its window files only."""
    from reel import brief as brief_mod
    from reel import project

    data = mine.load(parent)
    if not data:
        raise ValueError("no candidates yet: run the source through `reel factory` first")
    by_id = {c["id"]: c for c in data["candidates"]}
    unknown = [i for i in cand_ids if i not in by_id]
    if unknown:
        raise ValueError(f"unknown candidate id(s): {', '.join(unknown)}")
    words = project.word_table(parent)
    segs = SegmentTable.model_validate_json(parent.path("perception", "segments.json").read_text())
    opts = json.loads(parent.path("run_options.json").read_text()) if parent.path("run_options.json").exists() else {}
    parent_brief = brief_mod.load_brief(project.brief_path(parent, opts))
    studio = json.loads(parent.path("studio.json").read_text()) if parent.path("studio.json").exists() else {}
    made: list[Path] = []
    for cid in cand_ids:
        cand = by_id[cid]
        root = child_dir(parent, cid)
        child = Workspace.create(root)
        for f in parent.path("mezz").iterdir():
            if f.is_file() and not f.name.startswith("."):
                _link(f, child.path("mezz", f.name))
        for f in parent.path("perception").glob("*.json"):
            child.path("perception").mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, child.path("perception", f.name))
        manifest = json.loads(parent.path("source", "manifest.json").read_text())
        atomic_write_json(child.path("source", "manifest.json"), manifest | {"parent": parent.root.name})
        window = allowed_ranges(cand, words, segs)
        atomic_write_json(child.path("window.json"), {"parent": parent.root.name, "candidate": cand,
                                                      "ranges": [[r["clip"], r["word_start"], r["word_end"]] for r in cand["ranges"]],
                                                      "allowed": [list(w) for w in window]})
        note = (f"Clip Factory reel '{cand['title']}' from a longer recording. Opening line the miner found: “{cand['hook_text']}”. "
                f"Why: {cand['reason']}" + (f" Risks for a cold viewer: {'; '.join(cand['standalone_risks'])}." if cand.get("standalone_risks") else ""))
        base = parent_brief.model_dump() if parent_brief else {"project": root.name}
        base["project"] = root.name
        base["notes"] = ((base.get("notes") or "") + "\n" + note).strip()
        if not parent_brief or tuple(parent_brief.target_length_s) == tuple(brief_mod.Brief.model_fields["target_length_s"].default):
            base["target_length_s"] = list(mine.target_for(parent_brief, opts))
        brief = brief_mod.Brief.model_validate(base)
        atomic_write_json(child.path("brief.json"), brief.model_dump(mode="json"))
        child_opts = {k: v for k, v in opts.items() if k not in ("input", "analyse_only", "preview_first", "mine", "clip_target_s")}
        child_opts |= {"brief": str(child.path("brief.json")), "parent": parent.root.name, "candidate": cid}
        atomic_write_json(child.path("run_options.json"), child_opts)
        atomic_write_json(child.path("studio.json"), {"name": cand["title"], "client": studio.get("client"), "parent": parent.root.name,
                                                      "candidate": cid, "created": time.time()})
        window_tables(child, window, brief, make_sheets=make_sheets)
        made.append(root)
    known = [p.name for p in children(parent)]
    atomic_write_json(parent.path("mine", "children.json"), {"children": list(dict.fromkeys(known + [p.name for p in made]))})
    mine.log_picks(parent, cand_ids)
    return made


def batch_broll(ws: Workspace) -> list[str]:
    """B-roll ids the other reels from the same recording already use (sorted; [] for ordinary projects)."""
    w = ws.path("window.json")
    if not w.exists():
        return []
    parent = ws.root.parent / json.loads(w.read_text())["parent"]
    used: set[str] = set()
    for sib in children(Workspace(parent)):
        fin = sib / "plan" / "finish.json"
        if sib != ws.root and fin.exists():
            used |= {b.get("asset") for b in (json.loads(fin.read_text()).get("broll") or []) if b.get("asset")}
    return sorted(used)


def _anchor_file(ws: Workspace) -> Path | None:
    w = ws.path("window.json")
    if not w.exists():
        return None
    return ws.root.parent / json.loads(w.read_text())["parent"] / "mine" / "batch_style.json"


def batch_style(ws: Workspace) -> dict | None:
    """Caption family and look of the set's anchor: the first reel of this recording to finish its finish pass. It is
    fixed once (mine/batch_style.json in the source), so siblings never flip each other's finish hash. None for
    ordinary projects, for the anchor itself, before any reel finished, or when the owner turned it off."""
    f = _anchor_file(ws)
    if f is None or not f.exists():
        return None
    opts = json.loads(ws.path("run_options.json").read_text()) if ws.path("run_options.json").exists() else {}
    if opts.get("batch_style") is False:
        return None
    style = json.loads(f.read_text())
    return None if style.get("from") == ws.root.name else style


def record_batch_style(ws: Workspace) -> None:
    """After a reel's finish pass: the first one of the set becomes the anchor."""
    f = _anchor_file(ws)
    fin = ws.path("plan", "finish.json")
    if f is None or f.exists() or not fin.exists() or not f.parent.exists():
        return
    plan = json.loads(fin.read_text())
    atomic_write_json(f, {"from": ws.root.name, "caption_family": (plan.get("captions") or {}).get("family"),
                          "look": (plan.get("grade") or {}).get("look")})
