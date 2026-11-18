# ADR-0030: Harness rules, primary score and change-acceptance rule

- **Status:** Accepted (2026-11-18). `--bare` resolved by owner: **no bare** — decision calls run on the Claude Code plan login; `--tools Read` keeps the global CLAUDE.md's tool instructions inert; the extra context is accepted.
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Amends:** ADR-0020 (decision calls), ADR-0029 (eval + self-improvement)
- **Research:** `docs/research/agent-harness-best-practices.md`, `docs/research/eval-harness-design.md`, `docs/research/self-improvement-design.md`

## 1. Decision-call rules (amends ADR-0020)
- `claude -p … --tools Read --allowedTools Read --permission-mode dontAsk` (or `--permission-prompts none`); `--allowedTools` alone only pre-approves.
- **One fresh session per decision;** state in files. `--resume <id>` only for bounded revision loops, under a per-reel lock (concurrent resumes can lose messages; oldest images are silently dropped in long sessions).
- Prompt order: persona → schema → tagged tables/contact sheets → question last. Contact sheets ≤ 2,576 px long edge. Small index in the prompt; full tables Read by path on demand.
- Failure = non-zero exit, `is_error: true`, missing structured output, `refusal` or `max_tokens` stop. Retry by resuming with actionable validator messages (field, rule, fix); cap retries; then fail the stage.
- Stop with SIGINT; set `BASH_DEFAULT_TIMEOUT_MS` (Bash is not in `--tools` anyway); `CLAUDE_CODE_RETRY_WATCHDOG=1` for unattended runs; `--max-turns` cap.
- Pin: `claude install <version>` + `DISABLE_AUTOUPDATER=1`; full model IDs (no aliases); log `session_id`, `total_cost_usd`, model ID, version per call; 1-hour prompt-cache TTL setting for revision chains.
- **Open — `--bare`:** recommended for scripts (skips global CLAUDE.md, hooks, skills, MCP, auto memory) but requires `ANTHROPIC_API_KEY`, conflicting with running on the Claude Code plan (ADR-0019). Without it, every call loads the owner's global CLAUDE.md (lean-ctx rules) — wasted context. Options: (a) API key + `--bare` for decision calls only; (b) no bare, accept the overhead; (c) a dedicated `CLAUDE_CONFIG_DIR` profile without the global CLAUDE.md (verify).

## 2. Primary score (per reel, 0–100)
P = 100 · Σ w_f·S_f / Σ w_f over the families the reel has:
- **Story** (w .40, needs a pro-edited gold final): .30·hook IoU + .35·word-keep F1 + .15·(τ+1)/2 + .20·max(0, 1 − |log₂ cut-rate ratio|); τ dropped if < 3 shared segments.
- **Captions** (w .20): .6·(1 − WER) + .4·(1 − median timing error / 150 ms).
- **Style** (w .15): per-genre robust z-score vs the reference library (median/MAD), zero inside the genre's IQR.
- **Soft gates** (w .10): pass rate of warning-level gates.
- **Reviewer** (w .15·c): c = 0 until calibrated against pro-editor labels; .5 at κ ≥ .4; 1 at κ ≥ .6.
Hard gates, false `sendable`, conformance failures and crashes are **vetoes**. Audience metrics are tracked separately, not in P.

## 3. Change-acceptance rule (unifies both research designs)
Runs: 3 per arm per tuning reel (v0 plan-level: 5). A change set is accepted only if **all** hold:
1. Stage A: each change alone on 3 reels improves the mean; Stage B: survivors combined on the full tuning set.
2. No new veto.
3. Mean paired gain ≥ δ_min = max(2 points, 2·SD(baseline-vs-baseline)/√n).
4. One-sided paired sign-flip permutation test p ≤ .10.
5. No family below tolerance (Story −2, Captions −1, Style −3, Reviewer −3, Gates 0); no reel drops > 8 points; English and Hinglish subsets each non-negative.
6. Confirmation re-run with fresh runs for both arms.
Edits: ≤ 3 single-node changes per round, ≤ 40 changed lines, delta-only (no whole-file rewrites — avoids context collapse). Night stops after 2 rejected rounds or 3 accepted changes. Budget: v1 ≤ 100 reel-runs/night, v0 ≤ 250 plan-runs/night. Decisions must cite the knowledge-node IDs they used (failure attribution). Pro editor gives blinded verdicts every 5 accepted changes. v0 acceptances must re-pass at v1.

## 4. Prerequisite
The project must be a **git repository** (versioned knowledge, one tagged commit per accepted change, rollback).

## Consequences
- **Good:** reliable headless calls; improvements counted only when real.
- **Bad:** with 6–10 tuning reels only large, consistent gains register; eval nights consume Claude Code usage.
- **Notes:** Timeline-Bench details in the eval design come from a secondary summary; "OmniEdit-Bench" (cited earlier as arXiv 2608.05049) could not be re-found by a second agent — treat as unverified.
