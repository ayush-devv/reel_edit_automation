# Reel Studio — design system (dark pro studio)

Source for the Penpot file "Reel Studio — Design" (tokens → Penpot design tokens → Tailwind/CSS variables). Implements PRD `docs/product/prd-reel-studio.md`.

## Principles
1. **Footage first.** The reel is the brightest thing on screen; the interface stays dark, neutral and quiet around it.
2. **Show the why.** Every AI decision has a reason within one click.
3. **Verdict is the hero.** Sendable/Hold is the most visible status everywhere.
4. **3D explains.** 3D only where it reveals structure (pipeline, phone, layers); never on forms, lists or chat.
5. **Calm motion.** Short, purposeful transitions. Ambient 3D pauses while renders run; reduced motion gives flat equivalents.

## Colour tokens
Dark neutral surfaces (slightly blue, as in grading suites), one AI accent, semantic status colours. Every text/background pair below is measured ≥ 4.5:1 (WCAG AA) on base, raised and overlay surfaces; status colours ≥ 5.1:1.

| token | value | use |
|---|---|---|
| `bg.base` | `#0B0D12` | app background |
| `bg.raised` | `#12151C` | panels, cards |
| `bg.overlay` | `#1A1E27` | menus, popovers, inputs |
| `bg.inset` | `#07080C` | video wells, 3D stage floor |
| `line.subtle` | `#232836` | dividers, card borders |
| `line.strong` | `#343B4D` | focused borders |
| `text.primary` | `#E8EAF0` | body, headings (16.2:1 on base, 13.9:1 on overlay) |
| `text.secondary` | `#A3A9B8` | labels, metadata (8.3 / 7.1:1) |
| `text.muted` | `#858C9E` | timestamps, hints (5.8 / 5.0:1) |
| `accent.ai` | `#6A4BF0` | AI fills: primary buttons (white text 5.4:1), focus ring, AI tints — never as text on dark |
| `accent.ai.glow` | `#9D85FF` | AI text and links on dark (6.7 / 5.8:1), glows, active pipeline node |
| `accent.cyan` | `#36D6E7` | safe zones, playhead, selection |
| `status.sendable` | `#2BD47D` | Sendable badge, passed gates |
| `status.hold` | `#FFB020` | Hold badge, warnings |
| `status.fail` | `#FF4D5E` | Failed stage, blocking gate |
| `status.queued` | `#858C9E` | Queued |
| `layer.video` `layer.colour` `layer.punch` `layer.broll` `layer.captions` `layer.titles` | `#4C8DFF` `#FF7AB6` `#36D6E7` `#2BD47D` `#FFD400` `#FF8A3D` | exploded-layer planes and story-strip blocks |

## Type
Inter (UI) and JetBrains Mono (timecodes, costs). Both are OFL.

| token | size / line / weight | use |
|---|---|---|
| `display` | 32 / 40 / 700 | screen titles |
| `title` | 20 / 28 / 600 | panel titles, verdict |
| `body` | 14 / 20 / 400 | default |
| `label` | 12 / 16 / 500, +2 % tracking | badges, field labels |
| `mono` | 12 / 16 / 500 | timecodes, costs, word indices |

## Space, shape, depth
- Spacing scale in px: 4, 8, 12, 16, 24, 32, 48, 64. Panels use 24 inside, 16 between.
- Corner radii: 6 for inputs and buttons, 10 for cards, 16 for panels, 28 for the phone and PiP.
- Elevation is shown with borders and inner glow, not drop shadows. A raised card is `bg.raised` plus a 1 px `line.subtle` border. A focused element gets a 2 px `accent.ai` ring.
- Layout:
  - left navigation rail 72 px wide (icons + tooltips): Home, New edit, Studio;
  - content area on a 12-column grid, 1440 px design width, minimum 1280.

## Components
- **Button:** primary (`accent.ai`), secondary (outline), ghost, danger. Sizes 32 and 40.
- **Status badge:** Queued, Editing·stage, Sendable, Hold·n, Failed, Delivered. Each is a dot plus a label with a 12 % tint background.
- **Project card:** 9:16 thumbnail, title, client, length, badge. Hover lifts by 2 px with an `accent.ai` border.
- **Verdict card:** big Sendable/Hold, then reasons list, proof list, gates list (collapsible).
- **Decision feed item:** icon by kind (hook, line, caption, look, punch-in, SFX), one-line decision, reason in `text.secondary`, cost in `mono`.
- **Proof word chip:** timecode, word, suggestion, ✓ / ✎ actions.
- **Reviewer note:** severity bar (blocker red / major amber / minor grey), timecode link, problem, suggested fix.
- **Story strip block:** width ∝ duration, `layer.*` colour by beat, text on hover.
- **Chat bubble:** owner (right, `bg.overlay`) and Editor (left, `accent.ai` 12 % tint, with a "changed: …" summary and a Compare button).
- **Running-edits strip:** compact chips (project and stage), top of the live view.

## 3D scenes (Three.js + React Three Fiber; Penpot frames show the composition)
| scene | composition | camera / motion | performance |
|---|---|---|---|
| **Pipeline stage** (FR-3) | 13 stage nodes on a gently curved track over a dark reflective floor (`bg.inset`). They're grouped as Analyse (4), Decide (2), Build (5), Check and Deliver (2). | Slow dolly following the running node. The running node pulses in `accent.ai.glow`, done nodes glow steady, a failed node turns `status.fail`. Data "particles" flow along the track. | Instanced meshes, bloom only on the active node. Pauses while a render stage runs. |
| **Phone** (FR-4) | A 9:16 phone body (rounded, `radius 28`) with the reel as a video texture. Optional platform UI layer and a safe-zone glow layer in `accent.cyan`. | Drag to orbit ±35°, double-click to reset, idle sway ±3°. | One video texture, no post-processing. |
| **Exploded layers** (FR-5) | The current frame as 6 stacked transparent planes coloured by `layer.*`, about 120 px apart in depth, each with a label. Audio stems are thin waveform ribbons below. | Expanding animation 600 ms ease-out; orbit; a click focuses a plane and opens its reason. | Planes are textures rendered from the timeline at the playhead. |
| **Ambient** (FR-1, Studio) | Floating translucent film frames drifting in deep space. | Very slow drift. | ≤ 2 % GPU; stops while any render runs; static image under reduced motion. |

## Motion
- Durations: 120 ms (hover), 200 ms (panel), 400 ms (screen), 600 ms (3D explode).
- Easing: standard `cubic-bezier(0.2, 0, 0, 1)`.
- Reduced motion: no 3D motion, no parallax; crossfades only.
