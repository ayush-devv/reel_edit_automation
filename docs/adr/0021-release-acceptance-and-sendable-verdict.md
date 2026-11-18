# ADR-0021: Release acceptance test, sendable/hold verdict, caption proof

- **Status:** Accepted (owner decisions, 2026-11-18, council re-review issues #1–3) · Amended by ADR-0028 (judge = hired pro editor, not the owner)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Amends:** ADR-0014 (gold-set evaluation), ADR-0018 (autonomous exit test)

## Context
"≥ 70% of 3 held-out reels" meant 3/3; the owner recognises his own cut so A/B isn't blind; scoring the holdout every build burns it. Autonomous mode had no way to say a reel is NOT sendable, and nothing checked caption words (proper nouns came back < 0.5 confidence; Hinglish WER unknown; baked-in captions can't be fixed in the NLE package).

## Decision
1. **Gold set split:** tuning set (scored every build with automatic metrics: hook match, word-keep F1, order τ, cut-rate ratio, caption timing error, caption word accuracy) and a **holdout of 6 reels, ≥ 2 Hinglish**, used only at release candidates.
2. **Release acceptance:**
   - Owner judges each holdout tool reel **on its own** (not side-by-side with his cut): "sendable with no edits" yes/no. **Pass = ≥ 5 of 6.**
   - **Verdict precision:** every reel the tool marks `sendable` must be judged sendable; any false `sendable` fails the release.
   - Conformance corpus passes (frame count, sync, orientation, colour); captions in sync and word-accurate on English and Hinglish holdout clips; headless smoke run with 0 permission prompts.
3. **Verdict per run:** `sendable` or `hold(reasons)`. `hold` when any blocking gate fails after the bounded fix loop (max 3), when the Reviewer flags an unresolved issue, or when caption words remain uncertain.
4. **Caption proof:** low-confidence words are auto-corrected only against vocabulary from the brief, brand kit and on-screen OCR; any remaining word below threshold or outside that vocabulary triggers `hold` with a **timecoded proof list**. The owner confirms/corrects (~30 s) and the overlay re-renders. Hinglish word timing is pass/fail in the ASR bake-off, with phrase-level captions as the fallback.
5. **Reviewer calibration:** before trusting the auto-fix loop, measure the Reviewer against the owner's labels on the tool's own rough renders (not synthetic defects).

## Consequences
- **Good:** release gate measures what matters; autonomy is safe because the tool knows when to stop.
- **Bad:** a `hold` is a (short) manual step; needs ≥ 6 extra gold reels held out.
