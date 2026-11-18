# Requirements — Claude Reel Editor

_Last updated: 2026-11-18. Items marked **[ASSUMPTION]** were not confirmed by the user._

## 1. Functional requirements

| ID | Requirement | Source |
|---|---|---|
| FR-1 | User uploads a raw reel (one or more clips) and asks Claude to "edit it"; the system **autonomously returns a finished, professional, client-ready reel** (no manual steps), plus an NLE package (FCPXML/OTIO, ProRes 4444 alpha overlay, stems, SRT) as an escape hatch. _(ADR-0018, supersedes ADR-0012.)_ | User |
| FR-2 | Edit quality targets an expert short-form editor: hook in the first second, tight pacing, kinetic captions/typography, b-roll, SFX, punch-ins / simulated camera moves, speed ramps, colour grade. | User |
| FR-3 | User can revise by chat ("make the hook faster"); revisions patch the existing edit, never regenerate it from scratch. Undo is available. | Conversation |
| FR-4 | Spoken language: **English, Hindi, Hinglish** (code-switched). Captions in the spoken language; script for Hindi words is a setting (Roman / Devanagari). | User |
| FR-5 | Every edit decision carries a one-line reason the user can see (explainable edit list). | Competitive gap |
| FR-6 | Sound effects placed by Claude from a curated, indexed SFX library. | User (SFX focus) |
| FR-7 | Style imitation from a reference reel, measured (cut rate, shot length, caption density, zooms, SFX density, loudness). | Research + sample analysis |
| FR-8 | Export final MP4 (1080x1920) at the **project fps = source fps** (ADR-0015); NLE escape-hatch package (OTIO + FCPXML + alpha overlay + stems + SRT). | Research + council |
| FR-9 | Music from an **owned/licensed library** with musical editing (ADR-0022); copyrighted songs / trending audio never baked in (no-music variant exported). | User |
| FR-10 | Captions and typography adapt to the video's nature, mood and colour palette (not one fixed template); readability enforced by checks. | User (ADR-0011) |
| FR-11 | Professional, client-deliverable quality: the bar is an expert freelance editor's output, not basic auto-captions. Measured on the owner's gold set (ADR-0014). | User |
| FR-12 | Per-client brand kit (`brands/<client>.json`) overrides palette-derived caption tokens. | Council (ADR-0017) |
| FR-13 | Delivery profile: source fps kept, master, textless, no-music, SRT/VTT, cover, optional 4:5. | Council (ADR-0017) |
| FR-14 | Client review loop: watermarked timecoded review copies, client-note importer to item IDs, revision rounds, change log from reasons. | Council (ADR-0017) |

## 2. Non-functional requirements

| ID | NFR | Target | Status |
|---|---|---|---|
| NFR-1 | Render time, 60 s reel, local Mac (M5) | ≤ 90 s end-to-end render | Synthetic 1080p bench: ~54 s sequential (sum of measured steps); parallel 43 s estimated; **re-bench on real 4K HEVC** (ADR-0015) |
| NFR-2 | First draft latency (upload → preview) | ≤ 5 min for a 60 s reel | **[ASSUMPTION]** |
| NFR-3 | Claude usage per finished reel | Fits within the owner's Claude Code plan limits for the target reels/day | Runs in Claude Code (ADR-0019); §5 token figures kept as an API-equivalent reference |
| NFR-4 | Frame accuracy | Cuts on frame boundaries; output frame count = planned frame count | Benchmark found 1802 vs 1800 → must enforce |
| NFR-5 | A/V sync | ≤ 20 ms drift vs base render | Reference project practice |
| NFR-6 | Loudness | −14 LUFS integrated, ≤ −1.5 dBTP on the encoded file (convention, not a platform spec; ADR-0017) | Research |
| NFR-7 | Determinism | Same timeline JSON → identical frame count and timing + per-frame perceptual-hash tolerance (byte-identical is impossible with VideoToolbox/Chrome) | Revised (ADR-0017) |
| NFR-8 | Privacy | Faces detected, never identified (Anthropic AUP); user media never sent anywhere; only contact sheets and text tables are read by Claude Code | AUP + research |
| NFR-9 | Licensing | Every model, library and asset is commercial-safe or explicitly marked "internal only" | Research |

## 3. Constraints

| ID | Constraint | Source |
|---|---|---|
| C-1 | Claude (API and Claude Code Read tool) accepts text, images, PDFs — **no video or audio input documented**. All perception happens in our tools. | Official docs, verified 2026-11-18 |
| C-2 | Runs **locally** for now (developer Mac: Apple M5, 10 cores, 16 GB). | User |
| C-3 | Corporate network intercepts TLS; Node downloads need `NODE_EXTRA_CA_CERTS=~/.mac-ca-bundle.pem`. | Observed |
| C-4 | Local ffmpeg build lacks libass (no `subtitles` filter). | Observed |
| C-5 | Shell tooling is allowlisted by lean-ctx; new binaries need `lean-ctx allow`. | Observed |
| C-6 | Structured outputs: no recursive schemas, no numeric bounds → validator must enforce ranges. | Official docs |
| C-7 | Stock-API assets (Pexels, Pixabay, Coverr) may not be cached/indexed locally. | Provider ToS |
| C-8 | **Personal tool** used for paid freelance client work: every model, library and asset must permit commercial use of the output. | User |
| C-9 | Prefer **free, open-source, local** components (e.g. ASR); paid services only as optional plug-ins. Claude (via the owner's Claude Code plan) is the one paid dependency. | User |

## 4. Assumptions to confirm

- **[ASSUMPTION]** Input reels are 15–90 s, mostly people talking or doing things on camera.
- **Confirmed:** single user (freelance editor). **Remotion free-tier eligibility is the user's own declaration** after reading https://www.remotion.dev/license — pending.
- **Confirmed:** product form = personal tool (not SaaS).
- **[ASSUMPTION]** Volume during local phase: < 50 reels/day.

## 5. Back-of-envelope sizing (per 60 s reel)

**Claude tokens — first draft (API-equivalent reference only; under Claude Code (ADR-0019) this counts against plan usage limits, not billed per token):**

| Input | Tokens |
|---|---|
| System prompt + playbook + schema | ~10k |
| Footage tables (segments, words, faces, energy) | ~5k |
| 40 frames at 360x640 (~300 tokens each) | ~12k |
| SFX index | ~3k |
| **Input total** | **~30k → ~$0.12** |
| Output: plan JSON + reasons | ~4k |
| Thinking (always on; billed as output; `high` effort) | ~10–20k **[ESTIMATE — measure]** |
| **Output total** | ~15–25k → ~$0.30–0.50 |
| **First draft** | **~$0.40–0.60** (corrected 2026-11-18: earlier $0.20 omitted thinking tokens) |

- Each review pass (contact sheets, ~10k in + 3–8k out incl. thinking, `medium`): ~$0.10–0.20.
- Each chat revision: cached prefix ~30k at $0.20/MTok ≈ $0.006 + 5–10k output ≈ $0.10–0.20.
- **Per finished reel** (draft + 2 reviews + 3 revisions): **≈ $1–2**. Log `usage` per call to replace these estimates.
- Levers in order: caching (free), lower effort, then a cheaper model (measure quality first).

**ASR:** ElevenLabs Scribe ~ $0.22/hour (third-party figure) → < $0.01 per reel. Free self-hosted options cost only CPU time.

**Render (measured locally):** ffmpeg base 11 s + Remotion overlay 36 s + composite 7 s ≈ 54 s sequential, ≈ 43 s with base and overlay in parallel.

**Most sensitive number:** frame count sent to Claude. 40 small frames ≈ 12k tokens; 40 full-size frames ≈ 108k tokens (9x).
