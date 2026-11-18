"""Headless Claude Code decision calls (ADR-0019, ADR-0020, ADR-0030).

Rules applied to every call:
- `--tools Read` (+ `--allowedTools Read`, `--permission-mode dontAsk`): Claude can only read workspace files.
- Stripped context: `--safe-mode` (no CLAUDE.md files, hooks, skills, plugins, MCP; auth and
  built-in tools still work) plus no MCP servers, project settings only, no slash commands,
  dynamic system-prompt sections moved out. Measured 2026-11-18: without `--safe-mode` the
  owner's user-level CLAUDE.md leaked into calls; with it ~1k context tokens of overhead.
- Structured output via `--json-schema`; failure = non-zero exit, `is_error`, missing
  `structured_output`, or refusal / max-tokens stop.
- Pinned model id; every call logged (session id, cost estimate, usage, version) to log/runs.jsonl.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
STRIPPED = ["--strict-mcp-config", "--mcp-config", json.dumps({"mcpServers": {}}), "--setting-sources", "project",
            "--exclude-dynamic-system-prompt-sections", "--disable-slash-commands", "--safe-mode"]


class ClaudeCallError(RuntimeError):
    pass


@dataclass
class CallResult:
    data: dict
    session_id: str | None
    num_turns: int | None
    cost_usd: float | None
    usage: dict
    duration_s: float


@lru_cache(maxsize=1)
def claude_version() -> str:
    exe = shutil.which("claude")
    if not exe:
        raise ClaudeCallError("Claude Code CLI `claude` not found on PATH.")
    return subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()


def _previous_cumulative(log_file: Path | None, session_id: str) -> float:
    """`total_cost_usd` is cumulative over a resumed session; find the session's last total."""
    if not log_file or not log_file.exists():
        return 0.0
    last = 0.0
    for line in log_file.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("session_id") == session_id:
            last = e.get("cost_cum_usd", e.get("cost_usd")) or last
    return float(last)


def call(prompt: str, schema: dict, *, cwd: Path, persona_file: Path | None = None, model: str = DEFAULT_MODEL,
         effort: str = "high", resume: str | None = None, log_file: Path | None = None, label: str = "",
         timeout_s: int = 1800, meta: dict | None = None) -> CallResult:
    exe = shutil.which("claude")
    if not exe:
        raise ClaudeCallError("Claude Code CLI `claude` not found on PATH.")
    cmd = [exe, "-p", prompt, "--output-format", "json", "--json-schema", json.dumps(schema),
           "--tools", "Read", "--allowedTools", "Read", "--permission-mode", "dontAsk",
           "--model", model, "--effort", effort, *STRIPPED]
    if persona_file:
        cmd += ["--append-system-prompt-file", str(persona_file)]
    if resume:
        cmd += ["--resume", resume]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCallError(f"{label}: Claude call timed out after {timeout_s}s") from exc
    dur = round(time.time() - t0, 1)
    try:
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        out = {}
    cum = out.get("total_cost_usd")
    prev = _previous_cumulative(log_file, resume) if resume else 0.0
    cost = round(cum - prev, 6) if cum is not None else None
    entry = {"time": time.time(), "label": label, "exit": proc.returncode, "duration_s": dur, "model": model, "effort": effort,
             "session_id": out.get("session_id"), "cost_usd": cost, "cost_cum_usd": cum, "usage": out.get("usage"),
             "num_turns": out.get("num_turns"), "stop_reason": out.get("stop_reason"), "is_error": out.get("is_error"),
             "permission_denials": out.get("permission_denials"), "resume": resume, "claude": claude_version(), **(meta or {})}
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    if proc.returncode != 0 or out.get("is_error"):
        raise ClaudeCallError(f"{label}: Claude call failed (exit {proc.returncode}): {(out.get('result') or proc.stderr)[-600:]}")
    if out.get("stop_reason") in ("refusal", "max_tokens"):
        raise ClaudeCallError(f"{label}: stopped with {out.get('stop_reason')}")
    if out.get("permission_denials"):
        raise ClaudeCallError(f"{label}: permission denials (headless runs must have none): {out['permission_denials']}")
    data = out.get("structured_output")
    if not isinstance(data, dict):
        raise ClaudeCallError(f"{label}: no structured_output in the response")
    return CallResult(data=data, session_id=out.get("session_id"), num_turns=out.get("num_turns"), cost_usd=cost,
                      usage=out.get("usage") or {}, duration_s=dur)
