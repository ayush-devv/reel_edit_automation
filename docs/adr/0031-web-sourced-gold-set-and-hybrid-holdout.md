# ADR-0031: Web-sourced gold set; all current pairs tune, holdout filled later (hybrid)

- **Status:** Accepted (owner decision, 2026-11-19)
- **Date:** 2026-11-19
- **Deciders:** project owner
- **Amends:** ADR-0014 (gold set), ADR-0021 (split sizes), ADR-0028 (where gold finals come from)

## Context
- **The owner has no edited reels.** He isn't an editor, so ADR-0028's plan (owner footage, hired editor's finals) had produced nothing yet.
- **The gold set was built from the web** (`tools/goldset`). Each pair is an official YouTube Short (a professional edit) plus the 2–4 minute stretch of the full episode it was cut from. Every pair is **verified**: at least 60 % of the Short's words must be found in the downloaded raw window.
- **Result on 2026-11-19: 6 verified English pairs** (Diary of a CEO ×4, Huberman Lab ×2; 76–100 % word overlap) and **0 Hinglish**:
  - YouTube's caption endpoint throttled us for hours;
  - most Hindi creators' Shorts are standalone (vlogs, quizzes, music edits), not cut from episodes;
  - two apparent Raj Shamani matches were Whisper hallucinating music as repeated words. Verification rejected them, and the matcher now drops hallucinated repeats.
- ADR-0021 asks for at least 12 pairs with 6 held out (at least 2 Hinglish). The holdout is never used for tuning, so any pair placed there is lost for improvement. The acceptance rule's sign-flip test needs n ≥ 5 to reach p ≤ .10 with any slack (n = 6 → minimum p = 1/64).

## Decision
1. **All 6 current pairs are `tuning`.** They are used for `reel eval` baselines and `reel improve`. The style library (pacing, caption density, look) comes from their pro finals.
2. **The holdout is filled later by a hybrid route** and frozen once it reaches **6 reels including at least 2 Hinglish**:
   - **English:** more web pairs. `tools/goldset` retries when YouTube's caption endpoint stops throttling. New pairs default to holdout until it is full, then go to tuning.
   - **Hinglish:** made to order. The owner (or friends or clients, with permission) records 3–4 raw Hinglish talking-head clips, and the **hired pro editor from ADR-0028 / ADR-0034 edits them** (about $15–40 per reel; verify current rates).
3. **The release check stays locked** (`reel eval --set holdout --holdout` refuses to run) until the holdout is complete.
4. **Web-sourced media stays local.** It lives in the gitignored `samples/`, is used for internal evaluation only, and is never redistributed. `source.json` records each pair's URLs and licence note.

## Options considered
| Option | Tuning signal | Unbiased check now | Hinglish |
|---|---|---|---|
| **A (chosen):** 6 → tuning, hybrid holdout later | best (n = 6) | none; release blocked until holdout exists | via the hired editor |
| B: 4 tuning / 2 holdout now | weak (n = 4: p ≥ 1/16, passes only if every reel improves) | 2 English, which cannot meet the Hinglish rule | same gap |
| C: wait for 12 before any tuning | none until then | none | same gap |

## Consequences
- **Good:**
  - tuning starts now on real professional edits;
  - no pair is wasted;
  - the Hinglish holdout will be true raw + pro edit of exactly our task (talking head to reel), not a proxy.
- **Bad:**
  - no unbiased quality number until the holdout exists;
  - the gold set is podcast-heavy (one genre, English only), so tuning can overfit to podcast style;
  - web pairs' "raw" is an already-edited multi-camera episode, cleaner than a client's phone footage;
  - Hinglish depends on money and the owner's time.
- **Revisit when:** a public Hinglish raw + pro-edit source appears, or YouTube unblocks and English pairs exceed 12.

## Challenges raised
- *"Podcast Shorts aren't client reels."* True for raw quality. They are, however, real pro decisions on hook, line selection, captions and pacing, which is what the story and style scores measure. The made-to-order Hinglish pairs add true raw footage.
- *"Tuning on 6 reels overfits."* The acceptance rule's confirmation re-runs and tolerances limit this. The holdout is the real guard, and that is why release stays locked without it.
