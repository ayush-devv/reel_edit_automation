# Experiment 2 — Speech-to-text (part 1: English, free local model)

Date: 2026-11-18. Audio: `samples/bathroom.mp4` (English speech over a music bed, 73.7 s), 16 kHz mono.
Engine: `mlx-whisper` + `mlx-community/whisper-large-v3-turbo` (MIT), word timestamps on, Apple M5.

## Speed
- First run 150.8 s (includes ~1.6 GB model download).
- Warm run **4.6 s for 73.7 s of audio (~16x real time)**.

## Accuracy (97 words)
Transcript is correct except proper nouns:

| Heard as | Actually (from on-screen text) | Word confidence |
|---|---|---|
| "them" (6.72 s) | "Wortham" | 0.415 |
| "Madhsa" (12.74 s) | "Mansa" | 0.396 |
| "Diorma" (14.4 s) | "DearMa" | 0.423 |

Every real error had probability < 0.5; only 4 correct words also fell under 0.5.

## Timing
- "don't" spans 3.78–5.08 s (1.3 s) — a pause folded into the word. Matches the known Whisper failure; the compiler must re-snap edges to speech onset (VAD/RMS) and flag words > 1.2 s.

## Design consequences
1. **Custom vocabulary from the brief + on-screen OCR:** names, brands and product terms fed to ASR as a prompt/hotwords, and used to auto-correct low-confidence words. The correct spellings were visible on screen in this reel.
2. **Low-confidence words (p < 0.5) → "check" list** for Claude/user before captions are burned in.
3. **Suspect-word rule:** any word > 1.2 s, or with silence inside it, gets re-aligned.
4. Free local Whisper turbo is good enough for **English**; Hinglish still untested (needs clips).

## Pending (part 2)
Hinglish/Hindi clips in `samples/` → compare Whisper large-v3, Shruti, Oriserve Hindi2Hinglish, IndicWhisper (and Scribe as the paid ceiling if a key is provided).
