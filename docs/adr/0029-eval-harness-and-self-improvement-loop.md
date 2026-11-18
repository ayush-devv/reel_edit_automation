# ADR-0029: Eval harness + gated self-improvement loop

- **Status:** Accepted (2026-11-18) · Amended by ADR-0030
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Details:** ADR-0027 step 5 (learning loop), ADR-0014/0021/0028 (evaluation)

## Context
"Self-improving" needs an objective exam; without it, changes are guesses. Self-improving systems fail by gaming metrics, overfitting the tuning set, self-grading, silent regressions and runaway cost.

## Decision
**Three harnesses:**
1. **Agent harness** — `reel run` + headless Claude Code decision calls (ADR-0020). Unchanged.
2. **Eval harness** — `reel eval --set tuning|holdout`: runs the full pipeline headless per reel; scores QA gates, style match to the genre's pro reference library, Claude Reviewer rubric (advisory), gold metrics where a pro-edited final exists (hook match, word-keep F1, order τ, cut-rate ratio, caption accuracy/timing); writes `eval/scoreboard.jsonl` keyed by git commit + knowledge version + Claude Code version + model ID.
3. **Self-improvement loop** — `reel improve`:
   1. Eval on the tuning set.
   2. Diagnose: a Claude Code call reads failures (pro-editor notes, QA fails, low-scoring reels, audience results).
   3. Propose ≤ 3 small changes on a git branch — **only** `knowledge/` (rules, parameter ranges, priorities, anti-patterns), persona/prompt files, caption/style tokens, compiler parameters.
   4. Gate: re-eval; keep only if the primary score improves, no metric regresses beyond tolerance, and no hard gate newly fails; otherwise revert.
   5. Log to `eval/experiments.md` (change, reason, before/after scores).

**Guardrails**
- Primary score is a weighted set (gates pass rate, style match, Reviewer rubric, gold metrics) — never one number.
- **Holdout (6 reels) is never used in the loop**; only at release (ADR-0021/0028).
- Pro editor reviews a sample every N accepted changes to catch metric drift; their notes outrank automatic scores.
- **No code changes by the loop** — code edits need the owner's review; all changes in git with rollback.
- Budget per loop (reels × Claude calls) and scheduled runs (e.g. overnight) to respect Claude Code usage limits.

**Timing (revised 2026-11-18 at the owner's challenge):**
- Eval harness: built in build step 1.
- **Loop v0 — plan-level, text only:** enabled as soon as perception + selects exist (build step 4). Claude's story plan (takes, hook, kept words, order) is scored against plans aligned from pro-edited gold finals — no rendering needed. Improves story knowledge and prompts early.
- **Loop v1 — full:** enabled after CP1 (walking skeleton), scoring rendered reels (captions, audio, colour, motion, verdict).
- Design details: `docs/research/eval-harness-design.md`, `docs/research/self-improvement-design.md`.

## Consequences
- **Good:** measurable, compounding improvement; every change explained and reversible.
- **Bad:** eval runs consume Claude Code usage and time (full pipeline per reel); loop quality is bounded by metric quality — hence pro-editor sampling.
