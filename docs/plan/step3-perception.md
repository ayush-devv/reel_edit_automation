# Build step 3 — Perception

_Plan date: 2026-11-18 · Implements: ADR-0007 (free local ASR stack), ADR-0016 inputs, ADR-0011/0017 (palette, brand), ADR-0021 (vocabulary for caption proof), ADR-0027 (genre/brief context)._

## Status: implemented 2026-11-18 (English, synthetic speech); real footage + Hinglish pending
- `perception` stage in `reel run` writes words, segments, vad, scenes, faces, energy, prosody, palette, ocr; ~10 s for a 12 s clip on the M5 (OCR 3.8 s, ASR 3.4 s, VAD 0.9 s, faces 0.8 s).
- English ASR on macOS `say` speech: WER ≤ 10% (integration test); "Um" flagged as filler; low-confidence words flagged.
- **Found and fixed:** a misheard brand ("DearMa" → "Dioma") had *high* ASR confidence, so low-confidence flags missed it. Added vocabulary checking (`apply_vocabulary`): near-misses (≥ 0.85 similarity) auto-corrected with the original kept; name-like words not confirmed by the vocabulary go to the proof list with the closest suggestion (here "DearMa"). Names in the brief are confirmed.
- VAD uncovered-speech spans are labelled `filler_candidates` (Whisper ends words early, so breaths also appear) — refined by audio-edge snapping in step 4.
- Brief + brand loaders (`briefs/`, `brands/` JSON) feed the vocabulary; `reel run --brief/--brand/--language/--skip-visual/--asr-repo`.
- Perception extra (`uv sync --extra perception`): mlx-whisper, silero-vad, mediapipe (BlazeFace model cached in ~/.cache/reel/models), PySceneDetect, RapidOCR, onnxruntime, soundfile — MIT/Apache/BSD.
- Tests: **58 passed** (8 perception unit, 1 perception end-to-end).
- **Not yet verified:** face detection on real faces (synthetic clips have none), Hinglish/Hindi (bake-off in step 8), Devanagari OCR, OCR accuracy on real overlays.

## Goal
Turn each mezzanine into the facts Claude and the compiler need — words with timing and confidence, fillers, phrases, scenes, faces, energy, delivery stats, colour palette, on-screen text — plus loaders for the client brief and brand kit. One `perception` stage in `reel run`, all outputs under `perception/`.

## Done when
1. `reel run` produces `perception/{words,segments,vad,scenes,faces,energy,prosody,palette,ocr}.json` for every clip, idempotently.
2. On synthetic speech (macOS `say`), English ASR recovers the text (WER ≤ 10%), word times are monotonic and inside the clip, and low-confidence / suspect words are flagged.
3. Fillers: VAD speech with no transcribed word ≥ 150 ms becomes a cuttable filler span; lexical fillers (um/uh/hmm; Hindi "matlab/toh/na/yaar" marked *candidate*, judged by Claude).
4. Segments split on pauses ≥ 0.5 s, sentence punctuation, speaker change, or > 28 words.
5. Faces: per-sample boxes + per-segment summary (present, median box); no faces → empty, not an error.
6. Brief and brand loaders validate their JSON and feed the ASR vocabulary prompt.
7. Tests green; perception extras optional (`uv sync --extra perception`).

## Components (engine/src/reel/perception/)
| Module | Tool (licence) | Output |
|---|---|---|
| `audio.py` | ffmpeg | 16 kHz mono PCM per clip (cache) |
| `asr.py` | mlx-whisper large-v3-turbo (MIT); backend interface for the Hinglish bake-off winner | words.json: global index, clip, text, start/end µs (mezzanine clock), prob, `suspect` (> 1.2 s), `low_conf` (< 0.5) |
| `vad.py` | Silero VAD 6 (MIT, ONNX) | vad.json speech regions; filler spans |
| `segments.py` | — | segments.json (phrases, `seg_id`) |
| `scenes.py` | PySceneDetect AdaptiveDetector (BSD-3) | scenes.json cut times |
| `faces.py` | MediaPipe FaceDetector BlazeFace short-range (Apache-2.0; model cached in ~/.cache/reel) | faces.json samples @ 4 fps + per-segment summary |
| `energy.py` | numpy + ffmpeg | energy.json: audio RMS per 100 ms, motion (frame-difference) per sample |
| `prosody.py` | numpy | prosody.json per segment: words/s, pause ratio, loudness dB, mean confidence |
| `palette.py` | numpy k-means | palette.json per scene: 5 colours, luminance in caption zone, warm/cool |
| `ocr.py` | RapidOCR ONNX (Apache-2.0) | ocr.json on-screen text @ 1 fps (Latin; Devanagari later) |
| `brief.py`, `brand.py` | pydantic | `briefs/<project>.json`, `brands/<client>.json` |

## Not in step 3
Contact sheets + footage tables + selects (step 4), audio-edge snapping into the compiler (step 4/5), Hinglish engine choice (step 8 bake-off), Devanagari OCR.
