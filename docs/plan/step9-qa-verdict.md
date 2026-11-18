# Build step 9 — QA gates, Reviewer, fix loop, sendable/hold verdict (CP5)

_Plan date: 2026-11-18 · Implements: ADR-0006 (QA), ADR-0017 (gates measured on the render, warn until calibrated), ADR-0021 (verdict, caption proof, Reviewer calibration), ADR-0030 (fresh-context decision calls)._

## Status: implemented 2026-11-18 (CP5 engine-complete; calibration needs owner labels)
- `reel run` now ends with gates → fresh-context Reviewer (~$0.10/check) → `qa/verdict.md` (`sendable` / `hold(reasons)`) and runs the bounded fix loop (≤ 3). New commands: `reel proof`, `reel label`, `reel calibrate`.
- **Live on the `_speech` demo the verdict is `hold` — correctly:** the Reviewer saw the footage is a colour-bar test pattern with no speaker ("no edit can fix this") and that 8.9 s misses the brief's 15 s minimum.
- **Defects the Reviewer found that are now fixed in the engine:**
  1. The Editor wrote `stroke: "#000000"` but the overlay only understood `"true"`, so the outline was **silently dropped** (gate measured 1.5:1, Reviewer: words vanish). The overlay and gate now accept a colour, and **the validator enforces a value contract for every caption token** so an unrecognised value goes back to the Editor instead of becoming a silent no-op.
  2. One-word orphan caption page ("it.").
  3. Pages broke mid-phrase ("simple trick to / save money."). Paging is now a small DP: free breaks after punctuation, cheap at pauses, expensive after English function words / before Hindi postpositions → "Today I / will show you / one simple trick / to save money.".
  4. Hook title spoiled the payoff → finish persona: titles build curiosity, never give the answer, keep clear of burned-in text.
- My own test edit (a hand-changed hook title from the step-7 runner check) was in the plan during the first review — restored before the final run.
- **Open calibration questions** (owner labels decide): outlined text on a same-colour background passes the contrast gate (stroke counts) but the Reviewer still found it hard to read; punch-ins push text burned into the footage toward the edge (candidate gate: OCR text zones vs safe zone after zoom).
- Also fixed: an edit had deleted several CLI commands; restored, plus a test that every command stays registered.
- Tests: **124 passed, 1 skipped**.

## Design
**Gates** (`qa.py`, on the encoded render + overlay alpha + timeline). Each has a mode in `config.QA_GATES`: `block` or `warn`.
| gate | how | starts as |
|---|---|---|
| frame_count | final frames = timeline | block |
| loudness | −14 ± 1 LUFS, ≤ −1.5 dBTP on the final file | block |
| proof_words | unconfirmed unsure caption words (`qa/proof_list.json` minus owner confirmations) | block → `hold` |
| brief | must-keep lines kept, banned claims absent, CTA present (fuzzy on kept text) | block |
| dead_air | gap between kept words > 1.5 s on the output timeline | warn |
| frozen / black | ffmpeg `freezedetect` (> 3 s) / `blackdetect` (outside dip-to-black windows) | warn |
| caption_contrast | WCAG ratio of caption fill vs the base pixels behind it (box / stroke count) ≥ 4.5 | warn |
| caption_over_face | overlay alpha inside the face box at caption frames | warn |
| safe_zone | overlay pixels outside the platform safe zone (flash frames excluded) | warn |
| reading_speed | ≤ 20 characters/s per caption page | warn |
| face_cut | face box (after punch-in) leaves the frame | warn |

**Reviewer** (fresh Claude Code session, persona `reviewer.md`, Read-only). It reads the read-back, the brief, the plan's stated intents, the QA report and **contact sheets of the final render**, and returns issues with severity, timecode, category and a concrete fix instruction.

**Fix loop** (`autofix.py`, ≤ 3 loops):
- Fixable blocking gate failures (brief) are sent to the Editor's finish session as one revision request; the pipeline re-runs from compile.
- Trusted-Reviewer issues are sent the same way.
- Engine-side failures (loudness, frame count) are not sent to Claude; they mean `hold`.

**Verdict** (`qa/verdict.json` + `qa/verdict.md`):
- `sendable` only if no blocking gate fails, there are no unconfirmed proof words, and the Reviewer reports no blocker or major issue.
- Otherwise `hold(reasons)`, with the timecoded proof list.
- Warnings are listed but never block until the gate has been calibrated.

**Proof confirmations:** `reel proof --project P --ok 7 --fix 9=DearMa` records owner decisions in `qa/proof_confirmed.json`. Fixes change the caption text, and the run re-renders the overlay only.

**Calibration** (ADR-0021 §5):
- `reel label --project P --sendable yes|no [--note …]` stores the owner's judgement.
- `reel calibrate` reports, across labelled projects:
  - Reviewer agreement (accuracy, Cohen's κ, false `sendable` count);
  - each gate's false-positive rate on owner-sendable renders.
- A gate is promoted to `block` / the Reviewer marked trusted only by the owner editing `config.QA_GATES` / `REVIEWER_TRUSTED` after reading that report.

## Done when
1. `reel run` on `_speech` ends with `qa/verdict.json`. It's `hold`, because the demo has an unconfirmed proof word, `Dioma→DearMa`. After `reel proof --fix`, it re-renders the overlay only and turns `sendable` if nothing else blocks.
2. Gate unit tests on synthetic inputs: contrast pass/fail, caption over face, dead air, reading speed, brief compliance. Integration: freeze/black detection on a synthetic render.
3. The fix loop with a fake Claude: a failing brief gate → revision → passes → `sendable`; an unfixable failure → `hold` after ≤ 3 loops.
4. `reel label` / `reel calibrate` compute agreement and gate FP rates on fixture labels.
5. Tests green.
