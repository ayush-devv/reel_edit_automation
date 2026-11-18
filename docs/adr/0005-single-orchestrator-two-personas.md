# ADR-0005: One Claude orchestrator, two personas (Editor, Reviewer), own tool loop

- **Status:** Accepted (2026-11-18) · Amended by ADR-0016 · Runtime now Claude Code with `reel run` orchestration (ADR-0019/0020): the personas and tool ideas stand; "Messages API" and "strict tool schemas" below are historical
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
HKUDS VideoAgent's "30+ agents" are mostly audio/script tools; its graph search picks tools, not cut quality. LAVE uses one agent with plan → approve → execute. A reel pipeline is nearly fixed. Claude API options: Messages API + own tools; Agent SDK (runs on our host); Managed Agents (beta, ffmpeg sandbox, not ZDR-eligible).

## Options considered
| Criterion | A. One orchestrator, 2 personas, Messages API + ~7 tools | B. Multi-agent graph | C. Managed Agents sandbox |
|---|---|---|---|
| Fit to fixed pipeline | Good | Over-built | Good |
| Cost / tokens | Lowest | High | Session-hour fee + tokens |
| Control of caching / frames | Full | Full | Partial |
| Ops (local-first) | Simple | Complex | Remote dependency, beta |

## Decision
We propose **A**. Editor persona (strong model) writes the plan; Reviewer persona (separate context) judges renders. Tools: `get_segments`, `inspect_frames`, `search_assets`, `beat_grid`, `compile_timeline`, `render_preview`, `review_frames`. Strict tool schemas for plan output.

## Consequences
- **Good:** simple, cacheable prefix (footage tables + frames), explainable.
- **Bad:** one model's blind spots affect both roles unless Reviewer uses a different prompt/model.
- **Revisit when:** a stage needs independent parallel work (e.g. many b-roll searches) → add sub-agents for that stage only.
