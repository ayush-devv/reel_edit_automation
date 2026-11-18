# ADR-0002: Claude writes an intent plan; a compiler produces the exact timeline

- **Status:** Accepted (2026-11-18) · Amended by ADR-0016
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
LLMs guess timestamps poorly (±0.5–1 s from sparse samples). Whisper-family word edges drift. social-video-agent solves this with `edit-plan.json` (intent) → `compile` → `edl.json` (exact), snapping cut edges to heard speech. LAVE and VideoAgent use stable clip IDs. Benchmark showed frame-count drift (1802 vs 1800) when durations are not frame-aligned.

## Options considered
| Criterion | A. Intent plan (IDs) → compiler → timeline | B. Claude writes the final timeline directly |
|---|---|---|
| Cut precision | Compiler snaps to word edges + speech onset (RMS) and frame grid | Limited to Claude's estimates |
| Validation | Two layers (plan schema + timeline schema) | One |
| Chat revisions | Patch the plan; recompile | Patch timeline numbers by hand |
| Complexity | Extra compiler module | Simpler |

## Decision
We propose **A**. Claude references `seg_id`, word indices and asset IDs, each with a reason. The compiler converts to integer frames, snaps edges to speech, aligns durations to whole frames, expands rules (ducking, SFX peak alignment), and emits `timeline.json`.

## Consequences
- **Good:** frame-accurate, explainable (every clip keeps `src:{segment, words}`), small diffs on revision.
- **Bad:** two schemas to maintain; compiler is a critical component.
- **Revisit when:** Claude reliably produces frame-accurate times from tables alone (measure).

## Challenges raised
- Speed ramps: planned in intent, rendered in ffmpeg (see ADR-0004 open point).
