# ADR-0034: Release judgement by an independent pro editor (separate from the gold-set editor)

- **Status:** Accepted (owner decision, 2026-11-19)
- **Date:** 2026-11-19
- **Deciders:** project owner
- **Amends:** ADR-0028 (who judges release), ADR-0021 (acceptance test)

## Context
ADR-0028 made a hired pro editor the release judge because the owner is not an editor. Two later decisions added work for a professional editor:
- ADR-0031: edit 3–4 Hinglish raw clips into gold finals for the holdout;
- ADR-0033: rate about 6 of our tuning reels for calibration (κ).

If one person did both, they would judge our Hinglish reels against their own edit of the same footage, and their style preference would bias the release check.

## Decision
1. **Editor 1 (gold editor):** edits the 3–4 owner-recorded Hinglish raw clips into finished reels from a short brief. These become Hinglish holdout gold (ADR-0031).
2. **Editor 2 (independent judge), a different person:**
   - **Calibration:** rates about 6 tuning reels made by the tool (ADR-0033).
   - **Release check:** rates each of the **6 held-out reels** made by the tool.
   - Every rating answers one question: *"Is this sendable to a paying client with no edits?"*, yes or no, with a one-line reason and the timecode of any defect.
   - Each reel is rated **on its own**: never side by side with a gold final, and **blind** to the tool's `sendable` / `hold` verdict.
3. **Pass:** at least **5 of 6** held-out reels rated sendable, **and** no reel the tool marked `sendable` rated not sendable (no false `sendable`). The audience check (ADR-0028 §2) stays directional, not a gate.
4. **Hiring:** short paid test jobs on Fiverr or Upwork with a portfolio of short-form talking-head reels. The judge must read Hindi/Hinglish (two held-out reels are Hinglish). **Rates must be checked before hiring**; this ADR quotes no cost.
5. The judge's reasons feed the improvement loop (ADR-0027/0029) as labelled examples, **except** holdout reels, which are never used for tuning.

## Options considered
| Option | Independence | Cost | Logistics |
|---|---|---|---|
| **Two editors (chosen)** | full | two hires | more coordination |
| One editor, judging before making gold | partial (they still know the material) | one hire | simple |

## Consequences
- **Good:**
  - the release verdict cannot be biased by the judge's own edits;
  - blind, standalone rating matches how a client sees a reel;
  - calibration and release use the same judge, so κ applies directly.
- **Bad:**
  - two hires and coordination;
  - a single judge is still one person's taste (the audience check is the counterweight);
  - a Hinglish-capable judge narrows the hiring pool.
- **Prerequisites before the release check can run:** holdout complete (ADR-0031: 6 reels, at least 2 Hinglish); the release-check guard in `reel eval` refuses until then.
