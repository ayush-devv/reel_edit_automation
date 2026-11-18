# ADR-0006: Deterministic QA is the gate; Claude-as-judge is advisory

- **Status:** Accepted (2026-11-18) · Amended by ADR-0017
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
Agents over-claim success (Timeline-Bench reports 93% self-claimed success; per-edit VLM-judge agreement with humans is low, κ≈0.15 — figures from one agent's reading, pacing claims from the same paper are UNVERIFIED). OmniEdit-Bench gates scores on instruction accuracy. The sample reel clipped at +0.6 dBFS — a check would have caught it.

## Decision
- **Gate (code):** dead air > 1.5 s, frozen > 3 s, black frames, face cut by frame edge, characters/second, loudness −14 LUFS / ≤ −1 dBTP, A/V sync ≤ 20 ms, frame count = plan, OCR of captions = transcript.
- **Configurable warning (code):** text outside the platform safe zone (secondhand ad-template numbers; intentional placements allowed).
- **Advisory (Claude Reviewer):** local yes/no questions on contact sheets (3 passes, majority); pairwise "is vN better than vN-1"; editorial rubric for tracking only.
- **Instruction check:** timeline diff assertions per request type + accuracy-gated score.

## Consequences
- **Good:** objective, cheap, catches real defects.
- **Bad:** code checks cannot judge story or taste.
- **Revisit when:** Claude-judge agreement with human labels on our own reels exceeds an agreed threshold (measure in Experiment 1).
