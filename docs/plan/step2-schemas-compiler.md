# Build step 2 — Schemas, compiler, `reel validate`

_Plan date: 2026-11-18 · Implements: ADR-0002 (intent plan → compiler), ADR-0003 (own timeline schema), ADR-0016 (two-pass plan, stable IDs, patch ops, quote check), ADR-0004 (one owner per field), ADR-0030 (actionable validator errors)._

## Status: implemented 2026-11-18
- Schemas: `reel/schemas/{perception,plan,timeline}.py`; `reel schema story|finish|patch|timeline|words` exports JSON Schema. Claude-facing schemas verified: no numeric bounds, `additionalProperties: false` on every object (caption tokens are key/value objects, not a dict).
- `reel validate` (exit 2 on errors): duplicate/unknown ids, clip/word ranges, quote mismatch with "did you mean index N" fixes, overlapping reuse, hook must be first, ranges (zoom 1.0–2.0, ramp 0–120 f, speed 0.25–4, transition 2–15 f, gains, ducking), speech never retimed, caption family/tokens/script/emphasis, SFX/music/b-roll ids, knowledge ids (warning).
- `reel compile` → `timeline/timeline.json`: breath pad 80 ms clamped to neighbours, floor/ceil frame mapping, contiguous base clips + voice, clip-relative punch-in keyframes, transitions at cuts, caption pages per family max words (no overlap, ≥ 350 ms), SFX peak-aligned, music + ducking rule, b-roll, plan hashes; compiler refuses unvalidated input.
- `reel dry-run`: read-back script with running times and cut rate.
- Patch ops (insert/replace/delete by id) keep untouched items identical.
- Starter libraries: `assets/caption_styles/families.yaml` (5 families from the knowledge base), empty SFX/music/b-roll indexes.
- Tests: **49 passed** (14 new). Demo: `projects/_demo` validate → dry-run → compile (75 frames, 3 caption pages).

## Goal
Everything between "Claude wrote a plan" and "the renderer gets an exact timeline", testable without perception or Claude: typed schemas, a validator whose errors Claude can act on, a deterministic compiler on the step 1 time-map, a dry-run read-back, and patch operations for revisions.

## Done when
1. JSON Schemas for the story plan, finish plan and patch export cleanly for `claude -p --json-schema` (no recursion, no numeric bounds, `additionalProperties: false`, minimal optional fields).
2. `reel validate` rejects: unknown/duplicate IDs, word ranges outside a clip, overlapping reuse of words, quote mismatch (first/last word), out-of-range parameters (zoom 1.0–2.0, gains, etc.), references to missing items/assets, speed changes over speech — each error with `code`, `path`, `message`, `fix`.
3. `reel compile` turns plan + word table into a timeline: contiguous frame-exact clips, clip-relative keyframes, captions on output frames, SFX peak-aligned, music + ducking rule; total frames = sum of clips; every field tagged with its owner.
4. `reel dry-run` prints the edit as a read-back script (per item: words, duration, running time) + cut rate.
5. Patch ops (insert/replace/delete by item ID) apply and leave untouched items byte-identical.
6. Tests green.

## Data contracts
- **Perception inputs (produced for real in step 3; fixtures now):** `WordTable` — global word index, clip, text, start/end µs on the mezzanine clock, confidence, speaker. `SegmentTable` — `seg_id`, clip, word range, times.
- **Story plan (Claude pass 1):** ranked hook options; ordered keep items `{id, clip, word_start, word_end, first_word, last_word, beat, reason}`; `hook` = id of the first item.
- **Finish plan (Claude pass 2):** punch-ins, speed (non-speech), transitions, captions (family + tokens + emphasis word indices), SFX (by id, at a cut or word), music (by id), b-roll — each with `id` and `reason`, all referencing story item IDs.
- **Patch:** `ops: [{op: insert|replace|delete, target, after, story_item | finish_item}]`.
- **Timeline (source of truth):** fps, size, duration_f, assets, `video` clips (at_f, dur_f, src_in_us, transform keyframes, speed), `audio` (voice from clips, music, SFX), `overlay` (captions, titles), transitions, ducking rules; provenance `src:{item, words}` on every clip; owner metadata per field (ffmpeg/remotion/engine).

## Compiler rules (step 2 versions)
- Kept range → source µs from word edges ± breath pad (80 ms, clamped to neighbouring words); audio-edge snapping to speech onset arrives with perception (step 3 hook in place).
- µs → mezzanine frames (in = floor, out = ceil), placed back to back on the output grid; audio bounds from cumulative frames (no drift).
- Punch-in keyframes relative to the clip start, at the frame of the anchor word.
- Captions: each kept word mapped to output frames; grouped by the family's max words; emphasis flags.
- SFX: `at_f = anchor_f − peak_offset_f` from the SFX index.
- Music: trimmed to reel length (musical editing in step 7) + ducking rule from the voice clips.

## Not in step 2
Real ASR/perception (step 3), Claude calls (step 5), rendering (steps 5–6), audio-edge snapping and musical editing (steps 3/7).
