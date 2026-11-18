# Reel Studio (dashboard for the reel editor) — PRD

## 1. Objective

The reel editor engine already turns raw footage into a finished, client-ready vertical reel, but today it is driven only by terminal commands. This document defines Reel Studio: a dark, studio-style dashboard that runs in the browser on the owner's Mac, where he uploads raw footage and a brief, watches the edit happen live, reviews the result with the tool's own verdict, asks for changes in plain words, and delivers the files to the client. Three-dimensional (3D) scenes are used where they explain the edit better than flat screens can: the reel playing inside a 3D phone, the edit's layers pulled apart in depth, and the editing pipeline shown as a lit-up stage. The goal is that every action the owner takes on a client reel happens in one place, without the terminal.

## 2. Background

The owner is a software engineer starting to freelance as a short-form reel editor. He is not a professional editor, so he relies on the engine to make professional editing decisions and on the tool's quality checks to tell him whether a reel is safe to send. The engine (built in steps 1–11, see `docs/architecture.md`) already covers the full job: it analyses the footage, an AI Editor (Claude) picks the story and the finishing, the engine renders the reel, quality gates and an independent AI Reviewer judge it, and it writes a `sendable` or `hold` verdict plus a package for professional editing software. Revisions, client notes, caption-word proofing, owner labels, gold-set scoring and a self-improvement loop all exist as commands.

The friction today is that all of this lives in about twenty terminal commands and in files scattered across a project folder. Following a run means reading logs; reviewing means opening a video, a markdown verdict and a JSON proof list side by side; fixing one caption word means typing a command with a word index. A real end-to-end run on a 3.6-minute podcast clip took about 15 minutes, and the owner could not see what was happening or why. As soon as the owner has several client reels at once, terminal-only use stops being workable.

The competitor scan (`docs/research/competitor-teardown.md`) shows what creators already expect from AI reel tools. Opus AI Producer, Submagic, Captions, Descript, CapCut and Vizard all offer upload-to-reel, live progress, a preview, caption styling and chat edits. None of them shows *why* the AI cut each line, and none says whether the reel is safe to send. Reel Studio should therefore match the baseline those apps set and then make our two differences visible on screen: the Editor's stated reason for every decision, and the tool's verdict with its evidence (proof list, Reviewer notes, gate results).

The visual direction is a dark professional studio, in the style of DaVinci Resolve or Final Cut Pro, chosen because footage colours read most accurately on a dark surround. 3D is used for three hero moments (phone preview, exploded layers, pipeline stage) plus a calm ambient 3D backdrop on the home and studio screens. Forms, lists and chat stay flat for speed and readability. Designs are made in Penpot, the open-source design tool already installed at `http://localhost:9001`, so the design tokens can flow into code.

**Decisions taken for this document** (the owner asked for everything in one release; each is a decision, not an open question):

- **Platform:** a local web app at `http://localhost`, served by the engine. Wrapping it as a Mac desktop app is a later packaging step and is not described here.
- **Users:** single owner only. There are no team accounts or roles.
- **Client access:** clients do not log in. The owner shares a review copy. FR-9 adds an optional, expiring review link that the owner can expose on purpose.
- **Rendering:** always on the owner's Mac. There is no cloud rendering.
- **Manual editing:** guided adjustments to the plan (FR-8) are in scope. A free-form, drag-anything timeline like Premiere is not; fine-grained manual work goes through the export package to Final Cut or Resolve.
- **Concurrency:** several edits can run at once, with a resource guard (NFR-2).
- **Assumptions** (unconfirmed, change if wrong): English interface; macOS on Apple Silicon only; raw footage is uploaded as local files, not links; a single Claude account (the owner's Claude Code login) powers every AI call.

**Proposed stack:**

| Need | Choice | Licence |
|---|---|---|
| Design | Penpot (self-hosted); its MCP server lets Claude read and create designs | MPL-2.0 |
| 3D | Three.js, React Three Fiber, drei | MIT |
| Interface | React, shadcn/ui, Tailwind | MIT |
| Animation | Motion (formerly Framer Motion) | MIT |
| Video player | the browser's video player for finished reels; Remotion Player for live overlay previews | MIT / Remotion licence (free for a single owner) |
| Engine bridge | FastAPI around the engine, with live progress over WebSocket | MIT |

## 3. Functional Requirements

#### FR-1: Projects home

**Story:** As the owner, I want one screen that lists every client reel with its status so that I know at a glance what needs my attention.

**Requirements:**
- Opening `http://localhost:<port>` shows the Projects home.
- Each project appears as a card with:
  - a thumbnail (frame at 1 second of the latest render);
  - client name and project name;
  - length, last updated;
  - a status badge: Queued, Editing (with current stage), Sendable, Hold (with reason count), Failed.
- The owner can filter cards by status and client, and search by name.
- Cards are sorted by "needs me first": Hold, then Failed, then Sendable not yet delivered, then Editing, then Delivered.
- A primary button "New edit" opens FR-2.
- **Empty state:** with no projects, a short welcome and the "New edit" button.
- **Ambient 3D:** a slow, dark 3D backdrop (floating film-frame shapes) sits behind the cards. It pauses when any render is running (NFR-1) and is replaced by a static image when the system's reduced-motion setting is on.
- If the engine is not reachable, the screen shows "Engine is not running" with the command to start it, not a blank page.

**Dependencies:** None.
**Out of scope:** Archiving and deleting projects in bulk (one at a time is in FR-12).

#### FR-2: Start a new edit

**Story:** As the owner, I want to upload a client's raw footage with their brief so that the engine can edit it without me touching the terminal.

**Requirements:**
- Entry points: the "New edit" button on FR-1, or dragging video files anywhere onto the Projects home.
- **Upload:**
  - accepts one or more video files (mp4, mov, m4v, mkv, webm) up to 4 GB each;
  - rejects other files with a message naming the file;
  - shows a progress bar per file.
- **Brief form**, with every field optional except project name. The fields mirror the engine's brief:
  - client, language (English / Hindi / Hinglish / auto), platform, goal, audience, genre;
  - target length (min–max seconds), caption script (Latin / Devanagari / mixed);
  - must-keep lines, call to action, product names, banned claims, tone, spelling vocabulary, notes;
  - extra deliverables (4:5 feed, square).
- Optional extras:
  - pick a saved brand kit (FR-10);
  - a b-roll folder or files;
  - a reference reel the client likes.
- A "Start edit" button creates the project, starts the run (FR-3) and opens the live view.
- If another edit is running, the new one starts too if the resource guard allows (NFR-2); otherwise it shows "Queued — starts when a slot frees up".
- Briefs can be saved as templates and reused.

**Dependencies:** FR-3 (to show progress after starting).
**Out of scope:** Importing footage from links (YouTube, Drive); recording from a camera.

#### FR-3: Watch the edit live (3D pipeline stage)

**Story:** As the owner, I want to see what the tool is doing right now and why so that I trust it and know how long to wait.

**Requirements:**
- **3D pipeline stage.** The edit's stages are shown as lit nodes on a dark stage: Ingest, Mezzanine, Perception, Tables, Story, Finish, Compile, Render, Overlay, Composite, QA, Package, Variants. Done nodes glow steady, the running node pulses, skipped nodes are dimmed, and a failed node turns red.
- **Running stage detail:** its name in plain words (for example "Story: the Editor is choosing the hook and the lines to keep"), elapsed time and an estimated time left based on past runs of similar length.
- **Live decision feed.** As the AI Editor finishes each step, its output appears in plain words:
  - the chosen hook and why;
  - the kept lines in order with their reasons;
  - the caption style, look and punch-ins with reasons;
  - the cost of each AI call so far.
- Logs are available behind a "Technical log" toggle, not shown by default.
- **Cancel.** A "Cancel edit" button stops the run safely; the project shows "Cancelled — resume" and resuming continues from the last finished stage.
- **Failure.** If a stage fails, the node turns red, the plain-language reason is shown (for example "The footage has no audio track"), and a "Retry" button reruns from that stage.
- **Several edits at once.** A compact strip at the top lists all running edits with their current stage; clicking one switches the view.
- The view updates within 1 second of the engine changing state (NFR-3). Closing the browser does not stop the edit, and reopening shows the current state.

**Dependencies:** None.
**Out of scope:** Changing the plan while the Editor is still deciding.

#### FR-4: Review the reel (3D phone preview and verdict)

**Story:** As the owner, I want to watch the finished reel the way a viewer will see it, next to the tool's verdict, so that I can decide in under a minute whether to send it.

**Requirements:**
- Entry: opening a project whose edit has finished.
- **3D phone preview.** The reel plays inside a 3D phone that can be rotated by dragging and reset with a double-click.
  - A toggle overlays the platform's interface (Instagram Reels or YouTube Shorts buttons and caption area).
  - A second toggle highlights the safe zones in a soft glow.
  - Play, pause, scrub, mute and full-screen flat playback are available.
- **Verdict card** beside the phone: Sendable (green) or Hold (amber), with each hold reason in plain words.
- **Proof list.** Each unsure caption word is shown with its timecode and suggestion. Clicking a word jumps the video to it. The owner can mark it correct or type the right word and press "Fix". Fixes re-render captions only, and the card shows progress.
- **Reviewer notes.** Each note shows its severity, category, timecode and suggested fix. Clicking a timecode jumps the video there.
- **Quality checks.** All gates appear in a collapsible list, with pass, fail or warning and the measured value.
- **Labelling.** A "Would you post this?" Yes / No control records the owner's label for calibration (FR-11).
- Hold with no fixable reasons shows "Needs you" plus the reasons. Sendable shows a "Deliver" button leading to FR-9.

**Dependencies:** FR-3 (a finished edit).
**Out of scope:** Comparing two versions side by side (version history is in FR-6).

#### FR-5: Explore the edit's layers (exploded 3D timeline)

**Story:** As the owner, I want to see how the reel is built, layer by layer, and why each piece is there so that I understand and can explain the edit to a client.

**Requirements:**
- Entry: a "Layers" tab next to the preview in FR-4.
- **Exploded view.** The current frame is shown as stacked transparent planes pulled apart in depth, matching how the engine builds the picture: source video, colour, punch-in, b-roll, captions, titles. Audio is shown as stems: dialogue, music, effects.
- The owner can orbit the stack, scrub through the reel, and collapse the stack back into the finished frame with an animation.
- **Reasons.** Clicking any piece shows the AI Editor's reason for it, taken from the edit list. Examples: a kept line ("why this line, why here"), a punch-in, a caption page, a sound effect, the colour look.
- **Story strip.** A flat strip under the stack shows the kept lines in order as coloured blocks sized by duration. Hovering a block shows its text; clicking jumps the playhead.
- With reduced motion on, the stack is shown as flat side-by-side layers instead of 3D.

**Dependencies:** FR-4.
**Out of scope:** Editing from this view (changes go through FR-6 to FR-8).

#### FR-6: Ask for changes in plain words (revision chat)

**Story:** As the owner, I want to type "make the hook faster" and get a revised reel so that I can fix things without editing skills.

**Requirements:**
- Entry: a chat panel in the review screen.
- The owner types a request. The AI Editor replies in one line with what it will change, applies the change, and the reel re-renders. Only the stages that the change affects run again.
- **Before and after.** Each revision shows the line order and title, captions or look that changed. "Compare" plays the old and new versions of the changed section one after the other.
- **Version history.** Every revision is listed. The owner can open any earlier version and restore it as the current one.
- **Failure.** If the Editor's change fails the validator twice, the message says so in plain words and nothing changes.
- Each revision's AI cost is shown.

**Dependencies:** FR-4.
**Out of scope:** Voice input.

#### FR-7: Apply a client's notes

**Story:** As the owner, I want to paste the client's timestamped notes so that all their feedback is applied in one go.

**Requirements:**
- Entry: a "Client notes" button in the review screen.
- The owner pastes text such as "0:12 make this faster", "[0:04] cut this" or "love the colours". Each line is parsed into a timecode and a note; untimed lines apply to the whole reel.
- **Preview before sending.** Each note shows the line and the caption that are on screen at its timecode. The owner can edit or remove any note.
- "Apply notes" sends one revision (as in FR-6) and shows the result with before and after.
- Lines that cannot be read are listed as "Couldn't read" and are not sent.

**Dependencies:** FR-6.
**Out of scope:** Importing notes directly from email or messaging apps.

#### FR-8: Guided adjustments without AI

**Story:** As the owner, I want to make small, exact changes myself (drop a line, swap the order, change the caption style) so that I don't need a chat round-trip for obvious tweaks.

**Requirements:**
- Entry: an "Adjust" tab in the review screen.
- **Story list.** The kept lines are shown as cards in order. The owner can drag to reorder, remove a line, or restore a line from the list of lines that were not kept.
- **Trim.** The owner can trim the start or end of a line by whole words, by clicking the first or last word in its transcript.
- **Finish.** The owner can switch the caption family and the colour look and its strength from small visual swatches, and can turn the hook title, each punch-in and each transition on or off.
- Every adjustment is validated by the engine before it applies. Invalid changes show the validator's plain-language message, for example "This removes a must-keep line".
- "Apply" re-renders only what changed. The adjustment appears in the version history (FR-6) labelled "Manual".

**Dependencies:** FR-4, FR-6 (version history).
**Out of scope:** Frame-level trimming, keyframe editing and free-form layer moves. These go through the export package (FR-9) to Final Cut or Resolve.

#### FR-9: Deliver to the client

**Story:** As the owner, I want to download everything the client needs in one place so that delivery takes a minute.

**Requirements:**
- Entry: the "Deliver" button on a project.
- The screen lists:
  - the final reel;
  - extra aspect ratios (4:5, square) with thumbnails;
  - the low-resolution review copy;
  - the editing-software package (Final Cut timeline, OpenTimelineIO timeline, captions files, audio stems, overlay with transparency, edit list with reasons).
- **Opening and copying.** Each item has "Open in Finder" and "Copy path" actions. "Open in Final Cut Pro" opens the package's timeline if Final Cut is installed.
- **Platform warnings.** These come from the engine, for example "longer than the 180 s Reels limit".
- **Optional review link.** "Create review link" starts a local review page for this reel:
  - it shows the review copy and a notes box that writes into FR-7;
  - the link expires after a time the owner chooses (default 7 days) and can be revoked;
  - it is reachable from outside only if the owner exposes it on purpose (for example with a tunnel). The screen says this plainly.
- Marking a project "Delivered" records the date and moves it down the home list.

**Dependencies:** FR-4.
**Out of scope:** Posting directly to Instagram, YouTube or TikTok; client accounts.

#### FR-10: Libraries and brand kits

**Story:** As the owner, I want to manage my sound effects, music, b-roll and client brand kits in one place so that the Editor can use them.

**Requirements:**
- Entry: "Studio → Libraries".
- **Sound effects and music.** The owner picks a folder and a source plus licence (for example "Sonniss GDC 2024 — royalty-free commercial use"). The engine indexes it.
  - The screen lists files by category (SFX) or mood and tempo (music), each with a play button and its licence.
  - Indexing progress is shown, and unreadable files are listed.
- **B-roll.** Same as above for clips, showing the AI-written description, shot type and duration. Each clip can be previewed.
- **Brand kits.** Create or edit a brand kit:
  - client name;
  - colours (with colour pickers);
  - heading font;
  - logo;
  - locked caption style;
  - locked colour look.

  A live caption preview shows the brand applied.
- **Stock footage.** A search box queries Pexels when the owner has added an API key in settings (FR-12). Picked clips are downloaded into the project's b-roll with their licence.

**Dependencies:** None.
**Out of scope:** Editing audio files; generating music.

#### FR-11: Quality lab (gold set, calibration, self-improvement)

**Story:** As the owner, I want to see how good the tool is getting and help it improve so that I know when it is safe to send reels without checking each one.

**Requirements:**
- Entry: "Studio → Quality".
- **Gold set.** Lists the reference pairs (raw footage and a professional's final), each with its split (tuning or held out), language and source. Held-out pairs are visibly locked and cannot be scored except by "Release check".
- **Scores.** A chart of the average primary score per evaluation run over time, with a breakdown by family (story, captions, style, gates, Reviewer). Clicking a run lists each reel's score and opens our edit next to the professional's final.
- **Calibration.**
  - Shows how often the Reviewer agrees with the owner's "Would you post this?" labels, with a trust indicator that turns on when agreement is high enough.
  - Shows each quality check's false-alarm rate.
  - The owner can switch a check from "warn" to "block" here.
- **Self-improvement.**
  - "Run improvement" starts a night of improvement with a budget the owner sets.
  - The history lists each proposed knowledge change with its outcome (accepted with its gain, or rejected with the reason). An accepted change can be undone.
- **Release check.** "Run release check" scores the held-out set once, shows the result against the pass mark (5 of 6 sendable, no wrongly sendable reel), and records it.

**Dependencies:** FR-4 (labels).
**Out of scope:** Hiring or managing the external professional judge.

#### FR-12: Settings, health and costs

**Story:** As the owner, I want to see whether the tool is healthy and what it costs so that nothing fails silently.

**Requirements:**
- Entry: "Studio → Settings".
- **Health.** Shows the engine's readiness checks: video tools, AI models, renderer, disk space. Each has a green or red status and a one-line fix.
- **AI usage.** Calls and estimated cost per project, per day and per month, from the engine's call log.
- **Settings:**
  - number of edits allowed to run at once;
  - default brief values;
  - default deliverables;
  - Pexels API key (stored only on this Mac);
  - where projects are stored.
- **Project actions.** Delete or archive one project at a time, after a confirmation that names the project and the space freed.

**Dependencies:** None.
**Out of scope:** Billing, invoicing and client time tracking.

## 4. Non-Functional Requirements

| # | Requirement | Target | How it's measured |
|---|-------------|--------|-------------------|
| NFR-1 | 3D scenes stay smooth and never slow the edit | 3D screens at 60 fps (frame time p95 ≤ 16.7 ms) on the owner's M5 Mac when no render runs; while any render runs, 3D drops to ≤ 15 fps or a static frame, and render time grows by ≤ 5 % compared with the same render with the dashboard closed **(proposed)** | Browser performance trace on each 3D screen; the same reel rendered with the dashboard open vs closed |
| NFR-2 | Parallel edits do not crash the Mac | The resource guard starts a new edit only while estimated memory use stays under 12 GB of 16 GB; at most 3 edits run at once; the rest queue **(proposed)** | Activity Monitor peak memory during 3 parallel edits of 60 s raw clips; no edit fails from memory |
| NFR-3 | Live progress feels live | Stage changes and Editor decisions appear on screen within 1 s of the engine writing them (p95) **(proposed)** | Timestamp difference between the engine's state file and the screen update, over 20 runs |
| NFR-4 | Local only and private by default | The dashboard and API listen only on 127.0.0.1; every API call carries a per-install secret token; client footage never leaves the Mac except through a review link the owner creates on purpose | Port scan from another machine on the same network finds nothing; API call without the token is refused |
| NFR-5 | Usable without a mouse and with reduced motion | Every action reachable by keyboard; with the system's reduced-motion setting on, no 3D motion plays and every 3D view has a flat equivalent; text contrast at least 4.5:1 | Keyboard-only walkthrough of FR-1 to FR-9; macOS "Reduce motion" on and checked screen by screen; contrast checker on the design tokens |

## 5. Acceptance Criteria

#### AC-1 — Home shows what needs attention first *(verifies FR-1)*

**Given:** Four projects exist: one Hold, one Sendable, one Editing, one Delivered.
**Steps:**
1. Open the dashboard.

**Expected result:** The cards appear in the order Hold, Sendable, Editing, Delivered. Each card shows its thumbnail, client, length and status badge. The Editing card names its current stage.

#### AC-2 — Engine not running *(verifies FR-1)*

**Given:** The engine is stopped.
**Steps:**
1. Open the dashboard.

**Expected result:** The page shows "Engine is not running" and the command to start it, not a blank or broken page.

#### AC-3 — Start an edit from dropped files *(verifies FR-2)*

**Given:** The home screen is open.
**Steps:**
1. Drag one .mp4 and one .pdf onto the screen.
2. Fill in the project name and language Hinglish.
3. Press "Start edit".

**Expected result:** The .pdf is rejected with a message naming it. The .mp4 uploads with a progress bar. After "Start edit" the live view opens with the first stage running.

#### AC-4 — Live view shows decisions and survives closing the browser *(verifies FR-3)*

**Given:** An edit has just started.
**Steps:**
1. Watch until the Story stage finishes.
2. Close the browser tab and reopen it.

**Expected result:** The Story node turns steady, and the chosen hook and kept lines appear with reasons. After reopening, the view shows the same stage the edit is actually on.

#### AC-5 — A failed stage can be retried *(verifies FR-3)*

**Given:** An edit whose source file has been deleted mid-run.
**Steps:**
1. Wait for the failing stage.
2. Restore the file and press "Retry".

**Expected result:** The failing node turns red with a plain-language reason. After "Retry" the run continues from that stage, and earlier stages stay done.

#### AC-6 — Fix a proof word from the review screen *(verifies FR-4)*

**Given:** A project on Hold because the caption word "Dioma" is unconfirmed.
**Steps:**
1. Click the word in the proof list.
2. Type "DearMa" and press "Fix".

**Expected result:** The video jumps to that word. After the caption re-render finishes, the caption reads "DearMa", the word leaves the proof list, and the verdict updates.

#### AC-7 — Phone preview with platform overlay *(verifies FR-4)*

**Given:** A finished reel.
**Steps:**
1. Rotate the phone by dragging.
2. Turn on "Instagram overlay" and "Safe zones".

**Expected result:** The phone rotates smoothly and resets on double-click. Instagram's buttons and caption area appear over the reel, and the safe zones glow. Captions visibly sit inside them.

#### AC-8 — Layers explain a decision *(verifies FR-5)*

**Given:** A finished reel with at least one punch-in.
**Steps:**
1. Open "Layers".
2. Click the punch-in plane at its timecode.

**Expected result:** The frame separates into labelled planes. The punch-in shows the Editor's reason text. Collapsing the stack shows the finished frame again.

#### AC-9 — Layers with reduced motion *(verifies FR-5)*

**Given:** macOS "Reduce motion" is on.
**Steps:**
1. Open "Layers".

**Expected result:** The layers appear flat, side by side, with no 3D motion, and every label and reason is still available.

#### AC-10 — Chat revision with before and after *(verifies FR-6)*

**Given:** A finished reel.
**Steps:**
1. Type "make the hook shorter".
2. Wait for the re-render.
3. Press "Compare".

**Expected result:** The Editor replies in one line. The story list shows the shortened first line. "Compare" plays old then new. Version history lists the revision with its cost, and restoring the previous version brings the old reel back.

#### AC-11 — Client notes are previewed before sending *(verifies FR-7)*

**Given:** A finished reel.
**Steps:**
1. Paste "0:01 faster", "gibberish line ??" and "love it".
2. Remove the "love it" note.
3. Press "Apply notes".

**Expected result:** "0:01 faster" shows the line and caption at 0:01. The gibberish line is listed under "Couldn't read" and not sent. After applying, one revision appears in history.

#### AC-12 — Guided adjustment is validated *(verifies FR-8)*

**Given:** A reel whose brief has a must-keep line.
**Steps:**
1. Remove that line in "Adjust".
2. Press "Apply".
3. Instead, drag the second line to the top and apply.

**Expected result:** Removing the must-keep line is refused with "This removes a must-keep line". Reordering applies, re-renders, and appears in history as "Manual".

#### AC-13 — Delivery screen and review link *(verifies FR-9)*

**Given:** A Sendable project with 4:5 and square deliverables.
**Steps:**
1. Press "Deliver".
2. Press "Create review link" with a 1-day expiry.
3. Open the link, add a note, then revoke the link.

**Expected result:** All files are listed with thumbnails and "Open in Finder". The review page plays the review copy, and the note appears in FR-7's notes box. After revoking, the link shows "This review link has expired".

#### AC-14 — Index an SFX folder and build a brand kit *(verifies FR-10)*

**Given:** A folder with 20 sound effects, one of them corrupt.
**Steps:**
1. Add the folder with source "Sonniss GDC 2024" and its licence.
2. Create a brand kit with a pink accent colour.

**Expected result:** 19 effects are listed by category with play buttons and the licence. The corrupt file is listed as unreadable. The brand kit's live caption preview shows the pink accent.

#### AC-15 — Held-out reels stay locked *(verifies FR-11)*

**Given:** A gold set with 6 held-out pairs.
**Steps:**
1. Open "Quality" and try to score a held-out pair.
2. Run an evaluation of the tuning set.

**Expected result:** Held-out pairs show a lock and cannot be scored except through "Release check". The evaluation adds a new point to the score chart, and its reels open next to the professional's finals.

#### AC-16 — Health and costs are visible *(verifies FR-12)*

**Given:** The renderer's packages are missing.
**Steps:**
1. Open "Settings".

**Expected result:** The renderer check is red, with the one-line fix. The AI usage panel shows today's calls and estimated cost per project.

#### AC-17 — Parallel edits respect the guard *(verifies FR-2, FR-3)*

**Given:** The setting allows 3 edits at once.
**Steps:**
1. Start 4 edits within a minute.

**Expected result:** Three run and appear in the running-edits strip. The fourth shows "Queued — starts when a slot frees up" and starts automatically when one finishes.
