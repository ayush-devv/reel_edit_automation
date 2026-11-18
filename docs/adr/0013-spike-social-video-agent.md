# ADR-0013: Trial social-video-agent before building (fork vs build)

- **Status:** Superseded by ADR-0024 (2026-11-18) — code-level review replaced the spike; SVA is run only as a quality baseline
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
Council issue #13: "build from scratch" was never decided. `reference/social-video-agent` (Apache-2.0, ~42k lines Python, cloned locally) already provides: word-aligned EDL compiler with edges snapped to heard speech, ffmpeg base + Remotion motion layer, technical/brand QA and `reel-check`, face-aware reframing, constant per-range speed, FCPXML/OTIO/CMX export, resumable stages, a supervising-editor review stage. Missing (per grep): Hindi/Hinglish handling, speed ramps, palette-driven captions. The competitor teardown wrongly reported it as not on GitHub.

## Spike plan (2 days)
1. Install per its README (needs ffmpeg **with libass** — local build lacks it, C-4; use a libass build in a separate prefix).
2. Run its full workflow on one English gold-set reel and one Hinglish reel.
3. Record: output quality vs the owner's edit; which ADR features are missing; how hard it is to add (a) a Hinglish ASR engine behind its transcription interface, (b) caption style families with brand tokens, (c) speed ramps in its EDL, (d) our Claude integration (ADR-0010), autonomous Reviewer + auto-fix loop and NLE escape-hatch export (ADR-0018).
4. Note licence obligations (Apache-2.0 NOTICE, upstream MIT notices, Remotion licence declaration).

## Decision rule (updated 2026-11-18 after council re-review; supersedes the rule below)
Runtime is now Claude Code (ADR-0019/0020) — the same pattern social-video-agent uses, so the burden of proof is on building. Timebox environment setup (libass/zimg/placebo ffmpeg build, corporate TLS, lean-ctx allowlist) to ½ day. **Fork** (vendor at a pinned tag, don't track upstream) if all four hold:
1. Its continuous workflow runs **headless end-to-end** on one English gold reel with no intervention.
2. A Hinglish transcription backend registers behind its existing interface and feeds compile + captions **with no schema change**.
3. One real phone clip (HDR, rotated or VFR) passes frame-count and A/V-sync checks.
4. Speed ramps fit as chained speed items or a contained EDL/filter patch.
**Build** only if a core schema (plan, EDL or captions) cannot carry a requirement (ADR-0016/0018/0021/0022) without a rewrite. "Its caption look is worse" is not a reason to build. Port as modules: ADR-0007 (ASR), 0011/0017 (captions, brand), 0016 (selects/two-pass), 0018/0021 (verdict, Reviewer), 0020 (`reel run` orchestration), 0022 (music), 0023 (colour).

## Original decision rule (superseded)
- If the gaps are mostly ASR + captions + ramps and its EDL can express ramps and caption tokens without a rewrite → **fork** (ADR-0013 Accepted as "fork"); port ADR-0007/0010/0011/0012 as modules.
- Otherwise → **build** our own engine, reusing its ideas (packed transcript, edge snapping, QA reports).

## Consequences
- **Good:** may cut months of work; edge cases already solved.
- **Bad:** inherit someone else's schema and upstream drift.
