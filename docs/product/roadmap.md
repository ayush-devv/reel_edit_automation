# Roadmap and implementation plans (2026-11-20)

This file ties all the plans together and holds the implementation plans that weren't written elsewhere.

**Sources:**
- `ui-backend-plan.md` (Studio ↔ engine)
- `asset-library-plan.md` (licences, assets)
- `oss-feature-gap-plan.md` (features other open-source editors have, and the free replacements for paid items)
- `research_notes/oss-reverse-engineering/` and `research_notes/free-alternatives/` (how the other tools do it)

| Group | What | Size | Plan status |
|---|---|---|---|
| **1** | Before the first paying client | about 6–8 days | **Detailed below** |
| 2 | Growth: Clip Factory, asset search index, UI phases 3–4, free-model listening test | about 5–7 days | To write before building |
| 3 | Free replacements for paid features: SFX, music, dubbing, lip-sync, beauty pass | about 5–8 days | To write before building |
| 4 | Later: beat-synced montage, publishing, Resolve, Epidemic | 5 days or more | To write before building |

Done so far: the licence gate (asset-library phase A). It's on branch `engine/licence-gate` and not committed yet.

---

## Group 1: before the first paying client

**Build order and why:**
- G1.1 → G1.2 → G1.3 → G1.4 first: each is small and independent, and each improves every reel.
- G1.5 (partial re-render) comes next. It changes the render path and wants the earlier items' tests in place.
- G1.6 (hook preview) builds on G1.5's frame-range rendering.
- G1.7 and G1.8 are UI and asset work that can run alongside.

**Rules for every item:**
- **Engine tests** run against a fake workspace, with no network and no Claude (the caller is a fake).
- **A real-project check** on a copy of `_real_doac_v2` happens only where the item changes the output. The plan says which items need it.
- **Cost:** if the item adds a Claude call or forces existing projects to re-run a paid stage, the plan says so.
- **Done** means:
  - the tests pass;
  - the full suite passes (run with `SSL_CERT_FILE=$HOME/.mac-ca-bundle.pem`);
  - the web app type-checks and its tests pass;
  - the docs are updated;
  - the commit is made only when the owner says so.

---

### G1.1 Copy pack + client brand voice (0.5–1 day)

**What the owner and client get:** every package includes `COPY.md` and `copy.json`, ready to paste:
- the Instagram caption;
- up to 5 hashtags (Instagram's cap since December 2025, shared between the caption and the first comment);
- the first comment;
- the YouTube Shorts title and description.

The copy is written in the client's voice and language (English, Hinglish in Latin script, or Devanagari). Any credits a licence requires are always added, by code.

**Design**
- **Brand voice** (in `reel/brief.py`): `Brand` gains an optional `voice: BrandVoice`. Every field has a default, so existing brand kits stay valid. Fields:

  | Field | Meaning |
  |---|---|
  | `tone` | text |
  | `caption_language` | `en` / `hinglish_latin` / `hi_deva`; default: same as the brief |
  | `hashtags_always` | list |
  | `hashtags_pool` | list |
  | `banned_words` | list |
  | `emoji` | `none` / `light` / `heavy` |
  | `handles` | @mentions |
  | `cta_lines` | list |
- **New stage `COPY`**, placed after `COVER` and before `PACKAGE`:
  - **Input hash:** `plan/story.json`, `tables/summary.md`, the brief, the brand, the persona file, the prompt, the model. It doesn't depend on any render.
  - **Run:** one Claude call (`claude_call.call`, small effort) with a new persona `personas/copywriter.md`. It sees the kept transcript, the summary, the brief and the brand voice, and returns a pydantic `CopyPack` (`ig_caption`, `hashtags`, `first_comment`, `yt_title`, `yt_description`).
- **Checks in code** (`reel/copy.py`); a failure re-asks once with the issues listed:
  - Instagram caption ≤ 2,200 characters, **counted after the credits are appended**;
  - hashtags: at most `IG_HASHTAG_MAX = 5` in caption + first comment together (a constant: several 2026 sources report the cap, but it wasn't confirmed on Instagram's Help Center), each `#\w+`, none duplicated, none banned, `hashtags_always` included;
  - YouTube title ≤ 100 characters, description ≤ 5,000;
  - no `banned_words` and no brief `banned_claims`;
  - the CTA matches the brief's `cta` if it has one.
- **Credits:** `package.build` appends `library.credit_lines` to the Instagram caption and the YouTube description. Claude never writes credits, so a required credit can't be dropped. The package writes the **credited** version to `export/package/copy.json` and `COPY.md`; `plan/copy.json` is only Claude's draft.
- **Studio:**
  - Deliver shows a "Post copy" panel with a copy button per field.
  - The Brands form gets a "Voice" section.
  - API: `GET /api/projects/{pid}/copy` serves `export/package/copy.json` (the credited version), never the draft. The brand PUT already validates through `Brand`.

**Tests:**
- Defaults keep old brand files valid.
- The checks reject 6 hashtags across caption + first comment, a banned word, a missing always-hashtag, or a caption that goes over 2,200 characters once credits are added.
- `GET /copy` returns the credited version.
- A fake caller returns a bad pack and then a good one; the re-ask is tested.
- Credits are appended for a CC BY track and never duplicated.
- The stage hash ignores render files.
- A Studio route test.

**Cost and re-runs:**
- Adds 1 small Claude call per edit, and one more only when a re-ask is needed.
- Existing projects run it once on their next run. No render re-runs.

**Real-project check:** run COPY on the copy of `_real_doac_v2`. The owner reads `COPY.md`.

---

### G1.2 Wrong-number check, with Indian numbering (about 0.5 day): **built**

Built in `reel/numbers.py`; `validate.number_checks` / `number_issues`; `qa.numbers_match` (gate `numbers`, warn).

Known limit: "4K video" can't be told from "4k" = 4,000 in writing. It only causes a false error when the speaker says "four K" with no digits nearby.

**What it catches:** on-screen text that disagrees with what was said. For example, a counter showing "₹5 lakh" over "fifty thousand", or a keyword card saying "70%" when the speaker said 17.

**Design**
- **`reel/numbers.py` → `parse(text) -> list[Decimal]`.** It handles:
  - digits with Western or Indian grouping (`500,000`, `5,00,000`), decimals and `%`;
  - `₹ / Rs / INR / $`;
  - `k`, `L/lakh/lac`, `Cr/crore`, `million/billion`;
  - English number words up to the billions;
  - Hindi number words 0–100 (irregular, so a table in romanised and Devanagari forms) plus `sau/सौ`, `hazaar/हज़ार`, `lakh/लाख`, `crore/करोड़`;
  - Devanagari digits ०–९.
- **Check at plan time (cheap):** `validate_finish` gets issue `number_mismatch`. For every `keyword_card`, `counter` (value and text), `text_card`, `cta_card` and the hook title, every number in the text must match a number spoken within the word window (±2 words).
  - Tolerance: exact, or the display is the spoken value rounded to the shown precision ("4.97" spoken shows as "5").
  - **Error only when both sides parse confidently and still disagree.** Anything ambiguous is a warning, because every error buys a paid Editor retry. Ambiguous cases include years, ordinals ("1st"), "24/7", "10x", times ("5:30"), ranges ("3–5"), "Top 3" against "three things", and numbers with no spoken candidate nearby.
  - The Editor fixes errors in its existing repair loop, before any render.
  - **Before turning errors on**, run the parser over the finish plans of every existing project in `projects/` and record the false-positive count here. It must be 0 errors on plans the owner already accepted.
  - **Result, 2026-11-20:** 3 plans, 4 on-screen texts, **0 errors, 0 warnings**. The sample is small (there is no plan history), so re-run the sweep (`number_checks` over every `projects/*/plan/finish.json`) as projects accumulate. A false error costs one Editor retry, never a wrong reel.
- **Check at QA time (safety net):** gate `numbers_match` over the compiled timeline's titles and graphics against the kept words, using the same function. It starts in warn mode, like other new gates; calibration can promote it to blocking.

**Tests:**
- A table of about 40 parse cases: `"₹2.5 crore"`, `"25 लाख"`, `"पच्चीस"`, `"5,00,000"`, `"1.2M"`, `"seventy"`, `"70%"`.
- Mismatch and match cases in `validate_finish`.
- The gate result on a fake timeline.
- No false alarm on years (`2026`) when the speaker says the year.

**Cost:** free. It doesn't change any stage hash beyond the code of the validate and QA modules. QA re-runs on the next run; QA includes the Reviewer call, so that's one Reviewer call per project when it next runs.

---

### G1.3 Hindi captions break at the danda (about 1 hour)

`compile._break_cost` and `_bare` treat `.,!?;:—` as phrase ends but not `।` (and not `॥`), so Devanagari captions don't prefer to break at sentence ends. Add both to the set.

**Tests:** a Devanagari sentence pair breaks at `।`.

**Cost:** compile's code fingerprint changes, so **every project recompiles once**, which is cheap. Overlay and composite then re-run only where the pages actually changed (Devanagari projects). No Claude calls.

---

### G1.4 Real song structure: downbeats and the drop (0.5–1 day)

**What changes:** music already starts so a beat lands on the first cut. Two things improve:
- Downbeats become real, not "every 4th beat".
- The biggest energy lift (the drop) can land right after the hook: a cold open.

**Design**
- **Beat tracking:** at index time, run **Beat This!** (CPJKU) for beats and downbeats.
  - Licence, checked on the repo on 2026-11-20: "The code and the published model weights are released under the MIT license."
  - It runs on CPU; MPS isn't documented. The repo has no release tags, so pin the git commit and the checkpoint file's sha256 when adding it.
  - Keep librosa as the fallback when it's not installed.
  - It goes in `pyproject` as an optional extra.
  - The licence registry gets nothing new, since it's a tool, not an asset.
- **Sections and the drop:** computed with DSP only, no model. RMS energy and onset strength on a 0.5 s grid, a novelty curve, then the largest sustained energy rise that starts on a downbeat.
  - Index fields: `drop_ms`, `sections: [{start_ms, energy}]`.
  - This avoids model-licence questions; the All-In-One weights licence is unclear.
- **`compile.music_offset_us`:** when the reel has a hook (first item) and the track has a `drop_ms`, prefer the offset that puts the drop within ±1 beat of the hook's end cut. Otherwise keep today's "most cuts on a beat" rule. A finish-plan field isn't needed; the Editor can be told in the finish menu that tracks with a drop will land it after the hook.
- **Re-index:** `reel assets fetch --reindex-music` re-measures the 33 tracks.

**Tests:**
- Synthetic click tracks with a known downbeat phase and an energy step, so the drop is found within 1 beat.
- `music_offset_us` puts the drop on the hook cut.
- The fallback path works without Beat This!.

**Cost and re-runs:** the music index changes, and `_assets_fp` covers it, so **every project's next run re-does its finish pass (1 Claude call each), compile and render.** That is the same as when the Lottie pack was added. Batch it with G1.8's asset changes so this happens once, not twice.

**Real-project check:** the owner listens to the copy of `_real_doac_v2` with the new bed.

---

### G1.5 Partial re-render on revision (1–2 days)

**What the owner sees:** a caption, graphic or title note no longer re-renders the whole overlay, and a music or SFX note no longer re-renders the picture. Composite, QA (including the Reviewer call), cover and variants still run after it, so the overall time saved has to be measured; the real-project check quotes the full revise-loop time before and after.

**Why ours can be simpler than OpenEdit's:** both intermediate renders are **all-intra**, so every frame is a keyframe. Checked with `ffprobe` on `_real_doac_v2` on 2026-11-20:
- `base.mov`: ProRes Standard 4:2:2 10-bit + PCM, `has_b_frames=0`.
- `overlay.mov`: ProRes 4444, `has_b_frames=0`.

Chunks can therefore be spliced at any frame by stream copy, with no 2-second keyframe grid. Only `final.mp4` (H.264) is re-encoded, by the composite, which already runs every time.

**Design**
1. **Changed-frame ranges from the timeline, not from the agent** (`reel/rediff.py`).
   - **The baseline** is `render/overlay.rendered.props.json`, written **only after a successful render or splice**. It is never `overlay.props.json`, which `render_overlay` writes *before* rendering; after a failed render that file no longer matches `overlay.mov`.
   - **No baseline** (old projects, or after a failure) means a full render.
   - **Per element** (caption pages, titles, flashes, pips, graphics): matched by id. Added, removed or changed elements give `[start_f − pad, end_f + pad]`, with pad = 12 frames for entry and exit animations.
   - **Closure:**
     - any element overlapping a changed range in time joins it, because graphics avoid each other;
     - for caption pages, the **previous and next page** join too, because entry and exit depend on back-to-back neighbours (see `qa.page_samples`), even when the pages only touch.
   - **Global keys** (caption family or tokens, size, fps, duration, faces, safe zones, `layer`, renderer fingerprint) mean "render everything".
2. **Overlay:** for each range, `overlay.render_overlay(props, chunk, frames=(a, b))`, which is already supported.
   - Splice with the ffmpeg concat demuxer: the old overlay `inpoint/outpoint` plus the chunks, `-c copy`.
   - Then verify: frame count equals `duration_f`, and a pixel spot-check on the frames either side of every seam.
   - Fall back to a full render on any failure, so this path can never make an edit fail.
3. **Base audio-only changes** (`audio`, `ducking`, music/SFX assets; no video field changed):
   - **The render stage hash stays exactly as it is.** Changing its structure would re-render every project's base once.
   - Separately, compute a video-only fingerprint: the video fields, the video assets, faces, scenes, LUTs, mezzanines, code and CRF. Store it in `render/base.meta.json` after each successful base render.
   - When the stage re-runs and that fingerprint is unchanged, build the audio graph only (`render.build_command` gets an `audio_only` mode that writes PCM and stems), then remux: `-map 0:v` from the old `base.mov`, `-map 1:a`, `-c copy`.
   - A music change with `beat_pulse > 0` moves the beat-pulse keyframes, which changes the video fingerprint. It correctly takes the full path.
4. **The overlay stage hash stays as it is.** The *run* decides between partial and full. State meta records `partial: {ranges, frames_rendered}`, so the Studio can show "re-rendered 3.2 s of 41 s".
5. **Behind-the-subject titles** (`behind.mov`) keep their existing frame-window render.

**Tests:**
- `rediff` on synthetic props:
  - one changed caption page gives one padded range, including its back-to-back neighbours;
  - an overlapping graphic joins;
  - a family change gives a full render;
  - a missing `overlay.rendered.props.json` gives a full render.
- A failed chunk render leaves the baseline untouched, so the next run diffs correctly.
- Splice exactness, from a 50-frame test overlay rendered in full versus partial: identical frame count and checksums outside the ranges.
- An audio-only change leaves the video stream bytes untouched (same packet hashes).
- The fallback path.

**Real-project check:** on the copy of `_real_doac_v2`, change one caption word, then change the music gain. For each, record in this file the time of the overlay or render stage alone and of the **whole revise loop** (through QA and variants), before and after.

**Cost:** free. It saves render time and adds no Claude calls. No stage hash changes, so existing projects don't re-render because of it.

---

### G1.6 Hook preview in two looks (0.5–1 day)

**What the client sees:** a few minutes after the edit is planned, a review link shows **A** and **B** for the opening 3–5 s, each with a different caption style and colour look. They pick one, and the full render uses it.

**Design**
- **Run option `preview_first`:** the pipeline stops after `COMPILE`; a new `PREVIEW` stage runs only when the option is set.
- **A** is the Editor's own choice.
- **B** is picked deterministically, with no extra Claude call and no change to the finish schema:
  - the best-matching *other* caption family for the genre and mood (families' `for`/`mood`);
  - a contrasting look from `color.LOOKS` (warm↔cool, or natural↔punchy);
  - both still checked by `validate_finish` before use.
  - **Brand locks win:** if the brand kit locks the caption family, vary only the look, and the other way round. If both are locked, skip B and show only A ("your brand kit fixes the style").
- **Rendering:**
  - base with `-t <hook_end + 0.5 s>`, which is cheap because the hook is at the start of the graph;
  - **full resolution**: for 3–5 s it's cheap, and a second resolution path through `build_command` and the props would only add risk;
  - overlay with `--frames=0-N`;
  - a quick composite into `export/preview/hook_A.mp4` and `hook_B.mp4`.
- **How the run stops** (the runner has no pause):
  - With `preview_first`, the pipeline's stage list ends at `PREVIEW`, and the run finishes successfully there.
  - The project gets a new status, `awaiting_choice`, shown in Studio as "Waiting for the client's A/B pick" (Home's "Needs you" strip). It must never read as failed or incomplete.
- **Choice:**
  - The review link page (`review_links.py`) gets an "A or B" block.
  - The choice is stored like a note and applied through the existing adjust path (`_apply_adjust` `caption_family` + `look`).
  - The applied choice starts a normal full run (without `preview_first`).
  - The owner can also pick in Studio Review.

**Tests:**
- B differs from A and passes validation; a brand lock on the family varies only the look; a brand lock on both gives no B.
- A `preview_first` run ends at PREVIEW with status `awaiting_choice`, not failed.
- The `-t` render's duration.
- The choice posts and applies the adjustment.
- The review-link page includes both clips, with the CSP nonce kept.

**Cost:** two short low-resolution renders per edit, and only when the option is on. No Claude calls.

---

### G1.7 Studio: UI plan phases 1 and 2 (2–2.5 days)

These are already specified in `ui-backend-plan.md`, with an API route, engine tests and UI states per item. Notes from this pass:

- **A1 plain-language verdict:**
  - Engine `reel/verdict_plain.py` maps each gate code and Reviewer finding to one sentence plus timecode jump links.
  - The raw detail stays behind "Details".
  - It includes the new `numbers_match` (G1.2) and `licence_refused` codes.
- **A2 rename and set client:** `PATCH /api/projects/{pid}` updates the studio meta (name, client).
  - The brief's `client` is **not** edited, so the Editor isn't re-asked.
  - The licence gate's `UseContext` takes the brief's client, **else the studio meta client**. Without that fallback, the single-client rule would do nothing for CLI-made projects.
- **B1 real time-left estimate:**
  - Compute per-stage durations from every project's `state.json` (started/finished), per second of footage, as a median.
  - Return `eta_s`, or `null` with fewer than 3 samples.
  - (`log/runs.jsonl` holds Claude calls, not stage times.)
- **C1 b-roll at creation:** the stock toggle exists; add the "b-roll folder" field (a local path, validated as in `reference_url`).
- **C2 starter packs:** a library empty-state button that runs `reel assets fetch` as a job (`jobs.submit`).
- **D1 server-side templates:** `GET/PUT /api/templates`, stored in `~/.config/reel/templates.json` (0600). On first load, migrate the browser's localStorage copy once.
- **Also new brief fields in New edit:** client category, purpose, and "client accepts credits" (from the licence gate), under "Usage rights".

---

### G1.8 Free animations + a tool for adding hand-picked assets (about 0.5 day)

- **Asset-library phase B:**
  - Vendor **useAnimations** (300 Lottie animations, MIT) into `assets/lottie/useanimations/`, with their LICENSE as the pack notice.
    - Licence checked on the repo on 2026-11-20. Its README says: "The code and the animations are free for personal and commercial use."
    - The files are `icons/<name>.json`, with `icons/catalog.json` as metadata.
    - Read the LICENSE file itself when vendoring, and pin the commit.
  - Add a registry `sources:` entry → `mit`.
  - Run every file through `lottie.problems()`; the report lists refusals.
  - Generalise recolour: theirs are drawn in a single dark colour, ours in white, so detect the dominant flat colour and swap it for the accent.
  - Tag them from file names for the Editor's menu. The menu shows only the best ~20 by tag match, so the prompt doesn't grow by 300 lines.
- **Phase C:** `reel library add <file> --licence <id> --source <name> --source-url <url> [--attribution …] [--kind sfx|music|lottie]`.
  - Measures the file with the existing indexers and records `sha256`, `downloaded_at`, `licence_id` and `source_url`.
  - Refuses a licence id not in the registry, or a blocked one.
  - This is how the owner's hand-picked Pixabay music and Freesound CC0 sounds enter, never by bulk download.
- **Tests:** `library add` with a good licence, an unknown one and a blocked one; the recolour of a dark-stroke file; the menu cap.
- **Cost:** asset index changes re-run every project's finish pass once. Ship together with G1.4.

---

### Group 1 summary

| Item | Days | New Claude calls | Forces re-runs on existing projects |
|---|---|---|---|
| G1.1 copy pack | 0.5–1 | +1 small call per edit | The COPY stage only |
| G1.2 number check | 0.5 | Only when a confident mismatch triggers an Editor retry | QA once (1 Reviewer call) |
| G1.3 danda | 0.1 | — | Compile once for every project (cheap); overlay only where pages changed |
| G1.4 song structure | 0.5–1 | — | **Finish pass once** (batch with G1.8) |
| G1.5 partial re-render | 1–2 | — | — (saves time) |
| G1.6 hook preview | 0.5–1 | — | — (opt-in) |
| G1.7 Studio phases 1–2 | 2–2.5 | — | — |
| G1.8 animations + library add | 0.5 | — | **Finish pass once** (batch with G1.4) |
| **Total** | **about 6–8.5** | | |
