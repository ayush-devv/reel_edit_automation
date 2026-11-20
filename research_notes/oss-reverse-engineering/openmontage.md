# OpenMontage: reverse-engineering notes (clean-room)

> Source: shallow clone of OpenMontage (AGPL-3.0), read only, never executed.
> Analysed 2026-11-19. No code was copied; every mechanism below is described in my own words.
> **Evidence tags.** Every mechanism claim carries one:
> - **[code]**: I read the Python/TS that does it.
> - **[skill]**: it exists only as Markdown instructions to the LLM agent (a prompt), with no code enforcing it.
> - **[README]**: a claim in README/docs that I did not verify in code.
>
> This split matters a lot here. Much of what looks like a "feature" in OpenMontage is a prompt, not a program.

---

## 0. TL;DR

- OpenMontage is a **prompt-and-tool kit for a coding agent** (Claude Code, Cursor and similar), not a self-running engine. The agent reads YAML pipelines and Markdown "director" skills, then calls about 180 Python tools. Python only supplies tools, persistence and gates. It has **no runtime LLM calls**: the IDE agent *is* the LLM [README: `docs/ARCHITECTURE.md` §2; code check: grepping `lib/` and `tools/` finds no `anthropic`, `messages.create` or `chat.completions` client. `config.yaml`'s `llm:` block (provider, model, temperature) is parsed by `lib/config_model.py` but **nothing reads it**, so it is vestigial. "Multi-provider model routing" therefore exists only for *media* providers, not for LLMs].
- Its breadth is huge: 18 TTS, 29 image and 33 video-gen providers, 17 stock sources, Remotion, HyperFrames and FFmpeg renderers, and 12 pipelines. Its **depth on our use case (a talking-head reel from raw footage) is shallower than ours**. Its talking-head pipeline is `stability: beta`, has a $0.50 default budget, and amounts to transcribe, subtitles, silence-cut and compose.
- Things worth taking:
  1. Long-form to ranked clip batch (Clip Factory)
  2. Localization/dub as a pipeline shape
  3. A cheap face/eye "beauty pass"
  4. Video-conditioned and cut-fitted music generation
  5. SFX generation
  6. CLIP + MMR re-ranking of stock b-roll
  7. A provider-scoring/routing layer for generative assets
  8. Governance: budget caps with per-action approval, an append-only decision log, and checkpoint gates enforced in code
  9. A **content-addressed tool-output cache** (A9), which is the most direct idea for our "whole-stage re-render on revision" gap
- Red flags:
  - AGPL itself: copy nothing.
  - Wav2Lip (lip sync) has commercial-use restrictions upstream. Verify before use.
  - `suno_music` calls `sunoapi.org`, which looks like a third-party reseller rather than Suno. Verify the ToS.
  - MiniCut tools are a closed CLI that needs a login.
  - HyperFrames, GSAP, SadTalker and ACE-Step licences are **not stated in the repo**. Verify upstream.
  - Stock adapters (Wikimedia, Archive.org and others) only *record* licences. They do not gate them, except Openverse.

---

## 1. Maturity / provenance (what the repo shows)

| Signal | Value | Source |
|---|---|---|
| Last commit in clone | `2e003e6`, 2026-11-15 ("docs: add updated OpenMontage Instagram link") | `git log` (shallow, 1 commit visible) |
| Package version | `0.1.0` | `setup.py` |
| Licence | AGPL-3.0 | `LICENSE`, README badge |
| Star count | **not visible in the repo** | n/a |
| Tests | 206 test files, about 1,860 `def test_` functions in `tests/`. These are contract tests (every tool honours `BaseTool`), lib tests (checkpoint gates, decision log, slideshow risk, corpus), many tool tests, Backlot UI tests, and a "golden scenario" replay harness with **one** scenario (`tests/eval/golden_scenarios/talking_head_basic.json`, empty `golden_outputs/`) | [code] |
| Pipeline stability flags | production: animated-explainer, animation, avatar-spokesperson, cinematic, hybrid, screen-demo. beta: talking-head, clip-factory, documentary-montage, localization-dub, podcast-repurpose, character-animation | `pipeline_defs/*.yaml` |
| Docs | `docs/ARCHITECTURE.md` ("last updated 2026-10-25"), `docs/PROVIDERS.md` (price tables), provider refresh notes dated Oct 2026, READMEs in 4 languages | [README] |

My read: the project is active and has heavy test investment in contracts and plumbing. It has **almost no output-quality evaluation**: one golden scenario and no outputs. Several tools are flagged `EXPERIMENTAL` (`clip_search`, `corpus_builder`, `visual_qa`, `music_gen`).

---

## 2. Architecture map

### 2.1 How a run flows [code + skill]

```
user prompt
  → agent reads AGENT_GUIDE.md (routing rules)            [skill]
  → picks a pipeline_defs/<name>.yaml                       [skill; YAML is data]
  → "preflight": tool_registry.discover() → capability menu [code: tools/tool_registry.py]
  → for each stage in YAML:
       read skills/pipelines/<pipeline>/<stage>-director.md [skill]
       call tools (BaseTool.execute → ToolResult w/ cost)   [code]
       self-review with skills/meta/reviewer.md             [skill]
       lib/checkpoint.write_checkpoint(...)                 [code, enforces gates]
       if stage gated → status=awaiting_human, END TURN     [code raises if skipped]
  → compose (video_compose → Remotion | HyperFrames | FFmpeg) [code]
  → final_review artifact → publish                          [schema + skill]
```

- **Canonical stages:** research → proposal → script → scene_plan → assets → edit → compose → publish. Footage-led pipelines start at `idea` and skip research and proposal [code: YAML].
- **Agent instructions** live in three layers [README + verified dirs]:
  - **Layer 1:** `tools/` and `pipeline_defs/`: what exists.
  - **Layer 2:** `skills/`: OpenMontage conventions. These are per-pipeline "directors" (executive-producer, idea, script, scene, asset, edit, compose, publish) plus `skills/meta/` (reviewer, checkpoint-protocol, taste-direction, video-reference-analyst, voice-performance-director, bespoke-composition, and others).
  - **Layer 3:** `.agents/skills/` (about 92 vendored third-party "how the tech works" skills: GSAP, HyperFrames, ElevenLabs, Remotion, Three.js and so on).
  - Each tool's `agent_skills[]` field links Layer 1 to Layer 3.
- **Artifacts:** 20 JSON Schemas in `schemas/artifacts/` (brief, script, scene_plan, asset_manifest, edit_decisions, render_report, final_review, decision_log, cost_log, video_analysis_brief, source_media_review, proposal_packet, …). Each checkpoint is schema-validated before it is persisted [code: `lib/checkpoint.validate_checkpoint`].

### 2.2 Checkpoints and stages [code: `lib/checkpoint.py`]

- There is one JSON file per stage: `pipeline/<project>/checkpoint_<stage>.json`. Status is one of `pending | in_progress | awaiting_human | completed | failed`.
- Writes are atomic: a temp file, then `os.replace`. A superseded non-heartbeat checkpoint is first **copied to `history/`**, so re-runs and gate transitions stay reconstructable. That is the basis of Backlot "replay".
- **Gate enforcement:** if the pipeline YAML sets `human_approval_default: true` for a stage (or the caller asks), writing `completed` without `human_approved=True` **raises** `GATE VIOLATION`. The error message tells the agent to write `awaiting_human`, present the summary and end its turn.
- **Prerequisite enforcement:** a stage cannot be advanced to `awaiting_human` or `completed` unless every earlier stage in that pipeline's order has a valid `completed` checkpoint for the same project and pipeline type, approved where gated.
- The proposal stage additionally requires `proposal_packet.approval.status ∈ {approved, approved_with_changes}`.
- Checkpoint policies are `guided`, `manual_all` and `auto_noncreative` (config only; a caller may gate more strictly but never less).

### 2.3 How providers are chosen [code: `lib/scoring.py`, `tools/*/…_selector.py`, `tools/provider_routing.py`]

- There are three selectors: `tts_selector`, `image_selector` and `video_selector`. Each one discovers all registered tools for its capability and runs them through `filter_explicit_route`, which applies hard constraints: a pinned `preferred_tool`, `hosting_provider` or `model`; operation and route support (t2v, i2v, reference-to-video, edit, precise_edit); and mask or image-input support. It then calls `rank_providers` and executes the top selectable tool.
- An explicit `preferred_provider` is honoured **only if its best score is within 0.15 of the top score** (`video_selector.PREFERRED_PROVIDER_GAP`).
- Results carry `selection_reason`, the score breakdown, `alternatives_considered` and `fallback_tools`. A `rank` operation returns the ranking without generating anything.
- Details are in Card A1.

---

## 3. Feature cards

### A. Orchestration and governance

#### A1. Provider scoring and routing across 7 dimensions [code]

**What the user sees:** "I picked Kling v3 via fal for this shot (score 0.81: fit 0.9, quality 0.95, control 0.7); runner-ups: Veo 0.74, Seedance 0.72." Missing a key means it silently falls through to the next provider or a local one.

**How it works:** `lib/scoring.py`.
- **Dimensions and weights** (sum to 1.0): task_fit 0.30, output_quality 0.20, control 0.15, reliability 0.15, cost_efficiency 0.10, latency 0.05, continuity 0.05. Each dimension is 0–1.
- **task_fit:**
  - It tokenizes the intent text and each tool's `best_for` strings, expands both through a small hand-written synonym-cluster table (cinematic/film/trailer, social/reels/shorts and so on), and computes the **overlap coefficient** |A∩B|/min(|A|,|B|) rather than Jaccard, so tools that list many strengths aren't penalized.
  - Final fit is 0.7×intent-overlap + 0.3×style-overlap + 0.1, capped at 1.
  - If a tool has no `best_for`, fit is 0.3.
- **Context-driven modifiers on task_fit:**
  - Motion required but the tool is image-only: task_fit × 0.2.
  - Intent reads as "generated/stylized" but the provider is stock-like: task_fit × 0.55 and quality × 0.85.
  - Reference conditioning wanted: +0.18 fit and +0.12 control if the tool supports reference images; otherwise × 0.7. Image editing works the same way.
  - Cinematic intent with three or more "premium" features (native audio, multi-shot, camera direction, lip-sync, cinematic quality): +0.15 fit and +0.10 quality. With one or two such features: +0.05.
- **control:** a weighted checklist of `supports` flags (controlnet 2.0, reference_image 1.8, style_transfer 1.5, inpainting 1.5, img2img 1.3, negative_prompt 1.0, custom_size 0.8, aspect_ratio 0.7, seed 0.5), normalized so that half the total weight scores 1.0.
- **reliability:** `historical_success_rate` if present; else 0.95 for production tools, 0.8 for other available tools, 0.4 if degraded, 0 if unavailable.
- **cost_efficiency:** free scores 1.0. With a budget, cost/remaining > 0.5 scores 0.1, > 0.2 scores 0.5, otherwise 0.8. Without a budget, the steps are <$0.05 → 0.9, <$0.20 → 0.7, <$1 → 0.5, else 0.3.
- **latency:** measured p50 if present (≤1 s → 1.0, ≤10 → 0.8, ≤30 → 0.6, ≤60 → 0.4, else 0.2); else local 0.9, hybrid 0.6, API 0.4.
- **continuity:** 0.9 if the provider was already locked earlier in the project, 0.4 if it differs, 0.5 if nothing is locked.
- **Important finding:**
  - `quality_score`, `historical_success_rate` and `latency_p50_seconds` are **hand-set class constants** on some tools. Examples: Seedance 0.95, Runway 0.9, Kling avatar 0.82 with p50 240 s, Fish Audio 0.9 with p50 6 s.
  - **Nothing in the repo writes them from real runs.** The scorer is a static, hand-tuned prior, not a learned router.
  - A second scorer, `ProductionPathScore` (8 dims: delivery_fit 0.25, quality_fit 0.20, capability_confidence 0.15, fallback_integrity 0.10, budget_fit 0.10, speed_fit 0.08, controllability 0.07, consistency_fit 0.05), is **defined but has no caller**.

**Dependencies/licences:** pure Python. Each routed provider needs its own paid key.

**Clean-room build for us (M):**
- Add a capability registry where each provider adapter declares `best_for`, `supports`, cost estimator, runtime and stability.
- Add a scorer with explicit weights.
- We would do better by making it **learned**: log each generation's outcome (accepted or rejected by Reviewer or client, latency, actual cost) to SQLite and feed real success rate, p50 and quality back into the score.
- Use Claude for task_fit, a cheap structured call that scores intent against `best_for`, instead of synonym tables.
- Reuse: our `stock.py` Pexels/Pixabay fallback chain becomes the first two providers.
- Risk: it is premature until we have at least two generative providers per capability.

**Cost:** n/a.

#### A2. Budget governance: estimate → reserve → reconcile, caps, per-action approval [code]

**What the user sees:** "This shot costs $0.62, above your $0.50 per-action threshold. Approve?" and "First paid use of `kling_video`. Approve?" A running cost meter.

**How it works:** `tools/cost_tracker.py`, `config.yaml`.
- Every paid call is `estimate(tool, op, usd)`, then `reserve(id)`, then `reconcile(id, actual)` (or `refund`).
- Budget modes are `observe | warn | cap`. Defaults: total $10, 10% reserve holdback, `single_action_approval_usd` $0.50, `require_approval_for_new_paid_tool` true.
- `reserve` raises `ApprovalRequiredError` above the per-action threshold or on a tool's first paid use, and `BudgetExceededError` in cap mode.
- State persists to `cost_log.json`. Checkpoints embed a `cost_snapshot`.
- Each pipeline also has a `budget_default_usd`: talking-head 0.50; clip-factory, podcast, documentary and screen-demo 1.00; explainer, animation, cinematic, hybrid and avatar 2.00; localization 3.00.
- **Reference-based cost estimator** (`estimate_from_reference`), a nice touch:
  - Scene count is the larger of (the reference's cuts per minute × target minutes) and a pacing minimum: rapid_fire 10, dynamic_social 8, steady_educational 5, slow_contemplative 3, variable 6.
  - Narration words come from the reference's WPM (default 150).
  - Motion ratio is a per-scene-type weighted average: animation, b-roll and stock 1.0; product shot 0.9; transition 0.6; screen recording 0.45; talking head 0.35; diagram and chart 0.25; text card 0.2. It is capped at 0.95. When scene types are unknown, a fallback uses pacing, raised to at least 0.7 for shorts, IG or TikTok.
  - Video clips needed = max(motion scenes, motion seconds / clip length).
  - A ×1.3 retry buffer applies.
  - Images per scene are 2.0 for fast pacing, else 1.5.
  - Output: line items, low/high range (subtotal/1.3 … subtotal×1.15), a "sample cost" for 2 scenes, and confidence high/medium/low by data available.

**Dependencies:** none.

**Clean-room build (S):**
- We have no generative spend yet, so this becomes relevant once we add TTS, gen-video or music generation.
- Add a `budget.py` with the same three-phase ledger and per-client caps stored in project config.
- Surface it in the web app's approval UI.
- The reference-based quote is useful for **quoting clients** too.

**Cost:** n/a.

#### A3. Decision trail (append-only decision log) [code + skill]

**What the user sees:** a "Decisions" rail on the board: every provider, voice, music, runtime or fallback choice, with the options considered, a score per option, the reason, the rejected-because text, and confidence.

**How it works:**
- `schemas/artifacts/decision_log.schema.json`: each entry has `decision_id, stage, category` (17-value enum, e.g. provider_selection, render_runtime_selection, fallback_decision, budget_tradeoff, downgrade_approval, music_source, voice_selection), `subject, options_considered[{option_id,label,score 0–1,reason,rejected_because}], selected, reason, user_visible, user_approved, confidence`.
- `write_checkpoint` merges new decisions into `pipeline/<id>/decision_log.json`, de-duplicated by id, and back-links it from `proposal_packet` and `render_report` [code].
- The rule "when a decision changes, append a new entry with the same (category, subject) pair; the board shows the latest as *revised*" is **[skill]** (AGENT_GUIDE.md "Re-log Changed Decisions").
- The reviewer treats a runtime decision that lists only one option, when two runtimes were available, as **critical** [skill].

**Clean-room build (S):**
- We already have Claude story and finish passes that make choices. Have each pass emit structured `decisions[]` (alternatives plus reason), store them per project, and show them in the web app.
- Very useful for "why did you put this b-roll here?" questions from clients, and for revision.

**Cost:** n/a.

#### A4. Human approval checkpoints [code-enforced, skill-driven]

**What the user sees:** the run stops at idea, script, scene plan, assets and publish (per pipeline YAML) and waits for "approved". On reference-driven and generative pipelines, the proposal has a **`sample` sub-stage**, a 10–15 s preview clip that must be approved before the batch run [YAML: `animated-explainer.yaml` sub_stages]. Localization requires a **hero-scene dub sample** before batch TTS [skill: `localization-dub/asset-director.md`].

**How it works:** the gate is in code (Card 2.2). Ending the turn and presenting the artifact is [skill]. Reviewer protocol: findings are critical, suggestion, nitpick or investigation; a critical finding *must* carry a `proposed_fix` or it is downgraded; at most 2 revision rounds, then "pass with warnings" [skill: `skills/meta/reviewer.md`].

**Comparison:** we have client review links and revision from notes. They have *internal* gates per stage. For a freelancer, the useful idea is the **hero sample**: render the hook (first 3–5 s) in two looks and get a client pick before the full render.

**Clean-room build (S):** add a `sample` mode to our pipeline that renders only the hook window, plus a stage-gate flag in project state.

**Cost:** n/a.

#### A5. Delivery promise (anti-silent-downgrade) [code + skill]

**What the user sees:** "You asked for a motion-led video but only 40% of cuts are real motion; the rest are animated slides. Approve still-led fallback, or should I generate more motion?"

**How it works:** `lib/delivery_promise.py`.
- There are eight promise types: motion_led, source_led, data_explainer, teacher_explainer, screen_demo, avatar_presenter, hybrid, localization.
- Each type has rules: `still_fallback_allowed` and `min_motion_ratio` (motion_led 0.7, avatar 0.3, source_led 0.3, hybrid 0.2, others 0).
- `validate_cuts` classifies each cut:
  - motion: video file extension, or type video/animation/avatar
  - slide grammar: text_card, stat_card, the chart types, kpi_grid, comparison, progress, callout
  - still: anything else
- Slides do **not** count as motion. It flags a ratio below minimum, or more than 50% non-motion when stills aren't allowed.
- The `final_review.schema.json` field `promise_preservation` (delivery_promise_honored, runtime_swap_detected, silent_downgrade_detected, motion_ratio_actual) is required [code schema]. Checking it is [skill].

**Clean-room build (S):** for us, "promise" means things like "b-roll every ≤ N s" or "no static talking head > 6 s". It could be an extra QA gate on the compiled timeline.

#### A6. Pre-compose "slideshow risk" and variation scoring [code]

**What the user sees:** before rendering, "slideshow risk 3.2 / revise: 'text_card' dominates 75% of scenes; only 2/8 scenes state why they exist."

**How it works:** `lib/slideshow_risk.py`.
- **Six dimensions**, each scored 0–5 (lower is better) and averaged. Verdict: < 2 strong, < 3 acceptable, < 4 revise, ≥ 4 fail (do not compose). Empty plan = 5/fail.
- **repetition:** needs at least 3 scenes. +2 if one scene type exceeds 70%; +1.5 if fewer than 60% of descriptions are unique (first 50 characters); +1.5 if one shot size exceeds 60%.
- **decorative_visuals:** 5 × the share of scenes with none of `information_role`, `narrative_role` or `shot_intent`.
- **weak_motion:** among scenes with camera movement, 4 × the share lacking `shot_intent`. No movement at all scores 1.5.
- **weak_shot_intent:** 5 × the share without `shot_intent`.
- **typography_overreliance:** text, stat or KPI card share > 60% scores 4.0, > 40% scores 2.5, > 20% scores 1.0, otherwise 0.
- **unsupported_cinematic_claims:** only when renderer_family contains "cinematic". 1.8 per missing element: no hero_moment, < 30% scenes with movement, < 30% with a lighting key.

**Companion:** `lib/variation_checker.py` [code] runs eight checks. Each violation adds 0.6 to the score; verdicts use the same thresholds.
1. Dominant shot size above 50% (needs at least 4 scenes).
2. A run of at least 3 consecutive same-size shots.
3. Static or unspecified movement above 60%.
4. At most one lighting key.
5. No hero moment, or a hero moment with the same shot size as its neighbour.
6. At least 30% of descriptions contain a generic-buzzword phrase (from a short hard-coded list).
7. Fewer than 30% of scenes have texture keywords.
8. Fewer than 50% have shot_intent.

**Caveat:** both score **plan metadata only** (fields the LLM itself filled in), not pixels. An LLM can game them by filling in `shot_intent`. They are lint, not perception.

**Clean-room build (S):** our analogue is a **timeline-level monotony lint** on the compiled timeline, over things we actually render:
- longest stretch of unbroken talking head
- share of the reel with any overlay
- repetition of the same caption or graphic template
- the same transition used three times in a row
- punch-in cadence

This is better than theirs because it runs on facts, not self-reported intent. Feed it to the Reviewer persona.

#### A7. Post-render review [schema + thin code + skill]

**What the user sees:** a `final_review` with pass/revise/fail across technical probe, visual spot-check, audio spot-check, promise preservation and subtitle coverage.

**How it works:**
- `schemas/artifacts/final_review.schema.json` requires those sections, `frames_sampled ≥ 4`, booleans for black frames, broken overlays, unreadable text, unexpected silence, clipping and intelligible mix, and subtitle `coverage_ratio` / `timing_drift_detected`.
- **The tool behind it is thin:** `tools/analysis/visual_qa.py` only (a) extracts frames at given timestamps (default 1 s, 25/50/75%, end−1 s) for the agent to *look at*, (b) runs an ffprobe check against expected width, height, duration and audio, and (c) samples audio levels.
- Its docstring claims a "caption occlusion check" and "transition verification", but **the code does not implement either** (the op enum is review/probe/audio_levels only).
- `video_understand.py` can run CLIP or BLIP-2 locally over frames. Judging is [skill].

**Comparison:** our QA (Reviewer persona plus automatic gates plus verdict) is already at least as strong. Nothing to take except the **schema shape** (promise preservation, subtitle coverage ratio).

#### A8. Backlot, a living storyboard board [code]

**What the user sees:**
- A local web board (FastAPI + SSE + `watchfiles`) where stages light up, the script shows as a screenplay page, and the scene plan is a filmstrip that fills as assets generate.
- It also shows a decisions rail, a cost meter, renders, and **replay** of a finished run scrubbed from checkpoint history plus `events.jsonl`.
- Projects can be grouped into a "series".
- Localhost only, with a Host-header check against DNS rebinding [code: `backlot/server.py`, `state.py`, README].

**Mechanism:** `BaseTool` instrumentation appends events to `events.jsonl` (`lib/events.py`). The board derives all state from disk. The agent is not involved.

**Clean-room build (M):**
- We already have a web app. The idea worth taking is **"replay the edit"**: a timeline scrub of how the reel was built (story pass → finish pass → QA) as a client-facing "behind the edit" view.
- Moderate wow for clients, low priority.

#### A9. Content-addressed tool-output cache (selective recompute) [code]

**What the user sees:** re-running a project after a small change (one scene's prompt, one caption tweak) skips every tool call whose inputs didn't change. Cache hits come back with `cost_usd = 0` and `cached: true`.

**How it works:** `tools/base_tool.py` (`_cache_execute`, `_is_cacheable`, `cache_key`, `_fingerprint_value`) and `lib/asset_cache.py`.
- Every `BaseTool.execute` is wrapped automatically at subclass registration.
- **Key:** SHA-256 over the tool name, the tool version, the tool's declared `idempotency_key_fields`, and the normalized output-file suffix.
  - Any input value that is a path to an existing file is replaced by the **SHA-256 of the file's bytes**, walking nested lists and dicts.
  - So rewriting an input file in place changes the key, but moving the output location does not.
- **Eligibility:** the call is cached only when all of these hold:
  - the tool declares idempotency fields
  - the call has a concrete `output_path`
  - the tool is not a publisher
  - it is not a dry run
  - determinism is `DETERMINISTIC`, or `SEEDED` with a pinned seed (never `STOCHASTIC`)
  - it produces exactly one artifact
- **Store:**
  - The store is process-safe: a file lock with an O_EXCL fallback and a 60 s timeout.
  - The manifest is JSONL, rewritten atomically. It records tool, version, model, seed, the original cost (which a hit now "saves") and the result payload.
  - Blobs are **copied, never hard-linked**, so an in-place regeneration can't corrupt the cache.
  - Eviction is LRU at 20 GB (`OPENMONTAGE_ASSET_CACHE_MAX_GB`).
  - The cache is **off unless `OPENMONTAGE_ASSET_CACHE` is set**.
  - Its docstring says there is no dependency graph. Selective recompute falls out of correct keys.
- **Limits I found in code:**
  - `elevenlabs_tts` and `kling_video` are `STOCHASTIC`, so the expensive paid generators are mostly **not** cached, despite the docstring's framing.
  - `video_compose`, `remotion_caption_burn` and `audio_mixer` are `DETERMINISTIC` and cacheable, but the final compose is one call over the whole timeline. Any change re-renders the whole video, so there is no segment-level partial render.

**Clean-room build for us (M):**
- This is the right *pattern* for our "whole-stage re-render on revision" gap.
- Give each render step a declared input set, hash file contents (not paths), and cache by key.
- Go one level finer than they do: render the ffmpeg base **per timeline segment** (between hard cuts) and the Remotion overlay **per overlay window**, then concat and composite. A client note that touches 3 s re-renders about 3 s plus the cheap composite.
- **Also cache our stochastic paid calls** (TTS, gen-music) by input hash. For revisions you *want* the same bytes back unless the input changed.
- Risk: frame-exact segment boundaries and audio continuity across concat. Re-encode at segment joins or cut only on keyframes.

**Cost:** saves money; no API cost.

---

### B. Asset intelligence

#### B1. CLIP-based b-roll search: corpus, ranking and diversity [code]

**What the user sees:** "For the slot 'empty city street at 4 am, sodium light', here are the top 10 clips across Pexels, Archive.org, NASA and Wikimedia, de-duplicated so adjacent cuts don't look alike."

**How it works:**
- **`tools/video/corpus_builder.py`**, per query × source × candidate:
  - Download into `<corpus>/clips/`, skipping ids already indexed.
  - Extract N evenly spaced frames, avoiding the first and last.
  - Compute a cheap **motion score**: mean absolute pixel difference between the first and middle frame.
  - **CLIP ViT-B/32** (`openai/clip-vit-base-patch32`, 512-d, L2-normalized) embeds each frame. Frames are **mean-pooled** and re-normalized into one visual vector.
  - The source's tags or description (falling back to the query) are embedded as a **tag vector**.
  - Rows are appended to `index.jsonl` with full provenance (source, licence, creator, URL), plus `embeddings.npy` and `tag_embeddings.npy`. Save once at the end. Crash recovery truncates to the shortest of the jsonl/npy lengths.
  - Caps (`max_new_clips`), with per-source and per-candidate errors collected rather than fatal.
- **`lib/corpus.py`** and **`tools/video/clip_search.py`**:
  - `rank_for_slot`: fused score = (1−w)·cos(visual, query) + w·cos(tag, query), with default w = 0.3. Optional filters: `motion_min` (about 1.5 drops dead-still clips), kind, `exclude_ids` (already used). The docstring treats **≥ 0.25 as a rough "acceptable" CLIP B/32 score**.
  - `find_similar_set`: MMR. score = (1−λ)·sim(seed) − λ·max sim(already picked), with λ = diversity (default 0.3) over a candidate pool of 30.
  - `diversify`: greedy most-mutually-dissimilar subset, blended with original rank order.
  - Brute-force dot products. The docs say no FAISS is needed for a few hundred to a thousand rows (load under 50 ms).
- **`tools/video/clip_cache.py`:** a cross-project bytes cache at `~/.openmontage/clips_cache/`. It hard-links (copying across drives), keeps an atomic JSONL manifest with a file lock, and evicts LRU at a 20 GB cap.
- **`direct_clip_search.py`:** the fast path with no embeddings (download plus one thumbnail each) when the agent will eyeball the results.
- **17 stock adapters** in `tools/video/stock_sources/`: Pexels, Pixabay, Archive.org, NASA, ESA, JAXA, NOAA, NARA, LoC, Wikimedia, Openverse, Unsplash, Coverr, Mixkit, Videvo, Dareful, Pond5-PD.
- **Licence handling:**
  - Each candidate records a `license` string.
  - **Only Openverse filters** (`license_type=commercial,modification` by default).
  - Wikimedia records "verify per-file license", and Archive.org records `licenseurl` when present.
  - **No downstream gate** stops a CC-BY-SA or unknown-licence clip from being used.

**Dependencies:** torch, transformers, the CLIP weights (OpenAI CLIP is published under MIT; verify the model card), opencv and numpy.

**Clean-room build for us (S–M):**
- **Reuse:** our `stock.py` already fetches Pexels and Pixabay at edit time; our perception has scene cuts; `licences.py` and the licence registry are on the current branch.
- **Add:**
  1. For each b-roll slot, fetch about 15–30 candidates and run CLIP (or SigLIP) on 3–5 frames per candidate.
  2. Fuse with tag similarity and re-rank against Claude's slot description *plus the spoken words in that window*.
  3. MMR across the reel so adjacent b-roll differs.
  4. Gate on our licence registry. **We should be stricter than them.**
  5. Cache embeddings per asset id.
- **Risks:** CLIP on CPU costs about 150–300 ms per image (their figure), so roughly 30 s per reel. Hinglish slot text needs translating to English before the text encoder. Archive and NASA content fits Indian brand reels poorly.

**Cost:** free (local model). Stock APIs are free.

#### B2. Music generation, video-to-music and cut-fitted scores [code]

**What the user sees:**
- (a) "Generate a 30 s lo-fi bed": ElevenLabs Music, Google Lyria, Suno, or local ACE-Step via ComfyUI.
- (b) **"Score this cut"**: upload the edited video and get back a soundtrack composed *to the picture*, optionally with SFX and separate stems.
- (c) A deterministic local score whose chord changes and drum hits land exactly on every cut.

**How it works:**
- `tools/audio/music_gen.py`: ElevenLabs `/v1/music`, cost estimated at about **$0.05 per 30 s**. `force_instrumental` is tested.
- `google_music.py`: Lyria. The code comment says "Lyria 3 Pro is a flat **$0.08 per request**" (Lyria 3.5 is left unpriced).
- `suno_music.py`: talks to **`api.sunoapi.org`**. Comment: "Suno credits cost $0.005 each; a generation is roughly 10 credits", which works out to about $0.05.
- `comfyui_music.py`: local GPU, bundled model stack "ace-step-1-t2a", $0.
- `elevenlabs_soundtrack.py`: ElevenLabs **video-to-music** (`/v1/music/video-to-music`).
  - Up to 10 videos, ≤ 200 MB and ≤ 600 s combined.
  - Options: `description`, ≤ 10 `tags`, `add_sfx`, `separate_tracks` (returns a ZIP of stems that is safely unpacked: no absolute paths, `..` or colons; audio extensions only; ≤ 500 MB), `use_audio_as_reference`, and a model id.
  - Cost is **"unquoted"** (`cost_usd=None`).
- `minicut_music_fit.py`: takes the timeline (from `edit_decisions` cuts, accounting for speed) or cut times plus length. It writes a "song" data file with a four-chord loop in a chosen key and mode, one chord per shot, pulses that restart on each cut so every shot begins on a beat, and a low percussion hit on every cut after the first, plus a short master fade-out. A **closed MiniCut CLI** (needs `minicut login`, about 396 MB of samples) renders it locally to a WAV exactly the cut's length. Same cuts in, same song out. Trimming a shot changes only that shot's notes.
- `music_library.py`, `pixabay_music.py` (scrapes Pixabay's site, with bot-protection handling), `freesound_music.py`: free retrieval.

**Dependencies/licences:**
- ElevenLabs: paid key; check its commercial terms for generated music.
- Suno via sunoapi.org: **third-party reseller, red flag**.
- Lyria: Google key.
- ACE-Step: licence not stated in repo; verify.
- MiniCut: closed CLI with an account.
- Pixabay scraping: ToS risk.

**Clean-room build (S for API, M for cut-fit):**
- **Video-to-music** is the client wow. Send our *final cut without music* to the provider, get a bed scored to the picture, and run it through our existing ducking and beat alignment.
- Cut-fit procedural scoring could be built ourselves: MIDI from our timeline's cut list, rendered with FluidSynth and a permissively licensed soundfont. That is cheap, offline and perfectly aligned. Its musical quality is "corporate underscore", so it is fine for brand reels but not trendy creator reels.
- **Indian creators mostly want trending audio**, which generation can't legally provide.

**Cost:** ElevenLabs music about $0.05/30 s (code estimate); Lyria 3 Pro $0.08/request (code comment); video-to-music unquoted.

#### B3. SFX generation [code, thin]

**What the user sees:** a "whoosh with a glassy tail, 0.8 s" generated on demand.

**How it works:**
- The only generator is **`minicut_sfx.py`** (ElevenLabs Sound Effects v2 *through the closed MiniCut CLI*; a `dry_run` returns a price quote that must be approved).
- There is also the `add_sfx` flag on ElevenLabs video-to-music.
- There is a Layer-3 skill `.agents/skills/sound-effects/` documenting the ElevenLabs SFX API, but **no first-party direct tool**.

**Clean-room build (S):**
- Call a sound-generation API directly when Claude's finish pass asks for an SFX our 252-item library can't match (low retrieval score).
- Cache the result into the library with a licence record.
- Paid key.

**Cost:** not stated (MiniCut quotes per request).

#### B4. TTS and voice cloning [code]

**What the user sees:** narration in any of about 18 providers' voices, auto-chosen by the 7-dim scorer, with a **sample gate** before batch generation. Voice cloning is reused by id.

**How it works:**
- Providers: ElevenLabs, Google (Chirp3-HD), Azure, OpenAI, Fish Audio, Cartesia, Inworld, Kling, HeyGen, DashScope/Qwen, Doubao, Grok, Mistral, Gemini, MAI, MiniCut, and local Piper. `tts_selector` ranks them.
- **Cloning:** there is **no clone-creation flow in code**. Tools accept a pre-made voice id: Fish Audio `reference_id` ("reuse a cloned voice"), ElevenLabs `voice_id`, and HeyGen "instant voice" for `heygen_voice_convert` (speech-to-speech conversion).
- ElevenLabs cost estimate: **$0.0003 per character** [code]. Qwen3-TTS-flash about $0.000015/char [PROVIDERS.md].
- `skills/meta/voice-performance-director.md` [skill] sets a delivery contract, writing rules, a provider mapping and a sample gate.
- **Hindi:** the code doesn't special-case `hi-IN` anywhere except Azure STT, but Google, Azure and ElevenLabs accept language codes generically, so Hindi is *likely workable but untested here*.

**Clean-room build (M):**
- For us, TTS matters for: (a) **fixing a flubbed word** in the client's own voice (clone the voice from their footage, regenerate a phrase, splice it with our word-level timing), (b) brand reels with VO, and (c) dubbing (C-pipeline).
- Requires explicit **consent capture** for cloning.
- Use ElevenLabs or Sarvam-class Indian-language voices (Sarvam isn't in their repo).

**Cost:** per character (above).

#### B5. AI avatar and lip-sync [code]

**What the user sees:** a digital presenter speaking a script (HeyGen Avatar, Kling Avatar), or the original speaker's lips re-synced to new audio (Kling lip-sync, local Wav2Lip).

**How it works:**
- `tools/avatar/heygen_avatar.py`: "Avatar V digital-twin presenters", paid.
- `kling_avatar.py`: estimate **$0.35 base, ×1.7 for pro, +$0.04 with audio**, p50 240 s.
- `kling_lip_sync.py`: **$0.32 advanced / $0.34 full / $0.02 face-identify**.
- `lip_sync.py`: shells out to a local Wav2Lip checkout (`WAV2LIP_PATH`); the docstring mentions MuseTalk but the enum is only wav2lip/wav2lip_gan.
- `talking_head.py`: SadTalker (photo to talking head).

**Licences:** Wav2Lip: **verify; upstream terms restrict commercial use**. SadTalker and MuseTalk: not stated in repo; verify. HeyGen and Kling: paid APIs.

**Clean-room build (M via API):**
- Useful for **dub lip-sync** (C) and "brand explainer with presenter" when a client won't shoot.
- Needs a likeness-consent record and a disclosure watermark policy.

#### B6. Talking-head "beauty pass": face and eye enhance [code]

**What the user sees:** subtle skin smoothing, sharpening, shadow lift, **under-eye dark-circle brightening and iris brightening/sharpening** on talking-head footage, all on CPU.

**How it works:**
- `tools/enhancement/face_enhance.py`: named FFmpeg filter presets: edge-preserving `smartblur` for skin, `unsharp` sharpen at two strengths, and shadow/midtone lift for poorly lit footage.
- `eye_enhance.py`: MediaPipe Face Mesh (468 landmarks plus iris landmarks 468–477) locates the under-eye region (lower-lid landmarks) and the iris, then applies targeted OpenCV brightening and sharpening frame by frame.
  - Defaults: dark-circle intensity 0.4, and 0.3 for the brighten and sharpen controls.
  - Falls back to region-based FFmpeg filters if MediaPipe is missing.
- Both are optional tools in the talking-head compose stage.

**Dependencies:** FFmpeg; MediaPipe (Apache-2.0) and OpenCV (Apache-2.0).

**Clean-room build (S):**
- We already track faces. Add a per-frame landmark-masked adjustment (under-eye lift, iris pop, skin smoothing inside a face mask only) as a finish-pass option with a strength slider.
- Must be subtle, and **opt-in per client**: some creators find beautification off-brand.
- Risk: temporal flicker in masks. Smooth the landmarks over time, as we do for punch-ins.

**Cost:** free.

#### B7. Face-tracked auto-reframe [code]

`tools/video/auto_reframe.py` converts 16:9 to 9:16 by face detection, a smoothed box trajectory and an FFmpeg crop. **We already do this** (9:16 plus 4:5/1:1 variants), so skip.

---

### C. Rendering

#### C1. HyperFrames (HTML/CSS/GSAP renderer) [code wrapper + vendored skills + README]

**What the user sees:** motion-graphics-heavy compositions (kinetic type, product promos, launch reels, website-to-video, SVG character rigs, Three.js worlds) authored as **plain HTML + GSAP**. There is a registry of drop-in blocks (charts, grain overlay, shimmer sweep, shader transitions). There is also a "music-to-video" workflow where a beat-grid analysis drives the cuts.

**How it works:**
- `tools/video/hyperframes_compose.py` [code] materializes a workspace from `edit_decisions` plus `asset_manifest` (index.html, CSS, copied assets) under `projects/<name>/hyperframes/`. It then runs the upstream CLI via `npx hyperframes`: `lint` → `check`/`validate` → `render`, with a `--strict` option. Other operations include `inspect`, `scaffold_workspace`, `render_existing` (atelier) and `add` (a registry block). It prefers the npx offline cache and requires Node ≥ 22.
- The composition contract [vendored skill `.agents/skills/hyperframes-core`] is:
  - timing declared on DOM elements with `data-*` attributes (start/duration/track), plus sub-compositions
  - a **seekable** GSAP timeline built synchronously at page load
  - framework-owned media playback
  - determinism rules (banned non-deterministic APIs and an animatable-property allowlist)
  - render duration taken from the root `data-duration`
  - headless Chrome for validation and frame capture
- `music-to-video` [vendored skill] runs a deterministic beat-grid analyzer that writes an `audiomap.json` (beats, phrases, energy, onsets). Workers write frame files per beat group, assembled deterministically.
- **Policy** [skill, AGENT_GUIDE]: when both Remotion and HyperFrames are installed, the agent *must* present both and log the choice. Several pipelines (clip-factory, localization) are locked to Remotion because HyperFrames has no word-level caption burn parity.

**Licences:**
- HyperFrames is HeyGen's (`heygen-com/hyperframes`, vendored skills v0.7.17); **its licence is not stated in this repo, so verify**.
- The GSAP *skills* are stated as MIT (`.agents/skills/gsap/README.md`). The **GSAP library's own licence is a custom no-charge licence, not OSI**; verify its restrictions.

**Clean-room build (L, low marginal value):**
- We already have Remotion for overlays.
- What's worth stealing is the *pattern*: (a) a **lint/validate/inspect gate** before render (headless snapshot of N frames to catch layout overflow or contrast issues), and (b) a **beat-grid audiomap** artifact consumed by both cut placement and motion graphics.
- Do not add a second renderer.

**Cost:** free (local), except the HeyGen BGM/catalog features [skill].

---

### D. Reference-video analysis: theirs vs ours

**Theirs** [code: `tools/analysis/video_analyzer.py`; skill: `skills/meta/video-reference-analyst.md`]:
1. Download with yt-dlp; transcribe with faster-whisper; detect scenes.
2. Pacing profile: average, shortest and longest scene; cuts per minute; style by average scene length (> 10 s slow_contemplative, > 5 s steady_educational, > 2 s dynamic_social, else rapid_fire).
3. **Per-scene motion classification** with Farneback optical flow at 360p over 2–3 frame pairs, 0.4 s apart:
   - mean magnitude < 0.5 → `static_image`
   - variance < 2.0 → `animated_still` (Ken Burns-type pan or zoom on a still)
   - otherwise → `motion_clip`
4. Keyframes at each scene start plus midpoints for scenes over 3 s (plus quarter points in "deep" mode).
5. Audio-energy offset.
6. WPM; complexity (> 300 s or > 30 scenes = complex).
7. "Motion required" if at least 30% of scenes are motion clips.

- **Everything descriptive** (scene descriptions, visual_type, palette, typography, transitions, music style, closest playbook) is **left blank for the agent to fill by looking at keyframes** [skill].
- The skill mandates a "5-aspect" per-shot breakdown (subject, subject motion, scene with overlays as their own layer, spatial framing, camera), marking N/A explicitly. It also mandates **2–3 differentiated concepts, never a carbon copy**, and a **sample-first** render [skill].
- `_suggest_pipeline` maps every IG, TikTok or Shorts reference to the `animation` pipeline [code]. That is crude.

**Ours** already extracts style from references with real perception (ASR, cuts, faces, OCR, palette). Worth borrowing:
1. **Optical-flow motion typing** per shot (static, Ken Burns, real motion). It is cheap and helps classify b-roll style in reference reels.
2. **Separate "overlay layer" captioning** (text, graphics, lower thirds called out apart from the setting). We get this partly from OCR.
3. The **"differentiate, don't clone" rule** plus 2–3 concept options.
4. **Reference → cost/scene-count estimate** (A2).

---

### E. Pipelines: what each is, and fit for an Instagram-reel freelancer serving Indian creators/brands

Common skeleton: YAML stages + director skills + gates. Effort is for *our* stack.

| Pipeline | What it is (evidence) | Key tools | Fit for us | Effort |
|---|---|---|---|---|
| **Talking Head** | Raw speaker footage → transcribe, plan (frame sampler, face tracker, silence cutter), subtitles, mix, compose; optional face/eye enhance, colour grade, reframe, Remotion word captions. `beta`, $0.50 budget [YAML] | transcriber, silence_cutter, subtitle_gen, remotion_caption_burn | **This is our core, and ours is deeper** (story/finish passes, motion graphics, b-roll, QA, NLE export). Take only face/eye enhance | — |
| **Clip Factory** | Long source → ranked candidate moments → N independent shorts. Scoring on hook, coherence, value, energy, platform_fit; a **standalone test** (reject unresolved pronouns, references to earlier context, long lead-ins, endings before the payoff); diversity across sections, speakers, families and energy; yield targets 15–30 min → 3–6 clips, 30–60 → 5–10, 60+ → 8–15 [**skill**; no scoring code]. Remotion only. $1 budget, beta | transcriber, scene_detect, video_trimmer, video_compose | **Very high.** Podcasts, YouTube long-form and webinars are common for Indian creators and edtech brands. Plugs straight into our engine: the story pass becomes a "mine N clips" pass | **M** |
| **Podcast Repurpose** | Podcast audio or video → audiogram/caption-led clips, quote cards, optional full-episode companion [YAML + skill] | transcriber, audio_enhance, image_selector, diagram_gen | **High** for video podcasts (same as Clip Factory). Audio-only audiograms are medium (less IG-native) | S on top of Clip Factory |
| **Hybrid** | Source footage + generated/designed support (diagrams, overlays, gen-AI inserts) [YAML] | image/video selectors, compose | **High.** We already do source + stock b-roll + graphics. The delta is **AI-generated inserts** when stock fails (paid) | **M** |
| **Localization & Dub** | Transcript-first: translated subtitles → dubbed audio per language → optional lip-sync. Glossary/protected terms; hero-scene dub sample; drift tolerance 0.5 s; "languages expand 20–30%" [**skill**]. **No translation tool** (the agent translates) and **no duration-fitting code** (no time-stretch, re-pacing or segment fitting; only prose warnings). $3 budget, beta | tts_selector, subtitle_gen, lip_sync, audio_enhance | **Very high value** (Hindi ↔ English ↔ Tamil/Telugu/Marathi/Bengali reach for brands). Theirs is a scaffold; we would have to build the hard parts: segment-level timing fit, voice clone, mix over the original M&E, optional lip-sync | **L** |
| **Avatar Spokesperson** | Script → avatar presenter (HeyGen/Kling) + simple graphics; gates on lip-sync quality and framing [YAML] | heygen_avatar, kling_avatar, tts | **Medium.** D2C brands without on-camera talent; needs a consent and disclosure policy; paid ($0.35+/clip for Kling, code estimate) | **M** (API) |
| **Screen Demo** | Real capture (callouts, zoom crops, cleaned audio) **or** a synthetic deterministic Remotion TerminalScene with frame-accurate cue alignment (`lib/verify_scene_pacing.py` checks each narration cue has a visual landmark within ±1 s, and flags overflow, or underfill > 5 s) [code + YAML] | screen_recorder, TerminalScene | **Low–medium** (SaaS/edtech clients only; the terminal mode is niche) | M |
| **Animated Explainer** | Fully generated: research (≥ 5 cited sources) → 3 concepts with cost → sample → script → TTS + gen images/video → Remotion. README demo "THE LAST BANANA", 60 s, **$1.33** [README] | tts/image/video selectors | **Low–medium.** Faceless explainer reels exist in India (finance, facts) but it's a different product from editing client footage | L |
| **Animation** | Motion graphics, kinetic type, Manim math, Three.js worlds, Lottie; character-animation variant with SVG rigs + GSAP [YAML] | HyperFrames, Remotion, manim, threejs_world | **Low** as a pipeline. Pieces (kinetic type, logo stings) we already cover via Remotion | L |
| **Cinematic** | Mood-led trailers and brand films from supplied footage + optional gen inserts; checks hero_moment, camera movement and lighting coverage [YAML + slideshow-risk code] | video_selector, color_grade | **Medium** for brand launch teasers (wow); mostly a styling preset on our engine plus gen inserts | M |
| **Documentary Montage** | Retrieval-first montage from a CLIP-indexed archive corpus; tone→hold table (elegiac base 4 s, min 2.5, max 7; urgent 1.2/0.5/2.5); total hold within ±10% of target; heroes on downbeats; no two adjacent cuts share subject *and* scale; uniform grade for mixed-era footage [skill + code corpus]. $1, beta | corpus_builder, clip_search, color_grade | **Low** (Western public-domain archives, essay tone). The **CLIP retrieval and adjacency-diversity rules transfer** to our b-roll (B1) | — |

#### E1. Clip Factory: long-form → ranked batch of standalone shorts (full card)

**What the user sees:** "Here's your 52-minute podcast. I found 14 candidate moments, ranked them, and selected 7 clips: 2 hooks, 2 stories, 2 tips and 1 hot take. Each one stands alone. 9:16 with captions." The batch is approved once, then rendered N times.

**How it works:**
- **Stages [YAML `pipeline_defs/clip-factory.yaml`]:** idea → script → scene_plan → assets → edit → compose → publish. Gates are at idea, script, scene_plan, assets and publish. Default budget $1, `beta`. Runtime is locked to Remotion (word-level caption burn) or FFmpeg (pure trim).
- **Tools [code]:** transcriber (faster-whisper/WhisperX family), scene_detect, frame_sampler, subtitle_gen, audio_enhance, video_trimmer, video_compose, audio_mixer.
- **Selection logic is entirely [skill]** (`skills/pipelines/clip-factory/idea-director.md`, `script-director.md`). No scoring code exists:
  - The transcript is the "search surface".
  - Each candidate is scored on **hook, coherence, value, energy, platform_fit**. The brief must define the ranking criteria *before* extraction starts.
  - Clip "families" (hook, story, tip, and so on) make up a portfolio, not the same energy repeated.
  - **Standalone test:** reject or widen any clip with unresolved pronouns, references to earlier context, a long lead-in before the point lands, or an ending before the payoff.
  - Diversity across source sections, speakers, families and energy levels. Rank by quality, not chronology.
  - **Yield targets:** a 15–30 min source gives 3–6 clips, 30–60 min gives 5–10, and 60+ min gives 8–15. Never pad.
  - Per-candidate record (stored in `script.metadata`): source in/out, hook text, the reason selected or rejected, per-dimension scores, and **crop viability**. Batch-level fields: `candidate_clips`, `selected_clip_ids`, `ranking_model`, `rejected_candidates`, `source_coverage_map`, `platform_assignments`.
  - `scene_detect` is used only to sanity-check boundaries near promising moments.

**Dependencies/licences:** local ASR and FFmpeg, plus Remotion (we already hold the licence position). No paid API beyond the LLM.

**Clean-room build for us (M):**
- **Reuse:**
  - word-level Hinglish ASR
  - speakers and faces (crop viability, i.e. is the speaker trackable in 9:16 for this span)
  - the Claude story pass
  - the finish pass, compile, QA and NLE package per clip
- **Build:**
  1. A **mining pass**: Claude over the full transcript in overlapping chunks, emitting candidates with the five scores plus a standalone-test verdict. Make the standalone test a separate, cheaper Claude check.
  2. Deterministic post-filters: duration window (for example 20–75 s), minimum speech density, face-trackable ≥ 90% of the span, no mid-word boundaries (snap to VAD silences).
  3. Diversity selection (MMR over transcript embeddings plus a family quota).
  4. Batch orchestration that runs our existing per-reel pipeline N times, with a shared colour/caption style.
  5. A web-app "pick your clips" approval screen.
- **Risks:**
  - Hinglish hook detection quality.
  - Multi-speaker podcasts (needs a speaker-switch or split-screen layout).
  - Render time × N, which makes A9-style caching matter.

**Cost:** repo states only the $1 default budget. For us it is Claude tokens over a long transcript plus local render.

#### E2. Localization & Dub (full card)

**What the user sees:** "Your English reel in Hindi, Tamil and Telugu: translated captions, dubbed voice per language, original music and SFX kept, and a lip-sync option on close-ups." A 10-second hero-scene dub sample comes first for voice approval.

**What OpenMontage actually has:**
- **[YAML]:** stages idea → script (transcriber) → scene_plan (frame_sampler, scene_detect) → assets (tts_selector, subtitle_gen, optional lip_sync, audio_enhance) → edit → compose (Remotion/FFmpeg only) → publish. Gates on idea, script, scene_plan, assets and publish. Default budget **$3**, `beta`, max wall time 15 min.
- **[skill]** (`skills/pipelines/localization-dub/*`):
  - Source and target languages and a dub mode per deliverable are set at the idea stage.
  - A **glossary of protected terms** (brand and product names stay untranslated).
  - `timing_drift_tolerance: 0.5 s`, and the warning "some languages expand 20–30%".
  - Subtitles are produced first as the fallback deliverable.
  - A **hero-scene dub sample** gate before batch TTS.
  - Lip-sync is "optional, only for shots that can support it".
  - Metadata maps: subtitle, dub and lip-sync assets per language, `voice_map`, `pronunciation_warnings`, `blocked_assets`.
- **What is missing in code:**
  - **No translation tool.** The agent translates in-context.
  - **No duration fitting** anywhere: no time-stretch, re-pacing, segment alignment or retime of video.
  - **No separation** of dialogue from music and effects (M&E).
  - Lip-sync is local Wav2Lip (licence-restricted) or the Kling API.

**Dependencies/licences:** TTS providers (paid keys: ElevenLabs, Google, Azure and others); Kling lip-sync (paid); Wav2Lip (**verify; commercial restrictions upstream**).

**Clean-room build for us (L):**
- **Reuse:**
  - word-level ASR with segment timings
  - VAD
  - voice enhancement
  - the caption families (Devanagari and other scripts need font checks)
  - ducked mixing
  - the NLE package (per-language stems)
- **Build:**
  1. Claude translation with glossary and register control (Hinglish → Hindi or English), with a **human review screen** per segment.
  2. **Segment-level timing fit.** Per ASR segment, target duration = the original span ± tolerance. Ask Claude for a length-constrained rewrite first; then apply bounded time-stretch (about ±10–12%); then borrow from adjacent pauses; as a last resort, extend the video with a freeze or b-roll cutaway.
  3. A cloned-voice TTS of the client (consent record) or a stock Indian-language voice.
  4. **Dialogue/M&E separation** (source-separation model; check its licence) so the original music and SFX survive under the new voice.
  5. Optional lip-sync on close-up shots via a commercial API, gated by face-size and angle from our perception.
- **Risks:** translation naturalness in Indian languages, TTS prosody for Hinglish, lip-sync licence, render × languages.

**Cost (repo-stated units only):**
- $3 default pipeline budget
- ElevenLabs TTS $0.0003/char (code)
- Kling lip-sync $0.32–0.34 per job (code)
- Qwen3-TTS about $0.000015/char (PROVIDERS.md)

---

## 4. Where we are already ahead (don't rebuild)

- **Talking-head editing depth:** take selection, pause tightening, punch-ins, transitions, motion graphics, kinetic captions, hook title with text-behind-subject, Lottie, effects. Theirs is transcribe → silence cut → subtitles → compose.
- **Perception:** we have VAD, faces, OCR, speakers, palette and Hinglish ASR. Theirs relies on the agent's eyes on keyframes for anything descriptive.
- **QA:** we have a Reviewer persona plus automatic gates over the render. Their `visual_qa` only extracts frames and probes.
- **Delivery:** NLE package (FCPXML/OTIO, stems, captions, cover, licence manifest), aspect variants, client review links, revise-from-notes. They have an `export_bundle` and nothing client-facing.
- **Licence discipline:** our licence registry and the current `engine/licence-gate` work are stricter than their record-only approach.

---

## 5. Licence and red-flag register

| Item | Status in repo | Risk for us |
|---|---|---|
| OpenMontage itself | **AGPL-3.0** | Copy no code or prompts verbatim. This note is description only |
| Wav2Lip (`tools/avatar/lip_sync.py`) | Not stated; shells out to user checkout | **Red flag:** upstream terms are widely understood to restrict commercial use. Verify; prefer a commercial lip-sync API |
| SadTalker / MuseTalk | Not stated | Verify upstream before any use |
| Suno via `api.sunoapi.org` | Third-party endpoint | **Red flag:** looks like a reseller, not Suno. Generated-music rights unclear |
| MiniCut (`minicut_*`) | Closed CLI, login, credits | Vendor lock-in; not reusable |
| HyperFrames | Vendored skills v0.7.17 from `heygen-com/hyperframes`; licence **not stated** | Verify if ever used |
| GSAP library | Only the GSAP *skills* are stated MIT | GSAP's own licence is custom, not OSI; verify |
| ACE-Step (ComfyUI music) | Not stated | Verify |
| BLIP-2 (OPT-2.7b) in `video_understand.py` | Not stated | Verify OPT weights licence |
| CLIP ViT-B/32 | Not stated in repo | OpenAI CLIP is MIT (verify model card) |
| MediaPipe, OpenCV, faster-whisper | Not stated | Apache-2.0 / Apache-2.0 / MIT (standard; verify versions) |
| Stock: Wikimedia, Archive.org, NASA/ESA/JAXA etc. | Licence string recorded, **not gated** (only Openverse filters to commercial+modification) | Mixed CC-BY-SA, BY-NC and PD content can slip through. Our gate must reject NC/ND/unknown |
| Pixabay music (`pixabay_music.py`) | Scrapes the website, with bot-protection handling | ToS risk; use the official API or our library |
| yt-dlp reference download | Used by `video_analyzer` | Platform ToS: analyse only, never reuse footage |
| Paid keys | ElevenLabs, fal.ai, Kling, HeyGen, Google, OpenAI, Runway, etc. | Each feature that uses them needs a budget cap (A2) |

---

## 6. Costs stated in the repo (no invented numbers)

- **Per video (README demos):** "THE LAST BANANA" 60 s animated short, **$1.33**; "Reimagine Your Universe" 50 s vertical, **about $4**; "Imagine the Possibilities" showcase, **about $5** source generation. README tiers: "with an image/video provider ~$0.15–$1.50", "full setup ~$1–$3".
- **Pipeline default budgets (YAML):** talking-head $0.50; clip-factory, podcast, documentary and screen-demo $1; explainer, animation, cinematic, hybrid and avatar $2; localization $3.
- **In-code estimates:**
  - ElevenLabs TTS $0.0003/char
  - ElevenLabs music about $0.05/30 s
  - Lyria 3 Pro $0.08/request
  - Suno about 10 credits × $0.005
  - Kling avatar $0.35 (pro ×1.7, +$0.04 with audio)
  - Kling lip-sync $0.32–0.34 (face identify $0.02)
  - ElevenLabs video-to-music "unquoted"
- **PROVIDERS.md tables:**
  - Kling 2.5 Turbo Pro $0.07/s, Veo 3 $0.40/s, WAN 2.5 $0.05/s
  - Seedance 2.5 $0.134/s, Seedance 2.0 $0.112/s
  - FLUX Pro $0.05/image, FLUX Dev $0.03/image
  - Grok video $0.05–0.07/s
  - Pika: a 768p 10 s clip is about $0.20

---

## 7. Ranking: top 8 to build clean-room

**Formula:** score = wow (1–5) × fit (1–5) ÷ effort (S = 1, S–M = 1.5, M = 2, L = 3).
- **Wow** means what a *client* notices in the delivered reel or the service.
- **Fit** means fit for a freelance IG-reel editor serving Indian creators and brands, which mostly comes down to whether the feature plugs into our existing source-footage engine.
- Scores are my judgement. The arithmetic is shown so the order can be re-weighted.

| # | Feature | Wow | Fit | Effort | Score | One-line reasoning |
|---|---|---|---|---|---|---|
| 1 | **Talking-head beauty pass** (masked skin smoothing + under-eye/iris enhance; B6) | 3 | 5 | S (1) | **15.0** | Every creator notices "I look fresher"; we already track faces; free; Apache-licensed libs. |
| 2 | **Clip Factory**: long-form → ranked batch of standalone reels, incl. video podcasts (E1) | 5 | 5 | M (2) | **12.5** | One podcast or YouTube upload becomes 5–10 reels on our existing engine; we need only a mining pass plus batch orchestration. |
| 3 | **CLIP/SigLIP re-rank + MMR diversity** for our Pexels/Pixabay b-roll (B1) | 3 | 4 | S (1) | **12.0** | B-roll that matches the spoken line and doesn't repeat; local and free; pairs with our licence gate. |
| 4 | **Video-conditioned music ("score this cut")** + cut-fitted bed (B2) | 4 | 4 | S–M (1.5) | **10.7** | Escapes our 33-track library with music scored to our cuts; plugs into existing ducking; paid API, price unquoted. |
| 5 | **Localization & dub** (Hindi ↔ English ↔ regional) with voice clone + timing fit (E2) | 5 | 5 | L (3) | **8.3** | Biggest reach lever for Indian brands, but theirs is a prompt scaffold; translation review, duration fitting, M&E separation and cloned TTS are all ours to build. |
| 6 | **On-demand SFX generation** as library fallback (B3) | 2 | 4 | S (1) | **8.0** | When the finish pass can't match a sound from our 252 SFX, generate, cache and licence-record it. |
| 7 | **Hero-sample approval** (render only the hook, in 2 looks, for a client pick; A4) | 2 | 4 | S (1) | **8.0** | Cheap client-trust win that cuts full re-renders; reuses review links. |
| 8 | **Content-addressed render cache → segment-level re-render on revision** (A9) | 3 | 5 | M (2) | **7.5** | Directly attacks our known whole-stage re-render gap; clients feel it as faster revision turnaround. |

**Just below the line:**
- Generated inserts with provider routing and budget caps (Hybrid, A1/A2): 4×3/2 = 6.0. It becomes worth it once we have at least 2 generative providers.
- Timeline monotony lint (our fact-based slideshow-risk, A6): 1×5/1 = 5.0.
- AI avatar presenter and lip-sync (B5): 4×2/2 = 4.0. Needs consent and a commercial-safe provider, not Wav2Lip.
- Decision trail in the web app (A3): 1×4/1 = 4.0.
- Reference → cost quote (A2): 1×3/1 = 3.0.

**Deliberate override to consider:**
- By formula, Localization ranks 5th only because it is L effort.
- Strategically it is the only item that opens a *new revenue line* (multi-language variants per reel), so it deserves an early design spike even if it is built after #1–#4.

**Skip:**
- HyperFrames: a second renderer, L effort, low marginal value over Remotion.
- Documentary Montage: archive-centric.
- Animation, Explainer and Cinematic as standalone pipelines: a different product.
- The Backlot board: we have a web app; maybe "replay the edit" later.
