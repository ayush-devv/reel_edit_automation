# ADR-0028: Quality judged by a hired pro editor + audience data (owner is not an editor)

- **Status:** Accepted (owner decision, 2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Amends:** ADR-0014 (gold set), ADR-0021 (release acceptance)

## Context
ADR-0014/0021 assumed the owner could set and judge pro quality. The owner is a software engineer, not a professional editor.

## Decision
- **Gold set:** raw footage from the owner, friends or clients (with permission). Gold finals edited by a **hired freelance pro editor** for at least part of the set (enables the automatic metrics: hook match, word-keep F1, order, cut-rate ratio).
- **Per build (free, automatic):** Claude Reviewer with a rubric generated from the knowledge graph (advisory) + **style match** to the pro reference library for the reel's genre (pace, hook timing, caption density, music sync).
- **Release acceptance (replaces the owner-as-judge rule in ADR-0021):**
  1. The **hired pro editor** rates each of the 6 holdout reels on its own — "sendable to a paying client with no edits" — pass = ≥ 5 of 6, and no reel the tool marked `sendable` is rated not sendable.
  2. **Audience check:** a few tool reels posted on a test account; retention/completion compared with comparable reels in the same genre (directional, not a hard gate unless enough posts exist).
  3. The owner's own rating is recorded as the **client's view**.
- Pro-editor notes and audience results feed the learning loop (ADR-0027).

## Consequences
- **Good:** an independent expert verdict and real-world signal; no dependence on the owner's editing skill.
- **Bad:** paid reviews (rates vary — check Fiverr/Upwork); audience data is slow and noisy.
