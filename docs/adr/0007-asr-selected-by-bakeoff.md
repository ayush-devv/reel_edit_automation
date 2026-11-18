# ADR-0007: Free, local speech-to-text stack; Hinglish engine picked by bake-off

- **Status:** Accepted (2026-11-18). Approach accepted; the Hinglish engine slot is filled after the bake-off.
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
FR-4: English, Hindi, Hinglish with word-level timing for cuts and word-by-word captions. User requires **free, open-source** tools (no paid ElevenLabs). Findings:
- `mlx-whisper` + whisper-large-v3-turbo (MIT): English tested on the sample — 4.6 s for 73.7 s audio; only proper nouns wrong, all with confidence < 0.5; one word stretched over a pause (1.3 s).
- Hinglish candidates: Whisper large-v3 (Apache/MIT), **Shruti** (Apache-2.0, 55M, Oct 2026, self-reported 35% Hinglish WER), **Oriserve Whisper-Hindi2Hinglish** (Apache-2.0, romanized output), AI4Bharat IndicWhisper / IndicConformer (MIT).
- VoiceStudio (AGPL-3.0) and OpenWhispr (MIT) are apps that wrap the same engines; not used. Parakeet has no Hindi.
- Avoid: WhisperX Hindi aligner (no licence), whisper-timestamped (AGPL), CrisperWhisper weights (non-commercial), Meta MMS (non-commercial).

## Decision
One `transcribe()` interface returning the canonical word table (`word, start_us, end_us, prob, lang, script`). Behind it:
1. **Engine:** mlx-whisper large-v3-turbo for English. Hinglish/Hindi engine = winner of the bake-off (Whisper large-v3 vs Shruti vs Oriserve vs IndicWhisper) on 3–5 real clips, scored on WER, filler retention and caption-sync error.
2. **Vocabulary prompt:** names/brands from the client brief + on-screen OCR passed to the engine; low-confidence words (p < 0.5) auto-corrected against that vocabulary or flagged.
3. **Timing repair:** words > 1.2 s or with silence inside are re-aligned; cut edges snapped to speech onset with **Silero VAD** (MIT) in the compiler. stable-ts considered for steadier timestamps (licence to verify).
4. **Fillers:** voiced-but-untranscribed gaps from VAD become cuttable `filler` spans; lexical Hindi fillers ("matlab", "toh", "na") judged by Claude in context.
5. **Script:** IndicXlit (MIT) romanizes Devanagari per word, timing preserved; caption script is a per-project setting.

## Consequences
- **Good:** zero cost, fully local, client audio never leaves the Mac.
- **Bad:** Hinglish accuracy unproven; more engineering than one paid API.
- **Revisit when:** the best free engine's caption-sync or WER is unacceptable on real client footage → evaluate paid APIs as an optional plug-in behind the same interface.
