"""Pairwise judge for evals (roadmap 3b.2): our reel vs the pro's, asked twice with the sides swapped.

Evidence: Unified Agentic Video Editing (arXiv 2609.12769: both orders, order-dependent verdicts count as ties);
EditDuet (arXiv 2509.10761: a pairwise judge on keyframe grids matched human–human agreement). Timeline-Bench showed
per-edit judgements are noisy, so this family stays OUT of the primary score until it agrees with the owner's own
blind picks (`owner_agreement`), which the Quality lab collects.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reel import config

PERSONA = Path(__file__).resolve().parents[1] / "personas" / "pairwise_judge.md"
EFFORT = "medium"
SHEET_EVERY_S = 1.5
OWNER_LOG = config.EVAL_DIR / "pairwise_owner.jsonl"
PROMPT = ("Two edits of the same raw footage. Read pairwise/input.md, look at every contact sheet it lists for A and for B, "
          "and say which reel is better as a short-form reel.")


class PairVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    better: str  # "A" | "B" | "same"
    reasons: str


def _prepare(ws, ours: Path, pro: Path, ours_side: str) -> None:
    """Contact sheets and pace numbers for both reels, labelled only A and B."""
    from reel import qa, sheets
    from reel.probe import probe
    from reel.workspace import atomic_write_bytes

    files = {"A": ours if ours_side == "A" else pro, "B": pro if ours_side == "A" else ours}
    lines = ["# Two reels to compare (you don't know which is which)", ""]
    for side, f in files.items():
        dur = probe(f).duration_s
        stamps = [(t, f"{side} {t:.1f}s") for t in [k * SHEET_EVERY_S + 0.25 for k in range(int(dur / SHEET_EVERY_S) + 1)] if t < dur]
        made = sheets.make_sheets(f, stamps, ws.path("pairwise", side, "sheet"))
        try:
            pace = qa.measure_pace(f)
            pace_line = f"{pace['cuts_per_min']} scene cuts/min, longest stretch with no cut {pace['longest_static_s']} s"
        except Exception:  # noqa: BLE001
            pace_line = "pace not measured"
        lines += [f"## Reel {side}: {dur:.1f} s · {pace_line}", "", *[f"- {p.relative_to(ws.root)}" for p in made], ""]
    lines += ["Judge as a viewer scrolling Instagram: hook, clarity of the story, pacing, captions, look. Answer `better` = A, B or same."]
    atomic_write_bytes(ws.path("pairwise", "input.md"), "\n".join(lines).encode())


def _ask(caller, ws, ours: Path, pro: Path, ours_side: str) -> str:
    """'ours' | 'pro' | 'same' for one order."""
    from reel import decide

    _prepare(ws, ours, pro, ours_side)
    d = decide.decide(caller, ws, label=f"pairwise_{ours_side}", prompt=PROMPT, model=PairVerdict, persona=PERSONA, effort=EFFORT,
                      check=lambda v: [] if v.better in ("A", "B", "same") else [_issue()])
    b = d.plan.better
    if b == "same":
        return "same"
    return "ours" if b == ours_side else "pro"


def _issue():
    from reel.validate import Issue

    return Issue("bad_answer", "better", "`better` must be A, B or same.", "Answer A, B or same.")


def judge(ours: Path, pro: Path, work: Path, caller) -> dict:
    """Ask in both orders; a verdict that flips with the order is a tie."""
    from reel.workspace import Workspace

    ws = Workspace.create(work)
    first = _ask(caller, ws, ours, pro, "A")
    second = _ask(caller, ws, ours, pro, "B")
    if first == second:
        result = {"ours": "win", "pro": "loss", "same": "tie"}[first]
    else:
        result = "tie"
    return {"result": result, "orders": [first, second], "consistent": first == second}


def tally(results: list[dict]) -> dict:
    out = {"win": 0, "tie": 0, "loss": 0}
    for r in results:
        if r.get("pairwise"):
            out[r["pairwise"]["result"]] += 1
    return out


# ------------------------------------------------------------------ the owner's blind picks (calibration)


def side_of_ours(run_id: str, reel: str) -> str:
    """Which side the owner sees our reel on: fixed per (run, reel), unpredictable across them."""
    return "A" if int(hashlib.sha1(f"{run_id}/{reel}".encode()).hexdigest(), 16) % 2 == 0 else "B"


def record_owner(run_id: str, reel: str, choice: str, log: Path | None = None) -> None:
    if choice not in ("A", "B", "same"):
        raise ValueError("choice must be A, B or same")
    ours = side_of_ours(run_id, reel)
    pick = "same" if choice == "same" else ("ours" if choice == ours else "pro")
    f = log or OWNER_LOG
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as fh:
        fh.write(json.dumps({"at": time.time(), "run": run_id, "reel": reel, "owner": pick}) + "\n")


def owner_picks(log: Path | None = None) -> dict[tuple[str, str], str]:
    f = log or OWNER_LOG
    out: dict[tuple[str, str], str] = {}
    if f.exists():
        for line in f.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            out[(e["run"], e["reel"])] = e["owner"]  # the latest pick wins
    return out


def owner_agreement(rows: list[dict], log: Path | None = None) -> dict:
    """How often the judge's verdict matches the owner's blind pick (win↔ours, loss↔pro, tie↔same)."""
    picks = owner_picks(log)
    want = {"win": "ours", "loss": "pro", "tie": "same"}
    pairs = [(want[r["pairwise"]["result"]], picks[(row["run_id"], r["id"])]) for row in rows for r in row.get("reels", [])
             if r.get("pairwise") and (row["run_id"], r["id"]) in picks]
    agree = sum(a == b for a, b in pairs)
    return {"n": len(pairs), "agree": agree, "rate": round(agree / len(pairs), 3) if pairs else None}
