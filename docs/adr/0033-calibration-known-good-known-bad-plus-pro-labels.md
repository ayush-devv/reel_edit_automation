# ADR-0033: Calibration — automatic known-good / known-bad now, pro-editor labels at release

- **Status:** Accepted (owner decision, 2026-11-19)
- **Date:** 2026-11-19
- **Deciders:** project owner
- **Amends:** ADR-0021 §5 (Reviewer calibrated on owner labels), ADR-0017 (gates warn until calibrated), ADR-0030 (Reviewer weight by κ)

## Context
The Reviewer and the measured quality checks start untrusted. The Reviewer can hold a reel but does not drive automatic fixes, and the gates only warn until their false-alarm rate is known. The plan was owner labels via `reel label`. The owner prefers not to label by hand and is not an editor. The first real-footage run showed why calibration matters: the Reviewer called professional 1–3-word caption pages "flashing too fast", while the channel's own pro Short uses exactly that style. Its taste can disagree with real pros.

## Decision
1. **Now, automatic, no owner effort:**
   - **Known-good:** run the Reviewer and the gates on the **6 professional finals** of the gold set (ADR-0031). Every hold or failed gate there is a **false alarm**.
   - **Known-bad:** run them on copies of our renders with **injected defects**, one per copy: captions over the face, captions outside the safe zone, near-invisible caption contrast, a black or frozen stretch, a cut mid-word, a buried hook, loudness off target. Every pass there is a **miss**.
   - `reel calibrate` reports, per gate and for the Reviewer, the false-alarm rate on known-good and the miss rate on known-bad.
   - **Promotion rule:**
     - a gate is promoted from warn to block when its false-alarm rate is 0 of 6 and it catches its own defect type in at least 9 of 10 cases;
     - the Reviewer's issue categories with false alarms on pro finals become prompt and knowledge fixes, through the improvement loop and only if it measurably helps.
2. **At release:** the hired pro editor (ADR-0034) also rates about 6 of our tuning reels "sendable to a paying client with no edits".
   - That gives the expert agreement κ that ADR-0030 needs.
   - The Reviewer may drive automatic fixes (`REVIEWER_TRUSTED`) only when κ ≥ 0.4 **and** it has no false `sendable` on those reels.
3. **Optional:** the owner's own "would I post this?" labels are recorded as the *client's view* (ADR-0028). They are reported but never required.

## Options considered
| Option | Owner effort | Measures | When |
|---|---|---|---|
| **B now + pro labels at release (chosen)** | none | false alarms on pro work, misses on known defects, expert agreement on our output | today + release |
| B only | none | no expert check of our real output | today |
| Owner labels | ~15 min | client taste, not editing expertise | anytime |

## Consequences
- **Good:**
  - calibration starts today;
  - it directly measures the observed problem (the Reviewer disagreeing with pros);
  - promotion is objective.
- **Bad:**
  - injected defects are cleaner than real-world defects, so miss rates may look better than reality;
  - the 6 pro finals are one genre (podcast);
  - expert κ waits for the hired editor.
- **Implementation:** add pro-final review mode and a defect injector to `reel calibrate` (small; reuses `verdict.run` and the renderer).
