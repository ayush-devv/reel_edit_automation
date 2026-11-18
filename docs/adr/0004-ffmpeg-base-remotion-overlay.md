# ADR-0004: ffmpeg base pass + Remotion transparent overlay

- **Status:** Accepted (2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Detail:** [`docs/architecture/renderer-split.md`](../architecture/renderer-split.md)

## Context
Measured locally (Apple M5, 60 s 1080x1920 30 fps): ffmpeg base 11.1 s; Remotion with base inside 61.8 s; Remotion overlay only 36.2 s; ffmpeg composite 6.9 s. Requirements: pro-level kinetic typography placed freely (beside the face, mixed sizes), punch-ins and camera moves, transitions, b-roll, SFX, adaptive caption styles (ADR-0011).

## Options considered
| Criterion | A. Base inside Remotion | B. Transparent overlay + ffmpeg composite | C. ffmpeg only | D. HyperFrames instead of Remotion |
|---|---|---|---|---|
| Time per 60 s reel | ~74 s | ~54 s (≈43 s parallel) | ~15 s | Not measured |
| Kinetic text quality | Best | Best | ASS only (and no libass in local build) | Like Remotion |
| Effects that read base pixels in Remotion | Yes | No — must be ffmpeg | n/a | Like A/B |
| Licence / cost | Remotion free for individuals / companies ≤ 3 people | Same | Free | Apache-2.0 |

## Decision
**B.** Everything that changes pixels or sound — cuts, reframe, punch-ins, camera moves, **speed ramps**, LUT/grade, shot transitions, full-screen b-roll, audio mix — is ffmpeg. Everything on top — captions, kinetic typography, titles, stickers, icons, picture-in-picture, flashes, light leaks — is Remotion. ffmpeg composites the overlay and **copies the base audio** (Remotion AAC was ~45 ms late in the reference project).

### Resolved open point: speed ramps
Owned by **ffmpeg** (`setpts` expression per segment, `atempo` for audio where the voice is retimed). Remotion `remapSpeed` would need the base inside Remotion (option A) and is not used. Frame-interpolated slow motion (RIFE) is deferred until its weight licence is checked.

### Text behind the subject
Remotion draws the text on the overlay; ffmpeg composites the subject matte (precomputed) back over it. v1 matte: MediaPipe person segmentation; SAM 2.1 only if quality requires it.

## Consequences
- **Good:** fastest measured option; base and overlay render in parallel; every timeline field has exactly one owner.
- **Bad:** no Remotion effects that distort the base; ffmpeg punch-ins move in whole-pixel steps — supersample (render at 2x, scale down) for slow push-ins.
- **Revisit when:** a required effect needs base pixels inside Remotion (→ A), or Remotion licensing/telemetry becomes unacceptable (→ D).
