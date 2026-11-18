# Eval harness design (`reel eval`, `reel improve`)

Research draft, 2026-11-18. Implements ADR-0014/0021/0028/0029.

## 1. Principles
- **Reel is the unit.** Epochs (repeat runs) are averaged per reel, so n = number of reels [3].
- **Grader order:** deterministic checks first, then the LLM judge, then human labels to calibrate it [1][2].
- **Frozen judge.** Eval code, the rubric snapshot, the style library and `gold_plan.json` live in `eval/frozen/`, which the loop cannot write to.
  - Scores log the folder's hash `judge_hash`, and scores with different hashes are never compared.
  - Otherwise the loop could rewrite its own grader: it edits `knowledge/` (ADR-0029), which generates the rubric (ADR-0028).
- **Concurrent baseline.** Both arms run in one session on the same served model and Claude Code version.

## 2. Metrics (per reel, each scored on [0,1])

| | Metric | Computation | Score |
|---|---|---|---|
| H | Hook match | IoU of line-class word sets (§6) in the first 3 s, tool vs gold | IoU |
| F | Word-keep F1 | K = tool word set, G = gold word set (line classes). p = \|K∩G\|/\|K\|, r = \|K∩G\|/\|G\| | 2pr/(p+r) |
| τ | Order | Kendall τ-b over line classes both cuts kept. Dropped if fewer than 3 are shared | (τ+1)/2 |
| C | Cut-rate ratio | r = tool cuts/min ÷ gold cuts/min, with the same shot detector run on both renders | max(0, 1−\|log₂r\|) |
| W | Caption words | WER (jiwer) of caption text vs a verified transcript of the kept speech. Omitted words count as deletions. Hinglish is converted to a canonical romanization; CER is logged too | max(0, 1−WER) |
| T | Caption timing | Median \|caption on − word audio onset\| on the render. A p95 above 250 ms fails a gate | 1−min(1, med/150 ms) |
| S | Style | Per craft-playbook style-vector feature: z = (x−median_g)/(1.4826·MAD_g) against the genre library. z = 0 inside the genre IQR | mean of max(0, 1−\|z\|/3) |
| G | Soft gates | Warning-level gates passed ÷ gates that apply | ratio |
| R | Reviewer | 8–10 pointwise items (hook ≤1.5 s, story, dead air, pacing, legibility, audio, b-roll, CTA, brief): pass, fail with timecode, or "Unknown" [1]. Majority of 3 samples | passes ÷ answered |

**Vetoes (not weighted):**
- conformance failure;
- a newly failing blocking gate;
- a proper-noun caption error not sent to `hold`;
- a false `sendable`;
- a crash (P = 0, never dropped).

**Audience data (directional, not in P), per SnapUGC [7]:**
- ECR = share of viewers watching more than 5 s.
- NAWP = min(AWT/(0.556·d + 5.64), 1).

## 3. Primary score

P = 100 · Σ w_f·S_f / Σ_available w_f. Weights are renormalised over the families a reel has (Story needs a gold final). Pairing still holds because both arms are scored on the same reels.

| Family | S_f | w_f | Why |
|---|---|---|---|
| Story | .30H + .35F + .15τ + .20C (renormalised if τ dropped) | **.40** | Closest to pro taste; targets "correct but generic" (council #1) and quality-only failures [5]. ECR is set in the first 5 s [7] |
| Captions | .6W + .4T | .20 | Baked in; not fixable in the NLE (ADR-0021) |
| Style | S | .15 | Genre conventions; capped to avoid median-chasing |
| Soft gates | G | .10 | Saturates; regression guard [1] |
| Reviewer | R | **.15·c** | c from mean κ of admitted items: 0 uncalibrated, .5 at ≥ .4, 1 at ≥ .6; stored in `eval/frozen/` (§5) |

Build score = mean P, reported with per-family and per-language scores. v0 (plans only) uses Story alone.

## 4. Decision rule: "improved"

**Setup:**
- 6–10 tuning reels, 3 epochs per arm; plan-only v0 uses 5 epochs.
- `claude -p` has no seed or temperature, so epochs absorb variance [1].

**Noise floor.** On every change of model, CLI or `judge_hash`, run A/A (baseline vs baseline) with the decision's k, on disjoint uncached epoch indices (e.g. 1–3 vs 4–6). Set δ_min = max(2 points, 2·SD(d^AA)/√n).

**Accept only if all five conditions hold:**
1. **No new veto.**
2. **Effect size:** mean d ≥ δ_min, where d_i = mean_k P_cand − mean_k P_base.
3. **Significance:** an exact one-sided **paired sign-flip permutation test** (all 2ⁿ sign patterns) gives p ≤ 0.10.
   - It can be met even at n = 6, where the minimum p is 1/64.
   - A sign test discards magnitude, needing 6/6, 7/8 or 9/10 wins at p ≤ .05.
   - Bootstrap CIs undercover below ~10 reels: logged only.
4. **Guardrails:**
   - No family mean drops by more than its tolerance: Story 2, Captions 1, Style 3, Reviewer 3, Gates 0 points.
   - No single reel drops by more than 8 points.
   - No language stratum has a negative mean d.
5. **Confirmation:** 3 fresh, uncached epochs for **both** arms still give mean d > 0 (winner's curse; the cached session baseline may be a low draw).

p ≤ .10 suffices: changes are git-reversible and the pro editor audits every 5th acceptance (ADR-0029).

**Power is low.** 80% power (α = .05) needs a paired d_z of about 1.2 at n = 6 and 0.86 at n = 10 (approximate). v0 has only reels with gold finals (4–9): at n = 4 the minimum p is 1/16, so every reel must improve. Grow the tuning set to ≥ 12 with no-final footage (Gates, Style and Reviewer still apply).

## 5. Judge calibration (Reviewer vs pro editor)
1. **Labels.** The editor labels ≥ 30 tool renders, weak ones included (ADR-0021 §5): checklist items, overall 1–4, sendable yes/no; 10% repeats measure self-consistency.
2. **Blinding.** The Reviewer sees render, contact sheets and transcript only, never the rationale or build. Prefer a different model tier from the editing model [2] (self-preference [4]).
3. **Split the labels.** Tune wording on half; report agreement on the rest.
4. **Metrics:**
   - per item: Cohen's κ, or Gwet's AC1 when prevalence is skewed;
   - overall score: Spearman ρ;
   - issue recall: share of editor-flagged problems the Reviewer also flags.
5. **Gating:**
   - An item counts toward R when κ ≥ .4 and the lower bound is > .2.
   - An item can trigger `hold` only when its issue recall is ≥ .8.
6. **Builds, not single reels.** Timeline-Bench judges matched humans at agent level (ρ ≈ .93), but agreement on a single edit was only κ ≈ .15 [5].
7. **Pointwise, not pairwise.** Pairwise verdicts flip more often [6]. Any A/B judgment is run in both orders, and only consistent verdicts count [4][8].
8. **Recalibrate** on any model or CLI change.

## 6. Scoreboard, caching, reproducibility

**`eval/scoreboard.jsonl`** has one row per reel × arm × epoch:

| Group | Fields |
|---|---|
| Run identity | `run_id, ts, set, experiment_id, arm, reel_id, genre, lang, has_gold, epoch, cache_hit` |
| Versions | `git_sha, knowledge_sha, prompts_sha, judge_hash, ffmpeg_build, remotion_ver, asr_model_hash` |
| Model | `served_model_id, cc_version`, read from the JSON output rather than the `--model` flag, because silent remaps occur [9] |
| Scores | `metrics{H,F,tau,C,W,T,cer,S,G,R}, families{}, P, vetoes[], verdict, hold_reasons[]` |
| Cost | `claude_calls, tokens, wall_s` |

**`eval/experiments.jsonl`** records each decision: d_i, δ_min, p, guardrails, confirmation, and accept or revert. Reference designs: Inspect epochs and stderr [3][10]; promptfoo weighted assertions [11].

**Content-addressed caches:**

| Stage | Cache key |
|---|---|
| Perception | sha256(raw) + tool version (never redone in the loop) |
| Selects | perception hash + config |
| Claude decisions | hash(inputs, prompts, knowledge, model, CLI, epoch#) |
| Renders | timeline hash |

**Reproducibility:**
- Fresh `claude -p --output-format json` per decision; explicit `--allowedTools`; pinned CLI; no `--resume` [1].
- Local steps use fixed seeds; ffmpeg runs bit-exact.

**Budget per candidate:**
- v0: about 80 calls (8 reels × 5 epochs × 2), with the baseline cached.
- v1: adds 24 renders.
- At most 3 candidates per night, with hard caps.

**Line classes:** retakes of a line (normalised similarity ≥ .85) form one class; hand-check 10% of aligned gold plans; a gold final is one exemplar, not unique truth [5].

## 7. Failure modes

| Failure | Countermeasure |
|---|---|
| Keep everything | F1 precision; Reviewer dead-air item |
| Spurious cuts | Shot-length CV; Reviewer pacing item |
| Fewer captions | Omitted words count as deletions |
| Converge on genre median | No reward inside the IQR; Style weight capped |
| Loop edits its grader | `eval/frozen/` read-only; `judge_hash` must match |
| Overfitting tuning reels | Confirmation run; ≤ 3 accepts per session; rules cite ≥ 3 reels; rotate reels in; holdout only at release; track the tuning−holdout gap |
| Judge self-preference | Timecoded items; weight 0 until calibrated; editor notes outrank |
| Model drift; Hinglish masked | Concurrent baseline, A/A re-run; per-stratum guardrail |
| Saturated gates | Move to a regression suite [1] |

**Not adopted:** VBench [12] and OmniBench-99 [13] (nearest to the unfound "OmniEdit-Bench") score generative fidelity, not editing craft.

## Sources
1. Anthropic, Demystifying evals for AI agents — anthropic.com/engineering/demystifying-evals-for-ai-agents
2. Anthropic docs, develop-tests — platform.claude.com/docs/en/test-and-evaluate/develop-tests
3. Miller, "Adding Error Bars to Evals", arXiv 2411.00640
4. Zheng et al., "Judging LLM-as-a-Judge with MT-Bench", arXiv 2306.05685 
5. Gupta et al., "Timeline-Bench", arXiv 2609.35143 (details from the emergentmind.com summary)
6. Tripathi et al., "Pairwise or Pointwise?", arXiv 2504.14716
7. Li et al., SnapUGC, ECCV 2024, arXiv 2410.00289
8. Shi et al., "Judging the Judges", arXiv 2406.07791
9. claudeissues.com/issue/67299 (silent `--model` remap)
10. UK AISI Inspect, inspect.aisi.org.uk
11. promptfoo.dev/docs/configuration/expected-outputs
12. Huang et al., VBench, arXiv 2311.17982
13. OmniBench-99, arXiv 2412.02114
