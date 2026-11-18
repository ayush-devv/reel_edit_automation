# Build step 1 — Foundation

_Plan date: 2026-11-18 · Implements: ADR-0015 (mezzanine + time-map), ADR-0020 (`reel run`), ADR-0023 (pinned ffmpeg), ADR-0029/0030 (eval harness skeleton)._

## Status: implemented 2026-11-18 (synthetic corpus); real phone clips pending
- `reel doctor`: PASS — Homebrew `ffmpeg-full` 9.0.2 (zscale, tonemap, libplacebo, subtitles/libass, drawtext, ProRes ks + VideoToolbox), node v24.16.0, Claude Code 2.1.327.
- `reel conformance`: **7/7 PASS** — 25/60/29.97 fps, rotated, VFR, HDR-HLG 10-bit, no-audio: exact frame counts, fps kept (25 stays 25), rotation baked, bt709 tags, A/V offset ≤ 2 ms (−1.94 ms on 29.97 fps is the frame grid).
- `pytest`: **35 passed** (26 unit, 9 integration).
- `reel run`: idempotent (second run skips), resumable, locked; `reel eval`: manifest + scoreboard rows (commit, knowledge hash, tool versions).
- Fixes found by the corpus: colour tags missing on SDR clips (added `setparams` bt709); single-frame sync flash can be dropped by VFR→CFR (probe now 3 frames, onset-detected).
- Remaining for the exit test: real phone clips in `samples/conformance/` (rotated iPhone HDR, VFR low-light, 60 fps, clap/flash) → `reel conformance --real`; re-benchmark on real 4K HEVC.

## Goal
A tested engine that turns any phone clip into a clean, single-clock **mezzanine**, tracks every stage in a resumable state machine, and has an eval harness ready to score later stages. No Claude calls yet.

## Done when (exit test)
1. `reel doctor` passes: pinned ffmpeg has zscale, libplacebo, libass, drawtext, VideoToolbox; ffprobe, node and claude are found and versions logged.
2. Conformance corpus (synthetic now, real phone clips later) passes after S0:
   - CFR at the project fps; frame count = round(duration × fps) ± 0;
   - rotated source comes out upright with no rotation metadata;
   - VFR source becomes CFR with A/V offset ≤ 20 ms (flash + beep probe);
   - HDR-tagged source comes out bt709 SDR (tagged + measured);
   - 25 fps source stays 25 fps (never forced to 30).
3. `reel run <folder>` is idempotent (second run skips), resumes after a crash, refuses a concurrent run (lockfile), and writes only through temp-then-rename.
4. `reel eval` writes a scoreboard row keyed by git commit + knowledge version + tool versions; gold metric functions (hook IoU, word-keep F1, Kendall τ, cut-rate ratio, caption WER/timing) pass unit tests.
5. `pytest` green (unit + integration).

## Layout
```
engine/
  pyproject.toml            uv project, Python 3.12, entry point `reel`
  src/reel/
    cli.py                  argparse CLI: doctor | probe | run | eval | conformance
    config.py               paths, pinned ffmpeg resolution, constants
    tools.py                subprocess wrapper for ffmpeg/ffprobe (logging, errors, timeouts)
    doctor.py               environment checks
    probe.py                ffprobe → typed SourceProbe (fps, VFR, rotation, colour/HDR, audio)
    timebase.py             exact rational time-map: source µs ↔ project frame ↔ audio sample
    mezzanine.py            S0: build + run the mezzanine command per clip
    workspace.py            project layout, atomic writes, lockfile, hashing
    runner.py               stage state machine (state.json, input-hash keys, resume)
    stages/ingest.py        copy/link sources, probe, fingerprint, choose project fps
    stages/mezzanine.py     S0 stage
    evalh/metrics.py        gold metrics (pure functions)
    evalh/harness.py        manifest, scoreboard, run bookkeeping
    conformance/corpus.py   synthetic test clips (VFR, rotated, 25/60 fps, HDR-tagged, flash+beep)
    conformance/checks.py   frame count, CFR, orientation, colour tags, A/V offset
  tests/                    unit + integration (integration skips if pinned ffmpeg missing)
```

## Key designs
- **Pinned ffmpeg:** Homebrew `ffmpeg-full` (keg-only; does not replace system ffmpeg). Resolution order: `$REEL_FFMPEG` → `<brew prefix>/opt/ffmpeg-full/bin/ffmpeg`. `reel doctor` refuses to run S0 without the required filters.
- **Project fps:** dominant source fps snapped to a standard rate (23.976, 24, 25, 29.97, 30, 50, 59.94, 60); 120/240 fps sources → 60 (or 30 by flag). Never converts 25 → 30.
- **Time-map:** `fractions.Fraction` arithmetic only. Segment boundaries in output frames; audio boundaries from **cumulative** frame positions × 48000 / fps, rounded once (no per-segment drift; 29.97 fps = 1601.6 samples/frame).
- **Mezzanine:** per clip → `mezz/<clip_id>.mov`: ProRes 422 (VideoToolbox, falls back to prores_ks), yuv422p10le, CFR via `fps=` filter, autorotate baked + rotation metadata cleared, even dimensions, square pixels, bt709 tags; HDR (PQ/HLG) tonemapped with a zscale chain; audio PCM s16le 48 kHz stereo.
- **State machine:** `state.json` = per stage {status, input_hash, outputs, started/finished, error}. A stage is skipped only if its input hash matches AND its outputs exist and validate. Writes go to `*.tmp` then `os.replace`. `run.lock` holds PID; stale locks detected.
- **Eval harness skeleton:** `eval/manifest.yaml` lists tuning/holdout reels (holdout flagged, refused unless `--holdout`). Scoreboard rows: commit, knowledge hash, tool versions, per-family scores, vetoes. Families without data yet are omitted (score formula re-normalises, ADR-0030).

## Owner actions
- `! brew install ffmpeg-full` (installs the pinned build; system ffmpeg untouched).
- Later: real phone clips into `samples/conformance/` (rotated iPhone HDR, VFR low-light, 60 fps, clap/flash).

## Not in step 1
ASR, perception, Claude calls, compile, render, Remotion — steps 2–11.
