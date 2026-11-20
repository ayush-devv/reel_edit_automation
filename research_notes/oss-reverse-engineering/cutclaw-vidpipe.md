# CutClaw + vidpipe: reverse-engineering for clean-room features

Date: 2026-11-19. Method: read source only (shallow clones; nothing executed). Every claim is tagged
**[code]** (read in source, path given) or **[README]** (project's own claim, not verified in code).
Statements about third-party platforms (API limits, app review, bans) come from general knowledge and are
tagged **[external — verify]**. Untagged statements in the cards are our design proposals.
Repo roots below are abbreviated `CutClaw/` and `vidpipe/`.

## 0. Licence status (read first)

| Repo | Finding | Consequence for us |
|---|---|---|
| CutClaw (GVCLab, commit db48d08) | No LICENSE file anywhere [code: `find`]. README has no licence section. | All rights reserved. **Ideas only**; describe mechanisms in our own words; no code or prompt text copied. |
| vidpipe (htekdev, commit 9660a8b) | `package.json` says `"license": "ISC"`; README badge and "ISC © htekdev" [README]. **No LICENSE file in the repo**, even though `package.json` `files` lists one [code]. | Reuse is reasonable under the declared ISC with attribution ("ISC © htekdev", link to repo, keep notice in our THIRD_PARTY file). Risk: no licence text to copy; record the declaration (package.json + README line) as provenance. Its deps are mostly MIT/Apache; see per-card notes. |

Third-party pieces these repos depend on (checked on the project pages today):

| Dependency | Used by | Licence | Flag |
|---|---|---|---|
| madmom | CutClaw downbeats (RNN + DBN) | code BSD; **model/data files CC BY-NC-SA 4.0**; commercial use requires contacting the authors | **NC — do not use** |
| aubio | CutClaw pitch + mel-energy keypoints | **GPL-3.0-or-later** | **Copyleft — avoid** (librosa does the same) |
| Beat This! (CPJKU/beat_this) | alternative for us | code **and weights MIT** (training data mixed — their own caveat) | OK |
| All-In-One (mir-aidj/all-in-one) | alternative for song sections | repo MIT; weights' licence not stated on the page; I believe it pulls madmom for post-processing — **verify before use** | Check |
| pyannote speaker-diarization-community-1 | CutClaw diarization | CC-BY-4.0, gated on HF | OK with attribution |
| UltraFace ONNX | vidpipe webcam detection | MIT (repo) | OK |
| Montserrat | vidpipe captions | OFL (`assets/fonts/OFL.txt`) | OK |
| Gemini 2.5 Pro, OpenAI whisper-1, gpt-image-1.5, Exa search, Late API (getlate.dev), GitHub Copilot SDK (needs Copilot subscription), Azure/AWS storage | vidpipe | **paid / closed SaaS** | Replace with Claude + our stack |
| scenedetect (BSD-3), decord (Apache-2.0), sentence-transformers all-MiniLM-L6-v2 (Apache-2.0), whisper.cpp (MIT), LiteLLM (MIT) | CutClaw | permissive | OK |

---

## 1. CutClaw — how it works

Goal [README]: turn hours of film/vlog footage plus one song into a music-synced montage from a one-line
instruction. Built around **a named protagonist in a film** (Joker, Batman); the prompts reject any
shot without the protagonist. That framing matters for fit: our footage is talking heads.

### 1.1 Decomposing long footage [code]
Three threads run in parallel (`local_run.py` `main`):
- **Thread A (film only):** ASR via cloud model through LiteLLM or local whisper.cpp, optional pyannote
  diarization, adjacent same-speaker lines merged if gap ≤ 1 s (`src/config.py`, `src/video/preprocess/asr.py`).
  Then one LLM call reads the whole subtitle file to name characters and map speakers (`src/video/deconstruction/get_character.py`).
- **Thread B:** frames decoded at 2 fps, short side 240 px. Shot boundaries by PySceneDetect `AdaptiveDetector`
  (film: threshold 3.0, min 3 frames; vlog: 1.5, min 45) (`src/video/preprocess/video_utils.py`, `src/config.py`).
  Shots longer than 30 s are chunked. **One VLM call per shot** fills a fixed JSON schema: location type,
  3–5 environment tags, time of day, lighting, colour palette, characters + expressions, props, main action,
  shot scale, camera move, angle, narrative function, mood (`SHOT_CAPTION_PROMPT` intent, `src/video/deconstruction/video_caption.py`).
- **Shot → scene merge** (`src/video/deconstruction/scene_merge.py`): adjacent shots are merged into a scene unless
  similarity < 0.5. Similarity = 0.30 × location (soft lookup table, e.g. interior↔exterior 0.05) + 0.15 × time
  of day (soft table) + 0.35 × environment-tag set similarity (MiniLM embeddings, mean best-match both ways) +
  0.20 × cosine of the "lighting + palette" text embedding. "Bridge" shots (inserts, reactions, close-ups) don't
  break a scene; scenes > 300 s are split, tiny ones merged.
- **Scene analysis:** one VLM call per scene (6–64 sampled frames + subtitles). It classifies the scene
  (content / studio logo / title card / credits / transition / mixed) and scores **editing importance 0–5** on
  emotional intensity and visual quality (`src/video/deconstruction/scene_analysis_video.py`, prompt intent in `src/prompt.py`).
- **Thread C (audio)**, see 1.3.

All results are cached on disk per video, so re-editing the same footage with a new instruction skips this
stage [code: existence checks in `local_run.py`; README says the same].

### 1.2 Screenwriter → Editor → Reviewer loop [code]
**Screenwriter** (`src/Screenwriter_scene_short.py` `Screenwriter.run`), all plain LLM calls:
1. *Pick the music span.* The LLM sees the song's Level-1 sections (name, description, times, a "duration ok"
   mark) and the instruction, and returns one section index. Target 5–15 s (`AUDIO_SEGMENT_MIN/MAX_DURATION_SEC`);
   a section outside that range is cut to its first 10 s (the midpoint of 5–15). Up to 3 retries with validation feedback; fallback is the
   section closest to 10 s. Prompt intent: prefer chorus/drop/build-up unless the mood says otherwise.
   (`src/audio/short_music.py` has an energy-density "find the climax" picker, but **nothing calls it** [code].)
2. *Structure proposal.* Sees every scene summary, the audio summary and the sections in the chosen span. It
   must pick 8–15 scenes, every one featuring the protagonist, and spread across early/middle/late thirds of the
   film. A deterministic check rejects < min(8, n) scenes, bad indices, or an empty third, and feeds the reason
   back (max 2 retries).
3. *Shot plan.* For each music sub-segment in the span: one shot, duration = the sub-segment's duration
   ("exactly"), drawn from the chosen scenes. Prompt intent: storyboard language only (what is visible), score
   each candidate 0–3 on style, visible elements, energy match and subject presence (target 9–12/12); fast
   segment → motion/impact, build-up → anticipation, drop → explosive/reveal, breathing space → stillness;
   vary shot scale between neighbours; reject any choice that needs dialogue or plot to make sense.
4. *Hook dialogue.* From the subtitles, the LLM picks one continuous run of lines (target ~15 s; hard window
   max(6, t−5)…t+5 s) that is dramatic, quotable and understandable out of context, preferably spoken by the
   protagonist; no banter, filler, ping-pong or singing. The answer is matched back to real subtitle lines by
   text similarity and the duration is re-checked; it searches the tail of the subtitles first, then the head,
   then 3 random windows.

**Editor** (`src/core.py` `EditorCoreAgent`, one ReAct agent **per shot**, function calling, temperature 1.0,
≤ 20 iterations). Tools:
- `semantic_neighborhood_retrieval`: lists shot captions of the recommended scenes; the agent may look only
  ±3 scenes around them (enforced, otherwise an error is returned).
- `fine_grained_shot_trimming`: sends up to 60 frames of a requested range + subtitles to the VLM, which returns
  sub-segments with cut type, description, visual quality 1–5, mood, intensity and protagonist presence. Output
  is rejected and retried if the segments cover < 50 % of the range.
- `review_clip`: overlap check against already-used ranges.
- `commit`: up to 3 stitched sub-ranges, gaps ≤ 2 s; auto-trims the last range if it overruns by ≤ 1 s.
Loop guards: an identical trim request three times restarts the shot's conversation; a context-length error
restarts; "no tool call" gets a nudge. Prompt priorities: protagonist present + emotion first, quality and
duration second, literal content match last.

**Reviewer** (`src/Reviewer.py`), runs inside `commit` before it is accepted:
- deterministic: parses ranges, ≤ 3 sub-clips, gap ≤ 2 s, |duration − target| ≤ 1.0 s (`ALLOW_DURATION_TOLERANCE`),
  no overlap with used footage;
- VLM protagonist check: every frame at native fps (capped to 60) in batches of 8, 16 batches concurrently.
  Per frame: protagonist present? minor character? bounding box (in 1000×1000 space), face quality. A frame
  "breaks" if minor character, no protagonist, no box, or box's short side < max(30, min_box/2).
  **Pass if ≥ 70 % of frames are good** (`MIN_PROTAGONIST_RATIO`). The per-frame boxes are stored with the shot
  and later drive the crop.
- Defined but **never called**: an aesthetic score check (lighting/colour/composition/camera/interest 1–5,
  pass ≥ 3.0). The "does the clip match the content/emotion" check is a TODO [code].

**Parallel orchestration** (`ParallelShotOrchestrator`): 4 shot agents at once; if two results overlap, the
one with the higher 0.6 × protagonist ratio + 0.4 × duration accuracy wins and the loser reruns with the
overlap as a forbidden range (≤ 2 rerun rounds). Results checkpoint to JSON so a crashed run resumes.

### 1.3 Music analysis and rhythm [code]
Library: **madmom** `RNNDownBeatProcessor` + DBN tracker (4/4, 55–215 BPM, 60 tempi, transition λ 100,
threshold 0.05, 100 fps), patched for NumPy 2 (`src/audio/audio_Madmom.py`). Plus **aubio** YIN pitch
(keep confidence ≥ 0.8, NMS 0.3 s, ≤ 50 points) and **aubio** 40-band mel energy (peaks ≥ 30 % of max, NMS 0.3 s,
≤ 50 points). Keypoints in quiet stretches (more than 45 dB under the loudest frame) are dropped
(`src/audio/madmom_api.py`). Each keypoint type is min-max normalised separately; composite score =
weight × normalised intensity (weights all 1.0).

Pipeline (`src/audio/audio_caption_madmom.py`):
1. **Level-1 sections** from an audio LLM (README recommends Gemini). It labels Intro/Verse/Chorus/Bridge/
   Build-up/Drop/Outro with times; the prompt asks for 15–45 s sections, code accepts 5–60 s and retries up to
   5 times, then clamps to the song length or falls back to 30 s blocks.
2. Keypoints are budgeted per section: `AUDIO_TOTAL_SHOTS` (200) shared in proportion to each section's keypoint
   count; top-scored kept, then a global minimum spacing, gap filling where an interval exceeds the max, and
   merging where it is under the min.
3. Section boundaries are **snapped to the nearest keypoint**.
4. **Level-2 sub-segments** inside each section: take *all* raw keypoints by strength and accept one as a cut
   only if it is ≥ `min_segment` from every accepted cut; split any interval > `max_segment` evenly.
   Defaults in code: min 0.1 s, max 2.0 s [code]. README's table says 3.0/5.0 s [README] — they disagree.
5. One audio-LLM call **per sub-segment** returns mood, energy "1–10 + trend", tempo feel.

**How cuts land on the rhythm:** there is no snapping at render time. Each planned shot's length *is* the
keypoint-to-keypoint interval, and the music is trimmed from the chosen section start, so if every shot is
exactly its length the cuts fall on keypoints. But the Reviewer accepts ±1 s, `commit` only trims overruns, and
`render/render_video.py` extracts each clip with its *committed* length and joins them with the concat demuxer.
**Errors accumulate, so later cuts drift off the beat** (code-inferred; not measured). One more useful trick:
if a source shot boundary falls inside a chosen clip, the renderer slides the clip to start at that boundary
(same length), so a hidden source cut never lands between two beats (`adjust_clip_for_scene_cuts`).

**Hook dialogue + music:** with `--render-hook-dialogue`, the dialogue clip plays first with its subtitle
text centred; music starts *earlier in the song by the hook's length*, at 0.5× volume during the dialogue, so
the chosen section starts exactly when the montage starts. Loudness is matched to −18 LUFS / LRA 11 / −1.5 dBTP
and an optional ending bumper gets a music fade.

### 1.4 Vertical cropping [code]
`render/render_video.py` `calculate_optimal_crop_center`: per shot, average the protagonist box centres from
the Reviewer's VLM frames, weighted by box area, scale from 1000-space to pixels, and use **one static
full-height crop** at that x (clamped). No tracking, no smoothing, no per-frame motion. Shots without boxes are
centre-cropped. **We are ahead here**: `engine/src/reel/framing.py` already does static/tracked/fill/speaker
crops per camera shot. No card.

### 1.5 Models and per-run API calls
Models [README]: video VLM "Gemini-3, Qwen3.5, GPT-5.3"; audio "Gemini-3"; agent "MiniMax-2.7, Kimi-2.5,
Claude-4.5"; all through LiteLLM. Calls per run, counted from code (S shots in the film, C merged scenes,
K music sub-segments, P planned shots ≈ 5–15 for a 5–15 s span at ≤ 2 s per cut):
- ASR: batched cloud calls, or 0 with whisper.cpp; character ID: 1.
- Footage: **S** shot-caption VLM calls + **C** scene VLM calls (hundreds to thousands for a feature film; one-time, cached).
- Audio: 1 structure call (≤ 5 retries) + **K** sub-segment calls (K ≈ song length / ~1–2 s ≈ 100–200 for a 3-min song).
- Screenwriter: ≈ 4–8 calls (span ≤ 3, structure ≤ 2, plan ≤ 4, hook 1–2 per window × up to 5 windows).
- Editor per shot: ≤ 20 agent turns + one VLM call per trim (≤ 60 frames each) + ⌈frames/8⌉ (≤ 8) VLM calls per
  commit attempt; × (1 + reruns ≤ 2) for overlap losers.
- Rough total for one short after cached ingest: **~100–400 LLM/VLM calls**. Ingest is the expensive part.

### 1.6 Bugs and README-vs-code gaps [code]
- `local_run.py:451` has a stray `w` line → NameError before the Editor runs from the CLI.
- `local_run.py` imports `src.core_vlog` for vlog mode; the file doesn't exist (vlog editing is broken in the CLI despite README "vlog").
- `core.py:1041` restores `msgs_snapshot`, which is never defined (crash path after model retries fail).
- Aesthetic check unused; content-match review is a TODO; `find_climax_section` unused.
- README segment defaults (3/5 s) ≠ config (0.1/2.0 s).

---

## 2. vidpipe — how it works

Goal [README]: drop a long recording (developer screen-casts with a webcam) in a watched folder and get an
edited video, captions, 15–60 s shorts, 1–3 min medium clips, chapters, a summary, a blog post, social posts
for 5 platforms, thumbnails and a scheduled publish queue. Pipeline in `src/L6-pipeline/pipeline.ts`; each
stage is wrapped so a failure doesn't stop the rest [code].

### 2.1 Finding many shorts in one recording [code]
`src/L4-agents/ShortsAgent.ts`. One agent session over the **whole word-timestamped transcript**
(each segment printed with per-word `[start-end] word`). Tools: `add_shorts` (batches), `review_shorts`
(returns a summary of everything planned, avg score, and asks "would you share it? combine into composites?
drop < 8"), `finalize_shorts`.
- **Viral score** per short = (hook × 3 + emotional intensity × 2 + shareability × 3 + completion × 2 +
  replay × 2) / 3 on 1–5 factors → 1–20; keep ≥ 8 (configurable `minViralScore`).
- Each short must carry: title (5–10 words), description, 3–6 tags, hook text (≤ 60 chars), hook type
  (cold-open / curiosity-gap / contradiction / result-first / bold-claim / question), emotional trigger
  (awe / humor / surprise / empathy / outrage / practical-value), narrative structure (result-method-proof /
  doing-x-wrong / expectation-vs-reality / mini-list / tension-release / loop), share reason, loop flag.
- **Hook-first ordering** (default strategy): the 2–5 s payoff moment is moved to the front, the rest plays
  chronologically up to it, no repeat; the hook must be a complete clause, else stay chronological.
- **Composites** encouraged: "every time X happens", escalation arcs, before/after pairs.
- Duration guidance in prompt: prefer 20–45 s; TikTok 21–34, Shorts 15–30, Reels 7–30.
- Then per short: frame-accurate re-encoded extraction with **1 s padding on each side of every segment**
  (`src/L2-clients/ffmpeg/clipExtraction.ts`), platform variants, captions burned per variant, `.md` metadata.
- **Enforcement gap:** viral ≥ 8, duration window, overlap avoidance and `maxClips` live **only in the
  prompt**; the `add_shorts` handler accepts anything [code]. `maxClips` is computed but never inserted.
- **README overclaims:** the prompt says clip "direction" may come from Gemini visual+audio analysis, and ideas
  can steer clips, but `generateShortsInternal` passes `undefined` for both — **in the main pipeline, shorts
  come from the transcript alone** [code: `src/L5-assets/MainVideoAsset.ts:783–795`].
- Medium clips (`MediumVideoAgent.ts`): same pattern, 60–180 s, 5–8 min chunks, crossfades.

### 2.2 "Visual enhancement" [code]
`src/L5-assets/visualEnhancement.ts`: (1) upload the cleaned video + transcript to **Gemini 2.5 Pro**, which
writes a free-text report of moments where an explainer image would help (timestamp range, what's on screen,
background brightness, image idea, safe placement, 5–12 s), and must say "none" when not needed;
(2) `GraphicsAgent` decides generate/skip per moment and writes a refined prompt; clamps size to 15–30 % of
width; asks for ≥ 10 s between overlays, 6 corner/side regions, flat-infographic style, opaque background
contrasting with the video; (3) **gpt-image-1.5** (quality high, size auto; the code itself estimates **$0.07
per image**) → ffmpeg `overlay … enable=between(t,a,b)` composite. Built for coding screencasts.

### 2.3 Transcript drift handling [code]
- After silence removal the edited video is **re-transcribed** with Whisper and saved as `transcript-edited.json`;
  main-video captions use that (`MainVideoAsset.getEditedVideo/getCaptions`). The older math-shift approach
  (`adjustTranscript` in `pipeline.ts`: subtract removed time; words inside a removal snap to its start) is still
  there; `test-transcript-drift.ts` compares the two and checks a past bug where nested `segment.words` weren't
  shifted (> 2 s drift = warning, > 5 s = fail).
- Shorts sidestep drift by cutting from the **original** video with the **original** transcript.
- `ProducerAgent` prompt: Gemini's timestamps "can drift", the transcript is authoritative; cross-check any
  Gemini cut against spoken words before cutting.
- Silence removal itself (`SilenceRemovalAgent.ts`): ffmpeg `silencedetect` −30 dB / 1 s, only gaps ≥ 2 s sent
  (30 longest), the LLM keeps dramatic/thinking pauses, total removal **capped at 20 %** of duration, single-pass encode.

### 2.4 Social post / caption generation [code]
`src/L4-agents/SocialMediaAgent.ts`: one agent per video, plus one per short and per medium clip. Optional
Exa web search for links first, then one `create_posts` call with 5 posts (TikTok ≤ 150 chars emoji-heavy,
YouTube SEO title+description, Instagram ≤ 30 hashtags (trimmed in code), LinkedIn 1–3 hashtags, X ≤ 280).
Input = clip title/description/tags + overlapping transcript (≤ 3000 chars) + whole-video summary ("tease the
broader topic"). Output = ready-to-paste text in a Markdown file with YAML front-matter (status: draft,
hashtags, links, slugs). A "unified" tone mode keeps one message across platforms. Brand voice is **not**
injected into these prompts [code] (it is into summary/blog/ideation/thumbnails).

### 2.5 brand.json [code]
`vidpipe/brand.json` + `src/L1-infra/config/brand.ts`: name, handle, tagline, voice (tone/personality/style),
advocacy (primary, interests, avoids), **customVocabulary** (joined into the Whisper `prompt` to bias spelling
of brand terms), hashtags (always / preferred / per-platform), content guidelines (shorts/blog/social focus),
pillars, differentiators, **introOutro** (per-platform/aspect files, fade, rules per content type, e.g. shorts
outro only), **thumbnail** (reference image for style transfer, style text, sizes per platform).

### 2.6 Scheduling and publishing [code]
- `schedule.json`: timezone, per-platform per-clip-type weekly slots (e.g. 3 slots/day for shorts), avoid-days,
  idea spacing (same platform ≥ 6 h).
- `src/L3-services/scheduler/scheduler.ts` `findSlot`: walk future slots; take an empty one; idea-linked posts
  displace non-idea posts (which recursively re-find a slot); between two idea posts the sooner `publishBy`
  wins; non-idea posts never displace. `rescheduleAllPosts` replays everything (ideas first, by urgency).
- Publishing via **Late API** (getlate.dev, paid SaaS): upload media → `createPost` with `scheduledFor` or a Late
  queue; rate-limit (429 / daily limit) parks a platform for the batch (`src/L7-app/review/approvalQueue.ts`).
  Note: TikTok calls hard-code `content_preview_confirmed: true` and `express_consent_given: true` — a
  compliance risk (that consent is supposed to come from the user).
- `vidpipe chat` — an agent that edits the schedule conversationally [README; `ScheduleAgent.ts` exists].

### 2.7 Review UI [code + README]
Express app (`src/L7-app/review/routes.ts`, `public/index.html`): pending posts grouped by video/clip, platform
tabs, video preview, edit text (`PUT /api/posts/:id`), approve/reject single or bulk, "next slot" per platform,
accounts/profile. Swipe-style keys: ← reject, → approve, Esc cancels an edit [code: `index.html`,
`index-single.html`]. README says arrows navigate and Enter/Backspace approve/reject [README] — the code's
mapping differs; no Enter/Backspace handler exists.
Approve → schedule → Late.

### 2.8 Other client-facing bits
- **Platform variants** [code `aspectRatio.ts`, `faceDetection.ts`]: 9:16, 1:1, 4:5. For screencasts it finds the
  webcam overlay (UltraFace on 15 frames → corner → edge refinement by column/row brightness steps) and builds a
  split screen (screen ~65 % top, webcam ~35 % bottom); else centre crop.
- **Captions** [code `captionGenerator.ts`]: one ASS event per word state (active word bigger + coloured),
  ≤ 5 words/group, 3 words/line, new group after 0.4 s gap; portrait captions at MarginV 770 and a hook "pill"
  at MarginV 250 to stay clear of platform UI dead zones. (We have this.)
- **Chapters** (JSON/MD/ffmetadata/YouTube text), **summary README with screenshots**, **dev.to blog**,
  **thumbnails** via gpt-image with a brand reference image [code].
- **Idea bank (ID8)**: trend-researched video ideas as GitHub Issues, linked to recordings, used for scheduling
  priority [code + README].
- **Cost report** per run (tokens, $ by agent/model/service → `cost-report.md`) [code]. We already have
  `engine/src/reel/studio/costs.py`.
- Pipeline presets `pipeline-specs/{minimal,clean,full}.yaml`; JSONL progress events on stderr [code].

### 2.9 Per-run API calls (vidpipe, from code)
For N shorts and M medium clips: Whisper 1 call per ≤ 25 MB audio chunk, twice (original + edited);
silence agent 1 session; Gemini 0–1 upload (enhancement) or 1 (producer path); GraphicsAgent 1 session +
0–k gpt-image; ShortsAgent 1 session; Medium 1; Chapters 1; Summary 1; IdeaDiscovery 1; social 1 + N + M
sessions (each may call Exa); Blog 1; thumbnails up to 1 + N + M image calls. Typical N=5, M=3:
**~15 agent sessions, 2 Whisper passes, ≤ 1 Gemini, ≤ ~12 image generations**, plus Late calls at approval.

---

## 3. Feature cards (things we lack or do worse)

Effort is for our stack (Python 3.12 + Claude + ffmpeg + Remotion). Score = wow (1–5) × fit (1–5) ÷ effort
(S = 1, M = 2, L = 3).

### Card A — Dialogue cold-open, then the music drops  *(CutClaw idea)*
- **User sees:** the reel opens on the client's strongest standalone line (6–15 s) with the bed playing quietly
  under it; then a 1–3 s non-speech beat (b-roll stretch, pause, title card, montage) where the music's
  chorus/drop hits un-ducked, before the body resumes. In CutClaw the rest of the edit is a silent montage
  (original audio defaults to 0.0 [code]), so the drop plays at full level for the whole reel; in our
  talking-head reels the client keeps talking and ducking would pull the drop back under speech, so the effect
  only exists where there is a non-speech window after the hook.
- **Mechanism:** (1) pick a hook line run from the word transcript: standalone, quotable, no filler or
  back-and-forth; validate by matching the chosen words back to real transcript words and re-checking duration
  (6–15 s). (2) choose the music window so its chosen section start = end of hook; start the bed earlier by the
  hook's length, ducked during it (CutClaw used a flat 0.5×; we already have exact speech ducking). (3) loudness
  match. Our story pass already picks a hook item; this adds the "music drop after the hook" timing rule.
- **Deps/licences:** none new.
- **Effort:** **S, assuming Card D is built** (it needs section labels to find a real drop). Reuse `mix.py`
  ducking, music start-offset logic, hook selection in `decide.py`; the story pass must reserve the
  non-speech window.
- **Risks:** some clients' strongest line is mid-sentence, so fall back to a normal open; many talking-head reels
  have no non-speech window, so the effect is optional, not default.
- **Score:** wow 4 × fit 3 ÷ 1 = **12** (fit lowered from 4: needs a non-speech beat that most talking-head reels lack).

### Card B — Brand kit + ready-to-post copy pack  *(vidpipe, ISC, adapt)*
- **User sees:** with the reel they get Instagram caption (Hinglish or English per brand), first-comment
  hashtags, YouTube Shorts title + description, alt text, on-screen hook variants; spellings of brand/product
  names correct in captions; brand bumper rules (e.g. outro on every reel, intro only on long videos).
- **Mechanism:** a `brand.json`-style file per client: voice (tone/personality/style/avoid), custom vocabulary,
  hashtag banks (always / preferred / per platform), content guidelines, intro/outro rules per platform/aspect,
  cover style. Vocabulary goes into our ASR's prompt/hotwords and the Hinglish post-correction; voice + banks go
  into one Claude call per reel that returns structured posts (schema with per-platform limits checked in code;
  current limits must be confirmed first — IG caption ~2,200 chars, IG hashtag cap (was 30, may have changed),
  YT title 100 chars [external — verify]). Unlike vidpipe, inject brand voice into the
  social prompt and validate limits in code.
- **Deps/licences:** Claude only; vidpipe's schema/structure reusable with "ISC © htekdev" attribution.
  Skip Exa (paid) unless a client wants links.
- **Effort:** **S–M** (S for copy pack; bumpers add a bit). Reuse `brief.py` (client brief), `package.py` (add
  `posts/` to the package), Studio settings.
- **Risks:** generic, "AI-sounding" Hinglish; hashtag spam. Keep the client approving copy in Studio.
- **Score:** wow 4 × fit 5 ÷ 1.5 = **13.3**.

### Card C — Many reels from one long recording  *(vidpipe, ISC, adapt)*
- **User sees:** upload a 40-min podcast/webinar/vlog → a ranked board of 5–10 candidate reels with title,
  hook, score, why-it-will-be-shared; pick some → each goes through our full finish pass.
- **Mechanism:** one Claude "miner" pass over our word-level (Hinglish-aware) transcript plus our
  perception tables (scenes, faces, energy), chunked by topic. Tools: add/review/finalize as in vidpipe, with
  the weighted viral score (hook ×3, emotion ×2, share ×3, completion ×2, replay ×2 → /3, keep ≥ 8/20), hook
  type, emotion, structure, loop flag, composites, and payoff-first ordering when the payoff is a full clause.
  **Enforce in code** what vidpipe only asks for: duration 20–60 s, no overlap > 20 %, sentence-boundary starts,
  max count, score floor. Each accepted candidate becomes a story-pass brief for the existing pipeline. Our
  Reviewer + QA gates then judge each reel.
- **Deps/licences:** Claude only. vidpipe prompt structure/rubric reusable with attribution; don't use Whisper-1
  or the Copilot SDK.
- **Effort:** **M**. Reuse `selects.py`/story pass, `variants.py`, Studio projects (one parent, N child reels).
  Cost scales with N finish passes + renders — show a per-candidate cost before rendering.
- **Risks:** hours of Hinglish transcript exceed one context → chunk + global rerank; LLM "viral scores" are
  uncalibrated (log client picks to calibrate later); per-reel cost.
- **Score:** wow 5 × fit 5 ÷ 2 = **12.5**.

### Card D — Song structure + real downbeats  *(CutClaw idea, our own libs)*
- **What we do worse:** `library.py` downbeats = every 4th librosa beat with a phase guess; no idea where the
  chorus/drop is, so the bed may start in a verse.
- **User sees:** the music bed for a 20 s reel is the drop/chorus, not the intro; zoom pulses hit true downbeats.
- **Mechanism:** at library indexing time, compute beats/downbeats with **Beat This!** (MIT code + weights) and
  sections (All-In-One labels if its weights/deps clear the licence gate; else a self-similarity novelty curve
  + RMS energy in librosa, labelled by energy rank). Store `sections[]` (label, start, end, energy) in the music
  index. Window choice: highest-energy section ≥ reel length (merge neighbours as CutClaw's unused climax picker
  does), start snapped to a downbeat; offer the LLM the labelled sections (CutClaw-style) only when the brief
  names a mood. Also add a quiet-gate (drop beats > 45 dB under peak).
- **Deps/licences:** Beat This! MIT (torch); All-In-One "MIT" repo but weights/madmom dependency must be checked;
  **never madmom models (CC BY-NC-SA) or aubio (GPL)**.
- **Effort:** **S–M**. Offline, per library track; reuse `library.py`, `licences.py` gate, music index JSON.
- **Risks:** torch dependency weight; mis-labelled sections on Indian film/indie music with tempo changes —
  keep energy-based fallback.
- **Score:** wow 3 × fit 4 ÷ 1.5 = **8**.

### Card E — Approve, schedule and publish board  *(vidpipe, ISC, adapt; different backends)*
- **User sees:** client approves reel + caption in Studio; it is queued into the brand's posting slots
  (e.g. Reels 08:30/12:00/19:30 IST) and posts itself to Instagram and YouTube; calendar view; "post now" bumps
  the queue.
- **Mechanism:** per-client `schedule.json` (timezone Asia/Kolkata, per-platform per-content-type weekly slots,
  avoid-days, spacing). Slot finder like vidpipe's: first free slot; priority items (campaign/deadline) displace
  ordinary ones, which recursively re-slot; ties by deadline. Publisher adapters: Instagram Graph API content
  publishing (Business/Creator account + Meta app review) and YouTube Data API v3 upload (quota-limited;
  unverified apps upload private) [external — verify]. Late API is an optional paid shortcut. Rate-limit →
  park platform for the batch.
- **Fit notes:** TikTok is banned in India [external — verify] — drop it; vidpipe's America/Chicago slots and LinkedIn/X focus need
  re-targeting. vidpipe's hard-coded TikTok consent flags are a pattern to avoid.
- **Deps/licences:** Meta/Google APIs (free but gated by review/quotas); vidpipe scheduler logic reusable with
  attribution.
- **Effort:** **L** (OAuth per client, token refresh, app review, failure handling). We already have client
  review links, which halves the UI work.
- **Risks:** platform review delays; posting on a client's account = liability; must store tokens securely.
- **Score:** wow 5 × fit 4 ÷ 3 = **6.7**.

### Card F — Beat-grid montage mode  *(CutClaw idea)*
- **What we lack:** we never cut picture to the music; speech cuts stay where words end.
- **User sees:** a music-led variant (event recap, product showcase, travel/b-roll stretch, "best moments"
  opener) where every cut lands on a downbeat/accent, energy of shots follows the song (calm verse → slow shots,
  drop → fast punchy shots).
- **Mechanism:** (1) cut grid = Card D's downbeats + accents (mel-energy peaks), budgeted per section in
  proportion to keypoint density, with min/max interval (e.g. 0.5–2.5 s, tighter in drops), boundaries snapped
  to downbeats. (2) per interval, the finish pass picks a visual (b-roll, stock, silent client footage) using
  storyboard language: energy match, shot-scale variety, no reuse (overlap check), protagonist/subject present.
  (3) **frame-exact durations** — trim each shot to its interval in frames; never let ±1 s tolerances
  accumulate as CutClaw does. (4) avoid source cuts inside an interval (slide the clip to start on the source
  cut). Speech segments are untouched: grid applies only to montage stretches or a music-only variant.
- **Deps/licences:** Card D outputs; our scenes/OCR/faces tables; Claude.
- **Effort:** **M–L** (timeline schema for montage spans, selection, QA gate "cut-on-beat error ≤ 1 frame").
- **Risks:** talking-head clients rarely have enough non-speech footage; stock b-roll can feel generic.
- **Score:** wow 5 × fit 3 ÷ 2.5 = **6**.

### Lower-ranked / no card
- **AI explainer overlays** (vidpipe 2.2): wow 3, fit 2 (edtech only), M, paid images, brand-safety risk → **3**.
  If wanted, generate with Claude-authored SVG/Remotion cards instead of image models.
- **Parallel per-shot agents with overlap arbitration** (CutClaw 1.2): internal speed-up, no client wow.
- **Long-video silence pass capped at 20 %** (vidpipe 2.3): we already tighten pauses; the 20 % cap is a cheap
  safety rule worth copying into our pause logic.
- **Chapters / blog / idea bank**: low fit for reels clients.
- **Split-screen for webcam screencasts**: only for edtech clients; our framing covers talking heads.
- **Vertical crop** (CutClaw): we are ahead (see 1.4). **Captions, 4:5/1:1 variants, cover frames, cost
  tracking**: we already have them.

---

## 4. Ranking — top 6 by wow × fit ÷ effort

| # | Feature | Source | Score | Effort | Licence notes |
|---|---|---|---|---|---|
| 1 | Brand kit + post-copy pack (B) | vidpipe (ISC) | 13.3 | S–M | Reuse with "ISC © htekdev"; no LICENSE file in repo |
| 2 | Many reels from one recording (C) | vidpipe (ISC) | 12.5 | M | Same; drop Whisper-1/Copilot SDK |
| 3 | Dialogue cold-open → music drop (A) | CutClaw (ideas only) | 12 | S (after D) | No deps; needs a non-speech window |
| 4 | Song sections + real downbeats (D) | CutClaw idea | 8 | S–M | Beat This! MIT; **not madmom (NC) or aubio (GPL)**; verify All-In-One weights |
| 5 | Approve → schedule → publish (E) | vidpipe (ISC) | 6.7 | L | Meta/YouTube APIs (review, quotas); Late is paid; no TikTok (India) |
| 6 | Beat-grid montage mode (F) | CutClaw idea | 6 | M–L | Depends on D |

Build order suggestion: D before A and F (both need sections/downbeats); B before E (copy is what gets approved).
