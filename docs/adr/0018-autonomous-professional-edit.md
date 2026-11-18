# ADR-0018: Autonomous professional edit by default; NLE package as escape hatch

- **Status:** Accepted (owner decision, 2026-11-18: "I want it to edit professional edits for me") · Amended by ADR-0021 (acceptance = 6 held-out, ≥ 5/6; sendable/hold verdict)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Supersedes:** ADR-0012 (assistant-first)

## Context
The owner wants one command to produce a finished, professional reel — not a first cut to polish. The council's warning stands: autonomy targets taste, the hardest problem, first; quality must be measured on the gold set (ADR-0014), not assumed.

## Decision
- **Default output:** a finished, client-ready `reel.mp4` from raw footage + optional brief/brand kit, with no manual steps.
- **Claude decides** the hook (best of its 2–3 ranked options), story, finishing and captions (ADR-0016 two-pass plan).
- **Quality loop built in:** code gates (ADR-0006/0017) + narrowed Reviewer (Opus 5.5) + bounded auto-fix loop (max 3 rounds) before the reel is returned.
- **Escape hatch kept:** the NLE package (FCPXML/OTIO, ProRes 4444 alpha overlay, stems, SRT) is still exported every run, so any reel can be fixed in Premiere/Resolve if needed.
- **Chat revisions** remain (FR-3) as patch ops by item ID.
- **Exit test:** on the gold set, the owner rates the tool's reel "sendable with no edits" in a blind A/B; release target ≥ 70% on held-out gold reels (one release, no phases).

## Consequences
- **Good:** matches the owner's goal; the escape hatch keeps every job deliverable while quality climbs.
- **Bad:** ~2–3 weeks more build before the first fully hands-off client reel; early reels will sometimes need the escape hatch.
- **Revisit when:** gold-set "sendable with no edits" rate stalls → invest in perception (e.g. native-video moment notes) or craft examples rather than more rules.
