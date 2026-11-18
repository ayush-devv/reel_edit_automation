# ADR-0003: Own timeline schema (pydantic v2); OpenTimelineIO for export only

- **Status:** Accepted (2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
The timeline must express multi-track video/audio, transform keyframes, speed ramps, transitions, kinetic text placed freely (sample reel: text beside the face, mixed sizes), b-roll, SFX, ducking, masks. It must be validatable, diffable, and fit Claude structured-output limits (no recursion, no numeric bounds).

## Options considered
| Criterion | A. Own pydantic schema | B. OpenTimelineIO as base | C. CapCut draft JSON | D. MLT XML |
|---|---|---|---|---|
| Keyframes / effects | Typed | Only in free-form metadata | 11 props, presets | Strings |
| Captions / kinetic text | Typed | None | Presets | Weak |
| Validation | JSON Schema + TS types generated | Versioned schema, untyped effects | None | None |
| License / risk | Ours | Apache-2.0 | Proprietary, ToS risk | LGPL |
| NLE handoff | Via export | Native | No | Kdenlive/Shotcut |

## Decision
We propose **A**, borrowing: CapCut's asset pool + clip-relative keyframes; FCPXML's time-map for speed; Creatomate/Shotstack's "scalar or `[{f,v,ease}]`" properties. Timeline placement in integer frames at one fps; source points in integer microseconds; masks as precomputed matte assets; ducking as a rule the compiler expands. Each field has exactly one owning renderer (ADR-0004). Export cuts to OTIO.

## Consequences
- **Good:** expresses everything the reference reel does; generated TS types keep Remotion in sync.
- **Bad:** we own schema evolution and migrations.
- **Revisit when:** an NLE round-trip becomes a core feature.
