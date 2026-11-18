# ADR-0008: Curated local SFX library with a JSON index (no embeddings)

- **Status:** Accepted (2026-11-18). Source mix default: both self-generated and hand-picked CC0; adjustable.
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
Claude cannot fetch or create sounds. Reels reuse a small vocabulary (whoosh, pop, ding, riser, hit, swipe, click…). Freesound's API is non-commercial without a deal; Mixkit/ZapSplat ban automation; BBC is non-commercial.

## Decision
80–120 sounds in `assets/sfx/`, loudness-normalised and trimmed, with `sfx_index.json` (id, category, tags, duration_ms, **peak_ms**, loudness, use_for, license, source). Claude reads the whole index (~3k tokens) and picks by id; the compiler aligns `peak_ms` to the cut/text frame. Sources (free-first, per the user's preference): self-generated with **Stable Audio Open** (open weights; commercial use free under $1M annual revenue — re-check licence before use) and hand-picked **CC0** sounds (Freesound website CC0 filter, Kenney — licence to verify). Paid generators (ElevenLabs SFX) optional only.

## Consequences
- **Good:** legally clean, deterministic, cheap.
- **Revisit when:** library exceeds ~1,000 sounds → add CLAP (LAION-CLAP, Apache-2.0) search.
