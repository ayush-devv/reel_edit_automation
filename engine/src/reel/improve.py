"""`reel improve` — gated self-improvement loop v1 (ADR-0029, ADR-0030 §3).

One round:
  baseline (R runs per tuning reel) → Improver proposes ≤ 3 single-node knowledge deltas →
  Stage A: each change alone on 3 reels must raise the mean → Stage B: survivors together on
  the full tuning set must pass the acceptance rule → confirmation re-run of both arms →
  accepted deltas are committed to knowledge/learned/overrides.yaml (git commit + tag), else reverted.

Only knowledge changes (never code), only the tuning split (the holdout is refused by the
harness), ≤ 40 changed lines per round. The night stops after 2 rejected rounds, 3 accepted
changes or the reel-run budget.
"""

from __future__ import annotations

from datetime import datetime, timezone

import copy
import json
import subprocess
import time
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel, ConfigDict

from reel import claude_call, config, knowledge
from reel.evalh import acceptance
from reel.workspace import atomic_write_bytes

PERSONA = Path(__file__).parent / "personas" / "improver.md"
LOG = config.EVAL_DIR / "improve_log.jsonl"
MAX_CHANGES = 3
MAX_LINES = 40
STAGE_A_REELS = 3

Runs = dict[str, list[dict]]
Evaluate = Callable[..., Runs]  # evaluate(reels: list[str] | None, runs: int, label: str) -> Runs


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Field_(_Strict):
    key: str  # summary | when_to_use | avoid_when | parameters (JSON object as text) | for "add": also id/type/name/genres
    value: str


class Change(_Strict):
    id: str
    kind: str  # "edit" an existing node | "add" a new technique / anti_pattern node
    node_id: str
    fields: list[Field_]
    evidence: str  # which reels / scores / reviewer issues motivate it
    expected_effect: str


class Proposal(_Strict):
    diagnosis: str
    changes: list[Change]


# ------------------------------------------------------------------ overrides


def _value(key: str, v: str):
    if key == "parameters":
        return json.loads(v)
    if key == "genres":
        return [g.strip() for g in v.split(",") if g.strip()]
    if key == "core":
        return v.strip().lower() == "true"
    return v


def with_changes(base: dict, changes: list[Change]) -> dict:
    ov = copy.deepcopy(base) or {}
    for c in changes:
        f = {x.key: _value(x.key, x.value) for x in c.fields}
        if c.kind == "edit":
            ov.setdefault("edit", {}).setdefault(c.node_id, {}).update({k: v for k, v in f.items() if k in knowledge.EDITABLE_FIELDS})
        else:
            ov.setdefault("add", []).append({"id": c.node_id, **{k: v for k, v in f.items() if k != "id"}})
    return ov


def check_changes(changes: list[Change], base: dict) -> list[str]:
    graph = knowledge.nodes()
    problems = []
    if len(changes) > MAX_CHANGES:
        problems.append(f"{len(changes)} changes > {MAX_CHANGES}")
    for c in changes:
        keys = {x.key for x in c.fields}
        if c.kind == "edit":
            if c.node_id not in graph:
                problems.append(f"{c.id}: unknown node {c.node_id}")
            if keys - set(knowledge.EDITABLE_FIELDS):
                problems.append(f"{c.id}: fields {sorted(keys - set(knowledge.EDITABLE_FIELDS))} not editable")
        elif c.kind == "add":
            if c.node_id in graph:
                problems.append(f"{c.id}: node {c.node_id} already exists")
            if not {"type", "name", "summary"} <= keys:
                problems.append(f"{c.id}: a new node needs type, name, summary")
        else:
            problems.append(f"{c.id}: kind must be edit or add")
        try:
            [_value(x.key, x.value) for x in c.fields]
        except json.JSONDecodeError:
            problems.append(f"{c.id}: parameters is not a JSON object")
    lines = len(yaml.safe_dump(with_changes({}, changes), sort_keys=True, allow_unicode=True).splitlines())
    if lines > MAX_LINES:
        problems.append(f"delta is {lines} lines > {MAX_LINES}")
    return problems


def write_overrides(ov: dict) -> None:
    knowledge.LEARNED.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(knowledge.LEARNED, yaml.safe_dump(ov, sort_keys=True, allow_unicode=True).encode())
    knowledge.nodes.cache_clear()


# ------------------------------------------------------------------ evidence + proposal


def evidence_md(baseline: Runs, rows: dict[str, list[dict]]) -> str:
    lines = ["# Tuning-set evidence (baseline)", "", "Scores 0–100; families 0–1. Lower = worse. Holdout reels are never shown.", ""]
    for reel, runs in baseline.items():
        ps = [r.get("primary") for r in runs]
        lines.append(f"## {reel} — primary {ps}")
        for r in rows.get(reel, [])[:1]:
            d = r.get("detail", {})
            lines.append(f"- families {json.dumps(r.get('families'))}")
            if d:
                lines.append(f"- story {json.dumps(d.get('story'))}")
                lines.append(f"- captions {json.dumps(d.get('captions'))}")
            lines += [f"- reviewer: {i}" for i in r.get("review_issues", [])[:6]]
            lines.append(f"- knowledge used: {', '.join(r.get('knowledge_used', []))}")
            lines += [f"- veto: {v}" for v in r.get("vetoes", [])]
        lines.append("")
    lines += ["# Knowledge you may change (id — summary)", ""]
    lines += [f"- `{n['id']}` [{n.get('type')}] {n.get('summary', '').strip()[:160]}" for n in knowledge.nodes().values()
              if n.get("type") in ("technique", "anti_pattern", "principle")]
    return "\n".join(lines) + "\n"


def claude_proposer(caller=claude_call.call):
    def propose(evidence: str) -> Proposal:
        work = config.EVAL_DIR / "improve"
        atomic_write_bytes(work / "evidence.md", evidence.encode())
        res = caller("Propose knowledge changes. Read evidence.md first.", Proposal.model_json_schema(), cwd=work,
                     persona_file=PERSONA, effort="high", log_file=work / "runs.jsonl", label="improve")
        return Proposal.model_validate(res.data)
    return propose


# ------------------------------------------------------------------ the loop


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=config.REPO_ROOT, capture_output=True, text=True).stdout.strip()


def commit_accepted(changes: list[Change], decision: dict) -> str | None:
    rel = str(knowledge.LEARNED.relative_to(config.REPO_ROOT))
    msg = ("learned: " + "; ".join(f"{c.kind} {c.node_id}" for c in changes)
           + f"\n\nmean gain {decision['mean_gain']:+.2f} (δ_min {decision['delta_min']}), p={decision['p']}\n")
    _git("add", rel)
    _git("commit", "-m", msg, "--", rel)
    tag = "learned/" + time.strftime("%Y%m%d-%H%M%S")
    _git("tag", tag)
    return tag


def _log(entry: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}, default=str) + "\n")


def run_night(evaluate: Evaluate, propose: Callable[[str], Proposal], *, runs: int = 3, rounds: int = 5, budget: int = 100,
              rows_of: Callable[[], dict] | None = None, commit: bool = True, dry_run: bool = False) -> dict:
    accepted: list[Change] = []
    rejected_rounds = 0
    used = 0
    base_ov = knowledge.load_overrides()
    history = []
    for rnd in range(rounds):
        write_overrides(base_ov)
        baseline = evaluate(None, runs, f"r{rnd}-baseline")
        used += sum(len(v) for v in baseline.values())
        proposal = propose(evidence_md(baseline, rows_of() if rows_of else {}))
        problems = check_changes(proposal.changes, base_ov)
        entry = {"round": rnd, "diagnosis": proposal.diagnosis, "changes": [c.model_dump() for c in proposal.changes], "problems": problems}
        if dry_run or problems:
            entry["outcome"] = "dry-run" if dry_run else "invalid proposal"
            _log(entry)
            history.append(entry)
            if dry_run:
                break
            rejected_rounds += 1
            if rejected_rounds >= 2:
                break
            continue
        # Stage A: each change alone on a few reels must raise the mean
        reels = sorted(baseline)[:STAGE_A_REELS]
        sub_base = {r: baseline[r] for r in reels}
        survivors = []
        for c in proposal.changes:
            write_overrides(with_changes(base_ov, [c]))
            cand = evaluate(reels, runs, f"r{rnd}-A-{c.id}")
            used += sum(len(v) for v in cand.values())
            gain = acceptance.decide(sub_base, cand)["mean_gain"]
            entry.setdefault("stage_a", {})[c.id] = gain
            if gain > 0:
                survivors.append(c)
        decision = {"accepted": False, "reasons": ["no change survived stage A"]}
        if survivors and used + 2 * runs * len(baseline) <= budget:
            write_overrides(with_changes(base_ov, survivors))
            cand = evaluate(None, runs, f"r{rnd}-B")
            used += sum(len(v) for v in cand.values())
            decision = acceptance.decide(baseline, cand)
            if decision["accepted"]:  # confirmation: fresh runs of both arms
                write_overrides(base_ov)
                b2 = evaluate(None, runs, f"r{rnd}-confirm-base")
                write_overrides(with_changes(base_ov, survivors))
                c2 = evaluate(None, runs, f"r{rnd}-confirm-cand")
                used += sum(len(v) for v in b2.values()) + sum(len(v) for v in c2.values())
                confirm = acceptance.decide(b2, c2)
                decision = confirm | {"stage_b": {k: decision[k] for k in ("mean_gain", "p")}}
        entry["decision"] = decision
        if decision.get("accepted"):
            base_ov = with_changes(base_ov, survivors)
            write_overrides(base_ov)
            accepted += survivors
            entry["outcome"] = "accepted"
            entry["tag"] = commit_accepted(survivors, decision) if commit else None
        else:
            write_overrides(base_ov)
            rejected_rounds += 1
            entry["outcome"] = "rejected"
        entry["reel_runs_used"] = used
        _log(entry)
        history.append(entry)
        if rejected_rounds >= 2 or len(accepted) >= 3 or used >= budget:
            break
    write_overrides(base_ov)
    return {"accepted": [c.model_dump() for c in accepted], "rounds": history, "reel_runs": used}


def harness_evaluator(caller=None):
    """Evaluate via the eval harness: fresh Editor decisions per run, stable workspaces (analysis cached)."""
    from reel.evalh import harness

    last_rows: dict[str, list[dict]] = {}

    def evaluate(reels: list[str] | None, runs: int, label: str) -> Runs:
        out: Runs = {}
        for k in range(runs):
            row = harness.run_eval("tuning", work_root=config.REPO_ROOT / "projects" / "_eval" / "improve", caller=caller,
                                   reels_filter=reels, label=f"{label}-{k}", fresh_decisions=True)
            for r in row["reels"]:
                out.setdefault(r["id"], []).append(r)
                last_rows.setdefault(r["id"], []).insert(0, r)
        return out

    return evaluate, (lambda: last_rows)
