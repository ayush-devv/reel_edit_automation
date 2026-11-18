"""Reviewer + gate calibration against the owner's labels (ADR-0021 §5, ADR-0017).

Labels: projects/*/qa/owner_label.json {"sendable": bool, "note": str} written by `reel label`.
Reports Reviewer agreement (accuracy, Cohen's κ, false `sendable`) and each gate's
false-positive rate on owner-sendable renders. Promotion is the owner's decision (config).
"""

from __future__ import annotations

import json
from pathlib import Path

MIN_LABELS = 6
MAX_FP = 0.05


def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def collect(projects_root: Path) -> list[dict]:
    rows = []
    for qa_dir in sorted(projects_root.glob("*/qa")):
        label = qa_dir / "owner_label.json"
        if not label.exists():
            continue
        row = {"project": qa_dir.parent.name, "owner": json.loads(label.read_text())["sendable"]}
        if (qa_dir / "review.json").exists():
            row["reviewer"] = json.loads((qa_dir / "review.json").read_text())["sendable"]
        if (qa_dir / "verdict.json").exists():
            row["verdict"] = json.loads((qa_dir / "verdict.json").read_text())["status"] == "sendable"
        if (qa_dir / "gates.json").exists():
            row["failed"] = [g["gate"] for g in json.loads((qa_dir / "gates.json").read_text()) if not g["ok"]]
        rows.append(row)
    return rows


def report(rows: list[dict]) -> dict:
    rev = [(r["reviewer"], r["owner"]) for r in rows if "reviewer" in r]
    ver = [(r["verdict"], r["owner"]) for r in rows if "verdict" in r]
    good = [r for r in rows if r["owner"]]
    gates: dict[str, dict] = {}
    for r in good:
        for g in r.get("failed", []):
            gates.setdefault(g, {"false_positives": 0})["false_positives"] += 1
    for g, d in gates.items():
        d["fp_rate"] = round(d["false_positives"] / len(good), 3)
    return {
        "labels": len(rows), "owner_sendable": len(good),
        "reviewer": {"n": len(rev), "accuracy": round(sum(a == b for a, b in rev) / len(rev), 3) if rev else None,
                     "kappa": kappa(rev), "false_sendable": sum(a and not b for a, b in rev),
                     "trust_ready": len(rev) >= MIN_LABELS and sum(a and not b for a, b in rev) == 0 and (kappa(rev) or 0) >= 0.4},
        "tool_verdict": {"n": len(ver), "false_sendable": sum(a and not b for a, b in ver)},
        "gates_failing_on_sendable": gates,
        "gate_promotion_note": f"a gate can be promoted to block when ≥ {MIN_LABELS} owner-sendable renders show FP rate ≤ {MAX_FP:.0%}; "
                               "gates never failing on sendable renders are not listed",
    }
