# ADR-0012: Assistant-first product mode; NLE finishing export from M1

- **Status:** Superseded by ADR-0018 (2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Supersedes:** FR-1's "without further input" autonomy target (requirements.md)

## Context
Council (docs/reviews/2026-11-18-council-review.md, issue #2): a freelancer earns on editor-minutes per delivered reel. A strong first assembly with captions/graphics in minutes, polished in an NLE in ~15 minutes, is profitable now; full autonomy delays the first paid reel by months. OTIO alone drops the Remotion overlay.

## Options considered
| Criterion | Assistant-first (NLE finish) | Fully autonomous |
|---|---|---|
| Time to first paid reel | Weeks | Months (M1–M5) |
| Taste risk | Editor is the taste gate | Must be automated |
| Build scope | Smaller; Reviewer automation deferred | Larger |

## Decision
The tool produces a **first assembly + graphics + audio** and a **finishing package** from M1:
- FCPXML (Premiere/Resolve/FCP) + OTIO for the cuts.
- Remotion overlay as **ProRes 4444 with alpha** on its own track.
- Audio stems: voice, music, SFX.
- SRT/VTT captions; edit list with reasons.
- Also a rendered preview MP4 for quick review.
Chat revisions stay (FR-3). Automatic fix loops run only for code-gate failures; taste decisions go to the editor.

## Consequences
- **Good:** faster to revenue; real client feedback early; graphics stay editable.
- **Bad:** FCPXML writer + alpha export must be built in M1.
- **Revisit when:** gold-set A/B shows the tool's cut matches or beats the owner's edits on ≥ 70% of reels → automate more.
