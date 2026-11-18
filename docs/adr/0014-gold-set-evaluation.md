# ADR-0014: Gold-set evaluation is the quality instrument and the exit test

- **Status:** Accepted (owner has raw→delivered pairs, 2026-11-18) · Amended by ADR-0021 · Amended by ADR-0028 (owner is not an editor; pro editor + audience judge)
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
Council issue #1 (raised by 4 of 5 reviewers): every exit test was a proxy (gates pass, style vector ±20%), so the system would converge on "correct but generic" — the top risk — undetected. Plans are ID-based, so they can be diffed against a reference plan cheaply.

## Decision
1. **Gold set:** 10–15 pairs in `samples/gold/<name>/` — `raw/` (original footage), `final.mp4` (owner's delivered edit), optional `brief.md`. Held out: 3 pairs never used for prompt tuning.
2. **Gold plan:** align each final cut to the raw transcript (word IDs) automatically → `gold_plan.json`.
3. **Metrics per reel:** hook segment match; word-keep F1; segment order (Kendall τ); cut-rate ratio; caption timing error; editor-minutes to finish in the NLE.
4. **Primary metric:** owner's **blind A/B** (tool cut vs own cut, randomised order) + "sendable with no edits" yes/no (ADR-0018).
5. Every prompt, playbook or model change is scored on the gold set before adoption; results logged per build.
6. The release acceptance test uses these metrics, not proxies.

## Consequences
- **Good:** measures taste directly; cheap thanks to ID-based plans.
- **Bad:** depends on the owner's time for blind A/B; small sample (treat as directional).
- **Revisit when:** client acceptance data exists → add it as the top metric.
