# VEED OpenEdit: reverse-engineering notes

- Source: `veedstudio/open-edit`, Apache-2.0, shallow clone (one commit, `e4dc938 "Mirror from veed-llm-editor (#36)"`). I read the source and did not run it.
- Clone path: `/private/tmp/claude-502/.../scratchpad/oss/open-edit`. Every path below is relative to it.
- Size: about 35k lines of TypeScript in `cli/src/`, a skill in `.claude/skills/open-edit/`, and tests in `cli/tests/`.
- Runtime deps (`package.json`): `playwright-core@1.63.0` and `undici`. Nothing else.
- Provenance tags used throughout:
  - **[code]**: read in the source.
  - **[skill]**: stated in the agent skill markdown.
  - **[README]**: a marketing claim in `.github/README.md` with no code behind it.
  - **[inferred]**: my reading of how the pieces fit.

---

## 0. TL;DR

- **The renderer is open, not closed.**
  - In this snapshot, neither README calls the HTML renderer closed source. A grep for "closed source", "proprietary" or "minified" finds nothing.
  - `cli/src/render/` is plain TypeScript built with `tsc` (`cli/scripts/build.mjs`). It drives a pinned **Chrome Headless Shell** (Chrome for Testing, `render/browser.ts`) through playwright-core and the Chrome DevTools Protocol, and encodes with ffmpeg.
  - The closed parts are VEED's hosted services and the VEED models hosted on fal. See §1.5.
  - Caveat: users run the npm-published build, and I can't verify that it matches this mirror.
- **Partial re-render is explicit, not automatic diffing.**
  - The agent passes `--from/--to`. The renderer re-renders the fixed 2-second segments that overlap that range.
  - It also re-renders any other segment whose sampled DOM state (text, video file/time/box, images) or media bytes changed.
  - It splices the result with the ffmpeg concat demuxer using `-c copy`. Each segment was encoded by its own ffmpeg process with identical arguments, so each starts on an IDR frame. Audio is never in the render; it is muxed on afterwards.
- **We can port most of the valuable ideas into our Python + ffmpeg + Remotion stack.** Our declarative timeline JSON makes change detection *easier* than theirs.

---

## 1. Architecture

### 1.1 How an agent drives it

- **The skill is the runtime contract.**
  - `.claude/skills/open-edit/SKILL.md` (222 lines) is loaded by default.
  - `TRANSCRIPTION.md`, `CUT.md`, `FABRIC.md` and `VEED.md` load only when their situation comes up. This is progressive disclosure that keeps the context small.
  - `init` installs the skill into `.claude/skills/` (Claude Code) and `.agents/skills/` (Codex, Gemini CLI).
- **The skill sets the agent's stance:**
  - "You author the piece yourself, as an HTML page, and render it." **[skill]**
  - Talk-to-user rules: one line at the start, then the deliverable's path; no internals or progress spam.
  - Money rules: quote the price, wait for a yes, report the spend.
  - Faces rule: never draw over a face.
  - HDR rule: convert to SDR, keep the source's look, and don't grade unless asked.
- **The CLI is the tool surface.** It is `npx @veedstudio/openedit-cli <cmd>`, about 38 commands registered in `cli/src/cli.ts`.
  - Each command has a `usage` object with long `notes`, and `--help` prints them. The help text is effectively a second layer of agent documentation.
  - Commands print **one-line findings** to stderr (`render: also rendering segment(s) 4-5 ... again: ...`) for the agent to read.
  - **Design pattern worth copying:** tools *report* and never silently fix. Every warning is a sentence the agent can relay.
- **Agent-facing guardrails:**
  - Paid calls are two-phase: a quote, then `--yes` or `--approve <usd:quote>`.
  - The approval is bound to the hashed script, the presenter and the workspace for one hour (`FABRIC.md`, `commands/generate.ts`).
  - A **queue ledger** (`providers/queue-ledger.ts`) keys every fal request by its content, so an identical request is never bought twice, even across crashes and parallel agents.

### 1.2 A "piece" is an HTML page

- Everything for a piece lives in `runs/<key>/`: `index.html`, assets, `transcript.json`, `captions.js`, `faces.js`, renders, audio and `brief.json`. "The code is the edit." **[skill]**
- **Stage and layers:**
  - The canvas is `#stage` (or `[data-stage]`), captured at its own size.
  - Text goes inside `<div data-safe>`, a container fitted to the platform's safe zone. `safe-zone` writes the CSS; `render` injects one if the page has none (`commands/safe-zone.ts`).
  - The zone exposes `--caption-text`, `--card-text` and `--hook-text` size tokens.
- **Speaker layering (text behind subject):**
  - `<div id="stage" data-cutout="cutout.webm">` with three children: `[data-layer=footage]`, `[data-layer=behind]` and `[data-layer=front]`.
  - The CLI stacks them and draws the cut-out between `behind` and `front` (`render/speaker.ts`).
- **The page loads generated helpers:**
  - `captions.js`: cue shaping and word state.
  - `faces.js`: face and burned-in-graphic avoidance.
  - `zoom.js`: the screen-recording camera.
  - `speaker.js`.
  - All of them set **structure and state only** (`data-state="next|now|said"`, CSS custom properties `--progress`, `--cue-progress`). **The look stays the page's CSS.**
- **Time is the renderer's** (`render/page-runtime.ts`, 786 lines):
  - The injected script virtualises `performance.now`, `Date.now`, `requestAnimationFrame` and timers, and seeds `Math.random`.
  - Each frame it seeks every CSS and Web Animation, seeks `gsap.globalTimeline`, awaits `window.__seek(t)`, and seeks `<video>` elements to the exact frame.
  - A page marked `data-stateless` lets workers jump straight to their frames. Otherwise each worker **steps through every earlier frame** without capturing, so the output is identical whatever the worker count.
  - `render` verifies the `data-stateless` claim on one frame (jumped-to vs. stepped-to pixels) before trusting it (`commands/render.ts:284-343`).

### 1.3 How rendering is invoked

- `openedit render runs/<key>/index.html --out runs/<key>/out.mp4 --fps 30000/1001 --duration 12 [--footage clip.mp4] [--from 4 --to 6] [--draft] [--stills 0.5,2 --sheet s.jpg]`
- **Rates are exact rationals** (`render/timing.ts`). Decimal fps like `29.97` is refused with a hint.
- **Workers:**
  - Each worker is its own Chrome. The default is one per CPU for stateless pages, else `min(8, cpus/2)`.
  - There are at least 12 frames per worker, and runs are contiguous (`splitFrames`).
- **Capture:**
  - CDP `Page.captureScreenshot` produces a PNG, or with `--capture jpeg` a JPEG at about half the cost, which is lossy.
  - Frames are piped into **one ffmpeg per segment** (`image2pipe` → libx264 `veryfast` CRF 20, `-threads 4`, BT.709, yuv420p).
  - `--transparent` writes ProRes 4444 instead (`render/encode.ts`).
- **`--footage` fast path:**
  - Full-stage footage is *not* decoded by Chrome. The page is captured with alpha, and ffmpeg overlays it on the clip in the same per-segment encoder (`render/footage.ts`, `overlayGraph` in `encode.ts`).
  - Each segment's encoder input-seeks the footage half a frame early to its first frame, then renumbers with `setpts=N`.
  - This is the "many times faster" path for captions over footage. **It is the analogue of our base render + overlay composite, done in one pass per segment.**
- **Media proxies:**
  - Long-GOP, HDR or Chrome-unplayable `<video>` sources get an **all-intra copy** (`-g 1`, CRF 16) for frame-exact seeks.
  - Copies are optionally sized down to their drawn size, kept in the content-addressed cache `runs/.media` (10 GB LRU with a 24 h lease), and reused across renders (`render/media.ts`).
- **Text floor:** any text under 4.5% of the short side (49 px at 1080) is raised to the floor at render time, and the render lists what it raised.
- **`--draft`:** half scale, JPEG q80, x264 ultrafast CRF 28. The output must be named `*.draft.mp4` so it never pollutes the real cache.

### 1.4 Outputs and `runs/` layout

- Workspace root:
  - `OPEN_EDIT_ROOT`, else the nearest project above the cwd (`cli/src/config.ts:144-162`).
  - `runs/` is gitignored. The provider choice is in `.open-edit-prefs.json`.
- **`runs/<key>/`** (the key comes from the source video's filename):
  - `transcript.json`, `brief.json`, `index.html`, `captions.js`
  - `faces-<hash>/faces.json|faces.js`
  - `assets/` (with `assets/records/` and `assets/jobs/<key>/attempt-n.json` for the ledger)
  - `audio/mix.m4a`, `out.mp4`, `final.mp4`
- **`<out>.render/`**: `seg-00000.mp4…`, `seg-NNNNN.text.json`, `manifest.json`, `concat.txt` and `.lock`.
- **`<out>.text.json`**: the on-screen text record for `review`.
- **`<cut>.ranges/<sha256>.mp4`**: the per-range cut cache from `apply-edl`.
- Login state and the browser are in OS app-data (`~/Library/Application Support/veed-openedit`).

### 1.5 Open vs. closed

The third-party licence names in this table (Chromium BSD-style, ffmpeg LGPL/GPL, MediaPipe Apache-2.0, WhisperX BSD-2) are **[recall]**: they are not stated in the repo.

| Part | Status | Where |
|---|---|---|
| Renderer (virtual clock, Chrome capture, segment cache, splice) | **Open**, Apache-2.0 TS | `cli/src/render/*`, `cli/src/commands/render.ts` |
| Chrome Headless Shell | Google binary (Chromium BSD-style licences), downloaded at a pinned version | `render/browser.ts` |
| ffmpeg | User-installed or a downloaded static build (LGPL/GPL depending on the build) | `commands/install-ffmpeg.ts` |
| Captions, faces placement, safe zones, review checks, EDL cut, mix/mux, reframe, zoom, shots | **Open** | `captions/`, `faces/`, `verify/`, `commands/` |
| MediaPipe BlazeFace (face detection) | Apache-2.0, installed into its own venv | `faces/mediapipe.ts`, `commands/install-mediapipe.ts` |
| WhisperX | Open (BSD-2); local | `commands/install-whisperx.ts` |
| VEED transcription | **Closed hosted API** (`www.veed.io/api/v1`), spends VEED transcription credits | `veed/api.ts`, `veed/orchestrate.ts` |
| VEED Fabric presenter (`veed/fabric-one-lipsync`) + TTS preview | **Closed, paid** (AI Playground credits) | `veed/fabric*.ts`, `commands/generate*.ts` |
| Background removal, default route | **Closed hosted, free** (VEED project route) | `commands/background-removal.ts` |
| `veed/video-background-removal[/fast]`, `veed/lipsync/v2` on fal | **Closed models, paid** on the user's fal key | same + `commands/lipsync.ts` |
| VEED editor hand-off / pull (bookmarklets run inside veed.io) | Open client side; the editor is closed | `veed/editor-project.ts`, `commands/veed-project.ts`, `veed-pull.ts` |
| Any other fal model (Seedance, image models, TTS, music) | Third-party, paid, per-model terms | `providers/fal.ts`, `commands/fal.ts` |

---

## 2. Deep dives

### 2a. Partial re-render on revision **[code]**

This is our top interest. Files: `cli/src/commands/render.ts` (`renderVideo`, lines 933-1298), `cli/src/render/encode.ts`, `cli/src/render/timing.ts`, `cli/src/render/footage.ts`, `cli/src/render/text-record.ts`, `cli/src/render/media.ts`.

**What the user sees.**
- "Make the yellow darker" or "move the caption at 0:42 up" re-renders a few seconds, not the whole piece.
- The CLI prints `segments: 2 rendered, 28 reused` and lines such as `also rendering segment(s) 7 outside --from/--to again: the page shows other text ... (segment 7 at 14.033 s: text "Doors open at 7", which it did not show)`.

**1. Segmentation.**
- `planSegments(total, segmentFrames)` cuts the timeline into **fixed-length segments of `--segment` seconds, default 2**, rounded to whole frames (`timing.ts:53-63`).
- The grid depends only on the total frame count and the segment length. It does **not** follow content or cuts.

**2. What gets re-rendered.**
- **The agent chooses the range.** `--from/--to` is mapped to frames (`frameSpan`: a range that starts or ends inside a frame takes that frame), and then to every segment touching it (`segmentsTouching`).
- **There is no automatic source diff.** The page is recorded in the manifest by *path*, not by content hash, so editing the HTML does not by itself invalidate anything.
- **The cache must match exactly.** A patch is refused unless every manifest `Params` field is identical to this run's:
  - page path, fps, width/height, frames, segmentFrames, transparency, capture format/scale/quality
  - footage identity (path + size + mtime) and footageAt
  - HDR conversion chain, alpha handling, recodes, text floor, injected zone
  - the full encoder arg string, the Chrome build, and the ffmpeg banner
  - The check is `paramsDiffer`, `render.ts:696-700, 1005-1008`.
  - A different length or fps therefore means a full render.
- **A safety net catches segments outside the range that went stale.** Each candidate for reuse also passes these checks:
  1. **File integrity:** the segment file exists and its byte size equals the manifest's.
  2. **Text cache:** a usable `seg-N.text.json` exists. Otherwise the segment is re-rendered so the text record stays whole.
  3. **Media bytes:**
     - The manifest stores a `contentId` for every image/video the page loaded: a sha256 of the file, memoised by dev/inode/size/mtime/ctime in `runs/.media/versions/` (`media.ts:145`).
     - It also stores, per segment, `shows`: the `<video>`/`<img>` files its sampled frames displayed.
     - A segment that showed a changed file is re-rendered.
     - A changed file that **no sampled frame places** (a CSS background, an image drawn into a canvas) forces **every** segment to re-render.
  4. **DOM state comparison** (`changedState`, `render.ts:865-918`):
     - While the range renders, *extra* Chrome sessions (one per spare CPU, about one per 80 frames) **jump** to every sampled frame of every reusable segment. Samples are taken every ~100 ms of page time (`SAMPLE_MS = 100`, a whole number of frames).
     - At each frame they read the page's text and media state and compare it with the sample cached at render time (`stateDiffers`, `render.ts:832-852`).
     - **The comparison covers:**
       - every text entry: string, glyph box, drawn font size, fill colour, opacity, backing opacity, selector (`TextEntry` in `render/text-sampler.ts:21-47`)
       - every page `<video>`: file, clip time, box, visible box
       - `<img>` files not shown before
     - Any difference marks the segment stale.
     - A page that throws when jumped into marks its segments "unchecked", and they are re-rendered too.
  - All stale segments are rendered in a second pass after the requested range.
- **Blind spot.**
  - A purely visual change with no text, video or image outside the given range goes undetected and leaves a **stale segment**. Examples: a shape's or background's colour, an SVG path, a CSS filter, a canvas drawing.
  - The skill's answer is "re-render what changed": the agent has to give a range wide enough.

**3. Rendering the stale segments.**
- **Work split:** the segments are split into contiguous runs across workers (`splitFrames`). A run may start or end mid-segment.
- **Encoding:**
  - A worker that owns a whole segment streams PNGs straight into that segment's encoder.
  - A segment split across workers is **spilled** as one PNG per frame to `spill.<attempt>/`. It is encoded in order once all workers finish (`render.ts:1162-1177`).
- **Stateful pages pay a preroll.**
  - Each worker first steps through *every frame before its first* (no capture, but every `<video>` is seeked).
  - So a patch late in a long piece pays that whole preroll, which is the main cost of a patch on such a page.
  - Pages marked `data-stateless` (verified) jump straight in. *Remotion compositions are frame-pure by design, so we'd always be in the cheap case.*
- **Footage:**
  - With `--footage`, each segment's encoder takes the footage as input 0, input-seeked to the segment's first footage frame (`seekArgs`: `-ss (start-0.5)/fps + offset`).
  - It pads black before and after where the clip doesn't cover (`tpad`), and overlays the page's straight-alpha PNGs.
  - So the footage is **re-encoded per segment together with the overlay**. There is no separate base layer to reuse.
- **Atomic writes:**
  - Writes go to `seg-N.<pid>-<rand>.tmp` and are then renamed.
  - The old text JSON is deleted *before* the rename and the new one written *after*. A crash then leaves a segment with no text, which the next patch re-renders, and never old text next to new pixels.
  - A `.lock` file holding the PID prevents two renders into one cache. A stale lock is taken over by an atomic rename-aside (`acquireLock`, `render.ts:623-664`).

**4. Stitching** (`encode.ts:187-211`, `joinSegments`).
- **Why stream copy works:**
  - Every segment comes from a **fresh ffmpeg process**, so it starts on an IDR frame. That gives a closed GOP at each segment start with no special flags.
  - Every segment uses **byte-identical encoder arguments**, so the SPS/PPS and stream parameters match. This is what lets the concat demuxer copy them back to back.
  - `-threads 4` is fixed rather than scaled to the worker count, so x264 output is deterministic: the same page gives the same bytes whatever `--workers` was.
- **The join:**
  - It writes an **ffconcat list with an explicit `duration` for each file**. Durations are computed from cumulative frame counts in whole microseconds, as `us(at+frames) − us(at)`, so rounding never accumulates.
  - The comment explains why: ffmpeg 7 writes a segment laid over footage with its last frame carrying no duration, so the files' own durations can't be trusted.
  - Then: `ffmpeg -f concat -safe 0 -i concat.txt -c copy -an -movflags +faststart` → tmp → rename.
- **Post-join verification:**
  - `timingProblems` (`encode.ts:218-243`) ffprobes every packet pts without decoding.
  - It checks the frame count, that each frame lies within one tick of `i·den/num`, that the first pts is 0, and that the length is within half a frame.
  - Any failure makes the render fail and name the problem.
- **Post-render scan:** `pictureNotes` looks only at ±(end-card cap + still window) seconds around the patched range, plus the opening if the range starts at 0 (`render/picture-notes.ts`).

**5. Audio.**
- **The render is always silent** (`-an`).
- `mux-audio` lays sound on afterwards with `-c:v copy` and AAC 48 kHz, loudnorm to −14 LUFS / −1 dBTP (`commands/mux-audio.ts:173-177`).
- `mix-audio` builds a soundtrack from a mix spec (voice ducks music and SFX, the music bed loops with crossfades and fades out).
- So after a patch, the agent re-runs mux. The **whole audio track is re-encoded each time**, which is cheap; the picture is never re-encoded.
- `mux-audio` also copies `<video>.text.json` next to its output so `review` still has the record.

**6. A second, separate incremental layer: the cut (`apply-edl`).**
- Each EDL range's *picture* is encoded on its own into `<cut>.ranges/<key>.mp4` (`apply-edl.ts:707-748`).
- The key is `sha256` of: ffmpeg build + source **content digest** + all ffmpeg args (path removed) + the reframe crop script + the LUT digest.
- Changing one range re-encodes only that range. The rest are concat-copied.
- **The sound is re-cut from the sources on every run** in one filter graph: per-range `afade` in/out over extra audio taken from past each out-point, mixed rather than `acrossfade`d, with speech levelled across sources by measured LUFS. A butt join clicks, and decoding audio is cheap.
- Video joins are hard cuts (stream copy). Only the audio crossfades.

**Our adaptation (effort M).**
- Our timeline JSON is declarative, so we can do **content-addressed segments** instead of DOM sampling:
  - **Grid:** split the reel into fixed segments, 1-2 s, frame-snapped. The base render and the Remotion overlay must share one grid.
  - **Per-segment fingerprint:** `sha256(global render params + every timeline item whose [start−pre, end+post] overlaps the segment + asset content hashes + encoder args + ffmpeg/Remotion versions)`.
    - Transitions, punch-ins, caption cues and motion graphics that straddle a boundary dirty both neighbours.
    - Stateful filters such as `zoompan` or temporal denoise need a lookback margin.
  - **Render:** only dirty segments.
    - Base: ffmpeg with `-ss` input seek + `-frames:v N`.
    - Overlay: Remotion `renderMedia({frameRange:[a,b]})`.
    - Composite each segment, or better, composite inside the same ffmpeg segment encode as OpenEdit's `--footage` path does.
  - **Encode:** every segment with identical args and fixed `-threads`.
  - **Join:** ffconcat with explicit µs durations, then `-c copy`. Port `concatList` + `timingProblems` from `encode.ts` with attribution.
  - **Audio:** keep it separate and remux at the end (we already duck and beat-align, so re-mixing is cheap).
- This turns a client note like "change the caption at 0:12" from a full base+overlay+composite re-render into about 2-3 segments plus one mux.
- **Risks:**
  - Segment-boundary flicker if a filter isn't frame-pure.
  - Encoder-param drift after an ffmpeg upgrade. Mitigate by putting versions in the manifest, as they do.
  - Ensure every segment starts on an IDR frame; it does when there is one process per segment.
  - Variants (other aspect ratios or lengths) can't share caches.

### 2b. Frame review loop

- **What the user sees:** the README says "looks at the frames and fixes what it sees" **[README]**. Nothing in the code does vision. The **agent** looks at images using the tools below, and chooses which moments itself **[skill]**.
- **Tools [code]:**
  - `frames <video> --at 12.5,1:02 --frame 300-306 --every 0.5 --from 8 --to 11 --sheet`: exact-frame stills with half-frame-early seek arithmetic (`commands/frames.ts:73-88`), files named by frame index and seconds, tiled into one contact sheet. `--images <dir>` tiles reference pictures into one sheet (one turn, not N).
  - `render --stills 0.5,2,4 --sheet s.jpg`: renders just those moments of the *page* without a video render, composited over the footage when `--footage` is given (`renderStills`, `composeStill`).
  - `shots <reference>`: shot list plus storyboard sheets, 3 labelled frames per shot of 1 s or more (first/middle/last), the middle frame for shorter shots (`storyboard.ts`). Used for "make it like this reference".
  - `behind <page>`: per graphic laid behind the speaker, the worst-frame and mean visible share and the least-visible word. Measured by capturing the speaker layer and each graphic alone with alpha on Chrome's own drawing. Pass bar: 75% of the graphic and of each word on every frame (`commands/behind.ts`).
- **Automatic notes after every render** (`render/picture-notes.ts`, which never fail the render):
  - frame 0 blank, near-black or mid-fade (it becomes the platform cover)
  - stills/freezes held longer than their words allow
- **`review <final.mp4>`** is a pre-delivery report. It never modifies and always exits 0. `verify/checks.ts` holds 9 checks:
  - `dead-tail`: picture runs on more than 1 s past the last sound or word, with end-card logic.
  - `dead-air`: frozen or near-still picture over its limit; audio gaps over 2 s.
  - `length`: vs. the brief, ±max(1 s, 5%).
  - `canvas`: nearly-but-not 9:16, or under 1080 on the short side.
  - `blank-frames`: flashes of flat colour.
  - `text`: under the phone body-size floor, or below WCAG 3:1 contrast **measured on the video's actual pixels around the glyphs**.
  - `captions`: 1 s or more of speech with no caption (it recognises translated captions by rhythm, 3 phrases in step).
  - `numbers`: a number on screen that neither the transcript nor the brief says.
  - `graphics`: text over a graphic burned into the footage.
- **The text record makes these OCR-free:**
  - `render` writes `<out>.text.json`: every DOM/SVG text, sampled every ~100 ms, with box, font size, colour, opacity and backing, plus every page video's file, time and box.
  - Checks read that instead of OCR'ing pixels.
- **How fixes are applied:** the agent edits the HTML/CSS/`__seek` code, then re-renders with `--from/--to` around the moment. Findings are "yours to judge, not an order to re-render", and the agent must tell the user about findings it leaves **[skill]**.
- **For us:**
  - We already do contact sheets and measurements.
  - Worth stealing:
    1. Contrast measured on rendered pixels around each text box.
    2. Emitting a text record from Remotion props or our timeline, so checks are OCR-free.
    3. The first-frame-as-cover check.
    4. The `behind` visibility metric as a QA gate on our text-behind-subject hook.
    5. The "findings are reported, not auto-fixed" contract for our Reviewer persona.
  - Effort: S each.

### 2c. Caption timing and drift

- **The README's refusal claim is overstated.** It says "a transcript that has none [word timings] is refused rather than rendered badly" **[README]**. The code is more forgiving **[code]**:
  - `transcript/whisper-mapper.ts` maps every Whisper family through one pipeline:
    - WhisperX/openai/mlx/timestamped; OpenAI `verbose_json`; whisper.cpp `-oj -ml 1`, whose offsets are in ms
    - fal whisper/wizper chunks; flat word lists; TTS character timestamps
    - The pipeline is normalise → time → group → order → assert.
  - **Refused only if *no* word has a timing** (`whisper-mapper.ts:367-373`): "Without them the caption animation desynchronises".
  - **Partially-timed transcripts are interpolated:** each run of untimed words is spread between its neighbours' anchors, *across* segment boundaries, proportional to token length. They are counted and warned about ("12 of 340 words came back without timings, so those reveals are approximate").
  - A provider "word" containing whitespace (a segment in disguise) is split and counted as interpolated, so it doesn't pass as word-timed.
  - There is a hard invariant: words in == words out.
- **Why word timings matter:**
  - Captions are revealed per word (`data-state=next|now|said`) on the page clock.
  - With segment-level timings only, word reveals would be guessed, and the error accumulates within a segment ("drift").
- **Cut retiming:**
  - `apply-edl` and `retime-transcript` move source word times onto the cut, adjusting for speed changes.
  - The cut is **never re-transcribed**. The retimed transcript is written where a transcription would land, so the transcribe routes refuse to overwrite it.
- **Cue shaping** (`captions/page-script.ts`, which runs in both the page and Node):
  - It is dynamic-programming segmentation over word boundaries.
  - Break costs: sentence end 300, pause scaled 50-200 by gap, clause 25.
  - Limits: at most 2 lines × 42 characters (Netflix TTSG). Lines are fitted to the element's width **in the page's own font**, measured in the browser.
  - Timing: lag-out 0.5 s; gaps under 0.5 s are closed, so the screen clears only in a silence of 1 s or more. Hold is 0.5-7 s.
  - Emphasis: `data-key-words="forty@12.34"` gives at most 2 emphasised words per line.
  - Modes: one-word-at-a-time and one-line via attributes.
- **Placement:**
  - With `faces.js`, cues are placed off faces *and* off graphics burned into the footage.
  - Each cue holds one position per shot and moves only at a cut, unless no single spot clears every cue in that shot (`openeditFaces.placer`).
- **India-fit gaps (verified in code):**
  - The `SENTENCE` regex (`page-script.ts:59`) lacks the Devanagari danda `।` (U+0964), so Hindi-script captions won't break at sentence ends.
  - The numbers check knows English number words only, with scales thousand, million, billion and trillion (`verify/numbers.ts:40-41`). There is no lakh/crore or Hindi number word, so "1.5 lakh" spoken vs. "₹1,50,000" on screen would be flagged falsely.
  - `₹` *is* in the `CURRENCY` set (`numbers.ts:59`). But the "text is a single number" filter in `soleValue` (`numbers.ts:439`, character class `[^\d\s.,:%$€£+-]`) leaves out `₹`. So a lone "₹499" card may be handled differently from "$499". Verify before porting.
- **For us:** we already require word-level ASR. Worth porting (S):
  - The tolerant mapper with an interpolation count, if we accept third-party transcripts.
  - The DP cue breaker with in-font width fitting.
  - The "move only at cuts" placement policy.
  - The cue-shaping code is plain JS/TS, so it can be vendored into our Remotion layer with attribution.

### 2d. Translation and re-lip-sync

- **What the user sees** **[README]**: "translate my video to 5 languages using VEED Lipsync 2.0 on Fal". The result is one source clip with ES/FR/DE versions, re-lipsynced, each with its own caption style.
- **What exists in code:**
  - `commands/lipsync.ts`: `openedit lipsync video.mp4 narration.mp3 [--out]` calls the fal model **`veed/lipsync/v2`**.
  - The local video and audio are uploaded to **VEED asset hosting** (VEED login needed, not billed) so fal can fetch URLs, then the fal queue job is submitted.
  - **Pricing:** `$0.07 per second of output` on the **user's fal key** (code constant `FAL_LIPSYNC_V2_PRICE_PER_SECOND`, "fetched 2026-08-19"). A 60 s reel is about $4.20 per language.
  - HDR input is sent as an SDR copy.
  - Idempotent via `submitOnce`: identity = sha256 of the video and audio bytes, so a re-run resumes the paid job instead of re-buying.
- **What does NOT exist:** there is no translation code and no TTS/dubbing command.
- **The translation flow is [inferred]:**
  1. The agent (LLM) translates the transcript.
  2. `fal run <tts-model>` produces narration. Any fal TTS is allowed; it is the agent's choice and paid.
  3. `whisper tts-result.json narration.mp3` maps the TTS **character timestamps** into a word-timed transcript (the mapper supports that format explicitly).
  4. `lipsync video.mp4 narration.mp3`.
  5. `captions` on the new transcript, then render, mix and mux.
- **Paid parts:** the TTS model (fal), lipsync ($0.07/s, fal) and optional VEED transcription.
- **For us (M):**
  - Pipeline: Claude translation with a duration budget per phrase (Hindi↔English, regional languages) → TTS with voice clone (fal or ElevenLabs/Sarvam) → time-fit (atempo ±10%) → `veed/lipsync/v2` or an open alternative → retime captions from TTS alignment → our existing finish pass.
  - **Risks:**
    - Voice-clone consent and the platforms' synthetic-media labels.
    - Lip-sync artefacts on fast Hinglish code-switching.
    - Per-language cost.
    - Fabric/Lipsync model terms are VEED's.
  - **Reuse:** nothing to vendor except the ledger idea and the mapper's character-timestamp branch.

### 2e. Brand book via Figma MCP

- **[README] only.** The prompt "use Figma MCP to study my BrandBook and create branded campaign graphics using /open-edit" shows 3 campaign cards.
- **There is no Figma code in the repo.** A grep finds "figma" only in a CSS comment in `veed/login-success.html`.
- The mechanism is the coding agent's own Figma MCP (get design context, variables and screenshots) feeding colours, fonts and layout into the HTML page it writes. `fonts` fetches Google Fonts locally; brand fonts not on Google must be supplied as files.
- **For us (S):** we already have Figma MCP tools in this environment.
  - Add a `brand_kit` ingest that pulls variables (colours, type scale), logo exports and a page screenshot into our brief/brand profile. The story and finish passes consume it.
  - Fit caveat: many Indian SMB and creator clients keep brand kits in Canva or a PDF, not Figma. Add a Claude-vision path over PDF/PNG brand guidelines as the default, with Figma as the premium option.

### 2f. Other features we lack (candidates)

| Feature | What the user sees | Mechanism [code] | Files |
|---|---|---|---|
| **Reference-reel matching** (`shots`) | "Make it like this reel": the agent studies the reference's cuts, shot sizes and pacing | Hard cuts and fades through black, plus per-shot speech from its transcript and shot size from face boxes (CU/MCU/wide/no face), with storyboard sheets. Documented limits: dissolves read as one shot; about 1 in 3 jump cuts missed | `commands/shots.ts`, `storyboard.ts`, `faces/shot-size.ts` |
| **Numbers/claims check** | No wrong price or stat on screen | Numbers from the text record vs. transcript + brief, by value ("15 min" = "fifteen minutes" = "0:15"; "1.4M" ≈ 1,423,000). List numbering, clocks, names and under-0.25 s flashes are excluded | `verify/numbers.ts` |
| **Reframe 16:9→9:16 with face-follow + subtitle erase** | Podcast/YouTube → Reel crop that follows the speaker | The crop holds still while the face stays inside and eases only when it must; jumps at cuts; holds on the "most face height" for multi-face shots. `--erase` sends 6 s parts to a fal video model to remove burned subs (quoted, approve-once) and lays back only the erased rows | `commands/reframe.ts`, `faces/erase.ts` |
| **Captions avoid faces + burned-in graphics** | Captions never sit on a face or an old lower third | MediaPipe BlazeFace at 4 fps + OCR-free graphic detection (sharp, axis-aligned edges that hold while the frame changes); `place()` moves an element the least distance to clear them | `faces/*.ts`, `faces/graphics.ts` |
| **Screen-recording auto-zoom** | Tutorials legible on a phone | Cursor/click detection from frame differences, zoom until the text near the click reaches the min text size | `zoom/*.ts`, `commands/zoom.ts` |
| **Generated media via fal** | AI hooks/b-roll (Seedance), images, music, SFX | Generic `fal run` with upload, cost line and the never-buy-twice ledger | `providers/fal.ts`, `providers/queue-ledger.ts`, `commands/fal.ts` |
| **AI presenter (Fabric)** | Talking head from a script, no footage | VEED API + `veed/fabric-one-lipsync`; quote → approve → spend | `veed/fabric*.ts`, `commands/generate*.ts` |
| **NLE round-trip** | Client edits in VEED's editor, the agent pulls changes back | Plan JSON ↔ editor items; each page element becomes a transparent clip; bookmarklets | `veed/editor-project.ts`, `commands/veed-*.ts` |
| **Draft renders** | Fast preview links | Half scale, JPEG, ultrafast; separate cache | `commands/render.ts` (`DRAFT`) |
| **Platform safe zones incl. ads** | Text never under the TikTok/Reels UI | Per-app zone tables, a stricter `--ad` variant, size tokens | `commands/safe-zone.ts` |
| **Licensed stills** | Real photos with recorded terms | Wikimedia Commons search/save with a licence sidecar | `commands/stills.ts` |
| **Paid-call ledger** | No surprise double charges | Content-keyed claim → submit → record with leases | `providers/queue-ledger.ts` |

---

## 3. Feature cards (for us)

Effort: S ≤ 3 days, M ≈ 1-2 weeks, L > 2 weeks, for one dev on our stack.

1. **Segment-cached partial re-render**
   - User sees: revisions in seconds, not minutes; more revision rounds per day.
   - How: §2a.
   - Deps: ffmpeg concat demuxer; Remotion `frameRange`.
   - Licence: none new.
   - Effort: **M**.
   - Reuse: port `concatList`, `timingProblems`, the manifest/params-equality idea and the atomic tmp→rename + lock (Apache-2.0, attribute + NOTICE).
   - Rebuild: the fingerprinting from our timeline JSON.
   - Risks: boundary artefacts from non-frame-pure filters; cache invalidation bugs. Mitigate by putting tool versions and encoder args in the manifest and keeping a "full render" escape hatch.
2. **Numbers/claims check**
   - User sees: nothing wrong ships (prices, %, dates).
   - Deps: none.
   - Effort: **S** (+S for Hindi/Indian numbering: lakh, crore, 1,50,000, hazaar, Hinglish number words).
   - Reuse: the logic of `verify/numbers.ts` (port to Python, attribute).
   - Risks: false positives on Hinglish speech.
3. **Reference-reel matching**
   - User sees: "send me a reel you like" → the edit mirrors its rhythm, shot sizes and caption style.
   - Deps: our scene/face detection.
   - Effort: **M**.
   - Reuse: the storyboard selection rule (first/middle/last for shots ≥1 s) and the shot-size bins; rebuild in Python.
   - Risks: Instagram download ToS; copying a style too literally.
4. **Translation + re-lip-sync**
   - User sees: the same reel in Hindi, English, Tamil and more, lips matching.
   - Deps: fal `veed/lipsync/v2` (**closed, paid $0.07/s**) or alternatives, plus a TTS/voice clone (paid).
   - Effort: **M**.
   - Reuse: the ledger pattern and the character-timestamp mapping idea.
   - Risks: consent, cost, quality on code-switching, platform AI labels.
5. **Brand kit ingest (Figma MCP + PDF/Canva vision)**
   - User sees: on-brand colours, fonts and logo with no setup.
   - Deps: Figma MCP (already available), Claude vision.
   - Effort: **S**.
   - Reuse: nothing (no code upstream).
   - Risks: font licences for brand fonts; Figma access per client.
6. **Text-placement policy (faces + burned-in graphics, move only at cuts)**
   - User sees: captions never collide with faces or on-screen text.
   - Deps: our faces + OCR.
   - Effort: **S-M**.
   - Reuse: the algorithm description in `faces/page-script.ts`.
   - Risk: jitter if detection is noisy.
7. **Render-pixel QA additions** (contrast on real pixels, first-frame cover, behind-subject visibility ≥75%, text size floor)
   - Effort: **S**.
   - Reuse: thresholds and approach from `verify/text.ts`, `verify/blank-frames.ts`, `commands/behind.ts`.
8. **Podcast → reel reframe with face-follow**
   - User sees: long 16:9 → 9:16 clips.
   - Effort: **M**.
   - Reuse: the hold/ease/jump policy from `commands/reframe.ts`.
   - The subtitle-erase step is paid (fal).
9. **Draft previews**
   - Effort: **S**. Half-res, ultrafast, separate cache.
10. **Generated hooks/b-roll via fal**
    - Effort: **M**.
    - Paid; brand-safety and licence terms per model.
11. **Screen-recording zoom**
    - Effort: **M**. Niche (edtech/SaaS).
12. **NLE round-trip pull-back**
    - Effort: **L**. Low fit; we already export NLE packages.

---

## 4. Ranking: top 6 by (wow × fit) ÷ effort

- Wow: 1-5, client-visible delight.
- Fit: 1-5, a freelance reel editor serving Indian creators and brands.
- Effort: S = 1, M = 2, L = 3.

| Rank | Feature | Wow | Fit | Effort | Score | Why |
|---|---|---|---|---|---|---|
| 1 | **Brand kit ingest** (Figma MCP + PDF/Canva vision) | 4 | 3 | S | **12** | Instantly on-brand first drafts; no upstream code, but trivial for us with the MCP already present. |
| 2 | **Segment-cached partial re-render** | 4 | 5 | M | **10** | Clients feel it as turnaround: a note at 7 pm gets a fix in minutes. Directly attacks our slowest loop. |
| 3 | **Reference-reel matching** | 4 | 5 | M | **10** | Indian creators brief by sending reference reels; mirroring rhythm and shot sizes is visibly "gets it". |
| 4 | **Translation + re-lip-sync** | 5 | 4 | M | **10** | Highest wow; multi-language (Hindi/regional) versions are a sellable upsell. Paid per second, so price it in. |
| 5 | **Numbers/claims check** (+ lakh/crore) | 2 | 5 | S | **10** | Invisible when it works, catastrophic when missing (wrong ₹ price or offer). Cheap insurance. |
| 6 | **Text placement avoiding faces + burned-in graphics, moving only at cuts** | 3 | 4 | S-M (1.5) | **8** | Polished, "professional" look across every reel; builds on faces/OCR we already have. |

- Next in line, about 8 each: render-pixel QA additions (S), podcast→reel reframe (M), draft previews (S).
- The partial re-render ties at 10 with three others. I'd still **build it first**: it compounds (every later feature's revisions get cheaper) and it is our stated bottleneck.

---

## 5. Licence and reuse notes

- **Apache-2.0 obligations:**
  - Keep a copy of the licence.
  - Add the NOTICE text ("open-edit, Copyright 2026 VEED LIMITED, This product includes software developed at VEED") to our NOTICE.
  - Mark modified files with a "changed from open-edit" note.
  - The patent grant is included and terminates if we sue over the patents.
  - The embedded Inter and STIX fonts are OFL; irrelevant unless we copy `login-success.html`.
- **Safe to port with attribution:**
  - `render/encode.ts` (`concatList`, `timingProblems`, encoder-arg discipline), `render/timing.ts` (rational fps, segment planning)
  - the cue shaper in `captions/page-script.ts`, the mapper in `transcript/whisper-mapper.ts`
  - `verify/numbers.ts` logic, the safe-zone tables in `commands/safe-zone.ts`
  - the queue-ledger design in `providers/queue-ledger.ts`
- **Do not depend on:** the VEED API (closed, account-bound, credits), VEED fal models (closed, paid), or VEED bookmarklets/editor. Use them only as optional paid providers behind our own interfaces.
- **Chrome Headless Shell:** only needed if we adopt HTML-page rendering. We use Remotion, which bundles its own Chromium handling. **Remotion's own licence** (company licence above a size threshold) is unchanged by any of this.
