# Build step 8 — Hinglish engine, captions in the right script, proof list (CP4)

_Plan date: 2026-11-18 · Implements: ADR-0007 (free local ASR, Hinglish engine by bake-off), ADR-0021 (uncertain caption words → proof list / hold). Owner decision: build the harness now, run the real bake-off when clips arrive._

## Status: harness implemented 2026-11-18 — real bake-off pending owner clips
- All 5 engines run end to end through `reel bakeoff` (adapters in `hinglish_engines.py`, optional extra `bakeoff`).
- **Synthetic smoke** (2 clips of macOS Lekha TTS Hinglish; `analysis/bakeoff/2026-11-18-synthetic-smoke.md`), real-time factor after warm-up:
  | engine | WER | CER | RTF | script |
  |---|---|---|---|---|
  | oriserve-apex | 5.6 % | 1.5 % | 4.6 (transformers/MPS) | Roman |
  | shruti | 8.0 % | 3.7 % | **0.08** | Devanagari + Latin English |
  | whisper-turbo | 16.7 % | 7.2 % | 1.7 | Devanagari |
  | indicconformer | 29.7 % | 10.4 % | 0.9 | Devanagari (glued words) |
  | whisper-large-v3 | 27.2 % | 17.1 % | 3.4 | Devanagari |
  **Not a decision:** clean TTS, no fillers, no timing reference. English loanwords written in Devanagari ("सिंपल") count as errors because the keys are Roman — correct for Latin-script captions, harsh for Devanagari captions.
- Apex word times (borrowed turbo alignment heads) track Whisper turbo within ~20–40 ms on the same words; Shruti runs ~80 ms late. Real sync needs `words.tsv` references.
- Follow-ups if Apex wins: convert to MLX ourselves for speed; add per-word confidence (the pipeline returns none, so the proof list would miss low-confidence words).
- Also done: romaniser with medial schwa deletion + common-word exceptions; caption romanisation for `caption_script=latin`; `qa/proof_list.json` (kept unsure words with output timecodes); phrase-level caption fallback when > 15 % of kept words have bad timing; perception picks the engine per language from `config.ASR_ENGINES`.
- Tests: **112 passed, 1 skipped**.

## Candidates (facts checked 2026-11-18)
| engine (`reel bakeoff` name) | model | licence | output script | word times | notes |
|---|---|---|---|---|---|
| `whisper-turbo` | mlx-community/whisper-large-v3-turbo | MIT | Devanagari (hi) | native | current English engine |
| `whisper-large-v3` | mlx-community/whisper-large-v3-mlx | MIT | Devanagari; English words often Devanagari | native | third-party table: ~80 WER on MUCS, hallucinates on silence |
| `shruti` | udgamlabs/Shruti (Cactus engine, 55M) | Apache-2.0 | Devanagari Hindi + Latin English | native (`word_timestamps=True`) | self-reported 35 WER on MUCS — **trained on MUCS** |
| `oriserve-apex` | Oriserve/Whisper-Hindi2Hinglish-Apex (transformers) | Apache-2.0 | **Roman Hinglish** | via the turbo base's alignment heads (not shipped; fit unverified) | if it wins: convert to MLX ourselves (third-party MLX port has no licence) |
| `indicconformer` | OpenVoiceOS/ai4bharat-indicconformer-hi-onnx (onnx-asr) | MIT | Devanagari only | CTC token times → words | ~64 WER on MUCS (third-party) |
IndicWhisper (Vistaar, MIT, 4.3 GB zip outside HF) is not wired; add only if all of the above disappoint.

## Design
- **`reel bakeoff`** (`bakeoff.py`): dataset `samples/hinglish/<name>/{clip, transcript.txt[, words.tsv]}`; every engine on every clip; scores on script-agnostic keys → WER, CER, filler retention, word-onset error vs `words.tsv`, timing sanity, real-time factor; composite (accuracy .6, fillers .2, sync .2, scaled down by impossible timings). Writes `analysis/bakeoff/<run>/results.md` + hypotheses per engine.
- **`script.py`**: rule-based casual romaniser (schwa deletion incl. medial, nukta, conjuncts, nasals) + common-word exceptions; loose spelling key. Research found no off-the-shelf transliterator that produces casual Hinglish (IndicXlit fails on Python 3.12; uroman/aksharamukha/ITRANS give scholarly spellings).
- **Perception** picks the ASR engine per language from `config.ASR_ENGINES` (`hi`/`hinglish` → bake-off winner; Whisper large-v3 until then).
- **Captions:** brief `caption_script=latin` → Devanagari words romanised; `devanagari`/`mixed` → as transcribed. Roman→Devanagari is not offered (no reliable offline transliterator).
- **Proof list:** `qa/proof_list.json` = kept caption words with low confidence / unconfirmed names / suspect timing, with output timecodes (same frame mapping as the compiler). Feeds the `hold` verdict in step 9.
- **Phrase fallback:** if > 15 % of kept words have suspect or zero-length timing, captions switch to page-level timing (no per-word highlight).

## Done when
1. `reel bakeoff` runs every engine end to end on synthetic Hinglish (smoke) and writes the report.
2. Unit tests for the romaniser/keys, scoring, token merge, proof list, phrase fallback.
3. **Owner clips → real bake-off → winner set in `config.ASR_ENGINES` (pending clips).**

## Owner action
Put 3–5 real Hinglish reels in `samples/hinglish/<name>/` with `transcript.txt` (exactly what is said, fillers included, any script). Optional `words.tsv` (word, start s, end s) for 1–2 clips lets the bake-off score caption sync. Then: `engine/.venv/bin/python -m reel.cli bakeoff`.
