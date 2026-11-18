# ADR-0024: Build our own core; reuse social-video-agent's proven modules

- **Status:** Accepted (2026-11-18; owner asked for the option giving the best final result)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Supersedes:** ADR-0013 (2-day fork-vs-build spike)

## Context
A code-level review of `reference/social-video-agent` (SVA, Apache-2.0, ~48k lines, ~1,146 tests) — not only its README — found:
- **High floor:** RMS speech-edge snapping and seam joining (`editorial/acoustic.py`, `compile.py:join_seams`), measured voice repair and level matching (`edl/voice.py`, `levels.py`), frame-exact allocator and audio chain (ADR-002 in SVA), face/speaker reframing with smoothing (`reframe/`), broad QA (`qa/checks.py`, `opening.py`, `av_sync.py`), FCPXML/OTIO/CMX export (`export/timeline.py`), measured caption fitting (`captions/fit.py`).
- **Deliberate ceilings (design rules, not missing code):** no colour correction ("never correct a cast"), voice cleanup is repair-only ("never enhancement"), one music file with a fade, one caption style per brand and three style packs, kinetic word centred at the top only, advisory QA (no blocking verdict), cuts-only NLE export, constant speed only.
- **Structural mismatch with our needs:** no stable item IDs (index-based fixes lost on recompile), no quote check, no speed ramps, no mezzanine (tonemap silently skipped without libzimg), Polish/English heuristics throughout, no Hindi/Hinglish.

## Options considered
| Criterion | A. Fork SVA | B. Build from scratch | C. Build core + reuse SVA modules |
|---|---|---|---|
| Final-output ceiling | Lower — its invariants cap colour, voice, music, typography, verdict | Highest | Highest |
| Quality floor in the same build time | High | Lowest | High |
| Hinglish | Pass over every heuristic | Native | Native |
| IDs/patches, ramps, mezzanine, verdict | Core rewrite under its parity tests | Native | Native |
| Effort | Grows with each fight against its design | Largest | Medium |

## Decision
**C.** Our own core: mezzanine + time-map, `reel run` orchestration, plan/timeline schemas with stable IDs, patch ops and quote check, selects, two-pass plan, speed ramps, colour pipeline, voice chain, music library + musical editing, caption families + kinetic typography, SFX peak alignment, sendable/hold verdict, Hinglish.
**Reuse from SVA** (Apache-2.0; keep its LICENSE/NOTICE and upstream MIT attributions; adapt, don't track upstream):
- `editorial/acoustic.py`, `editorial/boundaries.py`, `compile.py:join_seams` — cut-edge snapping.
- `edl/voice.py` (measurement), `edl/levels.py`, `edl/loudness.py`.
- ADR-002 frame allocator / audio chain ideas (`allocate_range_frames`, `_audio_chain`).
- `reframe/smooth.py`, `reframe/speaker.py`, `reframe/detect.py` (YuNet).
- `qa/checks.py`, `qa/opening.py`, `qa/av_sync.py`.
- `export/timeline.py` (extend beyond cuts-only).
- `captions/fit.py` after a Devanagari/shaping check.
- Remotion component patterns from `remotion/*.tsx`.

**Baseline instead of spike:** run SVA (FFmpeg route if the Remotion declaration is pending) on 2 tuning gold reels and score them with the gold harness — the floor our build must beat.

## Consequences
- **Good:** highest achievable ceiling with proven fundamentals; no fight against another project's design rules.
- **Bad:** more to build than a fork; reused modules must be adapted to our schemas and tests.
- **Revisit when:** the SVA baseline scores near the "sendable with no edits" bar on the gold set → its ceiling is not the bottleneck and a fork becomes the faster route.

## Challenges raised
- Council re-review (devil's advocate) recommended forking, judging from README + grep; this ADR rests on a code-level read showing the limits are invariants. Kept the revisit trigger above as the guard.
