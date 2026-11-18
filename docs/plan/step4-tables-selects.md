# Build step 4 — Footage tables, selects, contact sheets, audio-edge snapping

_Plan date: 2026-11-18 · Implements: ADR-0016 (selects stage, tagged script), ADR-0002 (cut edges on heard speech), ADR-0030 (context per decision call), ADR-0019/0020 (what Claude reads via Read)._

## Status: implemented 2026-11-18
- `tables` stage (after perception) writes `perception/edges.json`, `tables/{script.md, segments.json, takes.json, words.tsv, summary.md, sheets.json}` and `tables/sheets/*.png`.
- Edge snapping (`perception/edges.py`): energy vs local noise floor, ≤ 400 ms search, never crosses neighbours; synthetic tone test within 20 ms; compiler uses heard edges + 100 ms breath (`compile_timeline(..., edges=)`, wired into `reel compile/dry-run`). Demo: 15 of 35 word edges moved.
- Selects (`selects.py`): repeated lines grouped (token similarity ≥ 0.6), flags restart/stumble/unfinished/filler/low_confidence, suggested rank (complete, confident, later takes win) — Claude decides.
- Script markers: `{um}`, `word(?)`, `⚠word→Suggestion`, `word[asr:orig]`, in-segment pauses ≥ 0.3 s, between-segment gaps ≥ 0.7 s.
- Contact sheets: segment midpoints + every 2 s, labelled, 4×3, 978×1290 px.
- Summary filters OCR noise (timecodes, numbers, near-duplicates).
- Tests: **64 passed** (6 new unit tests; perception end-to-end now runs through tables).

## Goal
Everything Claude reads for the story pass, in a compact, high-signal form — and cut edges that land where speech is actually heard, not where Whisper says words start.

## Done when
1. `tables` stage (after perception) writes: `tables/script.md` (tagged script), `tables/segments.json`, `tables/takes.json`, `tables/words.tsv`, `tables/summary.md`, `tables/sheets/*.png`, `perception/edges.json`.
2. **Audio-edge snapping:** each word gets heard start/end from short-time energy vs the local noise floor (search ≤ 400 ms, never crossing neighbouring words); compiler uses heard edges + 100 ms breath when present. On a synthetic tone-in-silence test the snapped edge is within 20 ms of the true onset.
3. **Selects:** repeated lines across segments are grouped into takes (token similarity ≥ 0.6); each take carries delivery stats and flags (restart, stumble/repeated word, fillers, low confidence, unfinished sentence) and a suggested rank — Claude decides.
4. **Script:** one line per segment `[s004 0:07.2–0:10.9 · take 2/3 of T02 · 3.1 w/s]` + text with markers: `{um}` filler, `word(?)` low confidence, `⚠word→Suggestion` proof, `(… 1.2 s)` pauses.
5. **Contact sheets:** per clip, a segment sheet (one frame per segment midpoint, labelled with seg id + time) and an overview sheet (every 2 s), 4×3 tiles, ≤ 2,576 px long edge.
6. Tests green.

## Not in step 4
Claude calls (step 5), rendering (step 5–6).
