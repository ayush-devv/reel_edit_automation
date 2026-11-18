# ADR-0016: Selects stage + two-pass plan + patch format + quote check

- **Status:** Accepted (2026-11-18, council issues #3, #10, #11)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Amends:** ADR-0002 (plan shape), ADR-0005 (tool ownership)

## Context
Claude cannot hear performance; nothing grouped retakes or described delivery; the plan was one big structured output; revisions had no patch format; a 30-rule playbook with density quotas would push over-editing.

## Decision
1. **S2.5 Selects (code):** detect repeated/near-duplicate lines across takes; flag restarts, stumbles, fillers; per-take delivery stats (speech rate, pitch range, loudness, disfluencies, ASR confidence, eyeline/face-on-camera). Output a readable **script with inline `[seg]` tags** + a take table. Word indices served on demand by a tool.
2. **Plan pass 1 — Story (Opus 5.5, effort high):** choose takes, hook (2–3 options ranked), kept ranges and order. Tool `dry_run_compile` returns a read-back script with durations and cut rate so Claude sees the result before committing. Claude picks the top-ranked hook (autonomous mode, ADR-0018); the alternatives are kept in the plan so a chat revision can swap them.
3. **Plan pass 2 — Finish (effort medium):** emphasis, punch-ins, b-roll, SFX, captions on the locked story.
4. **Stable item IDs;** revisions are `insert / replace / delete` ops by item ID, so "rest unchanged" holds by construction.
5. **Quote check:** every kept range quotes its first and last word; the validator rejects mismatches with a correction message (catches off-by-N word IDs).
6. **Playbook split:** mechanical rules (silence thresholds, fades, CPS, loudness, SFX timing) move to the compiler/gates. Claude gets ~8 judgment principles in Murch order (emotion → story → rhythm; hook/payoff; cut restatements; performance over rhythm; b-roll on proof) + 2–3 annotated gold-set edits as examples. Density targets become post-plan feedback ("31 cuts/min vs your usual 22"), not goals.
7. **Tool ownership:** Editor tools are read-only + `dry_run_compile`; the orchestrator owns compile, render and QA; code-gate failures never go to Claude unless they need an editorial choice.

## Consequences
- **Good:** story judgment gets the inputs it needs; revisions are safe; less over-editing.
- **Bad:** more perception work (take grouping, prosody stats); two Claude calls per draft.
