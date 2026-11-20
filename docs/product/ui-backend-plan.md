# Studio UI ↔ engine: review and integration plan (2026-11-19)

**Where it stands.** The Studio is already wired to the real engine through `studio/web/src/api/http.ts` and the FastAPI routes in `engine/src/reel/studio/app.py`:
- 41 routes;
- every screen loads real data;
- a run against `_real_doac_v2` found 0 console errors and 0 failed API calls;
- tests: 303 engine, 46 web.

So this plan isn't about connecting the two sides. It's about **closing the gaps** where:
- the engine can do something the UI can't reach;
- the UI shows engine internals to the owner;
- the engine returns a placeholder.

## What the review found

### A. Data the API returns but the UI shows badly
| # | Where | What the owner sees | Fix |
|---|---|---|---|
| A1 | Review verdict, warnings | Engine wording: `cut_in_word: 4 cut(s) inside a word: 0:16.96 start of v_k06.3 cuts "Look" 215 ms in…`, `proof_words: 1 unconfirmed caption word(s)` | One sentence per check in plain English, with the timecodes as jump links. The raw detail goes behind "Details". |
| A2 | Home, project header | CLI-made projects show their id (`_real_doac_v2`) and "No client" | Let the owner rename a project and set its client. |
| A3 | Story strip, Layers | Beat names come straight from the plan (`set…`, lowercase, truncated) | Map beat ids to display names, and show a tooltip with the line's text. |

### B. Placeholders the engine sends
| # | Field | Today | Fix |
|---|---|---|---|
| B1 | `eta_s` in the project detail | Always `null`; the web app guesses from fixed stage times | The engine estimates from this Mac's own past stage durations (`log/runs.jsonl`), scaled by footage length. |

### C. Engine features the UI can't reach (CLI only)
| # | CLI | Use | UI |
|---|---|---|---|
| C1 | `reel stock` + `run --broll <folder>` | Pexels b-roll for an edit | New edit → "B-roll": none / stock search (needs the Pexels key) / a folder. |
| C2 | `reel assets fetch` | The built-in SFX and music packs | Library empty state → "Get the starter packs" button (runs as a job). |
| C3 | Gate modes (warn ↔ block) | Calibration says when a check is ready to block | Quality lab → a switch on each check, allowed only when `promote_to_block` is true. Otherwise it explains why not. |
| C4 | Story-line edits | Drop or reorder kept lines (possible today only through a Revise request) | Adjust → "Story" section: list the kept lines with a remove toggle and drag to reorder, checked by the validator like the other adjustments. |
| C5 | `reel bakeoff` | Compare Hinglish speech-to-text engines | Quality lab → "Speech-to-text bake-off" action and its result table. |

### D. Things only kept in the browser
| # | What | Risk | Fix |
|---|---|---|---|
| D1 | Brief templates (localStorage) | Lost if the browser data is cleared; not on another browser | `GET/PUT /api/templates`, saved in `~/.config/reel/`. |

### E. Running it day to day
| # | Today | Fix |
|---|---|---|
| E1 | The server runs only while a terminal or session is open | A one-click launcher: a login item or LaunchAgent for `reel studio`. |
| E2 | You have to keep looking to know when an edit finishes or needs you | A browser notification when an edit turns Sendable, Hold or Failed (the Notification API, opt-in in Settings). |
| E3 | Review links work only on this Mac | Optional: "Share outside this Mac" via a tunnel the owner turns on. **This is a security decision for the owner**, so it's off by default. |

## Plan, in order

| Phase | Items | Why this order | Size |
|---|---|---|---|
| **1. What the owner sees every day** | A1 plain-language verdict, A2 rename and client, B1 real time left | They affect every edit and the Review screen, which is the main one | ~1 day |
| **2. Finishing the creation flow** | C1 b-roll at creation, C2 starter packs, D1 server-side templates | They remove the last reasons to open the terminal when starting an edit | ~1–1.5 days |
| **3. Control** | C4 story-line edits, C3 gate switches, A3 beat names | More power for owners who want it; built on the existing validator | ~1.5 days |
| **4. Running it** | E1 launcher, E2 notifications, C5 bake-off in the lab | Convenience; the bake-off matters before Hinglish clients | ~1 day |
| **Owner decision** | E3 sharing outside the Mac | Exposes a page to the internet; needs your explicit yes | — |

**Status (2026-11-20):**
- Phases 1–2 were built in G1.7.
- Phases 3–4 (C3, C4, A3, E1, E2, C5) were built in G2.4 (`docs/product/roadmap.md`, "Group 2 as built").
- E3 is still open.

**For every item, the same definition of done:**
- an API route with engine tests (a TestClient against a fake workspace);
- the web client and the mock version;
- a screen in the Cutting Room style;
- a route test;
- a screenshot against a real project.
