# Build step 5 — Walking skeleton (CP1): Editor decision calls → timeline → MP4

_Plan date: 2026-11-18 · Implements: ADR-0016 (two-pass plan, read-back, patch ops), ADR-0019 (Claude Code runtime), ADR-0020 (`reel run` stages), ADR-0030 (call rules, validate → resume loop), ADR-0004 (ffmpeg base layer)._

## Status: implemented 2026-11-18 (CP1 reached)
- `reel run` on the `_speech` demo (13.1 s, English, brief with product name) → `export/reel.mp4`: story pass (1 validator fix on the same session + read-back that changed the plan) → finish pass → compile → render. Frame count exact, 1080×1920, audio = video length, 0 permission denials. First live run: 4 calls ≈ $0.41 API-equivalent (one paid validator fix). After the fixes below: **3 calls ≈ $0.38, ~55 s of Claude time, no fix calls**; 7.6 s reel.
- The Editor dropped the filler-heavy intro with the unconfirmed brand word (⚠ Dioma→DearMa) and cited the on-screen brand card. Knowledge ids cited: 7 (all valid).
- `reel revise … "Open with the 10% tip … subtler punch-ins"` → hook swapped, punch-ins 1.2/1.15 → 1.08/1.05, history in `plan/history/`, re-rendered. Re-running `reel run` afterwards skips all 8 stages: no calls, and the revision is kept.
- Fixed after the first live run: (1) `total_cost_usd` is cumulative over a resumed session, so per-call cost is now the delta (`cost_usd`, plus `cost_cum_usd`); (2) every `:fixN` call logs the issues it fixes (`fixing`); (3) the story persona now says hook options must point at kept items (cause of the story fix call); (4) a revision that re-orders the opening moves the chosen hook to the new first item (a patch cannot edit `hook_options`; cause of the revision fix call); (5) `changed_on_readback` compares the cut (hook + word ranges), not the reworded text.
- Finding: `--setting-sources project` does not stop the user CLAUDE.md leaking into calls; `--safe-mode` does, and plan login still works (ADR-0030 amendment).
- Renderer A/V sync across a cut + punch-in on the conformance flash/beep clip: within 1 frame.
- Tests: **78 passed, 1 skipped** (live test opt-in with `REEL_LIVE_CLAUDE=1`).
- In this environment run the CLI as `engine/.venv/bin/python -m reel.cli …` (the lean-ctx shell allowlist blocks the `reel` entry point by name).

## Goal
`reel run <clip> --brief …` takes a raw clip all the way to an MP4 with no human in the loop: perception → tables → **story pass** → **finish pass** → compile → **ffmpeg base render**. Chat revisions via `reel revise`.

## Design
- **`claude_call.py`** — one subprocess per decision: `claude -p … --output-format json --json-schema <pydantic schema> --append-system-prompt-file <persona> --tools Read --allowedTools Read --permission-mode dontAsk --model claude-opus-5-5 --effort <e>` + stripped context (`--safe-mode`, empty strict MCP config, `--setting-sources project`, `--exclude-dynamic-system-prompt-sections`, `--disable-slash-commands`). cwd = workspace (Claude reads only workspace files). Fails on non-zero exit, `is_error`, refusal/max-tokens, missing `structured_output`, or any permission denial. Every call appended to `log/runs.jsonl` (session id, cost estimate, usage, turns, Claude version).
- **Context packs** written into the workspace: `context/brief_and_knowledge.md` (brief, real source duration, effective length target, core principles + genre playbook), `context/finish_context.md` (finishing knowledge, caption families, SFX/music/b-roll libraries, what the renderer can do at this step).
- **Personas**: `reel/personas/editor_story.md`, `editor_finish.md`.
- **Validate → resume loop**: plan fails `reel validate` → `--resume <session>` with the issue list (code, path, message, fix); ≤ 2 retries; final failure writes `plan/<pass>_issues.json` and fails the stage.
- **Read-back (ADR-0016)**: after a valid story, the compiled read-back script is sent on the same session; Claude confirms or returns a corrected plan (validated again).
- **Stages**: `PIPELINE` stays perception-only (ingest → tables, used by tests and eval); `EDIT_PIPELINE = PIPELINE + [story, finish, compile, render]` is what `reel run` uses. Decision stage input hash = tables fingerprints + brief + brand + persona + context pack + schema + model + effort, so re-runs never re-spend on unchanged inputs and never skip stale plans. Session ids in `plan/sessions.json`. The Claude caller is injectable (`options["claude_call"]`) for tests.
- **Renderer (`render.py`)**: one ffmpeg graph per timeline; per base clip, input-seek the all-intra mezzanine half a frame early + `trim=end_frame`, cover-scale to 1080×1920 centred on the median face (centre if none), punch-in scale keyframes via a per-frame expression; audio sample-exact from `timebase.audio_bounds` with 5 ms edge fades; `concat`; libx264 CRF 16 yuv420p bt709 + AAC 48 kHz, `+faststart`. Writes `render/base.mp4` and `export/reel.mp4`.
- **Out of scope here (rejected loudly, not silently dropped)**: captions/overlays (step 6), music/SFX/ducking/b-roll/transitions/speed (step 7). At this step the finish context offers only what renders: cut transitions and punch-ins; libraries are empty.

## Done when
1. `reel run projects/_speech_src/talk.mp4 --project projects/_speech --brief …` produces `render/base.mp4`; frame count = `timeline.duration_f`; audio samples = `duration_f × 48000 / fps` (±1 frame of samples).
2. Sync survives cuts: a cut-up timeline from a conformance clip (flash + beep) renders with A/V offset ≤ 1 frame.
3. Length target is a warning, never an error (the demo is 13 s, the default target 15–60 s); the context states the real source duration and an effective target capped to it.
4. Tests do not call Claude by default: fake caller covers valid, invalid-then-fixed and always-invalid plans; a live test runs only with `REEL_LIVE_CLAUDE=1` and asserts zero permission denials.
5. `reel revise --project … "request"` resumes the finish session, applies a `StoryPatch` + new `FinishPlan`, validates, compiles and re-renders.
6. Tests green.

## Not in step 5
Remotion overlay and captions (step 6), audio finishing, SFX/music, transitions, speed ramps, colour (step 7), QA/Reviewer/verdict (step 9).
