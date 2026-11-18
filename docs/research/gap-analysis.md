# Gap analysis: what a pro reel editor does that this build cannot (2026-11-19)

**Source of truth:** `engine/src/reel/capability_status.py` marks each of the 221 capabilities in `knowledge/capabilities.yaml`. The Editor sees the same list as `context/knowledge/capabilities.md`.

Today: **36 yes, 38 auto, 10 partial, 137 no**. Of the 137, 13 are `unsupported` by design: generative extend, relight, TTS, dubbing, object removal, lip sync, AI upscale, morph cut, planar replace, 3D camera track, ML interpolation, HDR delivery, retention analytics.

## 1. The "brain" (fixed in this change)
- **Before:** the Editor saw about 55 of 313 knowledge nodes (a keyword-filtered shortlist). It never saw the capability catalogue.
- **Now:**
  - every story and finish pass writes `context/knowledge/` to the workspace: `index.md` (all nodes, one line each), one full-detail file per graph file, and `capabilities.md` (yes / auto / partial / no);
  - both personas are told to read the full node before using a technique, and to cite nodes from anywhere in the library;
  - the shortlist stays as a starting point.
- **Hash:** the knowledge hash now covers `capabilities.yaml`, `knowledge.py` and `capability_status.py`.

## 2. Gaps that matter for talking-head / podcast reels, with how OSS does them

| # | Gap (capability ids) | How open source does it | Our implementation | Licence notes |
|---|---|---|---|---|
| A | **SFX + music libraries empty** (`audio.sfx_add`, `audio.music_bed` are wired but have no content) | see the audio research (§4) | auto-populate script → `assets/sfx`, `assets/music`, indexed by the existing `reel assets` | commercial-safe sources only |
| B | **J/L cuts, crossfades** (`cut.j_cut`, `cut.l_cut`, `audio.crossfade`) | video-use: 30 ms `afade` at every cut, pad cuts 30–200 ms | `finish.audio_leads`: audio of the next item starts N frames early, or the tail runs over; 30 ms fades on every cut | — |
| C | **Pause tightening inside a kept line** (`cut.silence_removal`, `trim.hold_extend`) | auto-editor margin model; video-use: cut only in silences ≥ 400 ms, never inside a word | compile pass: split items at inner pauses > threshold (brief pace), keep a 120 ms margin; end hold / freeze last frame | — |
| D | **Smooth face tracking + blurred fill + split screen** (`transform.auto_reframe` partial, `transform.blurred_fill`, `compositing.split_screen`) | openshorts (MIT): dead zone 0.25×crop, 3-detection jump confirm, velocity cap, snap on scene cut; blurred fill from a ¼-size `gblur`; SPLIT only if each speaker has ≥ 20 % of speech. AutoFlip (Apache): hold the shot static if motion < 0.5 % | offline per shot: static if median motion is small, else dead zone + jump confirm + `savgol_filter` + velocity cap; layout per shot (track / blurred fill / split) | do **not** port the YOLO fallback (ultralytics = AGPL) |
| E | **Active speaker** (`analysis.speaker_diarization`) | openshorts `active_speaker.py` (MIT): mouth motion per face in 0.4 s windows, audio gate 0.18 × peak, lead margin 0.15, switch after 3 windows | MediaPipe Face Landmarker `jawOpen` blendshape at ~12 fps on multi-face shots → speaker per word → drives reframing and SPLIT | pyannote community-1 only if audio-only labels are needed (CC BY 4.0, gated) |
| F | **Speed ramps, freeze frame** (`speed.ramp`, `speed.freeze_frame`) | setpts integral (tested: 6 s → 3.40 s vs 3.42 predicted); `asendcmd` + `atempo` for audio | `finish.speeds` gains `ramp_to` + ease; freeze = `tpad stop_mode=clone` | — |
| G | **Beat sync + zoom pulse** (`cut.cut_to_beat`, `transform.beat_zoom_pulse`) | `beat_this` (MIT code + weights) or librosa; snap cuts ±150 ms only into word gaps; openshorts punch curve: max 1.12, 0.25 s in / 1.3 s hold / 0.55 s out, smoothstep | beats already indexed for music; snap item edges in compile; `finish.beat_pulse` uses the existing punch-in machinery | madmom models are CC BY-NC-SA, so avoid them |
| H | **Motion graphics** (16 `graphics.*` + `text.number_counter`) | Remotion official MIT pkgs (`shapes`, `paths` evolvePath, `rough-notation` circle/box/underline, `animated-emoji`, `rounded-text-box`); HyperFrames (Apache) as pattern source for lower thirds, count-up, CTA, logo sting | new overlay layer `finish.graphics[]`: emoji_pop, lower_third, progress_bar, logo_watermark, callout (circle/box/underline/arrow), cta_card, countdown, counter, full_screen_card, gradient_scrim | Noto Animated Emoji is **CC BY 4.0**: the package writes a credit line. Avoid OpenMoji (BY-SA) and the brand-imitating HyperFrames blocks |
| I | **Look effects on the footage** (`effect.film_grain`, `vignette`, `camera_shake`, `glitch`, `chromatic_aberration`, `light_leak`, `exposure_pulse`) | must be ffmpeg on the base (the overlay is a separate alpha layer); light leaks as a separate screen-blended pass | ffmpeg `noise`, `vignette`, expression `crop` shake, `rgbashift`; procedural leak pass with `blend=all_mode=screen` | procedural, so no asset licences |
| J | **More transitions** (`cross_dissolve`, `dip_to_white`, `slide_push`, `glitch`) | ffmpeg `xfade` has all of them | add them to the transition renderer | — |
| K | **Voice enhancement** (`audio.voice_enhance`, `de_reverb`, `eq`, `breath_attenuation`) | see §4 | see §4 | — |
| L | **Cover frame / thumbnail** (`export.cover_frame`) | openshorts: face area × sharpness over 40 samples | add blendshape scoring (no blink, reward smile / brow / open mouth) near highlight moments; Claude picks from the top 5; written to the package | — |
| M | **Cut-point self-check** (QA) | video-use `timeline_view`: a 10-frame strip + waveform at each cut ±1.5 s, checked by the agent, at most 3 passes | QA sheets per cut fed to the Reviewer, alongside the existing gates | MIT |

**Not planned** (low value for talking-head reels, or unsupported): colour wheels / curves / qualifiers beyond looks, chroma / luma key, rotoscope, 3D tracking, stabilisation, lens correction, reverse / boomerang, pitch / voice effects, dubbing, TTS.

## 2b. Done in this change
- **C, pause tightening:** `story.max_pause_ms` (default 400 ms; 0 keeps a deliberate silence). Any pause inside a kept line that is longer becomes a jump cut. Punch-ins hold across those cuts. The read-back reports how many pauses were cut.
- **D, framing:**
  - per camera shot, the crop stays locked off when the face is still, and follows it with a smoothed, speed-capped path when it moves;
  - the tracker follows one face, so a second face never steals the frame;
  - two people too far apart for one vertical crop get the blurred-fill layout;
  - caption placement knows the fill layout.
- **I, footage effects:** `grade.grain`, `grade.vignette` (whole reel); `effects[]` shake / rgb_split / light_leak (procedural, screen-blended) / exposure_pulse on word windows, with per-type length limits and at most 6 per reel.
- **J, transitions:** `dip_to_white` and `glitch` added. Cross-dissolve and slide/push need overlapping frames from both shots (handles), so they stay out; pros rarely use them on talking heads.
- **B, J/L cuts: deferred on purpose.** With one camera, the other side of the cut shows the same speaker silent while their own voice plays (a lip-sync error). They land with E (a second camera or a second speaker).

## 2c. bang-motion (MIT, Claude Code skill; reviewed 2026-11-19)
- **What it is:** standalone HTML + GSAP compositions exported as opaque MP4. It has no alpha path, and its grain and light leaks use CSS blend modes.
- **Take the numbers and rules, not the code.** Re-implement in Remotion with `interpolate` / `Easing`:
  - text entrances: inUp, inLeft, inMask, inWords, inDepth;
  - emphasis marks: pill, under, marker, box, strike;
  - draw / slam / fly + float, counters, the camera-breathing push-through.
  - The recipe timings are in the review notes.
- **GSAP stays out.** Its "No Charge" licence has clauses about no-code animation tools and paid end users that may apply to us (UNVERIFIED; needs legal review). `@remotion/gsap` also refuses the repo's camera, blur, typing and counter helpers.
- **Layer rule:**
  - normal-blend art goes in the overlay: emoji pop, lower third, callouts, highlighter, progress bar, watermark, small counter;
  - textured or blend-mode pieces become full-screen 9:16 inserts: kinetic text card, big stat, CTA / end card, countdown.
- **Editor knowledge to add:**
  - which emphasis variant suits which topic;
  - the text-pocket contrast rule (background luminance ≤ 25 % or ≥ 80 %);
  - minimum sizes (body 44 / label 34 / title ≥ 100 px);
  - two cards in a row never share size, entry and position;
  - at most one push-through per video;
  - a style direction per content tone, kept consistent per creator (do not adopt its "every project looks different" rule).
- **Avoid** platform-UI imitations (follow / subscribe buttons with platform logos).

## 3. Order of work (one release; each lands with tests)
1. A sound libraries · B J/L cuts + cut fades · C pause tightening + end hold
2. D framing (smooth tracking, blurred fill, split) · E active speaker
3. H motion graphics · I footage effects · J transitions
4. F speed ramps · G beat sync / pulse · K voice enhancement
5. L cover frame · M cut-point self-check

Each new plan field is added to `capability_status.STATUS`, so the Editor learns about it the moment it exists.

## 4. Audio sourcing and voice enhancement
_Pending: the audio research report fills this section._
