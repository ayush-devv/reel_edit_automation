# Reel Studio — design audit and visual directions (2026-11-19)

**Scope:** the Penpot file "Reel Studio", 9 pages (design system plus 8 screens: Live edit, Review, Layers, Home, New edit, Revise, Adjust, Deliver).
**Method:** inspected through the Penpot MCP (structure, library and usage statistics), with every screen exported and reviewed.
**Unavailable references:** the "UI UX Pro Max", "Anthropic Frontend Design" and "Web Interface Guidelines" skills are not installed in this session. The analysis below rests on professional design practice and the product docs (`prd-reel-studio.md`, `design-system.md`).

## Phase 1 — Audit

### What the file contains (measured)
| Fact | Value |
|---|---|
| Library | 22 colours, 5 typographies, 34 tokens, **0 components** |
| Text layers | 524, using **10 font sizes** (11, 12, 13, 14, 15, 16, 18, 20, 30, 32) and **6 weights** (400–900), against 5 defined type styles |
| Corner radii in use | **15 distinct values** (2, 3, 4, 6, 7, 8, 10, 12, 14, 16, 28, 30, 40, 60, 400), against a 4-step scale |
| Stroked shapes | 173 of ~970 |
| Gradients | 11 (all decorative: placeholder thumbnails, glows) |
| Off-palette fills | white (35, mostly button text), plus 4 one-off colours in the phone mock |

### Strong decisions to keep
- **Dark, neutral surfaces around the footage.** This is right for video work: the reel is the brightest thing on screen.
- **JetBrains Mono for timecodes, costs and ids.** It is functional and already consistent.
- **Semantic status colours** (sendable, hold, fail, queued), plus a fixed colour per timeline layer.
- **Verdict-first Review**, and an Editor decision feed in which every decision carries its reason and cost. This "show the why" principle is the product's core idea.
- **3D only where it explains structure** (pipeline, phone, layers).
- **Inline validator errors** instead of disabled controls.

### Problems
| # | Problem | Why it matters | Severity | Correction |
|---|---|---|---|---|
| 1 | **No reusable components.** Every button, badge, card and tab is drawn by hand on each screen. | Nothing keeps the screens consistent; any change means editing everything; there is no handoff value for code. | **Critical** | Build a component library with variants: button, badge, tab, input, select, toggle, list row, panel, toast. |
| 2 | **Boxes inside boxes.** Panels (radius 16, border) hold items (radius 10, fill) that hold chips (radius 6–12, border). | Card soup is the most recognisable "AI dashboard" pattern. Three nested containers add visual noise and blur grouping. | High | Use one container level. Group with space and 1 px hairline dividers; list rows without card chrome. |
| 3 | **Radius sprawl:** 15 values. | Shape language feels improvised. | High | Use a 3-step scale: 4 for controls, 8 for surfaces, full for pills and avatars only. |
| 4 | **The violet accent is everywhere:** primary buttons, active nav and tabs, links, decision icons, chat, versions, progress, pipeline. | "AI" stops meaning anything. It competes with the status colours, which carry the real information. | High | Make the accent **mean one thing** (AI activity and the primary action) and use it sparingly. Navigation and selection use neutral contrast. |
| 5 | **11 saturated hues** on Live and Layers (accent, cyan, 4 statuses, 6 layer colours). | Reads as a carnival, and the status colours lose their urgency. | High | Desaturate the layer colours into a calmer family; reserve full saturation for status. |
| 6 | **Type scale drift:** 10 sizes and 6 weights; tracked all-caps 11 px labels used 65 times. | Hierarchy feels accidental. Tiny tracked caps are a generic dashboard trope and hard to read. | High | Use 6 sizes, 3 weights and sentence-case labels. Use caps only for tiny metadata, and sparingly. |
| 7 | **Generic identity.** It is a dark SaaS template with a violet accent, glows and gradient placeholders. | It doesn't look like an editor's tool and isn't distinctive. | High | Take the identity from the domain: editing suites, timecode and the timeline, with type-driven hierarchy. |
| 8 | **Decorative gradients and glows** (11). | Decoration without information; the "AI glow" cliché. | Medium | Remove them. Show emphasis through type, space and status colour. |
| 9 | **Icon language:** Unicode glyphs and emoji (♡ 💬 ↗ ✓ ✎ ↓ ▶ ♪ ◼) plus letter-in-a-box nav (H, N, S). | Inconsistent and amateur; nav letters are not icons, and icon-only actions have no accessible names. | High | Use one line-icon set (a Lucide-style 1.5 px stroke, 20 px grid). Pair nav icons with labels, and give every icon-only button a tooltip and accessible name. |
| 10 | **The Review screen has four equal-weight panels.** | The one action the owner must take (confirm 1 word) is buried mid-screen. | Medium | Make the verdict plus its single next action the hero; Reviewer notes and checks come second. |
| 11 | **Duplicated wayfinding.** The project name sits in the top bar, the tabs repeat on every project screen, and the rail uses letters. | Spends attention without adding orientation. | Medium | Use a project header with a breadcrumb (Projects › Sugar in your juice) and tabs once; the rail gets icons and labels. |
| 12 | **No interaction states.** Hover, focus, disabled, loading, empty and error states are not designed (only one validator error exists). | Not production-ready; engineers will guess. | High | Design a state row for every component, plus empty, loading and error screens. |
| 13 | **Inconsistent spacing:** panel padding mixes 16, 20 and 24; gaps mix 12, 16 and 24. | Uneven rhythm. | Medium | Use an 8-point scale: 24 panel padding, 16 within groups, 32 between sections. |
| 14 | **Many 11 px labels** (65 of them). | Strain at reading distance; borderline for low vision. | Medium | Set the minimum to 12 px and body to 14 px. |
| 15 | Penpot's preview exporter renders a serif fallback (Google Fonts are offline in its container). | Affects previews only; the canvas uses Inter. | Low | Optional: upload Inter and JetBrains Mono as local fonts in Penpot. |

## Phase 2 — Research and directions

**Product.**
- **What it does:** a local AI editor that turns raw talking-head and podcast footage into client-ready vertical reels.
- **Who uses it:** one owner, an engineer freelancing as an editor and not a trained editor, who works every day for long sessions.
- **What it must convey:** trust ("I can send this to a paying client"), control (see why, change anything), and calm speed.
- **Primary workflow:** start an edit → watch it run → read the verdict → fix → deliver.
- **Most important screens, in order:** Review, Live, Home.
- **Domain references:**
  - Craft tools (DaVinci Resolve, Final Cut, Frame.io): neutral greys, timecode as a first-class element, docked panels, colour only for meaning.
  - Editorial review culture: notes against a timecode, versions, a sign-off.

### Direction A — "Cutting Room": pro editing suite
- **Philosophy:** the tool an editor would trust. Domain-native, dense, quiet.
- **Personality:** precise and serious, like a craft instrument.
- **Colour:**
  - neutral graphite greys (no blue tint) in four steps;
  - one warm signal accent (amber `#E8A33D`) for the primary action and the playhead;
  - status colours at full strength;
  - layer colours desaturated.
- **Type:** Inter (UI) and JetBrains Mono, with timecode in large mono as a hero element; tight sizes (12, 13, 14, 16, 20, 28).
- **Layout:** docked panels split by 1 px hairlines, no cards. A persistent timeline/story strip spans the bottom of every project screen, like an NLE.
- **Components:** square-ish (radius 4); flat; hairline separators; segmented controls; dense list rows.
- **Strengths:** credible to clients and editors; footage is clearly the hero; information-dense.
- **Weaknesses:** can feel intimidating to a non-editor; less "wow".
- **Fit:** high for daily use and trust; medium for delight.

### Direction B — "Edit Notes": editorial paper
- **Philosophy:** the experience of getting notes back from a senior editor.
- **Personality:** literate, calm, distinctive.
- **Colour:**
  - warm paper (`#F3F0E8`) with ink black;
  - one red-ink accent for problems;
  - green for "approved";
  - footage sits in dark mats.
- **Type:** a serif display (Newsreader or Fraunces) with a grotesk body (Inter) and mono timecodes; the verdict is a typographic "stamp".
- **Layout:** a document-like column; reels as contact sheets; notes read like margin annotations.
- **Components:** underlined text links; ruled lists; minimal chrome.
- **Strengths:** very distinctive and unlike any AI dashboard; excellent for review and reading.
- **Weaknesses:**
  - a light surround fights "footage first" (it lowers perceived video contrast), and is tiring in long sessions;
  - it departs from your "dark pro studio" choice.
- **Fit:** high for the Review and notes moment; low for Live, Layers and long editing sessions.

### Direction C — "Control Room": broadcast operations
- **Philosophy:** a calm broadcast control room. Everything is monitored, nothing is decorated.
- **Personality:** confident and technical, with "instrument panel" clarity.
- **Colour:**
  - near-black canvas;
  - colour reserved for **signals**: one AI activity colour, used only when the AI is acting (running node, Editor typing), plus status colours;
  - everything else in greys.
- **Type:** big numeric and timecode readouts (JetBrains Mono or Space Grotesk numerals) with Inter UI; hierarchy carried by size and weight, not by boxes.
- **Layout:** a 12-column grid; zones separated by space and hairlines; "readouts" instead of cards; 3D treated as monitors.
- **Components:** flat; outlined only on focus; status as LED dots and readouts.
- **Strengths:** distinctive; keeps your dark studio and 3D hero moments; strong hierarchy.
- **Weaknesses:** can drift into sci-fi pastiche if overdone; needs discipline.
- **Fit:** high for Live and Layers; good for Review.

### Recommendation
**A, "Cutting Room", taking C's signal discipline.**
- It fixes the critical problems (card soup, accent overuse, generic identity) and is native to the domain.
- It keeps your "dark pro studio" choice and the 3D moments, presented as monitors.
- It gives the strongest client-facing credibility.
- From C it takes the rule that colour = signal.
- B is the most original, but it conflicts with footage-first and long dark-room sessions.

**Owner's decision:** A, "Cutting Room", with C's rule that colour means a signal.

---

# Final report — Cutting Room redesign (Phases 3–6)

The redesign lives in the same Penpot file. The old screens were kept for comparison on pages prefixed `v1 ·`. The new pages are:

| Page | Contents |
|---|---|
| `1 · Foundations` | Colour, type, spacing, radius, elevation |
| `2 · Components` | Components with variants and states |
| `3 · Review` – `10 · Deliver` | The 8 project and home screens, each 1440 × 900 |
| `11 · States` | Home empty, Review loading, Live failed |
| `12 · Library`, `13 · Quality`, `14 · Settings` | Studio screens |

Every change below was checked by exporting the board and looking at the result. When an export didn't match what the API reported, the change was redone and exported again.

## 1. Initial audit summary
See Phase 1 above. The worst problems were:
- no components;
- boxes inside boxes ("card soup");
- 15 radius values, 10 font sizes and 6 weights;
- violet used for everything;
- 11 saturated hues;
- emoji and letter icons;
- decorative gradients;
- no interaction states.

## 2. Major weaknesses identified
1. Nothing is reusable (Critical).
2. The identity reads as a generic AI dashboard, not an editor's tool.
3. Colour has no meaning: the accent marks navigation, links, AI and the primary action alike.
4. Type, radius and spacing were improvised for each screen.
5. Review buries the one decision the owner must make.
6. Components have no hover, focus, disabled, error or loading states.

## 3. Chosen design direction and rationale
**Cutting Room.** It is a neutral graphite editing suite in which the footage is the brightest thing on screen.
- **Docked panels, not cards.** Panels are split by 1 px hairlines.
- **Timecode is the hero.** It sits in a persistent story strip (the beats of the reel) at the bottom of every project screen, the way an NLE (non-linear editor) keeps its timeline docked.
- **Colour means a signal (from Direction C).** If something is coloured, it is asking for attention or reporting a state.

Why this direction: an editor's tool earns trust by looking like one. The owner's clients judge the output, and the owner spends long sessions in the app.

## 4. Colour palette (library path → hex; token set `cutting-room`)
| Role | Colours | Rule |
|---|---|---|
| Background | `bg/app` #0F1012, `bg/well` #08090A | The well sits behind footage. |
| Surfaces | `surface/1` #16171A, `/2` #1D1F23, `/3` #26282D | Elevation comes from tone, not shadow. |
| Lines | `line/hair` #2A2D32, `line/strong` #3A3E45, **`line/control` #666A72** | Hairlines divide areas. `line/control` outlines inputs, selects and toggles. It was added in QA (see §11). |
| Text | `primary` #ECEDEE, `secondary` #A9ACB2, `muted` #90949C, `disabled` #5C6067 | |
| Your move / you are here | `signal/amber` #E8A33D, plus hover #F0B458, pressed #CC8A28, on-amber #1A1305 | Used only for: the primary action, "Hold — needs you" and warnings, the playhead, the focus ring, the current-location marker (rail bar, tab underline) and the on state of a toggle. Never for data, decoration or selection inside lists. |
| AI working | `signal/ai` #9B8CFF | Only while the Editor is acting: the running stage, Editor messages, the live render. |
| Status | `sendable` #3CCB7F, `fail` #F5606C, `info` #6EA2E0 | Status always has a text label as well as a colour. |
| Layers | video #6F8FC6, colour #C58AA8, punch #6DB2B7, b-roll #74AF8C, captions #CBB35C, titles #C98B60 | Desaturated, so they don't compete with status. |

Measured contrast (WCAG 2), text colours against the four backgrounds:

| Text | Range |
|---|---|
| primary | 12.6–16.2 |
| secondary | 6.5–8.4 |
| muted | 4.9–6.3 |
| amber | 6.8–8.8 |
| ai | 5.3–6.9 |
| fail | 4.8–6.1 |
| on-amber on amber | 8.6 |

Disabled text is 2.3–3.0, which WCAG allows for inactive controls.

## 5. Typography system
| Style | Size / line height / weight | Font | Used for |
|---|---|---|---|
| display | 28/36/600 | Inter | Verdict |
| heading | 20/28/600 | Inter | Screen and panel titles |
| section | 16/24/600 | Inter | Group titles |
| body | 14/20/400 | Inter | Reading text |
| ui | 13/18/500 | Inter | Controls, rows, tabs |
| meta | 12/16/400 | Inter | Secondary detail; the minimum size |
| timecode-lg | 24/32/500 | JetBrains Mono | Playhead readout |
| timecode | 13/18/500 | JetBrains Mono | Timecodes, costs, sizes, ids |

**Measured across the 10 new pages:**
- **Sizes:** only {12, 13, 14, 16, 20, 24, 28}, down from 10 sizes.
- **Weights:** only {400, 500, 600}.
- **Exceptions:** two text layers at weight 700 and 800. Both are *reel content* (caption previews inside the phone and the Layers view), not UI.
- **Labels:** sentence case. No tracked caps.

## 6. Spacing and layout system
- **8-point rhythm.** Tokens `space.4/8/12/16/24/32/48`. Panel padding is 24, gaps within a group are 16, and gaps between sections are 32.
- **Shell.** Every screen uses the same shell:
  - a 72 px rail with icon + label navigation;
  - a 64 px header (breadcrumb, status, one primary and one secondary action);
  - underline tabs for project screens;
  - a 72 px story strip.
- **Radius.** Three values: 4 for controls (and story beats, fixed in QA), 8 for surfaces, and pill for toggles and badges.
- **Measured radii in use:**

  | Radius | Where |
  |---|---|
  | 4, 8, 10/20 | Controls, surfaces, pills |
  | 1.5 | Inside the film icon |
  | 1 | 6 px colour keys |
  | 26/32/58 | Phone device mock only |

## 7. Component architecture
Components live on `2 · Components` as variant sets, and the screens use instances: 59–101 instances per screen.

| Set | Variants |
|---|---|
| Button | 22 variants: primary and secondary × rest / hover / pressed / focus / disabled / loading; ghost and danger × the same states without loading |
| Input | rest / focus / error / disabled |
| Select | closed / open (menu with shadow) |
| Toggle | 3 variants (on / off / disabled) |
| Tab | active / inactive / hover |
| Nav rail item | — |
| Status | sendable / hold / failed / editing / queued / delivered (dot + label) |
| List row | — |
| Tooltip | — |
| Toast | — |
| Rail | Active state per destination |

There are 23 line icons (1.5 px stroke, 20 px grid). They replace all emoji and letter icons.

## 8. Screens redesigned
**Review (3).** The verdict and its single next action are the hero ("Confirm 'it'"). Next to them:
- the phone monitor;
- the proof list;
- Reviewer notes, as hairline rows.

**Live (4).**
- A 15-stage pipeline track, grouped Analyse → Decide → Build → Check & deliver.
- Progress, time left and stage timings with cost.
- The Editor decisions feed, with a reason and cost for each decision.
- The story strip shows "Rendering".

**Home (5).**
- A "Needs you" queue, with actions aligned to the right.
- Recent projects, shown as posters with status.

**Layers (6).** The exploded layer stack, with an inspector.

**New edit (7).**
- Drop zone and upload rows.
- The brief, grouped as Basics / Format / Content.
- One primary action.

**Revise (8).**
- A chat with the Editor, with a change summary and cost for each turn.
- Versions with restore.
- Client notes and how the Editor reads them.

**Adjust (9).** Guided adjustments using segmented controls and toggles.

**Deliver (10).**
- The package file list, with sizes.
- The credit that is required, shown as the amber "your move" item.
- Extra versions, platform checks, and the review link.

**States (11), added after the first report.**
- **Home, empty (first run).**
  - One primary action, "Start your first edit", plus a sample clip.
  - Three steps explain the product.
  - The header's "New edit" button is removed here so there is only one amber action.
- **Review, loading.** Skeleton blocks mirror the real Review layout exactly, so nothing shifts when content arrives. "Loading review…" is marked as a polite live region for screen readers.
- **Live, failed.**
  - **Header:** the status reads "Failed · render", in red with a label. "Retry render" is the only primary.
  - **Explanation:** what happened, in plain words, and that the work before it is saved.
  - **What to try:** three numbered steps, including a copyable fallback command.
  - **Log:** the last log lines in a well.
  - **Kept:** the Editor decisions, with a note that a retry costs nothing extra.
  - **Pipeline:** shows where it stopped.
  - **Story strip:** reads "Stopped".

**Library (12)** (from `Libraries.tsx`).
- Library tabs with counts.
- A dense sound table: play, id in mono, category, length, licence. A white bar marks the row being played, in neutral colours because playing isn't an action.
- A category filter.
- An "Add a folder" panel: kind, folder, source, licence, then "Index folder".
- "Couldn't read" rows with the reason for each file.

**Quality lab (13)** (from `Quality.tsx`).
- A score chart for tuning runs, with the selected run shown as a neutral ring, and family bars for that run.
- The **real** gold set from `eval/manifest.yaml`: 6 pairs, all tuning, 0 held out, 0 Hinglish.
- Self-improvement history, with accepted and rejected changes.
- Calibration: the Reviewer's agreement with the owner, "Not trusted yet", and the false-alarm rate and mode for each check.
- The release check, shown **locked** with the real reason (it needs 12 pairs, 6 held out, 2 of them Hinglish).
- A self-improvement budget.

**Settings (14)** (from `Settings.tsx`).
- Health checks: a check or cross, the name and a detail, with "optional" marked.
- Disk, memory and jobs.
- 30-day AI cost bars, with today highlighted, and cost per project.
- Studio settings:
  - edits at once, platform and language, as segmented controls and a select;
  - extra versions, as toggles;
  - the Pexels key;
  - the projects folder, read-only but full contrast (it is information, not a disabled control).
- "Remove a project", with a danger button that ends in "…" because it asks for confirmation.

## 9. Key improvements
| Problem | Before → after |
|---|---|
| Components | 0 → 9 variant sets (Button, Input, Select, Toggle, Tab, Nav item, Status, Row, Rail) plus Tooltip and Toast. They are used everywhere, so changing a main component updates all screens. |
| Card soup | One container level, divided by hairlines |
| Colour | Every hue has a defined role. Amber is limited to six "act here / you are here" roles (§4). It is never used for data or list selection, so on any screen the one amber button is the next action. |
| Type and radius | Type from 10 sizes / 6 weights to 7 / 3; radius from 15 values to 3 |
| Decoration | No gradients and no glows. Shadows only on menus and dialogs. |
| Wayfinding | Breadcrumb + tabs once; the rail has labels; the story strip keeps orientation on every project screen |
| States | Every control has hover / focus / disabled / error / loading designed |

**Phase 5 critique: the five weakest decisions, fixed and verified.**
1. Live had dead space and a fake playhead. It now has stage timings and a "Rendering" state on the strip.
2. Revise had two primary buttons. "Apply notes" is now secondary.
3. Deliver had meaningless file icons. They were removed, the warning icon sits only on CREDITS.txt, and "Mark delivered" sits next to "Create link".
4. New edit's group labels had no hierarchy. They are now the `section` style, and the form rhythm was opened up.
5. Home's queue actions were ragged. They are now right-aligned.

**Phase 6 QA fixes.**
- Story-beat radius changed from 2 to 4.
- Input, select and toggle outlines raised to 3:1 non-text contrast.
- Placeholders end with "…".
- Typographic apostrophes.

## 10. Remaining limitations (honest)
- **Screen states are shown once each, by pattern.**
  - One empty state (Home), one loading state (Review) and one error state (Live failed).
  - The other screens should follow these patterns, but their own empty, error and sparse versions aren't drawn.
  - Very long user content (long project names, long notes) isn't tested in the layouts.
- **The Select component has no built-in label.** Labels sit beside it as separate text layers. A later component revision should add a label slot like Input's.
- **Sample data.** The screens use sample data: the costs, health details, score history and improvement history are illustrative. The gold-set rows and the release-lock reason are real.
- **One width only (1440).** No laptop (1280) or ultra-wide layouts.
- **Exported previews use a serif fallback.** Penpot's exporter container can't load Inter or JetBrains Mono, so previews show a serif font; the canvas renders correctly. Fix: upload both fonts to Penpot as local fonts.
- **3D moments are flat stand-ins.** The phone orbit, the pipeline dolly and the exploded layers are drawn as flat compositions with notes. Motion has to be specified in code.
- **Instance layout doesn't follow component constraints.** Penpot instances didn't pick up constraint changes, so stretched inputs had their sizes overridden per instance. A later resize of the main component won't reflow them.
- **The Review phone is a placeholder** (no real frame).
- **The design is missing behaviour notes:**
  - "Cancel edit" and "Restore" need a confirmation or Undo;
  - icon-only download buttons on Deliver need tooltips and accessible names;
  - the focus ring must not hide under the sticky story strip.
- **No external review.** The "UI UX Pro Max" and "Anthropic Frontend Design" skills were not available. The Web Interface Guidelines were fetched from `vercel-labs/web-interface-guidelines` and checked by hand. No human designer has reviewed this work.

## 11. Final critique
**What works.**
- It now reads as a craft tool, not an AI template.
- The colour rule is the strongest decision: on any screen, the amber item is the thing to do next.
- The shell and story strip make the 8 screens feel like one product.
- The component library makes the system enforceable in code.

**What is weaker.**
- Density is high for a non-editor. New users may need first-run hints on Live and Layers.
- The violet "AI working" colour sits close to the layer blue at small sizes.
- Home is the least distinctive screen.
- Every screen in the app now has a design, and the three state patterns exist. Even so, it is a **complete design direction, not a pixel-final spec**: each screen's own edge states, one more width, and motion still have to be worked out in code.

**Phase 6 QA on the added pages (11–14)** used the same measured sweep:
- **Sizes:** only {12, 13, 14, 16, 20, 24}.
- **Weights:** only 400, 500 and 600.
- **Colours:** no off-palette fills or strokes.
- **Radii:** 4, 8 and pill.
  - Story-strip beats on the failed screen were corrected from 2 to 4.
  - The 3 px inner segment sits concentric inside a 4 px control.
  - The 2 px radius is on 4 px-tall data bars, which makes them pills.

**Next steps, in order.**
1. Add a 1280 layout.
2. Upload the fonts to Penpot.
3. Give Select a label slot.
4. Map the tokens to CSS variables in `studio/web`, replacing the violet accent and card styles there.
