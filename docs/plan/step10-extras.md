# Build step 10 — Full-scope extras (CP6)

_Plan date: 2026-11-18 · Implements: ADR-0018 (NLE escape hatch every run), ADR-0017 (delivery, brand-first, palette-adaptive captions), architecture §15 step 10._

Build order (value first): 10a NLE package → 10b delivery variants + review copy → 10c palette-adaptive captions → 10d client-note importer → 10e client b-roll (full + PiP) → 10f reference-style imitation → 10g text-behind-subject matte → 10h stock APIs (needs owner API keys).

## Status
### 10a NLE package — done
`export/package/` every run contains:
- `reel.mp4` and `overlay.mov` (ProRes 4444 with alpha), hard-linked so they take no extra space;
- `stems/{dialogue,music,sfx}.wav`, the finished buses written in the same ffmpeg pass as the base;
- `captions.srt/.vtt`;
- `timeline.fcpxml` (1.10): the cut on the mezzanines, the overlay on lane 1, stems on lanes −1…−3 (disabled), and speed changes as `timeMap`;
- `timeline.otio`, which round-trips through OpenTimelineIO;
- `edit_list.md`, every decision with its reason;
- `README.md`, saying what is baked where and the licences of library assets used.

Every FCPXML time is checked to sit on the frame grid. **Not yet opened in Final Cut / Resolve: owner check.**

### 10b Delivery variants + review copy — done
- The 9:16 master serves Reels, Shorts and TikTok.
- `brief.deliverables: ["feed_4x5", "square"]` builds re-laid-out variants. The base is cropped (face first, then text already in the footage) and the overlay is re-rendered at the new size, so nothing is cut off.
- `export/review/review.mp4`: 540 px, burned timecode, "REVIEW COPY" watermark (0.8 MB for 9 s).
- Platform duration limits are noted.
- The first crop centred blindly and cut off the burned-in brand banner; the crop now keeps text zones when the face allows.

### 10c Palette-adaptive captions — done
After compiling, the engine samples the source pixels behind caption pages and measures how much of the band each colour would vanish against (local clash, not average colour). If the fill clashes and there's no outline or box, it adds an outline. If the emphasis colour clashes, it swaps to the most legible colour from the footage palette and accents. Brand-set keys are never changed. Demo: yellow emphasis vanished on 46 % of the band, so it switched to the footage's own red. The base was not re-rendered.

### 10d Client-note importer — done
`reel notes --project P notes.txt [--dry-run]` parses `0:12 …`, `00:00:12 - …`, `12s: …`, `[0:04] …` and untimed lines. Each note is anchored to the item, its spoken line and the caption on screen at that time. All notes become one Editor revision, then re-render and re-check.

### Also fixed
The compile stage hash did not include its own code, so a compiler/adapt change was silently skipped. Stages now fingerprint the modules they depend on.

### 10e Client b-roll — done
`reel run … --broll <folder>`:
- Each clip is conformed like the main footage and gets a 3-frame contact sheet.
- **One Claude call describes all of them**: subject, shot, motion, mood, best moment. The result goes to `broll/index.json` and is merged with the owned library.
- The Editor sees descriptions and durations. The validator rejects spans longer than the clip.
- The compiler starts each cutaway at the clip's best moment.
- `full` b-roll is overlaid in the ffmpeg base: frame-exact in its slot, voice untouched, same colour treatment. `pip` is a card in the Remotion overlay, which is rendered with the workspace as its public dir.
- Tests:
  - the picture is replaced in exactly frames 20–34 and the beep doesn't move;
  - the PiP card is present only in its window, with the b-roll's colour;
  - indexing with a fake describer.

### 10f Reference-style imitation — done
`reel run … --reference <reel>` measures a reel the client likes. A profile goes to `context/reference_style.md`, both Editor passes read it, and the personas say to match it unless brief or brand override. It measures:
- cut rate and average shot length;
- motion;
- speaking pace (ASR);
- caption share, words per block, case, vertical position, light/dark text, boxed or not;
- colour: brightness, contrast, saturation, warmth, nearest look.

It also makes contact sheets. Tested on a synthetic 3-shot reel with burned-in upper-case captions.

### 10g Text behind the subject — done
- `hook_title.style: "behind"`. The Editor may use it only when a person is clearly visible in the opening clip; the face-presence check rejects it otherwise.
- The engine renders the behind-title as its own Remotion layer for just the title frames (`--frames`). It builds a person matte from the rendered base (MediaPipe selfie segmenter, Apache-2.0, feathered).
- The composite stacks base → behind-title → person (alpha-merged from the matte) → overlay.
- Synthetic test: the title shows on the background and is hidden behind the "person".
- The real segmenter runs (model auto-downloads).
- **Not yet seen on a real person: owner footage needed.** On the demo the Editor correctly chose `card` ("no person filling the frame").

### 10h Stock b-roll — done (needs owner key)
`reel stock "query" --out <folder>` searches the Pexels videos API with `PEXELS_API_KEY`:
- picks portrait renditions ≥ 1280 px tall, 2–30 s;
- writes a licence sidecar per clip;
- the clips then go through `--broll`, and credits appear in the package README.

Downloads stay per project, never in a shared library (Pexels licence). Tested with a mocked API. **Live search untested: needs the owner's free key.**

### Known gaps
- Variants (4:5 / square) do not re-render a `behind` title.
- B-roll audio is dropped (the voice continues).
- Only Pexels is wired (Pixabay would be the same adapter).

Tests: **139 passed, 1 skipped**.
