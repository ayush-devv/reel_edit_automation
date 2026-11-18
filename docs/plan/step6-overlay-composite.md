# Build step 6 — Remotion overlay + composite (CP2)

_Plan date: 2026-11-18 · Implements: ADR-0004 (ffmpeg base + Remotion transparent overlay + ffmpeg composite), ADR-0011/0017 (caption families, brand-first tokens), ADR-0026 (Remotion default)._

## Status: implemented 2026-11-18 (CP2 reached)
- `reel run` on `_speech` → `export/reel.mp4` with kinetic `bold_pop` captions, the Editor's hook title ("The 10% rule for saving money") and the base picture/voice. Frames 268/268, audio = video. Overlay 7–16 s, composite 6 s for a 9 s reel.
- All 5 families render (`assets/step6-families.png`, same frame each).
- Layout fixes found on the first render: the hook title collided with text burned into the footage → OCR text zones (persistent, ≥ 3 letters) are mapped to output coordinates and titles/captions are pushed clear of them; balanced title wrapping; caption pages shrink to one line (≥ 62 % of base size); emphasised words get extra spacing (transforms take no layout space).
- A renderer-only change re-ran just `overlay` + `composite` (the base was not re-rendered).
- Tests: **85 passed, 1 skipped** (7 new; the Remotion integration test checks the base is untouched outside the text and changed under it).
- Known limits (planned): legibility on busy/same-colour backgrounds (contrast gate step 9, palette-adaptive tokens step 10); `speaker_coded` uses one colour until diarisation (step 8); brand fonts other than Inter / Plus Jakarta Sans fall back to Inter.

## Goal
The reel gets its on-screen layer: kinetic captions in the family the Editor picked (brand kit wins), a hook title, and flash transitions. Rendered as a transparent overlay and composited once onto the base, with a single lossy encode at the end.

## Design
- **`renderer/`** — Remotion 4.0.538 project (pinned, seeded from the benchmark, headless shell already local). One composition `Overlay`: duration, fps and size come from the props (`calculateMetadata`). Transparent background, rendered as ProRes 4444 with straight alpha (`--image-format png --pixel-format yuva444p10le`).
- **Captions = one token-driven component** covering all five families: `case`, `highlight` (word | scale | none), `anim` (pop | fade | slide_fade), `box`, `stroke`, colours, font, weight, `zone` (lower_middle | lower_third | beside_face). Platform safe zones are respected (top 220 px, bottom 420 px, right 130 px on 1080×1920). Punctuation-only tokens (`%`) attach to the previous word; trailing periods/commas are dropped except in sentence-case families.
- **Fonts** bundled from `@fontsource` (Inter, Plus Jakarta Sans; SIL OFL), loaded before the first frame (`delayRender` + `document.fonts.load`). Brand fonts that are not installed fall back to Inter, and the run meta says so.
- **Token precedence:** family defaults < Editor tokens < brand kit (`caption_family` lock, `caption_tokens`, brand colours → `base_color`/`emph_color`, heading font → `font`).
- **Hook title:** new `FinishPlan.hook_title {text, reason}` (`""` = none, ≤ 42 chars / ≤ 7 words, validated). Shown from frame 0 until the end of the first item (1.5–3.0 s), upper third, in the caption family's font.
- **Flash transitions** are overlay events (`Timeline.flashes`, owner remotion), centred on the cut. Other transition types still render in step 7.
- **Base intermediate** becomes ProRes 422 + PCM (`render/base.mov`), so the only lossy encode is the composite (`render/final.mp4`, libx264 CRF 16 + AAC) → `export/reel.mp4`.
- **Stages:** `render` (base) → `overlay` → `composite`. Input hashes are split by field owner: a caption-only revision re-renders the overlay and composite, never the base.
- **Overlay props** = remotion-owned timeline fields + the face box in output coordinates (computed with the same crop geometry as the base renderer).

## Done when
1. `reel run` on `_speech` produces `export/reel.mp4` with captions synced to speech (each caption word's first frame = its word's first output frame), plus a hook title. Frame count = `duration_f`, audio length = video length.
2. Visual check: each of the 5 families rendered on the demo (contact sheet in the step notes); text stays inside the safe zones.
3. A caption-only change re-runs `overlay` + `composite` only.
4. Tests: props builder + token precedence + hook-title validation (unit); overlay render + composite on a short synthetic timeline, checking alpha (pixels outside captions are unchanged from the base) and frame count (integration, skipped without node/Remotion).

## Not in step 6
B-roll PiP and stickers (need the asset libraries — step 7), speaker-coded colours per speaker (diarisation, step 8), palette-adaptive tokens (step 10), caption-over-face QA gate (step 9).
