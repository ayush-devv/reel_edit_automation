# Roadmap and implementation plans (2026-11-20)

This file ties all the plans together and holds the implementation plans that weren't written elsewhere.

**Sources:**
- `ui-backend-plan.md` (Studio ↔ engine)
- `asset-library-plan.md` (licences, assets)
- `oss-feature-gap-plan.md` (features other open-source editors have, and the free replacements for paid items)
- `research_notes/oss-reverse-engineering/` and `research_notes/free-alternatives/` (how the other tools do it)
- `research_notes/harness-comparison.md` (our harness against commercial and open-source agentic editors, 2026-11-20)

| Group | What | Size | Plan status |
|---|---|---|---|
| **1** | Before the first paying client | about 6–8 days | **Built** (G1.1–G1.8, commits `00cdf10` … `6ab7999`) |
| **2** | Growth: Clip Factory, asset search index, UI phases 3–4, free-model listening test (+ two small additions from the harness comparison) | about 8–10.5 days as planned; 7–9.5 without the additions | **Built, not committed** (see "Group 2 as built"); real-project checks wait on owner input |
| **3a** | Client-facing: story check-in, per-client style memory, word-level text edits | about 4.5–5.5 days | **Detailed below** |
| **3b** | Proving quality: brief rubric, pairwise judge, revision evals, verdict-checked replies, gold-pair tooling | about 3–3.5 days | **Detailed below** |
| **3c** | Free generative assets: beauty pass now; SFX, music, voice, dubbing, lip-sync gated by the listening test | beauty pass 1–1.5 days; the rest 5–8 once models clear | **Detailed below** (generative items as gated outlines) |
| 4 | Later: beat-synced montage, publishing, Resolve, Epidemic | 5 days or more | To write before building |

Done so far: the licence gate (asset-library phase A) and all of Group 1.

---

## Group 1: before the first paying client

### Status (2026-11-20): all eight items built and tested

The work is on branch `engine/licence-gate`, committed per item, not pushed.

**Still open, and needing the owner:**
- **G1.4 listening check.** The 33 tracks were re-measured with Beat This!; BPM now matches the publisher's listed tempo far more often. Nobody has listened to a drop landing after a hook yet.
- **G1.5 real-project timing.** The partial re-render is proven frame-exact in tests:
  - a spliced overlay is identical to a full render;
  - an audio-only re-render gives identical sound and leaves the picture byte-identical.

  The before/after revise-loop times on `_real_doac_v2` still need a real run, which re-buys a finish pass.
- **G1.6 client review link.** The A/B choice is made in the Studio (project header) or with `reel preview-choose`. The client's review-link page doesn't show A/B yet.
- **G1.8 trademark logos.** 21 brand-logo icons (Instagram, YouTube…) are indexed but marked `trademark` and never offered.
- **Web type-check.** The web type-check is `npm run typecheck` (`tsc -b`). `tsc --noEmit -p .` checks nothing in this repo, because `tsconfig.json` only has references.

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

---

## Group 2: growth (planned 2026-11-20)

**What it adds:**
- a second product: many reels from one long recording;
- b-roll and SFX chosen by meaning;
- the remaining Studio controls;
- the evidence needed to pick the free generative models for Group 3.

**Two small additions** come from `research_notes/harness-comparison.md`. Each is marked *(addition)* and can be dropped:
- **G2.1 pacing numbers.** In the Timeline-Bench study (arXiv 2609.35143), editing agents' clearest measurable gap was cutting too slowly.
- **The owner-label buttons in G2.4.** The calibration machinery has 0 owner labels to work from.

**Build order and why:**
- **G2.1 pacing numbers** come first. They are small, improve every reel, and give the Clip Factory's miner and the Reviewer a pace measure.
- **G2.2 Clip Factory** is the big item and the new revenue line.
- **G2.3 asset search index** comes after G2.2, because the Clip Factory multiplies b-roll and SFX choices: N reels from one source would otherwise reuse the same few clips.
- **G2.4 Studio phases 3–4** can run alongside G2.2 and G2.3.
- **G2.5 listening test** is mostly owner time. Run it whenever downloads allow; Group 3 can't be planned without its results.

**Rules for every item:** the same as Group 1:
- fake workspace and fake caller in tests;
- a real-project check only where the output changes;
- cost and re-runs stated;
- done means the tests, the full suite and the web app all pass, and the docs are updated;
- a commit only when the owner says so.

**Owner tasks that run alongside** (not code; they gate how far Group 2 can be trusted):
1. **Label renders.** Label at least 12 rendered reels with `reel label` (or the G2.4 buttons). Without these, `reel calibrate` can't promote any gate except `frozen`, and the Reviewer can't be checked.
2. **Add Hindi/Hinglish gold pairs.** Add 2–4 pairs to the gold set (ADR-0031). The current 6 pairs are all English.
3. **Supply a long recording.** Provide one 20–60 min recording (a podcast or webinar) that may be used for internal testing. This is needed for G2.2's real-project check.
4. **Listen.** Run the G2.5 listening sessions, about an hour per set.
5. **Decide E3** (`ui-backend-plan.md`): review links outside this Mac. This is still the top-ranked missing feature in `harness-comparison.md` §3.

---

### G2.1 Pacing numbers and gates *(addition, about 0.5 day)*

**What the owner sees:** the verdict gains a line such as "Pace: 9 cuts/min (reference 14); longest stretch with no cut 7.5 s". The Reviewer is asked about pace with the numbers in front of it.

**Why:**
- Timeline-Bench measured agents changing shots at 0.72× the reference rate and holding their longest static shot 1.5× as long.
- Agents' self-checks raised pacing, story or shot choice in only 5.5% of their findings, against 66% of human editors' notes.
- Our gates measure technical defects, not pace.

**Design**
- **One measuring method for both sides.** `reference.py` already measures `cuts_per_min` with `visual.scene_cuts(video)` on pixels. Use **the same function** on our `render/final.mp4`, so a comparison with a reference reel or the pro finals is like for like.
  - Punch-ins are missed by scene-cut detection on both sides alike, which keeps the comparison fair.
  - The timeline also gives an exact count of cuts, punch-ins and b-roll in/out. It goes into the Reviewer pack only, not into the gate.
- **New measures in `qa.py`:**
  - `pace` (warn): cuts/min outside a band.
  - `static_stretch` (warn): longest interval with no scene cut, in seconds, above a ceiling.
- **Where the bands come from:**
  1. the project's reference video (`context/reference_style.md`), when there is one: ±35% of its cuts/min;
  2. otherwise a per-genre band in `config.PACE_BANDS`;
  3. its first values are measured with the same function on the 6 pro finals already used by `calibrate_auto` (ADR-0033), and written down with the date.
- **Reviewer pack** (`personas/reviewer.md` + its context) gets four numbers, as in Timeline-Bench's judge: cuts/min, longest static stretch, integrated LUFS, and the share of silent output.
  - Add one persona line: judge pacing, story and shot choice explicitly, not only defects.
- **Calibration:** `calibrate_auto` gains the two gates.
  - Known-good: the pro finals must pass.
  - Injected defect: freeze-extend one shot to 8 s, or drop every second cut. Built with the same tools as the existing injected defects.

**Tests:**
- `scene_cuts`-based measure on a synthetic clip with known cuts.
- The band comes from the reference when present, and from the genre otherwise.
- The gate warns outside the band and passes inside.
- The injected defects are caught.
- The Reviewer context includes the numbers.

**Cost and re-runs:** no new Claude call. The QA code fingerprint changes, so **QA re-runs once per project, which includes 1 Reviewer call each.**

**Real-project check:** run it on the copy of `_real_doac_v2`. Record our cuts/min next to the pro final's.

---

### G2.2 Clip Factory: many reels from one long recording (3–4 days)

**What the owner sees:**
1. New edit → "Long recording → several reels".
2. The recording is analysed once.
3. A **Clips board** shows 5–12 ranked candidates, each with:
   - title, hook line, length;
   - the reason;
   - the score breakdown (labelled "Editor's estimate", never "viral score");
   - the transcript excerpt and a strip of 3 frames;
   - an estimated cost per reel.
4. The owner ticks some and presses "Make reels". Each ticked candidate becomes a normal project: story, finish, QA, Sendable/Hold, package, review link.

**Design**

1. **Analyse the long recording once.**
   - The parent is a normal project run with the analysis-only pipeline (`PIPELINE`, no Claude calls).
   - Studio shows it with a new status, `source`. `project_status` returns "draft" today, which would read as unfinished.
   - **Unmeasured:** time and disk on long footage, in particular faces at 4 fps and overview contact sheets every 2 s (about 1,800 tiles per hour).
     - Step 1 of the real-project check measures both on a 20-min sample.
     - If the sheets dominate, raise `OVERVIEW_EVERY_S` for sources over 10 min. That changes the tables hash, but only for long sources.

2. **The miner: a new `MINE` stage and `reel/mine.py`, with one decision via `decide.decide`.**
   - **Persona:** `personas/clip_miner.md`.
   - **Input:** `tables/script.md`, `summary.md`, `segments.json`, the brief and the brand.
   - **Chunking:** for transcripts above a token budget, use overlapping chunks of about 15 min with 1 min overlap. Then a code merge, with no second LLM ranking call.
   - **Schema `ClipCandidates`**, one entry per candidate:
     - `id`, `title`, `hook_text`;
     - `ranges`: 1–3 `{clip, word_start, word_end, first_word, last_word}`, which lets a payoff-first open work like the story pass's hook;
     - `family`: hook, story, tip, hot_take, proof or myth;
     - `scores`: 1–5 each for `hook`, `standalone`, `payoff`, `energy`, `shareability`;
     - `standalone_risks`: list;
     - `reason`.
   - **Checks in code** (`validate_candidates`; errors go back to the miner through the existing repair loop):

     | Code | Fails when |
     |---|---|
     | `bad_range` / quote mismatch | the range or its quoted words don't match the word table (reuse `validate_story`'s word-range checks) |
     | `too_short` / `too_long` | spoken length, computed from words and edges, is outside the brief's `target_length_s`, default 20–75 s |
     | `mid_sentence_start` / `ends_mid_thought` | a range doesn't start or end on a segment boundary in `segments.json` |
     | `overlap` | more than 20% of the words are shared with a higher-ranked candidate |
     | `low_face` | the speaker's face is present in less than 90% of the span (`faces.json`), so the 9:16 crop isn't viable |
     | `opens_on_reference` (warning) | the first word is a back-reference ("this", "that", "he", "she", "they", "yeh", "woh", "isliye", "toh", …) |

   - **The score is computed in code, not by Claude:** `(hook×3 + standalone×3 + payoff×2 + share×2 + energy×1) / 11`, on a 1–5 scale.
     - Keep candidates at 3.0 or above.
     - Select greedily by score, with a family quota (no more than half from one family) and the overlap rule.
     - Yield target as OpenMontage suggests: about 1 per 4–6 min of source. Never pad.
   - **Output:**
     - `mine/candidates.json`: all candidates, with code scores, issues and selected/rejected status;
     - `mine/board.md`.
   - **Input hash:** the tables files, brief, brand, persona, prompt, schema and model.

3. **Each picked candidate becomes a reel project: `reel/clipfactory.py` `spawn(parent, ids)`.**
   - **Folder:** `projects/<parent>__<cand>/`.
   - **Shared files are hard links, not symlinks.**
     - Studio's `media_path` refuses symlink escapes.
     - Claude Code may refuse to read outside the project folder.
     - `package._link` already hard-links, with a copy fallback.
     - Hard links cost no disk. Deleting or re-analysing the parent never breaks a reel made from it, because each reel keeps its own inode.
     - What to link:
       - `mezz/*.mov` and the enhanced-voice files (`voice_enhance.json` points into `mezz/`);
       - `source/manifest.json` (copied, with a `parent` field);
       - `perception/*.json` (copied; they're small);
       - the contact-sheet tiles that fall in the window.
   - **The window:** `window.json` holds the candidate's ranges plus a margin of about 20 s either side, so the Editor can find a better first line.
   - **Windowed tables:** `tables/script.md`, `segments.json`, `takes.json`, `words.tsv`, `sheets.json` and a regenerated `summary.md` are filtered to the margin. The `tables` code gains a `window` parameter.
     - Word indexes stay **global**, so `KeepItem` ranges stay valid against the full word table.
   - **Copied from the parent:** brief, brand and `run_options`. The candidate's title, hook and reason go into the brief as a "clip" note.
   - **`studio.json`:** `{name: title, client: parent's client, parent: <id>, candidate: <id>}`.
   - **Pipeline:** a reel project runs **`edit.STAGES` only**. `reel run --project <child>` sees `window.json` and skips the analysis stages. The runner asserts this, so a reel project can never write into analysis files.

4. **The window is enforced everywhere, not just in the first story pass.**
   - **Length:**
     - `Inputs.source_s` is the length of the window's speech, not of the whole recording.
     - `effective_target` and `story_pack` use it.
     - Otherwise the Editor would be told "source 3,600 s".
   - **Validation:**
     - `validate_story(..., window=None)` gains an `outside_window` error.
     - It is used by `_story_valid`, by `decide.revise` (through `apply_story_patch` + `validate_story`), and by autofix, so a later revision can't wander into the rest of the podcast.
   - **Hashes:** the story stage hash includes `window.json`. Existing projects have none, so their hashes don't change.

5. **Batch.**
   - `reel factory --project <parent> --make c01,c04,…` spawns the reels and queues one `run` job each through `JobManager.submit`. Jobs queue one after another; render memory already limits parallel runs.
   - **Consistent look across siblings:**
     - when the brand kit locks the caption family and look, nothing more is needed;
     - otherwise, after the first reel's finish pass, its caption family and look are written into the siblings' run options as `style_hint`;
     - the finish menu shows it as "this batch uses…", so the Editor keeps it unless the footage really differs. The owner can turn this off.
   - **Cost estimate before "Make reels":**
     - each reel costs about 5 Claude calls (story ×2, finish, Reviewer, copy, plus any fixes);
     - the estimate is the median cost per call label across past projects (`log/runs.jsonl` via `studio/costs.py`), times N, shown as a range.
     - This is the scoped version of `harness-comparison.md` §3 #6.

6. **Studio.**
   - **Routes:**
     - `GET /api/projects/{pid}/clips` returns the candidates and code scores;
     - `POST /api/projects/{pid}/clips/make {ids}`;
     - the children are listed under the parent.
   - **The Clips board.** Owner picks are logged to `mine/picks.jsonl`, both picked and skipped. That is the label set for calibrating the miner's scores later, because today they are only Claude's opinion.

**Out of scope for v1:**
- split-screen layouts for two-camera podcasts. Candidates with `low_face` are rejected instead;
- topic chapters;
- composite clips from more than 3 ranges.

**Tests (fake caller, synthetic 10-minute word table):**
- each issue code in the miner's checks;
- the score and selection: overlap rule, family quota, yield cap;
- the repair loop: a bad pack, then a good one;
- `spawn` writes hard links, not symlinks:
  - `media_path` serves a reel project's sheet;
  - deleting the parent folder leaves the reel project runnable;
- windowed tables hold only margin words, with global indexes kept;
- `source_s` comes from the window;
- `outside_window` fires in `_story_valid` and on a revision patch;
- the reel pipeline never runs `ingest`, `perception` or `tables`, and the parent's perception files are byte-identical after a child run;
- the package of a reel project contains real mezzanine files;
- Studio routes; the `source` status; picks logging.

**Cost and re-runs:**
- the miner: 1 call per chunk, plus fixes;
- each reel: about 5 calls, as in a normal edit;
- no existing project re-runs: there are no hash changes without `window.json`.

**Real-project check (owner's long recording):**
1. Analyse a 20-min sample and record the minutes and GB per stage (B1's stage rates then cover long footage).
2. Mine the full recording; the owner reads the board.
3. Make 3 reels and label each with `reel label`.
4. Record: candidates found, how many the owner would post, analysis time, cost per reel.

---

### G2.3 Asset search index: b-roll and sound by meaning (1.5–2 days)

This is asset-library phase D, scoped down by a licence fact found while planning.

**What the owner sees:**
- cutaways that match the line being spoken;
- no near-identical clips twice in one reel, or across sibling reels from the same recording;
- SFX and Lottie choices that fit the moment, from all 252 SFX and 300 animations rather than a capped list.

**The licence fact that shapes it.** In `assets/licenses/registry.yaml`, `ml_indexing_ok` is **true only for `owned`, `cc0-1.0`, `cc-by-4.0` and `mit`**. It is unset, so false, for `pexels`, `pixabay-content` and `client-supplied`.
- So **no embeddings may be computed from stock or client b-roll files.** That rules out SigLIP-style image embeddings, which phase D had planned for video.
- What is allowed, subject to the owner's confirmation:
  - text over metadata;
  - the Claude-written b-roll descriptions, which already exist.
- **Owner question:** does `broll_describer` sending stock frames to Claude count as "ML indexing" under those licences? It has been done since step 10. Record the answer on the registry rows.

**Design**
- **`reel/search_index.py`:** a derived, gitignored SQLite file in `assets/.index/`. It is rebuildable and never a source of truth, as the asset-library plan says.
  - Table `assets(id, kind, licence_id, ml_ok, text)`.
  - An FTS5 table over name, tags, category, mood and description.
  - **Verify first:** that the Python build's bundled sqlite has FTS5, and add a `reel doctor` check. If it doesn't, fall back to a pure-Python BM25 over the same text, which is fine at this size.
- **Embeddings, text only:**
  - a small local multilingual sentence-embedding model over:
    - the asset text (all assets: this is text we wrote, not the licensed file);
    - each kept line, Hinglish included.
  - **Verify before choosing:**
    - the model's code and weights licence (for example multilingual-e5-small; read its card);
    - Hinglish quality on 20 kept lines against their best b-roll;
    - `sqlite-vec`'s licence, or plain numpy cosine, which is enough for under 2,000 assets.
  - CLAP audio embeddings for SFX (cc0/owned, `ml_ok` true) are a later step, after verifying the `laion/clap` weights licence.
- **Ranking for the finish menu** (`decide.finish_pack`):
  - per kept item, the top 3 b-roll by cosine and BM25 combined;
  - then MMR across the reel, so no clip or near-duplicate (description cosine above 0.9) appears twice;
  - SFX: the top 30 by the beat and line text;
  - Lottie: the top 20, replacing the tag-match cap from G1.8.
  - Licence-refused assets are filtered before ranking, as today (`_allowed`).
  - **Sibling reels** from G2.2 get a "used in this batch" penalty.
- **Fallback:** when the optional `[search]` extra isn't installed, today's menus are used unchanged.
- **New gate `broll_repeat` (warn):** the same b-roll id twice, or two descriptions above 0.9 cosine.

**Tests:**
- a fake deterministic embedder;
- MMR picks diverse items;
- refused assets never ranked;
- `ml_ok` false assets have no file-derived features;
- the fallback without the extra;
- the batch penalty;
- the `broll_repeat` gate.

**Cost and re-runs:** no new Claude call. The finish menu changes, so through `_assets_fp` and the pack **every project's next run re-does its finish pass once (1 Claude call each), plus compile and render.** Ship it in one release, not piecemeal.

**Real-project check:** 3 reels' b-roll and SFX picks, before and after; the owner marks each cutaway "fits / doesn't".

---

### G2.4 Studio phases 3–4, plus owner labels and kept adjustments (2.5–3 days)

The items are specified in `ui-backend-plan.md` (C3, C4, A3, E1, E2, C5). These are the implementation notes found while planning, plus two small additions.

**C4: story-line edits** (drop or reorder kept lines in Adjust):
- Build a `StoryPatch` from the UI (a delete, or a move as delete + insert) and run it through the existing `apply_story_patch` + `validate_story`.
- **Orphans:** finish elements bound to a deleted item id (punch-ins, SFX anchors, graphics, b-roll, effects) are dropped by code. A reorder keeps them.
- Then `validate_finish`, then re-run from compile with no Claude call.
- If the finish plan still fails, offer "Ask the Editor" (the revise path) instead of saving a broken plan.
- A reel project made by G2.2 also enforces its window here.

**C3: gate switches:**
- **Mode override.** `config.QA_GATES` is code, so add a user override, `~/.config/reel/gates.json` (0600), read by `qa.apply_modes`.
  - The switch is enabled only when the calibration report's `promote_to_block` is true for that gate. Today that is `frozen` only.
- **Switching a mode recomputes only the verdict** from the stored gate results.
  - `qa.apply_modes` and `verdict.py` already separate the two steps.
  - It does not re-run the QA stage, whose hash includes `QA_GATES` and which would cost a Reviewer call.
  - The QA hash then uses the merged modes.

**A3: beat names:** a display map of beat ids, plus a tooltip with the line text from `projects.words_text`. UI and one field.

**E1: launcher:**
- `reel studio --install-launcher` writes `~/Library/LaunchAgents/com.reel.studio.plist`; `--uninstall-launcher` removes it.
- KeepAlive, logs to `~/Library/Logs/reel-studio.log`.
- It still binds 127.0.0.1 only. E3 stays a separate owner decision.

**E2: notifications:**
- The web Notification API, opt-in in Settings.
- Fired from the existing `studio/events.py` stream when a project turns `sendable`, `hold`, `failed`, `awaiting_choice`, or, new with G2.2, `source` ready.

**C5: bake-off in the lab:**
- A `bakeoff` job kind running `reel bakeoff`, with the result table in the Quality lab.
- It matters because `config.ASR_ENGINES` keeps Hindi and Hinglish on `whisper-large-v3` until the owner's clips are scored. This is the path to choosing the Hinglish engine.

**Owner-label buttons** *(addition)*:
- Review gets "Sendable / Hold + note" buttons, writing `qa/owner_label.json` exactly as `reel label` does.
- The Quality lab shows "owner labels: n (a gate can be promoted after 6 owner-sendable renders)" from `calibrate.MIN_LABELS`.

**Kept adjustments** *(addition)*:
- **The problem:** `_apply_adjust` (`studio/app.py`) writes straight into `plan/finish.json`. A later chat revision returns a complete new finish plan, so an owner's manual change (music off, a different look) can be undone silently.
- **The fix:**
  - log each adjustment to `plan/adjustments.jsonl`;
  - list the active ones in `REVISION_PROMPT` as "the owner set these by hand; keep them unless the request is about them";
  - after a revision, compare those fields and add a warning issue `adjustment_reverted` when one changed without the request mentioning it.

**Tests:**
- per `ui-backend-plan.md`'s definition of done;
- **C4:** orphan dropping, a reorder that keeps bindings, and the fall-through to "Ask the Editor";
- **C3:** the switch is refused when `promote_to_block` is false, and switching re-computes the verdict with no Reviewer call;
- **Labels:** the label file matches the `reel label` format;
- **Adjustments:** a revision that reverts a logged adjustment raises `adjustment_reverted`.

**Cost:** no new Claude calls. A C4 edit re-renders from compile.

---

### G2.5 Free-model listening test (0.5–1 day of tooling, plus owner listening)

**What the owner gets:** a blind A/B page per set (SFX, music, voice), and a decision note per Group 3 item saying which free model, if any, is good enough for client reels.

**Design**
- **`reel listen prepare --set sfx|music|voice`:**
  - renders a fixed prompt set with each candidate that is installed;
  - writes `eval/listening/<set>/<prompt>/<model>.wav` plus a manifest recording, per output: the model, its commit, the weights sha256, the licence id and the generation time.
- **The prompt sets are desi on purpose:**
  - **SFX:** pressure-cooker whistle, auto-rickshaw horn, crowd "wah!", cash-register ding, dhol hit, phone notification, whoosh.
  - **Music:** an upbeat Bollywood-pop bed at 100 bpm with no vocals, lo-fi chai-shop, a corporate-motivational build, a devotional-calm bed.
  - **Voice:** Hindi, Hinglish and Tamil lines, including numbers said in lakh and crore.
  - **Voice cloning:** tested **only on the owner's own voice**, with written self-consent kept in the folder (the consent rule from `dubbing.md` §7).
- **The candidates** come from `oss-feature-gap-plan.md`'s free-replacement table:
  - **SFX:** Stable Audio 3 Small-SFX, against MOSS-SoundEffect v2.
  - **Music:** ACE-Step 1.5 and Stable Audio 3 Medium, against the MIDI + FluidSynth fallback.
  - **Voice:** Maya 2 Native, ZONOS3-Mini, Chatterbox Multilingual V3 and VoxCPM2.
  - **Sarvam Bulbul v3 is a paid API, not a free model.** Include it only as a labelled paid reference point, if the owner wants a benchmark for Hinglish.
- **The listening page** (a static page in Studio):
  - pairs in random order and random sides;
  - choices: A / B / tie, plus "usable in a client reel? y/n";
  - results go to `eval/listening/<set>/results.json`;
  - a summary gives the win rate, the usable rate and the generation time on this Mac.
- **The decision rule:** a model is adopted for Group 3 only if its usable rate is at least 70% **and** it beats the fallback. Otherwise Group 3 keeps the fallback or waits.
- **Before anything is downloaded:**
  - check free disk (SA3 Small-SFX is about 3.5 GB, ACE-Step about 10 GB);
  - read each model's licence file and model card again at its pinned commit;
  - add a licence-registry row per generator, for example Stability's Community Licence with its "Powered by Stability AI" credit and revenue cap, **before** any generated file can enter a reel.

**Tests:** manifest writing, blind pairing (the side is randomised and never shown), results aggregation, the decision rule, and refusal of a model with no registry row.

**Cost:** no Claude calls. The cost is download time and disk, and generation time is unknown on this Mac for ACE-Step.

---

### Group 2 summary

| Item | Days | New Claude calls | Forces re-runs on existing projects |
|---|---|---|---|
| G2.1 pacing *(addition)* | 0.5 | — | QA once (1 Reviewer call each) |
| G2.2 Clip Factory | 3–4 | miner: 1 per chunk; each reel is a normal edit | — |
| G2.3 asset search index | 1.5–2 | — | **Finish pass once** (1 call each) |
| G2.4 Studio phases 3–4 (+ labels, kept adjustments *(additions)*) | 2.5–3 | — | — |
| G2.5 listening test | 0.5–1 + owner time | — | — |
| **Total** | **about 8–10.5** (about 7–9.5 without the additions) | | |

The roadmap's earlier estimate was 5–7 days. The difference comes from three things:
- the additions;
- enforcing the Clip Factory window in every story path, not only the first pass;
- the C4 orphan handling and verdict-only gate switching found while planning.

### Group 2 as built (2026-11-20; not committed)

All five items are built and tested with fakes. Each item needs owner input before it is proven on real work; that input is listed per item. Where the build differs from the plan above, the item says so.

**G2.1 pacing:**
- **Code:** `qa.pace_profile` / `measure_pace` / `timeline_changes` / `pace_gates`; `verdict.pace_numbers`, which writes `qa/pace.json`.
- **Gates:** `pace` and `static_stretch`, both in warn mode.
- **Reviewer:** gets a "Pace" section and one new persona line.
- **Measured the same way, with `visual.scene_cuts` on the final render:**

  | Reel | Cuts per minute | Longest stretch with no cut |
  |---|---|---|
  | Pro finals in `samples/gold` (6 reels) | 1.6 to 32 | 5 to 64 s |
  | Our `_real_doac_v2` render | 22.8 | 6.4 s |
  | Its own pro final (`thediaryofaceo_HAXzFdJ9U-0`) | 22.5 | 14.9 s |

  So our reels are **not** slow the way Timeline-Bench's agents were. And no fixed genre band means anything.
- **Changes from the plan:**
  - The gates judge only against the project's **reference reel** (±35% cuts/min; longest stretch at most 1.5× the reference's). Without one they report the numbers and pass.
  - `calibrate_auto` was not extended: the pro finals have no reference reel, so the gate would pass trivially.
  - A failed measurement is recorded as "not measured" and does not pass.
- **Cost:** QA re-runs once per project, with 1 Reviewer call each.

**G2.2 Clip Factory:**
- **Code:**
  - `reel/mine.py`: miner checks, the engine's score, selection with the family quota, overlap rule and yield cap, and chunking.
  - `personas/clip_miner.md`.
  - `stages/mine.py` (`MINE_PIPELINE`).
  - `reel/clipfactory.py`: `spawn`, windowed tables, `load_window`, batch-style anchor, `batch_broll`.
  - The window enforced through `decide.Inputs.window` / `story_issues` in the story pass, `_story_valid`, revisions, autofix, Studio adjust and the CLI validators.
- **CLI:** `reel run <recording> --mine [--clip-length 20-75]`, `reel factory --project <source> --make c01,c03 [--run]`, and `reel run --project <reel project>` with no input.
- **Studio:**
  - "Long recording → several reels" in New edit.
  - The Clips board tab.
  - `source` and `clip` project kinds.
  - Analysis stages show as "shared" in reel projects.
  - A cost estimate per reel, from past edits' median call costs, once 3 edits exist.
- **Changes from the plan:**
  - Reel projects regenerate their own contact sheets for the window, instead of hard-linking tiles.
  - The batch look is **anchored once**: the first reel to finish writes `mine/batch_style.json` in the source. Without the anchor, siblings would flip each other's finish hashes and re-buy finish passes.
  - Sibling b-roll use is a menu hint only, not hashed, for the same reason.
- **Real-file check, with no Claude calls (2026-11-20):**
  - **Setup:** an APFS clone of `_real_doac_v2` as the source, a hand-written candidate, and `spawn`.
  - **Spawn:** 33 s, including the contact sheets. The window was words 0–532, about 172 s of speech.
  - **Validation:** the parent's story plan passes against the window.
  - **Re-render:** `reel rerun --from compile` produced the base, overlay, composite, QA, cover and package.
  - **Results:**
    - the package is 355 MB of real files, with no symlinks;
    - the mezzanine is the same inode in both projects (a hard link);
    - the source's perception files are byte-identical afterwards;
    - QA: Hold on one unconfirmed caption word, the same as the source project; 24.9 cuts/min.
  - **Chunking:** on the real `script.md`, a 0–30 s window keeps 14 of 68 segment lines.
  - **One environment hiccup:** the first overlay attempt failed when Puppeteer couldn't kill its headless Chrome (`kill EPERM`) while the test suite was also rendering. A retry from the overlay stage passed. This is not Clip Factory code.
- **Still to do with the owner:** the real-project check on a 20–60 min recording. It covers the miner's quality, analysis time and disk on long footage; `OVERVIEW_EVERY_S` stays unchanged until then.
- **Not done:** Studio uploads are capped at 4 GB, which a long recording can exceed. The CLI `--mine` path has no cap.

**G2.3 asset search index:**
- **Code:**
  - `reel/asset_search.py`: in-memory BM25 over the text the engine already holds, optional `embed` hook, near-duplicate folding, sibling penalty.
  - The finish pack's b-roll menu ranked per kept line ("suits k03").
  - New gate `broll_repeat` (warn).
- **Changes from the plan:**
  - No SQLite/FTS5 file: per-project pools are tens to hundreds of clips, so an on-disk index adds a file and no speed.
  - No embedding model was chosen. Its licence and Hinglish quality are still a verify step, so Hinglish lines match English descriptions only through shared words.
  - The SFX and Lottie menus are unchanged: SFX names carry little meaning, and Lottie was already tag-matched in G1.8.
- **Cost correction:** the finish hash does not include `decide.py`, so this does **not** force a finish re-run on existing projects. The new menu applies the next time a finish pass runs anyway.
- **Owner question, still open:** the `ml_indexing_ok` question about `broll_describer`.

**G2.4 Studio phases 3–4:**
- **Built:**
  - **C4** story-line edits: `reel/story_edit.py`, adjust kind `story_lines`, the Adjust → Story panel.
  - **C3** gate switches: `config.gate_overrides` / `gate_modes`, `PUT /api/lab/gates/{gate}`, `verdict.recompute` with no Reviewer call, the Quality-lab switch.
  - **A3** beat names: `beatLabel`, story-strip tooltips with the line text.
  - **E1** launcher: `reel studio --install-launcher` / `--uninstall-launcher`.
  - **E2** notifications: opt-in in Settings; `hooks/notify.ts`.
  - **C5** bake-off in the lab: `POST /api/lab/bakeoff`, `Lab.bakeoff`.
  - **Kept adjustments:** `reel/adjustments.py`, `plan/adjustments.jsonl`, the revision prompt section, `adjustment_reverted` warnings.
- **The owner-label buttons already existed** (Review → "Would you post this?" → `POST …/label`), so nothing new was needed.
- **E3** (sharing outside this Mac) is still your decision.

**G2.5 listening test:**
- **Code:**
  - `reel/listen.py`: desi prompt sets; blind pairs with opaque file names; votes; the adopt rule (usable ≥ 70% and wins > 50%).
  - `reel listen prepare|summary --set sfx|music|voice`.
  - `/api/listening/*`.
  - Studio → Quality lab → Listening test.
- **How models get in:** no model is bundled or downloaded. Each one is declared in `~/.config/reel/generators.json` with its command, commit and weights hash. A generator whose `licence_id` has no registry row, or a blocked one, is refused.
- **Baselines:**
  - SFX and music: today's library (the nearest indexed file).
  - Voice: macOS `say` as a reference only, never adoptable.
- **Owner to do:** download candidates (disk first), read their licences, add registry rows, declare them, listen.

**Tests:**
- Engine: 471 passed, 1 skipped (`SSL_CERT_FILE=$HOME/.mac-ca-bundle.pem`, run on its own). This includes the new `test_pace.py`, `test_clipfactory.py`, `test_studio_clips.py`, `test_asset_search.py`, `test_studio_controls.py` and `test_listen.py`.
- Web: 57 passed; the type check passes and `npm run build` succeeds.
- Run alongside a real render, two Remotion overlay tests failed on contention. They pass when the suite runs on its own.

---

## Group 3: what comes after Group 2 (planned 2026-11-20)

**Sources:** the ranked gaps and harness ideas in `research_notes/harness-comparison.md` (§3, §4), and the old Group 3 list.

**A correction found while planning:** harness idea #1 (statistical acceptance in `reel improve`) is **already built**. `evalh/acceptance.py` has a paired permutation test, a noise-based minimum gain, a confirmation re-run and per-language subsets. What limits it is the data: 6 English gold pairs. So Group 3b builds tooling for growing the gold set, not new statistics.

**Order and why:**
- **3a first.** These are client-visible wins that need nothing from the owner.
- **3b alongside.** It pays off as the owner's labels and Hindi pairs arrive.
- **3c.1 (beauty pass) any time.** It uses MediaPipe, which is already installed.
- **3c.2–3c.5 only after the listening test** clears a model for each.

**Rules:** the same as Groups 1 and 2: fakes in tests, a real-project check where the output changes, cost and re-runs stated, and a commit only when the owner says so.

---

### Group 3a: client-facing

#### 3a.1 Story check-in before the money is spent (about 1 day)

**What the owner sees:**
- An optional stop after the story pass, before the finish pass and render are paid for.
- One plain paragraph: the hook, the kept lines in order with timings, and what was left out.
- At most 3 questions, each with buttons: "Open with option 2 instead?", "Use take 3 of this line (the engine's suggested take) instead?", "Drop this 9-second line?".
- Approve, answer, or type a change.

**Design**
- **The stop:** a run option `story_checkin`. The pipeline's stage list ends at STORY, like G1.6's `preview_first`. The project status becomes `awaiting_story`, shown under "Needs you". It never reads as failed.
- **The questions come from code, with no Claude call and no schema change.**
  - A schema change would put the schema in the story hash and re-run every project's story pass.
  - The questions are built from:
    - `hook_options` ranked 2 and 3;
    - take groups where the Editor kept a take other than the suggested one (`tables/takes.json`);
    - kept lines over 8 s;
    - dropped segments that contain a `brief.must_keep_lines` match, which become a warning, not a question.
- **Answers apply through code paths that already exist:**
  - a hook swap or a dropped line: `story_edit.reorder`;
  - a different take: a `replace` op validated by `validate_story`, with the window for Clip Factory reels;
  - free text: `decide.revise` on the story session, which costs one Claude call;
  - then the run continues from FINISH.
- **Studio:**
  - a "Check the story first" toggle in New edit, also available as a brand-kit default;
  - the check-in panel in the project header, like the hook chooser;
  - the review link page can show it to the client, behind the same token.

**Tests:**
- the stop and the status;
- each question type built from fixtures;
- each answer applied and re-validated, including the window;
- the continue job's arguments;
- the review-link block.

**Cost:** no new Claude call unless the owner types a change. It saves the finish pass and render on a story the owner would reject.

#### 3a.2 Per-client style memory: "edit like my last approved reel" (about 2 days)

**What the owner sees:**
- The 4th reel for a client looks like the first three without setting anything.
- New edit offers "Match: last approved reel for this client", or a specific past reel.
- Studio shows the client's style card: caption family, look, pace, music mood, typical length, and recurring notes ("no SFX", "keep it under 40 s").

**Design**
- **The memory file:** `projects/.clients/<client-slug>.json`. It is derived and rebuildable from the projects. The client is the brief's `client`, or else the studio client.
- **When a reel is learned from:** when it is marked **delivered**, or labelled sendable by the owner. These are real approvals, not the engine's own verdict. Each entry records:
  - from `plan/finish.json`: caption family and tokens, look and strength, grain and vignette, punch-ins per minute, SFX per minute, graphic kinds, hook-title style, b-roll share, music track mood and energy;
  - from `qa/pace.json`: cuts per minute and the longest static stretch;
  - the reel's length;
  - the owner's adjustments (`plan/adjustments.jsonl`) and revision requests (`plan/history/*_request.json`), as raw notes.
- **The profile:** medians over the last 5 approved reels, plus the notes that recur in at least 2 reels. Notes are condensed by code (deduplicated, counted), not by Claude.
- **How the Editor uses it:**
  - the story and finish packs get a "# This client's approved reels" section: the medians and the recurring notes, phrased as defaults, not rules;
  - brand-kit locks still win.
- **"Match a past reel":** sets `options["reference"]` to that project's `export/reel.mp4`. The existing REFERENCE stage and `reference_style.md` then do the rest, and the G2.1 pace gates judge against it automatically.
- **A drift check (warn, `client_style_drift`):** after finish, code compares caption family, look and cuts per minute with the profile. It warns when two or more of them differ and the brief doesn't ask for a change.
- **Hashes:** the story and finish hashes include the profile's fingerprint only when a profile exists. New approvals then change the next edit's packs, but never re-run finished projects: hashes are checked only when a project runs.

**Tests:**
- learning only from delivered or owner-sendable reels;
- medians and recurring notes;
- the pack section;
- "match a past reel" setting the reference;
- the drift warning;
- no profile means no hash change;
- the client slug falls back to the studio client.

**Cost:** no new calls. One finish pass re-runs only for projects run again after their client gains a profile.

**Real-project check:** this needs the owner's 3 or more delivered reels for one client. Until then, test it on copies.

#### 3a.3 Word-level text editing (about 1.5–2 days)

**What the owner sees:** in Adjust → Story, each kept line opens to its words. Striking words removes them, and "trim to here" trims the line's start or end. The validator checks the result as with any other adjustment.

**Design**
- **Engine:** `story_edit.cut_words(story, fin, item_id, ranges)` splits an item around the removed words into `k07a` and `k07b`, keeping the original id on the first part.
- **Finish elements:**
  - an element anchored to a word moves to the part that holds the word;
  - an element spanning a removed word is dropped and counted in the note;
  - SFX anchored "cut after item" follow the last part.
- **Checks:**
  - a cut inside a word is refused, using word edges;
  - removing a whole line goes through `reorder`;
  - in a Clip Factory reel, the window is still checked.
- **API:** adjust kind `story_words` with `{item, remove: [[from, to]]}`, logged as a kept adjustment.
- **Studio:** a word-chip view, using `TimelineView.story[id].text` plus word indices (a new field). Shift-click selects a range.

**Tests:** the split, rebinding, dropping, edge refusal, a removal that empties a line, the window, and the route plus the web.

**Cost:** no calls. A re-render from compile, which G1.5 makes partial where it can.

**Group 3a total:** about 4.5–5.5 days.

#### Group 3a as built (2026-11-20)

**3a.1 story check-in:**
- **Code:**
  - `reel/checkin.py`: build and answer.
  - The `CHECKIN` stage and `edit.checkin_pipeline(base)`, working for ordinary and Clip Factory reels.
  - `story_edit.reorder_story`.
- **CLI:** `reel run … --story-checkin`, then `reel checkin --project <p> [--yes q1,q2] [--note "…"] [--approve] --continue`.
- **Studio:**
  - a "Check the story before the full edit" toggle;
  - the `awaiting_story` status ("check the story");
  - the check-in panel in the project header;
  - `GET/POST /api/projects/{id}/checkin`;
  - a notification.
- **Changes from the plan:**
  - Answers change only `story.json`: no finish plan exists yet at the stop.
  - The client-facing review-link block and a brand-kit default are **not built**. The toggle is per project.

**3a.2 client style memory:**
- **Code:**
  - `reel/client_memory.py`, writing `projects/.clients/<slug>.json`.
  - Learning on "delivered" and on an owner "sendable" label. Withdrawing the approval forgets the reel, unless it is still delivered.
  - The story and finish packs get the profile section.
  - The story and finish hashes include the profile only when one exists.
  - QA gate `client_style_drift` (warn).
- **Studio:**
  - a style card under Client in New edit;
  - "Edit like <past reel>" (`match_project`, which becomes the reference reel);
  - `GET /api/clients/{name}`.
- **Real check:** waits on 3 or more delivered reels for one client.

**3a.3 word-level edits:**
- **Code:** `story_edit.cut_words` and adjust kind `story_words`; `TimelineView.story[id].words`; a "Cut words" row in Adjust → Story.
- **Changes from the plan:** removals are whole words by index, so a cut inside a word can't happen, and no edge check was needed.

**Tests:**
- new `test_checkin.py` and `test_client_memory.py`;
- additions to `test_studio_controls.py`;
- web route tests for the check-in, the client card and word cuts.

---

### Group 3b: proving quality

#### 3b.1 A rubric frozen per brief (about 0.5 day)

**The idea:** the Reviewer scores against criteria written *before* any output exists. Evidence: VideoArgus, arXiv 2608.05485.

**Design**
- At the STORY stage, code writes `plan/rubric.json` from the brief and the client profile, with no Claude call:
  - must-keep lines;
  - the CTA;
  - banned claims;
  - target length;
  - tone and genre;
  - the hook within 2 s;
  - the client's recurring notes.
- `Review` gains `rubric: [{id, met, evidence}]`. The Reviewer may not add or remove criteria; a validator check returns any change to it.
- `verdict_md` shows the met and unmet criteria. An unmet must-keep or CTA criterion is a Hold reason. Other criteria are warnings.
- **Cost:** the Review schema is part of the QA hash, so **QA re-runs once per project, with 1 Reviewer call each**. Ship it together with 3b.2 so it happens once.

#### 3b.2 Pairwise judge for evals, both orders (about 1 day)

**The idea:** for each gold reel, a judge sees our reel and the pro reel as contact sheets plus the same four pace numbers. It is asked twice with the sides swapped; when the two answers disagree, the result is a tie. Evidence: Unified Agentic Video Editing; EditDuet.

**Design**
- `reel eval --pairwise` adds a `pairwise` family: wins, ties and losses against the pro reel.
- It stays **out of the primary score** until it agrees with the owner's own pairwise picks. The Quality lab gets a small "which is better?" page reusing G2.5's blind A/B component.
- **Cost:** 2 Claude calls per gold reel per eval run. It is opt-in.

#### 3b.3 Revision evals: "do what I asked, don't break the rest" (about 1 day)

**Design**
- `eval/revisions/*.yaml` cases, each with: a project snapshot, a client note, the expected output region (seconds), and the expected change kind (caption, music, cut).
- The harness runs `decide.revise` on a copy, compiles the result, and uses `rediff.changed_ranges` (from G1.5) between the old and new overlay props, plus a timeline diff.
- **Scores:**
  - *did it*: a change in the expected region, of the expected kind;
  - *collateral*: changed frames outside the region;
  - *don't break*: no new failing gate.
- Seed 6 cases from `_real_doac_v2` notes. The scoreboard gains a `revisions` family.
- **Cost:** 1 Claude call per case per run.

#### 3b.4 Replies checked against the gates (about 0.5 day)

**The problem:** in Timeline-Bench, agents claimed success in 93% of runs, including 95.5% of the runs that failed a test. Our revise and notes replies are Claude's words, written before the re-render and QA.

**Design:**
- After the re-render, the version entry's reply gets the measured verdict appended, for example "QA: Hold, 1 caption word to confirm".
- The Studio Revise chat shows the reply and the verdict together.
- **Cost:** no calls.

#### 3b.5 Gold-pair tooling (about 0.5 day)

**Design:**
- `reel gold add <raw folder> <final.mp4> --language hi|hinglish|en --split tuning|holdout`.
- It copies the files into `samples/gold/<id>/`, writes the brief stub, refreshes `eval/manifest.yaml`, and refuses a pair whose final is not derived from the raw (an audio fingerprint overlap check).
- The Quality lab shows "Hindi/Hinglish pairs: n", which unlocks the per-language acceptance subset.
- This makes the owner task (2–4 Hindi pairs) a 2-minute job per pair.

**Group 3b total:** about 3–3.5 days.

#### Group 3b as built (2026-11-20)

**3b.1 rubric:**
- **Code:**
  - `reel/rubric.py` and a `RUBRIC` stage before STORY (no Claude call). It writes `plan/rubric.json` from the brief and the client profile.
  - `Review.rubric` holds one answer per criterion. A changed list is sent back to the Reviewer; an empty answer becomes a verdict warning, not an error.
  - An unmet required criterion (must-keep, CTA, banned claim) is a Hold reason; the others are warnings.
  - The Review screen shows a "Brief checklist".
- **Cost:** the QA hash includes the rubric, so **QA re-runs once per project (1 Reviewer call)**.

**3b.2 pairwise judge:**
- **Code:**
  - `evalh/pairwise.py` and `personas/pairwise_judge.md`.
  - `reel eval --pairwise` (2 calls per reel). Scoreboard rows carry `pairwise` and the files.
  - The owner's blind picks: a Quality lab panel → `eval/pairwise_owner.jsonl`, plus an agreement rate.
- **Kept out of the primary score:** not wired into acceptance until the agreement is known.

**3b.3 revision evals:**
- **Code:**
  - `evalh/revisions.py`, plus 6 seed cases in `eval/revisions/` against `_real_doac_v2`.
  - `reel eval --revisions` (1 call per case).
  - The project copy uses hard links and is never touched.
- **Changes from the plan:** "don't break" is measured on the plan validator (errors and new warnings), not by rendering and gating. This keeps a case to one Claude call and no render.
- **Real-file check, with a fake Editor and no Claude, on `_real_doac_v2` (2026-11-20):**
  - The first version reported a one-word caption change as about 97 s of overlay change and 167 s of picture change. Two causes, both fixed:
    - the baseline was the project's stored timeline, compiled by an older engine. It is now a fresh compile of the unrevised plans;
    - picture spans were counted twice. They are now merged.
  - After the fix:
    - a look change scores did-it with 0 s of collateral;
    - one emphasised word scores 0.54 s changed, 0.46 s of it just outside the asked region (its page edge).
  - Project inputs load once per case. Each load re-probes every mezzanine, minutes on a long source.
- **A bug found and fixed in G1.5:** `rediff` iterated padded caption pages until nothing new joined. Back-to-back pages, which are normal, then chain-reacted into a full re-render.
  - The fix: one padded pass for pages after the graphics closure.
  - New test: `test_back_to_back_pages_do_not_chain_into_a_full_render`.
  - New `rediff.changed_elements`, for what actually changed.

**3b.4 replies checked against the gates:** `projects.with_measured_verdict`. Every new version's reply and the live revision event end with "· QA after the change: Sendable / Hold, n reason(s): …".

**3b.5 gold-pair tooling:**
- **Code:** `evalh/gold_add.py`, `reel gold add <raw> <final> --language hi|hinglish|en [--split] [--genre] [--channel]`.
- **The "cut from this raw" check:** 1.5 s pieces of the final's speech envelope are each matched against the raw, minus a chance baseline (the raw played backwards).
- **Measured on the 6 gold pairs:**
  - own raw: +0.047 to +0.205 (5 of 6 above +0.13);
  - another pair's raw: −0.002 to +0.046.
- **What that means:** the two overlap, so this is a guard, not proof.
  - Below +0.03, the pair is refused; `--no-check` overrides.
  - Below +0.08, it is accepted with a "watch them side by side" warning.

#### Group 3c as built (2026-11-20)

**3c.1 beauty pass:**
- **Code:**
  - `reel/beauty.py`: face boxes from the existing Face Landmarker at 6 fps on the rendered base; an interpolated, feathered skin ellipse written as an FFV1 matte; a masked `bilateral` (sigmaS 6, sigmaR 0.08) plus a +0.012 brightness lift, re-encoded to ProRes with the audio kept.
  - `Brief.beauty`, `Brand.beauty: off|light`, and a New edit toggle.
  - It runs inside the RENDER stage after a full base render. An audio-only re-render keeps the processed picture.
  - It joins the render and picture fingerprints only when on, so projects with it off don't re-render.
- **QA gate `beauty_strength` (warn):** face-region detail loss, Laplacian variance before and after, limit 35%. "Not measured" fails.
- **Real-face check on a clone of `_real_doac_v2`'s base (2026-11-20):**
  - **First version:** the face was found in 489 sampled frames, with −17% face detail in 134 s for 97 s of reel. Looking at the frames, the eyes and lips had softened, and it started to read as filtered.
  - **Changes made:** the eye band and the mouth are now carved out of the matte (box proportions, `beauty.EYES` / `MOUTH`), and the strength was lowered (sigmaS 5, sigmaR 0.06).
  - **Second version:** −10% face detail; smoother cheeks; eyes and mouth closer to the original, though the carve-out isn't landmark-exact on angled faces.
  - That run took 1,039 s while another heavy job was running. Building the mattes for 2,900 frames takes 1.1 s, so render time is dominated by the ProRes re-encode.
- **Not built:**
  - eye brightening;
  - a per-project Adjust toggle (it's set in the brief or brand);
  - the Brands-screen field (the brand JSON accepts `beauty`).

**3c.2–3c.5 (generated SFX, music, voice/dubbing, lip-sync): not built, still gated** on the listening test (G2.5): a model must be downloaded, its licence row added, and the owner's blind votes must clear it. Dubbing also needs the speaker's written consent.

---

### Group 3c: free generative assets

#### 3c.1 Beauty pass, opt-in (about 1–1.5 days)

**What the client sees:** a gently fresher face (smoother skin, slightly brighter eyes) that never reads as "filtered". It is off unless the brand kit or the brief turns it on.

**Design**
- **Masks:** per-frame face-oval and eye masks from the MediaPipe Face Landmarker that `cover.py` already uses. They are sampled at 6 fps, interpolated, feathered, and written as a low-resolution matte (`render/beauty_mask.mov`), cached by the mezzanine fingerprint.
- **Render:** in `render.build_command`, a masked `bilateral` (skin) plus a small local `eq` lift (eyes) inside the matte. Strength is capped at `light`.
- **Switches:** `Brand.beauty: off|light`, brief `beauty: bool`, and a per-project Adjust toggle.
- **A QA gate (warn, `beauty_strength`):** measures the face-region detail loss (Laplacian variance before and after) and warns above a cap. "Never reads as filtered" is measured, not promised.
- **Never on by default.** The UI notes that it shouldn't be used on minors; there is no age detection.

**Tests:** mask interpolation, the filter graph, the gate on a synthetic face, and the brand and brief switches.

**Cost:** no calls. The base render re-runs only for projects that turn it on.

#### 3c.2–3c.5 Gated on the listening test (outlines; detailed when a model clears)

| Item | Needs from G2.5 | Shape |
|---|---|---|
| **3c.2 Generated SFX** | an SFX model with usable ≥ 70% that beats the library | The finish pass may request a missing sound as a short text in a new optional `sfx_requests` field. It's a schema change, so it ships with another finish-schema change. The file is generated once, measured by the existing indexer, and stored as an owned asset with the generator's licence row. |
| **3c.3 Music fitted to the cut** | a music model that clears; otherwise the MIDI + FluidSynth fallback | Score to the compiled cut times and the drop on the hook (G1.4). The stems already exist, so it slots in as a music asset. |
| **3c.4 Indian-language voice and dubbing** | a voice model that clears, plus **written consent** from the speaker per language | A design spike first: Claude translation with a glossary; timing fit (rewrite to length, then speed control, then pause trims, then a stretch of at most ±15%); captions in the target script; per-language packages. |
| **3c.5 Lip-sync** | 3c.4 done; a commercial-safe face parser in place of the non-commercial one | MuseTalk on close-ups only, gated by face size from perception. LatentSync on a rented GPU as the fallback. |

**Owner tasks for Group 3:**
- 3 or more delivered reels for one client (3a.2's real check);
- the Hindi gold pairs (3b.5 makes it quick);
- pairwise picks (3b.2);
- model downloads and listening (3c.2–3c.5);
- speaker consent for voice cloning (3c.4).
