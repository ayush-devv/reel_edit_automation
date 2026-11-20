"""Cost guard (roadmap 4.1): what this month has cost, a monthly cap, and quote → approve for paid generator calls.

- Month to date = every project's Claude calls this calendar month (reel.studio.costs) + paid generator charges from
  the ledger.
- The cap (Studio Settings, `monthly_cap_usd`, 0 = off) is checked before a new paid run starts: past it, the owner
  must say "spend anyway". A run already going always finishes; nothing stops mid-edit.
- A paid generator (`paid: true` in ~/.config/reel/generators.json, with a `price`) never runs without an approval
  bound to the exact request (its input hash). The ledger is content-keyed: an identical request that was already
  bought returns the earlier output instead of being bought twice.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()


class ApprovalNeeded(RuntimeError):
    """A paid call has a quote but no approval for this exact request."""

    def __init__(self, generator: str, request_hash: str, quote_usd: float):
        super().__init__(f"{generator}: this paid request needs your approval (quote ${quote_usd:.2f}); "
                         f"approve it in Studio → Costs, or `reel spend approve {request_hash}`")
        self.generator, self.request_hash, self.quote_usd = generator, request_hash, quote_usd


def ledger_file() -> Path:
    return Path(os.environ.get("REEL_CONFIG_DIR") or Path.home() / ".config" / "reel") / "paid_ledger.jsonl"


def request_hash(generator: str, payload: dict) -> str:
    return hashlib.sha256(json.dumps({"g": generator, "p": payload}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def quote(spec: dict, *, chars: int = 0, seconds: float = 0.0) -> float:
    """USD for one request from the generator's declared price: {"usd": x, "per": "call" | "1k_chars" | "second"}."""
    price = spec.get("price") or {}
    usd, per = float(price.get("usd") or 0.0), price.get("per", "call")
    n = {"call": 1.0, "1k_chars": chars / 1000.0, "second": seconds}.get(per)
    if n is None:
        raise ValueError(f"unknown price unit {per!r}: use call, 1k_chars or second")
    return round(usd * n, 4)


def _entries(f: Path | None = None) -> list[dict]:
    f = f or ledger_file()
    out = []
    try:
        for line in f.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def _append(entry: dict, f: Path | None = None) -> None:
    f = f or ledger_file()
    with _lock:
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": time.time(), **entry}, ensure_ascii=False) + "\n")


def approve(h: str, f: Path | None = None) -> dict:
    q = next((e for e in reversed(_entries(f)) if e.get("kind") == "quote" and e.get("hash") == h), None)
    if q is None:
        raise KeyError(f"no quote {h}")
    _append({"kind": "approval", "hash": h, "generator": q["generator"], "quote_usd": q["quote_usd"]}, f)
    return q


def pending(f: Path | None = None) -> list[dict]:
    """Quotes with no approval and no purchase yet (newest first, one per request)."""
    es = _entries(f)
    done = {e["hash"] for e in es if e.get("kind") in ("approval", "bought")}
    seen, out = set(), []
    for e in reversed(es):
        if e.get("kind") == "quote" and e["hash"] not in done and e["hash"] not in seen:
            seen.add(e["hash"])
            out.append({k: e.get(k) for k in ("at", "hash", "generator", "quote_usd", "what", "project")})
    return out


def paid_call(gen_id: str, spec: dict, payload: dict, out: Path, run, *, chars: int = 0, seconds: float = 0.0,
              what: str = "", project: str | None = None, f: Path | None = None) -> str:
    """Run one generator call. Free generators just run. A paid one: reuse an identical earlier purchase if its file is
    still there; else run only with an approval for this exact request (else record the quote and raise ApprovalNeeded).
    Returns "free" | "reused" | "bought"."""
    if not spec.get("paid"):
        run()
        return "free"
    h = request_hash(gen_id, payload)
    es = _entries(f)
    bought = next((e for e in reversed(es) if e.get("kind") == "bought" and e.get("hash") == h and Path(e.get("output", "")).is_file()), None)
    if bought:
        out.parent.mkdir(parents=True, exist_ok=True)
        if Path(bought["output"]).resolve() != out.resolve():
            shutil.copyfile(bought["output"], out)
        return "reused"
    usd = quote(spec, chars=chars, seconds=seconds)
    if not any(e.get("kind") == "approval" and e.get("hash") == h for e in es):
        if not any(e.get("kind") == "quote" and e.get("hash") == h for e in es):
            _append({"kind": "quote", "hash": h, "generator": gen_id, "quote_usd": usd, "what": what[:200], "project": project}, f)
        raise ApprovalNeeded(gen_id, h, usd)
    run()
    _append({"kind": "bought", "hash": h, "generator": gen_id, "usd": usd, "output": str(out), "project": project}, f)
    return "bought"


def paid_this_month(now: float | None = None, f: Path | None = None) -> float:
    start = _month_start(now)
    return round(sum(float(e.get("usd") or 0.0) for e in _entries(f) if e.get("kind") == "bought" and (e.get("at") or 0) >= start), 4)


def _month_start(now: float | None = None) -> float:
    d = datetime.fromtimestamp(now or time.time())
    return datetime(d.year, d.month, 1).timestamp()


def month_to_date(projects_root: Path, now: float | None = None, f: Path | None = None) -> dict:
    from reel.studio import costs

    start = _month_start(now)
    claude = 0.0
    for log in projects_root.glob("*/log/runs.jsonl"):
        if log.parent.parent.name.startswith("."):
            continue
        claude += sum(c["cost_usd"] for c in costs.calls(log) if (c["time"] or 0) >= start)
    paid = paid_this_month(now, f)
    return {"claude_usd": round(claude, 4), "paid_usd": paid, "total_usd": round(claude + paid, 4)}


def status(projects_root: Path, cap_usd: float, now: float | None = None, f: Path | None = None) -> dict:
    """What the Studio shows before a run: month to date, the cap, one edit's estimate, and whether a new run is over."""
    from reel.studio import costs

    mtd = month_to_date(projects_root, now, f)
    est = costs.per_reel_estimate(projects_root)
    cap = max(0.0, float(cap_usd or 0.0))
    next_low = (est or {}).get("low_usd", 0.0)
    return {"month": mtd, "cap_usd": cap or None, "estimate": est, "over_cap": bool(cap) and mtd["total_usd"] + next_low >= cap,
            "pending": pending(f)}
