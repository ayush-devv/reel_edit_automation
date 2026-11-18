# ADR-0025: Remotion only for motion graphics (no Claude Motion, no Capsule)

- **Status:** Superseded by ADR-0026 (2026-11-18) — Claude Motion kept as an opt-in fallback
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
Owner asked about "Capsula Motion". Two candidates:
- **Claude Motion** — Anthropic artifact type (beta, Team/Enterprise) used by social-video-agent's ADR-005: a Claude session writes a "film"; MP4 export is manual in the browser; exports are mute and opaque (no alpha), full-frame scenes only, ≥ 1 s scenes, no CLI/API export, and media/brand files must be uploaded. Not among the artifact types available in this session.
- **Capsule** (capsule.video) — enterprise video editor turning After Effects templates into branded motion templates; demo-only pricing; no public API/SDK found.

## Decision
All motion graphics, captions and kinetic typography are rendered by **Remotion** from caption families + brand kit (ADR-0004, 0011, 0017). Neither Claude Motion nor Capsule is part of the pipeline.

## Consequences
- **Good:** fully automatic, reproducible, alpha overlay, brand-checked; no media upload; no extra subscription.
- **Bad:** designed hook/end cards must be built as our own Remotion families.
- **Revisit when:** Claude Motion gains an API/CLI export with alpha and is available on the owner's plan → consider it for optional hand-designed full-frame hook/end cards only.
