# Build step 11 — Gold-set scoring, self-improvement loop, release candidate

_Plan date: 2026-11-18 · Implements: ADR-0014 (gold set), ADR-0021 (acceptance: 6 held-out, ≥ 5/6 sendable), ADR-0029 (eval + self-improvement), ADR-0030 §2–3 (primary score, change-acceptance rule). Owner decision: build the scorer + loop now; tuning starts when gold pairs arrive._

## Status: 11a + 11b implemented 2026-11-18 — 11c (tuning, release candidate, holdout) waits for the gold set

### 11a Gold scorer (`evalh/gold.py`, `reel eval`)
- `reel eval` runs the **full edit** (fix loop included, as in real use) on every reel of the split and scores it against the owner's `final.mp4`.
- **Gold side:** the final is transcribed and aligned back to the raw word table.
  - Alignment uses greedy longest-common-run matching on script-agnostic keys, so re-ordered lines and repeated takes are found.
  - The first version used order-preserving matching and missed re-ordered openings.
  - This gives the kept words, their order, and the hook (words in the first 3 s). Cut rate comes from scene detection on both sides.
- **Families (ADR-0030):**
  - Story: hook IoU on the same 3 s definition both sides, kept-word F1, segment-order τ, cut-rate ratio.
  - Captions: our caption text vs ASR of our own render, plus onset error.
  - Soft gates: warn-gate pass rate.
  - Reviewer: weighted by the calibrated κ (0 until `reel calibrate` shows κ ≥ .4).
  - Vetoes: blocking gates, crashes.
- **Self-gold test:** our own render is used as the "owner's final", then the full edit is re-run and scored. Result: no vetoes, word F1 > .9, high primary. This proves the alignment → scoring chain end to end.
- Gold folders: `samples/gold/<name>/{raw/, final.mp4, brief.json?}`. `reel eval --init` writes the manifest; the owner marks 6 reels (≥ 2 Hinglish) `split: holdout`.

### 11b Self-improvement loop v1 (`improve.py`, `reel improve`)
**What a change can touch:** only knowledge, as deltas in `knowledge/learned/overrides.yaml` (edit `summary`/`when_to_use`/`avoid_when`/`parameters`/`core` of one node, or add a technique/anti-pattern). Applied on load, never written into the generated graph, so `build_kb.py` can't erase what was learned. Stage hashes include the overrides, so a delta really re-runs the Editor.

**Round:**
1. Baseline: R runs per tuning reel, with fresh Editor decisions per run (stage cache bypassed) so decision variance is measured.
2. The Improver (Claude, persona `improver.md`) reads the evidence: families, story detail, Reviewer issues, cited node ids. It proposes ≤ 3 single-node changes, ≤ 40 lines.
3. Stage A: each change alone on 3 reels must raise the mean.
4. Stage B: survivors together on the full tuning set must pass the **acceptance rule** (`evalh/acceptance.py`):
   - no new veto;
   - mean paired gain ≥ δ_min = max(2, 2·SD(base-vs-base)/√n);
   - one-sided paired sign-flip permutation p ≤ .10;
   - family tolerances: story −2, captions −1, style −3, reviewer −3, gates 0;
   - no reel drops > 8;
   - English and Hinglish subsets each ≥ 0.
5. Fresh confirmation runs of both arms.
6. Accepted → git commit of the overrides file + tag `learned/<time>`. Rejected → reverted.

**Limits:** stops after 2 rejected rounds, 3 accepted changes, or the reel-run budget (default 100). The holdout is never touched (the harness refuses it). `--dry-run` shows the proposal only.

Tests: the statistics (permutation p, δ_min, every rejection reason), overrides (edit/add, validation), and a full night with a fake evaluator (good edit accepted, useless one dies in stage A, 2 rejected rounds stop the night, rejected deltas reverted).

**Not implemented:** loop v0 (plan-level, no render). v1 subsumes it once gold data exists. The style family needs the per-genre reference library (from `--reference` profiles of gold finals); it is absent until then and the primary score re-normalises.

### 11c Release (needs owner data)
1. Gold set: ≥ 12 pairs in `samples/gold/`, 6 marked holdout (≥ 2 Hinglish).
2. Hinglish bake-off (`reel bakeoff`) → set `config.ASR_ENGINES`.
3. `reel eval` baseline on the tuning set.
4. A few renders labelled (`reel label`), then `reel calibrate` → promote gates / trust the Reviewer.
5. `reel improve` nights.
6. Tag a release candidate → `reel eval --set holdout --holdout` → the owner (and the hired pro editor, ADR-0028) judges each held-out reel on its own. **Pass = ≥ 5 of 6 sendable and no false `sendable`.**

**Cost note:** a reel-run is ~4–6 Claude calls (story ×2, finish, review, fix loops) ≈ $0.4–1 API-equivalent on the plan. A night at the default budget is ~100 reel-runs.
