# ADR-0001: Claude plans; tools perceive and render

- **Status:** Accepted (forced by constraint C-1)
- **Date:** 2026-11-18
- **Deciders:** project owner, Claude (architecture partner)

## Context
Claude cannot ingest video or audio (official docs, verified 2026-11-18). It reads text and images and writes text/JSON. A 60 s reel has 1,800 frames; sending them all is ~2.9M+ tokens. Reference systems (social-video-agent, browser-use/video-use, LAVE, VideoAgent) all turn footage into text before an LLM reasons over it.

## Options considered
| Criterion | A. Claude plans; tools perceive + render | B. Claude writes ffmpeg/code directly | C. Use a native video model instead of Claude |
|---|---|---|---|
| Fits Claude's inputs | Yes | Yes | n/a |
| Frame-accuracy | Deterministic tools | Fragile, hallucinated commands | Varies |
| Debuggability | Every artifact inspectable | Opaque shell strings | Opaque |
| Editorial reasoning | Claude's strength | Same | Weaker for craft (VEU-Bench) |
| Reversibility | High | Medium | Low |

## Decision
We choose **A**: perception tools convert the reel into text tables + a few small frames; Claude writes an edit plan; deterministic code compiles and renders. Claude never touches video bytes and never writes raw ffmpeg commands.

## Consequences
- **Good:** cheap (~30k tokens per draft), deterministic renders, every step leaves an artifact.
- **Bad / costs we accept:** quality ceiling is set by perception; Claude cannot see motion between sampled frames or hear tone/music.
- **Revisit when:** Claude's API documents native video/audio input.

## Challenges raised
- "Won't Claude miss visual moments?" → mitigated by motion/audio energy curves, frames-on-demand tool, coarse→fine moment finding (ADR-0002).
