# ADR-0027: Expert knowledge system + learning loop ("training" Claude without changing its weights)

- **Status:** Accepted (owner decisions, 2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Amends:** ADR-0016 (playbook split), ADR-0011/0017 (caption families) — the playbook becomes one input to this system.

## Context
The owner is a software engineer, not a professional editor, and wants Claude to edit at master level. Claude's weights cannot be changed by us; Claude already knows general editing theory. What turns a general model into an expert *in this tool* is: a complete action space, precise "when/why/how much" knowledge, annotated examples, and a feedback loop that updates that knowledge based on measured results. Public sources first; owner's course/book files later.

## Decision — four layers + one loop
1. **Capability catalog (what can be done):** every operation an NLE offers (Premiere, Resolve, CapCut, After Effects): cut/trim, transitions, transform/keyframes, speed/ramps, colour, audio FX, text/captions, graphics, compositing/masks, effects, export. Each entry: parameters, typical ranges, renderer owner (ffmpeg / Remotion / not supported), timeline-schema field. `knowledge/capabilities.yaml`. Coverage of the timeline schema is checked against it.
2. **Craft knowledge graph (when, why, how much):** nodes `Principle`, `Technique` (→ capability), `Genre` (talking-head, testimonial, product, tutorial, vlog, montage…), `Platform`, `Goal/Effect` (retention, clarity, emotion, energy), `Parameter`, `AntiPattern`, `Example`, `Source`; edges `achieves`, `applies_to`, `uses`, `conflicts_with`, `requires`, `demonstrated_by`, `cited_from`. Files in `knowledge/graph/*.yaml` (no graph database needed at this size). Every node is a **paraphrased** principle with a citation — never copied text (copyright).
3. **Reference reel library:** 50–100 pro reels per genre analysed for personal study — measured style vectors (cut rate, shot lengths, hook timing, caption density, typography, music sync, colour) + Claude-written breakdowns like `analysis/bathroom/notes.md`. Store measurements and notes, not the videos for redistribution.
4. **Compilation into each run:** classify the reel's genre → load core principles (~8, always), the genre playbook (retrieved subgraph), 2–3 annotated example breakdowns, the capability catalog as the schema/vocabulary; mechanical rules go to the compiler and QA gates; the Reviewer's rubric is generated from the same graph.
5. **Learning loop (the "training"):** every evaluated reel produces lessons — pro-editor notes, audience retention, QA failures, Claude self-review — that become **proposed graph edits** (new rule, changed parameter range, rule priority per genre, new anti-pattern). A proposed edit is adopted only if it improves the tuning-set score without regressing (eval-driven, versioned knowledge). This is how the system improves over time without weight updates.

**Optional later — real neural training where it pays:** once there are hundreds of labelled reels (pro verdicts, audience retention), train small local models for narrow judgments Claude is weak at: retention predictor, hook strength scorer, cut-point quality. Claude stays the decision-maker; these become inputs.

## Build of knowledge v1 (public sources)
Parallel extraction agents per source family → candidate cards with citations → de-duplicate and resolve conflicts (prefer platform data > studies > practitioner consensus > single opinions) → sample reviewed by the hired pro editor → versioned release of `knowledge/`.
Source families: editing classics (e.g. Murch's rule of six, film-grammar texts), platform creator guides (Instagram, YouTube Shorts, TikTok), research (already in `docs/research/`), public short-form editing courses/tutorials (paraphrased), NLE manuals (capabilities), pro reel breakdowns.

## Consequences
- **Good:** expertise does not depend on the owner; knowledge is inspectable, versioned and measured; improves with every evaluated reel.
- **Bad:** extraction and curation effort; more knowledge can make edits worse unless every change is measured; copyright discipline required.
