"""What the verdict did NOT check (roadmap 4.2; harness comparison §4 idea 6, "unknown is not missing").

Decided by code from the stored QA results (qa/gates.json, qa/review.json), never from a Claude claim, and kept out of
the QA stage's fingerprint (verdict.py / qa.py / cuts.py): adding this changes no hash, so no project re-buys a Reviewer
call. Three lists:
- not_measured: a check that ran but couldn't measure (no reference, no face, decode failure). It is shown as a problem
  to look at, never as a pass (these gates already return ok=False in warn mode);
- partial: a check that skipped some of what it should look at (`measured.skipped`);
- never: what no gate looks at, so the owner knows where their own eyes are needed.
"""

from __future__ import annotations

import json
from pathlib import Path

NOT_MEASURED_MARKS = ("not measured", "could not", "couldn't", "unmeasured", "no reference", "not available", "failed to")

NEVER_CHECKED = [
    "whether the story is interesting or persuasive for this audience",
    "whether the music suits the client (taste), beyond loudness and ducking",
    "comic and emotional timing (a joke landing, a pause for effect)",
    "whether a claim in the speech is true (only the brief's banned claims are checked)",
    "how the reel looks on the client's own phone and in their feed",
]


def _read(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def report(ws: Path) -> dict | None:
    gates = _read(Path(ws) / "qa" / "gates.json")
    if gates is None:
        return None
    not_measured, partial = [], []
    for g in gates:
        detail = str(g.get("detail") or "")
        if any(m in detail.casefold() for m in NOT_MEASURED_MARKS):
            not_measured.append({"gate": g.get("gate"), "why": detail})
            continue
        skipped = (g.get("measured") or {}).get("skipped") or []
        if skipped:
            partial.append({"gate": g.get("gate"), "skipped": len(skipped), "why": f"{len(skipped)} item(s) couldn't be checked"})
    review = (Path(ws) / "qa" / "review.json").exists()
    if not review:
        not_measured.append({"gate": "reviewer", "why": "no Reviewer look at this render (QA ran with --skip-review)"})
    return {"not_measured": not_measured, "partial": partial, "never": NEVER_CHECKED, "reviewer": review}


def lines(rep: dict | None) -> list[str]:
    """Plain lines for a terminal or a reply."""
    if not rep:
        return []
    out = [f"couldn't check {x['gate']}: {x['why']}" for x in rep["not_measured"]]
    out += [f"{x['gate']}: {x['why']}" for x in rep["partial"]]
    return out


def reply_tail(ws: Path) -> str:
    rep = report(ws)
    n = len((rep or {}).get("not_measured", [])) + len((rep or {}).get("partial", []))
    return f"; {n} check(s) couldn't run fully: look at those yourself" if n else ""
