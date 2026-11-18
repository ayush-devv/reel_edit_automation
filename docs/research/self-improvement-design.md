# Self-improvement loop design (`reel improve`)

Status: proposal · 2026-11-18 · implements ADR-0027 §5, ADR-0029

## 1. Constraints
No weight changes; 6–12 tuning reels; minutes per v1 eval; nondeterministic runs. Prerequisite: the project is **not yet a git repo**.

## 2. Methods surveyed

| Method | Mechanism | Data / cost / evidence | Fit |
|---|---|---|---|
| **GEPA** [1] | Reflect on traces and textual feedback, then mutate one module. Per-instance Pareto pool. Minibatch gate before the full eval. | Needs a metric plus textual feedback. ~1.8k–7k rollouts. Beats GRPO by about 6% on average (up to 20%) with up to 35× fewer rollouts, and MIPROv2 by >10%. | **Core**, at a budget about 100× smaller. |
| **ACE** [2] | Generator → Reflector → Curator. Itemised bullets with IDs and helpful/harmful counters. Delta merges applied by non-LLM code. Grow-and-refine. | Needs execution feedback and a strong Reflector. +10.6% on agents, +8.6% on finance. Names **brevity bias** and **context collapse**: a full rewrite cut 18,282 tokens to 122 and accuracy from 66.7 to 57.1. | **Core.** Our YAML nodes already are the bullets. |
| MIPROv2 [3] | Grounded instruction and demo proposals, chosen with a Bayesian surrogate. | Hundreds of evals. Up to +13%. | No, too many evals. |
| OPRO [4] | The meta-prompt holds past solutions with their scores. | Up to +50% on BBH. Train scores ran **5–20% above test**. | Borrow the score trajectory and early stopping. |
| TextGrad [6], APE [5] | Critiques used as "gradients"; sample instructions and select. | GPQA 51%→55%. APE matched humans on 19/24 tasks. | Critique wording only. |
| Reflexion [7], Self-Refine [8] | Verbal self-feedback. | HumanEval 91%; about +20%. | Runtime Reviewer only. |
| AWM [9], Voyager [10] | Induce reusable workflows or skills from successes. | +24.6% and +51.1% relative; 15.3× faster milestones. | Feeds the ADD operator. |
| Dynamic Cheatsheet [11] | Self-curated evolving memory. | Game of 24: 10%→99%. | Caution: it is the collapse case in [2]. |
| FunSearch [12], AlphaEvolve [13] | Evaluator-driven program database with diff edits. | Thousands of evals. | Borrow the archive, diff edits and an evaluator the loop cannot touch. |
| Failure modes | Reward hacking and Goodhart over-optimisation [14,15]. Adaptive reuse overfits small sets [4,16]. | | Motivate §8. |

**Choice:** GEPA reflective mutation + per-reel Pareto archive; ACE delta-only edits and counters; paired noise-aware gate with a Ladder-style margin [16].

## 3. Mutable vs frozen
- **Mutable.** The owner-owned allow-list `eval/improve.allow` covers:
  - node fields in `knowledge/graph/*.yaml`
  - the per-genre priority sidecar `knowledge/priorities.yaml` (the schema has no priority field)
  - persona-prompt sections
  - caption/style tokens
  - compiler parameters
- **Frozen:** code, scorer and weights, gold plans, hashed eval manifest, holdout, `knowledge/SCHEMA.md`, and the Reviewer rubric (built from the graph per ADR-0027, so **pinned to the last release** — the loop must not move its own grader).
- Diffs outside the allow-list are rejected before evaluation.

## 4. Failure attribution
1. Every decision call outputs `applied_nodes: [ids]`. The run log records the loaded nodes and the knowledge version.
2. Each metric emits a feedback sentence (GEPA's μ_f), e.g. "hook at 4.2 s, gold at 0.8 s; plan cited `tech.hook.slow_build`". QA failures and pro notes are attached, and pro notes rank highest.
3. ACE-style counters go in the sidecar `eval/node_stats.jsonl`:
   - a node cited in a failing decision gets `harmful+1`
   - a node cited on an above-median reel gets `helpful+1`
4. The Diagnoser classifies each failure:

| Failure | Action |
|---|---|
| Wrong node | Mutate the node |
| Missing node (gold did X, no loaded node covers X) | ADD |
| Retrieval miss | Fix the `genres` edges |
| Prompt or parameter | Mutate it |
| Metric or gold artefact | Report to the owner; no mutation |

## 5. Mutation operators (one node or field each)
- **ADD:** a technique or anti-pattern node, induced AWM-style by contrasting good and bad reels. It gets `sources: [{title: "experiment:<id>"}]`, `evidence_level: single_opinion` and `confidence: low`. It is paraphrased and contains nothing reel-specific.
- **PARAM:** shift or narrow one range by ≤ 25% of its span.
- **PRIORITY/CONFIDENCE:** move one step.
- **EDGE:** add or remove a `genres`, `conflicts_with` or `requires` edge.
- **PROMPT:** change one persona section, ≤ 10 lines. Appending is preferred.
- **TOKEN:** set one caption/style token within its capability's range.
- **DEPRECATE:** set confidence to low and drop the node from retrieval. Nothing is ever deleted. A schema `status` field needs the owner's decision.
- **MERGE:** GEPA merge of deltas from two archive entries that lead on different reels.

**Lint:**
- No whole-file rewrites; these cause brevity bias and collapse.
- Must be schema-valid.
- Citation required.
- No tuning-reel IDs or transcript phrases, so the loop cannot memorise the gold.
- ≤ 40 changed lines per round.
- Compiled context grows ≤ 5% per round.

A periodic ACE-style **refine** (dedup) pass is itself a candidate and goes through the same gate.

## 6. One round
```
0 Champion = tag kb-vN. If the model or Claude Code version changed, re-baseline:
  run each reel k times (v0 k=3, v1 k=2).
  σ = max(σ_r, σ_pooled), where σ_pooled is pooled across reels.
1 Diagnose (one Claude call): failures + feedback + node_stats + the last 10 experiments
  with scores and verdicts (OPRO trajectory) → ranked failure classes.
2 Propose (one Claude call): ≤3 deltas, each a commit on improve/<date>-r<n>,
  each with a predicted effect.
3 Stage A (GEPA minibatch): each delta alone on 3 reels
  (2 targeted + 1 random passing).
  Keep it if the minibatch mean rises and no hard gate fails.
4 Stage B: the survivors combined, on the full tuning set.
  If that fails, try the best single delta.
5 Accept (§7). Confirm by re-running the 3 biggest-win reels; the wins must replicate.
6 Merge and tag kb-vN+1. New champion baseline = mean of its Stage B and confirm runs,
  not the lucky winning run. Update the archive and node_stats.
  Log to eval/experiments.md (delta, rationale, per-reel before/after, σ). Log rejects too.
7 Stop after 2 consecutive rejected rounds or 3 accepted changes (OPRO early stopping).
```

## 7. Acceptance and Pareto
Let d_r = S_cand,r − mean S_champ,r, using the ADR-0029 weighted score. Its noise is σ_d ≈ σ·√(1+1/k). Accept only if **all** of these hold:
1. #{d_r > σ_d} − #{d_r < −σ_d} ≥ 2. This is a paired sign test, not a mean.
2. The mean of d_r is ≥ max(1 point, 1 pooled SE). Ladder-style: a gain within the noise never becomes the new best [16].
3. No reel has d_r < −2σ_d.
4. No component metric (gate pass rate, style match, each gold metric) regresses beyond its tolerance.
5. No hard QA gate newly fails.
6. The gain does not come from the rubric alone.

**Archive:**
- Production keeps one champion.
- The archive (≤ 8 commits) keeps any candidate that leads within σ_d on at least 1 reel. This is GEPA's per-instance Pareto, which avoids greedy local optima [1].
- Parents are sampled in proportion to the number of reels they lead.
- There is no per-genre front, since there is about 1 reel per genre. Results are reported in 2–3 genre buckets: speech-led, visual-led, montage.

## 8. Budget and safeguards
**Budget per night** (aborts at the cap; re-baselining counts toward it):

| | Typical round | Worst-case round | Re-baseline | Nightly cap |
|---|---|---|---|---|
| **v1** | ~24 reel-runs | 9 + 24 + 24 + 3 = 60 | 24 | ≤ 2 rounds, ≤ 100 reel-runs |
| **v0** | ~40 plan-runs | ~60 plan-runs | 36 | ≤ 4 rounds, ≤ 250 plan-runs |

**Safeguards:**
- **Holdout isolation:**
  - Holdout paths are denied to the loop.
  - The holdout is scored only at release.
  - Tuning-reel reuse is counted, and fresh reels are rotated in after about 20 accepted changes, because adaptive reuse erodes validity [16].
- **Pro-editor sampling:**
  - Every 5 accepted changes, the editor gives blinded before/after verdicts on 3 reels.
  - If they prefer the old version on 2 of 3, the batch is reverted and the score re-weighted.
  - If the correlation between automatic scores and pro verdicts drifts, the loop freezes (reward hacking [14,15]).
- **Rollback:** one tagged commit per change; scoreboard keyed by commit/knowledge/CLI/model; environment shifts trigger re-baselining, not reverts.
- **No code edits:** enforced by the allow-list and a pre-eval diff check.

## 9. v0 (plan-level, no rendering)
- **Gold plans:** pro finals aligned to the raw footage give the takes, hook span, kept words and order.
- **Run:** perception cache plus the story-plan call only.
- **Score:** hook overlap (tolerance window), word-keep F1, Kendall τ, duration ratio.
- **Scope:** story modules only — hook, structure and pacing nodes, the story persona, and selection parameters.
- **Cost:** seconds per reel, which allows k=3 and more candidates.
- **Tolerance:** gold is one valid edit among several, so metrics are tolerant and pro notes override.
- **Carry-over:** v0 acceptances are tagged `validated: plan`. They must pass the first v1 run or they are reverted.

## Sources
1. GEPA, arXiv:2507.19457
2. Agentic Context Engineering, arXiv:2510.04618
3. MIPRO, arXiv:2406.11695
4. OPRO, arXiv:2309.03409 (§5.4)
5. APE, arXiv:2211.01910
6. TextGrad, arXiv:2406.07496
7. Reflexion, arXiv:2303.11366
8. Self-Refine, arXiv:2303.17651
9. Agent Workflow Memory, arXiv:2409.07429
10. Voyager, arXiv:2305.16291
11. Dynamic Cheatsheet, arXiv:2504.07952
12. FunSearch, Nature 625 (2024)
13. AlphaEvolve, arXiv:2506.13131
14. Reward Model Overoptimization, arXiv:2210.10760
15. Goodhart variants, arXiv:1803.04585
16. The Ladder, arXiv:1502.04585
