# ADR-0011: Adaptive caption & typography style engine

- **Status:** Accepted (2026-11-18) · Amended by ADR-0017
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
User requirement: captions must follow the video's nature, mood and colour tone — not one fixed template. The reference reel (`analysis/bathroom/notes.md`) uses kinetic typography beside the face, mixed sizes, one enlarged key word, colours matched to a warm-orange / teal grade. Competitors use opaque presets (Submagic "kelly/karl/ella"). Claude must choose a style, but rendering must stay deterministic and on-brand.

## Options considered
| Criterion | A. Fixed presets only | B. Claude writes free CSS | C. Style tokens: measured palette + Claude picks preset family and parameters |
|---|---|---|---|
| Adapts to footage | No | Yes | Yes |
| Deterministic / validatable | Yes | No (anything goes) | Yes (bounded tokens) |
| Quality floor | Template-level | Unpredictable | Preset quality + adaptation |
| Explainable | Weak | Weak | Each token has a reason |

## Decision
**C.**
1. **Perception measures the look:** dominant and accent colours per scene (k-means on downscaled frames), average luminance under the caption zone, skin-tone region from face boxes, contrast, saturation, warm/cool bias. Output `palette.json`.
2. **A small library of caption style families** (Remotion components), e.g. `kinetic_side` (beside face, mixed sizes), `word_pop` (bottom, active-word highlight), `minimal_lower`, `bold_box`, `editorial_serif`. Each exposes typed tokens: font pairing, base/emphasis colour, highlight style, position zone, max words, animation curve, case.
3. **Claude (Editor) picks** the family and tokens from content type + mood (from transcript and frames) + `palette.json` + brief/brand, with a reason per choice. Emphasis words chosen from the transcript.
4. **Code enforces quality:** WCAG-style contrast ≥ 4.5:1 against the measured background under the text, never over the face box, ≤ 20 chars/s, glyph coverage for Devanagari/Latin, and a max of one enlarged word per line. Platform safe zone (default x 120–888, y 288–1248 on 1080x1920) is a **configurable warning**, not a hard fail.
6. Craft source: [`docs/research/craft-playbook.md`](../research/craft-playbook.md) (caption rules 15–18).
5. A reference reel can seed the tokens (style vector from FR-7).

## Consequences
- **Good:** adapts per video while staying deterministic and checkable; extensible by adding families.
- **Bad:** the families must be designed and built well — this is where most of the "pro look" effort goes.
- **Revisit when:** clients ask for brand kits → add a brand-token layer that overrides palette-derived tokens.
