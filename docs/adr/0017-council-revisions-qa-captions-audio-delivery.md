# ADR-0017: QA gate calibration, brand-first captions, audio finishing, delivery profile

- **Status:** Accepted (2026-11-18, council issues #7, #8, #9, #12)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Amends:** ADR-0006 (gates), ADR-0011 (caption tokens). Both remain in force except where changed here.

## 1. QA gates (amends ADR-0006)
- **Remove** the OCR(captions) = transcript gate (unrealistic on animated, mixed-script text). Check caption text/position from timeline + Remotion props; OCR only the overlay on a flat background as a sanity check.
- **Measure on the render, not the source:** caption-over-face from the overlay's alpha mask vs MediaPipe faces detected on the rendered base; contrast on final pixels.
- **A/V sync** via a beep+flash probe (drift vs base render was circular).
- **Calibrate:** measure each gate's false-positive rate on clean gold-set renders before making it hard; until then it is a warning.
- **Safe zone:** hard gate for CTA, logo and end-card text (per-element override); warning for kinetic captions.
- **Loudness:** two-pass linear loudnorm targeting −1.5 dBTP, measured on the final encoded file.
- **Determinism (NFR-7):** identical frame count and timing + per-frame perceptual-hash tolerance; pin models and fonts; cache perception by (source hash, model version).

## 2. Brand-first captions (amends ADR-0011)
- `brands/<client>.json`: fonts, colours, logo, end card, CTA, locked caption family, saved preferences. **Brand tokens override palette-derived tokens.**
- Ships with caption families + brand tokens; palette adaptation is a fallback when no brand kit exists.

## 3. Audio finishing
- Voice chain per clip: denoise (candidates DeepFilterNet / RNNoise — licence to verify), high-pass, EQ, de-ess, compression, gain-match across clips.
- Room tone under cuts instead of bare 30 ms fades.
- Never speed-ramp speech (ADR-0015).
- Music: **resolved by ADR-0022** — owned/licensed music library with musical editing; no-music variant still exported; songs never baked in.

## 4. Delivery profile
- Keep project fps = source fps; high-bitrate master; textless version; no-music version (for platform trending audio); SRT/VTT; cover frame; optional 4:5 cut-down.
- Client review copies: watermark, burned-in timecode, version slate. Client-note importer maps output timecode → item IDs via the timeline; revision-round counter; change log from plan `reason` fields.
