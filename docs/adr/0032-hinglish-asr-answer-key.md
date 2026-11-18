# ADR-0032: Hinglish ASR answer key — MUCS 2021 now, creator human subtitles later

- **Status:** Accepted (owner decision, 2026-11-19)
- **Date:** 2026-11-19
- **Deciders:** project owner
- **Amends:** ADR-0007 (Hinglish engine by bake-off on owner clips)

## Context
The Hinglish speech-engine bake-off (`reel bakeoff`, build step 8) needs a correct transcript (an answer key) for each test clip. ADR-0007 assumed the owner's own clips with transcripts. The owner chose not to transcribe by hand, and no Hinglish gold pairs could be collected from the web (ADR-0031). Candidates are Whisper turbo, Whisper large-v3, Shruti, Oriserve Apex and IndicConformer. Shruti and IndicConformer were trained on MUCS 2021 data.

## Decision
1. **Now:** score the bake-off on the **MUCS 2021 Hindi-English code-switched test set** (OpenSLR SLR104, CC BY-SA 4.0). It has human-written transcripts (Hindi in Devanagari, English in Latin) and is used for internal evaluation only.
   - Clips are imported into `samples/hinglish/<id>/` (`clip`, `transcript.txt`) by a script that samples about 40 utterances of 5–20 s.
   - **In-domain discount:** Shruti and IndicConformer trained on MUCS, so either one must beat the best of the other engines by at least 5 WER points to win on MUCS alone.
2. **Later, automatically:** when YouTube's caption endpoint stops throttling, `tools/goldset` collects 3–5 Hinglish talking-head videos whose creators uploaded **human subtitles**, not automatic ones (yt-dlp separates `subtitles` from `automatic_captions`). The bake-off re-runs on them. **This result overrides MUCS if the two disagree**, because it is reel-style speech.
3. **Caption timing** is not taken from the answer key. It is measured by the gold-reel scoring (caption onset error, ADR-0030) and by the Hinglish holdout reels (ADR-0031).
4. **Engine consensus** (several engines agreeing) is never used as an answer key. It is allowed only as a tie-breaker between engines within 1 WER point of each other.

## Options considered
| Option | Ground truth? | Owner effort | Fit to reels |
|---|---|---|---|
| **MUCS now + human subtitles later (chosen)** | yes | none | lectures now, reels later |
| Owner corrects drafts | yes | ~10 min | exact (owner clips) — declined by owner |
| Hired transcriber | yes | money + wait | exact |
| Engine consensus | no | none | — |

## Consequences
- **Good:** an engine can be chosen today with no owner work; a real-speech check follows automatically.
- **Bad:**
  - MUCS is lecture audio (NPTEL), cleaner and slower than reels, so results may not carry over;
  - two candidates have a home advantage (handled by the 5-point discount);
  - the human-subtitle step depends on YouTube unblocking and on finding human Hinglish subtitles, which are rare.
- **Revisit when:** the human-subtitle re-score disagrees with MUCS, or a reel-domain Hinglish test set with human transcripts appears.
