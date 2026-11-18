# ADR-0022: Owned music library with musical editing

- **Status:** Accepted (owner decision, 2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Resolves:** music open point in ADR-0017 §3 / FR-9

## Context
Brand reels usually sit on a music bed; the reference reel's montage is cut to the music; the owner's gold finals likely have music (blinding). Platform music libraries don't cover exported MP4s; songs/trending audio are never baked in.

## Decision
- **Library:** `assets/music/` of tracks the owner has a licence for (royalty-free / owned / commercially licensed for client work), each with a licence record.
- **Index** `music_index.json`: id, file, licence, BPM, key, mood tags, energy curve, sections (intro/verse/drop/outro with times), **clean ending points**, loopable regions, beat grid (beat_this + librosa).
- **Claude picks** a track by id with a reason (mood, energy, brand fit) in the finish pass.
- **Compiler does the musical edit:** trim to reel length ending on a clean musical ending (or a loop + ending), align a section change or drop to the hook/payoff, snap montage and b-roll cuts to beats where speech allows, duck under voice (rule-based, ADR-0003), fade/hit at end card.
- **No-music variant** is still exported (for platform trending audio).

## Consequences
- **Good:** finished, on-brand reels; montage rhythm like the reference.
- **Bad:** the owner must build and licence the library; beat/section analysis adds perception work.
