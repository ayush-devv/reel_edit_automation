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

### 10e–10h — next
- 10e client b-roll: index a client folder; Claude-written descriptions from contact sheets; full-frame b-roll in the base and PiP in the overlay.
- 10f reference-style imitation: measure a reference reel (cut rate, caption style, colour) and give the Editor a style profile.
- 10g text behind the subject: segmentation matte, title drawn under the person.
- 10h stock APIs (Pexels/Pixabay): need owner API keys; assets fetched per project, not cached into a library.

Tests: **130 passed, 1 skipped**.
