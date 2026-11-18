# reel — engine

Python engine for the Claude-driven reel editor. Build step 1 (foundation): pinned toolchain, S0 mezzanine, `reel run` state machine, eval-harness skeleton. Plan: [`docs/plan/step1-foundation.md`](../docs/plan/step1-foundation.md).

## Setup
```bash
brew install ffmpeg-full          # pinned build (keg-only; system ffmpeg untouched)
cd engine && uv sync --extra dev  # Python 3.12 env
uv run reel doctor                # must print PASS
```
On a TLS-intercepting network: `SSL_CERT_FILE=~/.mac-ca-bundle.pem UV_SYSTEM_CERTS=1 uv sync --extra dev`.

## Commands
| Command | What it does |
|---|---|
| `reel doctor` | Checks the pinned ffmpeg (zscale, tonemap, libplacebo, libass/subtitles, drawtext, ProRes, VideoToolbox), ffprobe, node, claude |
| `reel probe FILE` | fps, VFR, rotation, colour/HDR, audio of a clip |
| `reel run INPUT [--project DIR] [--fps 30] [--force STAGE]` | Runs the pipeline (step 1: ingest → mezzanine) into a resumable workspace |
| `reel conformance [--real]` | Builds the synthetic corpus (25/60/29.97 fps, rotated, VFR, HDR-HLG, no-audio — each with a flash+beep sync probe), makes mezzanines, checks them; `--real` adds `samples/conformance/*` |
| `reel schema story\|finish\|patch\|timeline\|words` | JSON Schema for `claude -p --json-schema` |
| `reel validate --project P [--story F] [--finish F]` | Semantic checks with actionable fixes (exit 2 on errors) |
| `reel dry-run --project P` | Read-back script of the story plan (running times, cut rate) |
| `reel compile --project P` | Validate + compile plans into `timeline/timeline.json` |
| `reel eval --init` / `reel eval [--set tuning]` | Creates `eval/manifest.yaml` from `samples/gold/`; runs a set and appends a row to `eval/scoreboard.jsonl` (holdout refused without `--holdout`) |

## Mezzanine contract (ADR-0015)
ProRes 422 10-bit `.mov`, CFR at the project fps (dominant source fps snapped to a standard rate — 25 stays 25), rotation baked in and cleared, square pixels, even dimensions, bt709 SDR (HDR PQ/HLG tonemapped via zscale), PCM s16le 48 kHz stereo (silence if the source has none). Checked per clip: codec, pixel format, CFR, rotation, orientation, colour tags, frame count ±1, audio format, A/V offset ≤ 20 ms.

## Workspace
`projects/<name>/` with `source/` (symlinks + manifest), `mezz/` (clips + report), `state.json`, `run.lock`, and folders for later stages. Stages skip only when their input hash matches and outputs exist and validate; writes are temp-then-rename.

## Tests
`uv run pytest -q` — unit tests always; integration tests run when the pinned ffmpeg is installed.
