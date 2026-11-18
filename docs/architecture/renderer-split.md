# Renderer split: ffmpeg (base) vs Remotion (overlay)

**Status:** Accepted (2026-11-18) — see ADR-0004. Speed ramps resolved: ffmpeg.
**Date:** 2026-11-18

## Rule

- Anything that changes **the video pixels or the sound** is done by **ffmpeg** (base layer).
- Anything that **sits on top** of the video is done by **Remotion** (transparent overlay layer).
- ffmpeg then composites the overlay onto the base and copies the base audio.

## Proposed split

| Effect | Changes video or sits on top? | Owner |
|---|---|---|
| Cuts, trims, reorder | Video | ffmpeg |
| Crop to 9:16 / follow face (reframe) | Video | ffmpeg |
| Punch-in, zoom, simulated camera pan | Video | ffmpeg |
| Speed ramps, slow-mo | Video | ffmpeg |
| Color grade / LUT | Video | ffmpeg |
| Transitions between shots (whip, zoom, blur) | Video | ffmpeg |
| Full-screen b-roll cutaway | Video (replaces it) | ffmpeg |
| Voice, music bed, ducking, SFX, loudness | Sound | ffmpeg |
| Kinetic word captions | On top | Remotion |
| Hook title, lower thirds, CTA | On top | Remotion |
| Emoji, stickers, icons, progress bar | On top | Remotion |
| Picture-in-picture b-roll card | On top | Remotion |
| White flash, light leak | On top | Remotion |
| Text behind the person | Both | Remotion draws text; ffmpeg composites the person matte back over it |

## Evidence (local benchmark, 2026-11-18, Apple M5, 60 s 1080x1920 30 fps)

| Step | Time |
|---|---|
| ffmpeg base pass (6 cuts, crop, 3 punch-ins, 1.5x segment, LUT, fades, ducking, loudnorm) | 11.1 s (VideoToolbox) / 13.9 s (libx264) |
| Remotion, base video inside (approach A) | 61.8 s |
| Remotion, transparent overlay only (approach B) | 36.2 s |
| ffmpeg composite overlay + copy audio | 6.9 s |
| **Total A (base inside Remotion)** | ~74 s |
| **Total B (overlay, sequential / parallel)** | ~54 s / ~43 s |

## Consequence for timeline JSON

Every field must belong to exactly one renderer, so the compiler can split `timeline.json` into an ffmpeg job and a Remotion job. A field with no owner means Claude can request an effect nothing renders.

## Open points

- Speed ramps: ffmpeg `setpts` (this doc) vs Remotion `remapSpeed` (timeline-schema research). Under approach B they must be ffmpeg.
- Transitions that need both shots' pixels must be ffmpeg (`xfade` or custom). Remotion-only transitions are limited to overlays (flash, light leak).
- Re-check if we ever need effects that read base pixels inside Remotion (e.g. WebGL distortions) — that would push us back to approach A.
