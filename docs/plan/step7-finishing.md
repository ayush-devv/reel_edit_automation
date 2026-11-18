# Build step 7 — Finishing: audio, SFX, music, transitions, speed, colour (CP3)

_Plan date: 2026-11-18 · Implements: ADR-0004 (ffmpeg-owned base effects), ADR-0015 (speech never retimed), ADR-0017 (audio/delivery), ADR-0022 (owned music library), ADR-0023 (colour pipeline). Owner decisions: SFX = Sonniss GDC bundles (indexed locally); music = synthetic test tracks until the owner adds an owned library._

## Status: implemented 2026-11-18 (CP3 engine-complete; real SFX/music libraries pending owner downloads)
- **Audio:** voice chain (high-pass, de-click, tracking denoise, de-ess, 3:1 compression) → two-pass loudnorm in the composite. Demo: −16.4 → **−14.2 LUFS, −1.51 dBTP**, exact sample count (loudnorm pads its output, so it is trimmed back). Room tone: quietest ≥ 0.5 s gap per clip, looped raw under that clip's segments; the test shows no digital silence at cut joins. (The `say` demo has no ≥ 0.5 s pause, so no room tone there, which is correct.)
- **SFX:** `reel library sfx <folder> --source … --license …` indexes a Sonniss-style folder (category from folder/file names, peak time, length ≤ 6 s). The Editor sees ≤ 6 per category, closest to the typical length. A cue's peak lands on its anchor frame; when the anchor is earlier than the sound's lead-in, the head is trimmed.
- **Music:** `reel library music <folder>` indexes tempo, beats, downbeats (librosa) and mood (folder name or `<file>.json` sidecar). The bed starts so a downbeat hits the first cut, fades in/out, and ducks with an exact gain envelope from the kept-speech spans (test: 12 dB planned → 9–15 dB measured).
- **Transitions** zoom / whip / blur / dip_to_black are frame-local: frame count unchanged, A/V within 1 frame. The first whip slid shots off-screen and showed black, so it is now an enlarged in-frame pan with directional blur that carries across the cut.
- **Speed:** constant 0.25–4× on non-speech items; compiler retimes the layout; 2× test = exactly half length, flash/beep in sync.
- **Colour:** per-clip LUT = gray-world white balance (±10 %) + exposure correction only outside a comfortable band (0.30–0.60 mean luma) + look at strength; 7 looks defined in code; brand kit can lock the look. Tinted test clip pulled toward neutral; strength 0.5 = exactly halfway.
- **Runner fix:** stages no longer re-run just because an upstream stage ran; each re-runs when its own input hash changes. Verified on the demo: a hook-title-only change re-ran compile → overlay → composite and **skipped the base render** (step 6 had claimed this, but it was only verified for renderer-code changes). Render hash now includes the renderer/mix/colour code.
- Live demo: the Editor chose look `clean` at 0.35 with a reason, no transitions/SFX (one cut, empty SFX library).
- Tests: **103 passed, 1 skipped**.
- Not done: de-reverb (no adequate ffmpeg filter; revisit if gold reels need it); validator SFX craft-fit warnings (whoosh ↔ transition etc.) beyond the menu guidance; pans (`x`/`y` keyframes) still rejected.

## Goal
The base layer sounds and looks finished. That means a clean, level voice with no gaps you can hear at the cuts, designed SFX, a music bed that ducks under speech, transitions that keep the frame-exact layout, speed changes on non-speech shots only, and per-clip colour correction plus a look.

## Design (in build order)
**A. Voice chain + delivery loudness** (`audio.py`, rendered in the base pass)
- Per voice clip: high-pass 80 Hz → de-click (`adeclick`) → denoise (`afftdn`, tracking the measured noise floor) → de-ess (`deesser`) → gentle compression (`acompressor` 3:1). Mix → two-pass `loudnorm` to **−14 LUFS integrated, ≤ −1.5 dBTP** (measured on the final encode by `verify`).
- **Room tone:** the quietest ≥ 0.5 s non-speech stretch of each clip (VAD) is looped under the whole voice track at its own level, so cut boundaries never drop to digital silence.
- De-reverb has no good ffmpeg filter: recorded as a gap, revisited only if gold-set reels need it.

**B. SFX library** (`reel library sfx <folder>`)
- Indexes a Sonniss folder (wav/aif): id, path, duration, **peak time** (loudest 10 ms), loudness, category from folder/file keywords (whoosh, pop, click, riser, hit/impact, swipe, glitch, ding, boom), source + licence. Claude sees a capped, category-balanced list.
- Mixing: `adelay` to the peak-aligned start, gain, summed with the voice before loudness normalisation. The craft rules (`whoosh` length ≈ transition, `riser` ends on the reveal, `hit` on the punch-in) go in the finish context and the validator checks anchor/category fit. The guide is about 8 SFX per reel, warned above 15.

**C. Music bed + ducking** (`reel library music <folder>`)
- Index: duration, loudness, tempo + beat times (librosa), mood tags from the folder name or a sidecar.
- Render: the bed starts at a beat-aligned offset chosen so a downbeat lands on the first cut. It fades in and out, and ducks under the voice via `sidechaincompress` (depth from the plan) or a gain envelope from the word table, whichever is cleaner.
- Synthetic test tracks (click + pad at known BPM) prove beat alignment and ducking depth.

**D. Transitions without changing the layout** (`render.py`)
- Each transition only touches the frames of the two shots next to the cut (out-going tail N/2, in-coming head N/2), so every shot keeps its exact frame range, no handles are needed, and A/V stays locked. `zoom` = scale ramp + blur, `whip` = horizontal slide + motion blur, `blur` = gaussian ramp, `dip_to_black` = fade through black. `flash` stays in the overlay.

**E. Speed on non-speech items**
- Constant rate per item (0.25–4×, validator already forbids speech). The compiler computes the output length from the rate. Video uses `setpts`; audio uses `atempo` chains, or is muted for > 2× / < 0.5×.

**F. Colour**
- Per-clip correction toward a neutral reference (gray-world white balance + exposure toward a mid-grey target, both clamped), measured from the mezzanine.
- Then a **look LUT** at partial strength (`lut3d` blended). Looks live in `assets/luts/` (neutral-clean, warm, cool, punchy, film, generated with `tools/bench/make_lut.py`). The Editor picks `grade {look, strength, reason}`; the brand kit can lock it.

## Done when
1. Final mix measures −14 ± 1 LUFS and ≤ −1.5 dBTP; the room-tone floor is present at every cut (no frame of digital silence inside the voice track).
2. SFX: a synthetic click library indexes with correct peak times, and a cue lands its peak on the anchor frame (±1 frame).
3. Music: a synthetic 120 BPM bed has a beat on the first cut (±1 frame) and ducks ≥ the planned dB under speech.
4. Each transition type renders with frame count unchanged and A/V offset ≤ 1 frame (flash/beep probe).
5. A non-speech item at 2× renders at half its source length, exact.
6. Colour: a tinted synthetic clip is pulled toward neutral; a LUT at 0.5 strength sits halfway between the original and full strength.
7. Live `_speech` run: the Editor can use every new option, and the reel renders and passes the checks above. Tests green.

## Owner actions
- Download Sonniss GDC bundles (gdc.sonniss.com), point `reel library sfx` at the folder.
- Later: add owned music to a folder and run `reel library music`.
