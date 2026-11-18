# ADR-0015: S0 mezzanine — one canonical clock, colour space and orientation

- **Status:** Accepted (2026-11-18, council issue #4–5)
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
Real client footage is iPhone/Android HEVC, often HDR (HLG/Dolby Vision 10-bit), rotated via metadata, VFR, 60/240 fps, mixed across clips. The only real sample is 25 fps SDR; the render benchmark used synthetic 1080p. Perception tools (MediaPipe/OpenCV frame indices, PySceneDetect, Whisper) would each run on a different clock. `tools/bench/base.fg` has no `fps=` after `setpts`, a likely cause of the 1802-vs-1800 frame drift (unverified).

## Decision
1. **S0 writes one mezzanine per clip:** CFR at the **project fps** (default = dominant source fps, e.g. 25 or 30 — never force 30 on 25 fps footage), bt709 SDR (HDR tonemapped), rotation baked in, square pixels, 48 kHz audio, short GOP (intra-friendly, e.g. ProRes 422 or all-I H.264). Source originals untouched.
2. **All perception and rendering read only the mezzanine;** frame index on the mezzanine is the single clock. Word times are converted once to mezzanine frames.
3. **One tested time-map function** (source µs ↔ mezzanine frame ↔ output frame) shared by compiler, ffmpeg graph builder and Remotion caption timing.
4. **Base render:** cut each segment separately from the mezzanine with frame-exact trims; `fps=` after every retime; concat. Speed ramps as piecewise-constant sub-segments; **never ramp speech** (mute/replace voice or ramp only b-roll/action).
5. **Golden conformance corpus** in the release acceptance test: rotated iPhone HDR, VFR low-light, 60 fps, mixed-fps multi-clip, a clap/flash sync clip. Assert frame count, A/V offset via beep+flash probe, orientation, colour swatch ΔE.
6. Re-benchmark on 4K HEVC input.

## Consequences
- **Good:** every accuracy promise (frame count, sync, caption timing) rests on one clock.
- **Bad:** extra transcode time and disk per project.
