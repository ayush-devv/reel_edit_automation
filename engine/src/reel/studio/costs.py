"""AI cost from each project's call log (log/runs.jsonl, written by reel.claude_call).

`total_cost_usd` from Claude Code is cumulative over a resumed session. Newer log rows store it as
`cost_cum_usd` (and `cost_usd` is already the per-call delta); older rows have only `cost_usd`, which
then holds the running session total. Per-call cost is therefore always
    cum(row) − cum(last row of the session this call resumed)    (0 when not resumed)
with cum = cost_cum_usd if present, else cost_usd.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path


def calls(log_file: Path) -> list[dict]:
    """Every Claude call of one project, in log order, with its own (delta) cost."""
    if not log_file.exists():
        return []
    out, last_cum = [], {}
    for line in log_file.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        cum = e.get("cost_cum_usd")
        if cum is None:
            cum = e.get("cost_usd")
        if cum is None:
            delta = 0.0
        else:
            prev = last_cum.get(e.get("resume"), 0.0) if e.get("resume") else 0.0
            delta = max(0.0, float(cum) - prev)
            if e.get("session_id"):
                last_cum[e["session_id"]] = float(cum)
        out.append({"time": e.get("time"), "label": e.get("label", ""), "cost_usd": round(delta, 6),
                    "duration_s": e.get("duration_s"), "ok": e.get("exit") == 0 and not e.get("is_error")})
    return out


def project_total(log_file: Path) -> float:
    return round(sum(c["cost_usd"] for c in calls(log_file)), 4)


def summary(projects_root: Path, days: int = 30, now: float | None = None) -> dict:
    since = (now or time.time()) - days * 86400
    by_project: dict[str, float] = {}
    by_day: dict[str, float] = {}
    n = 0
    for log in sorted(projects_root.glob("*/log/runs.jsonl")):
        pid = log.parent.parent.name
        if pid.startswith("."):
            continue
        for c in calls(log):
            if not c["time"] or c["time"] < since:
                continue
            n += 1
            by_project[pid] = by_project.get(pid, 0.0) + c["cost_usd"]
            day = datetime.fromtimestamp(c["time"]).strftime("%Y-%m-%d")
            by_day[day] = by_day.get(day, 0.0) + c["cost_usd"]
    return {"total_usd": round(sum(by_project.values()), 4), "calls": n,
            "by_project": [{"id": k, "usd": round(v, 4)} for k, v in sorted(by_project.items(), key=lambda kv: -kv[1])],
            "by_day": [{"date": k, "usd": round(v, 4)} for k, v in sorted(by_day.items())]}
