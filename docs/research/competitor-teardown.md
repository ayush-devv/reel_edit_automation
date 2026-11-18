# Competitive teardown: AI reel editors (as of Nov 2026)

Legend: **D** = official docs/changelog · **M** = vendor marketing only · **R** = third-party review · **?** = not found/unverified · **N** = not offered. Pricing is approximate; third-party sources conflict.

## 1. Capability matrix

| Product | Input | Auto-cut | Kinetic captions | B-roll | SFX | Punch-ins | Reframe | Music | Chat edits | API |
|---|---|---|---|---|---|---|---|---|---|---|
| **Opus AI Producer** | raw talking-head, ≤5 min | D | D | D (own clips) | D beta | D | D | D beta (ducked) | D | MCP, restricted |
| Opus Clip (clipper) | long → clips | D | D | M | ? | ? | D | ? | M (4.0) | D (API + 27-tool MCP) |
| CapCut | both | M | D (templates) | ? | library | M | M | library | ? | ? |
| Submagic | both | D (silence, bad takes) | D | D (stock + AI-gen) | M | D | ? | D (your track) | N | D |
| Captions (Mirage) | raw → edit | M | D | D (AI-gen) | D (prompted) | M | ? | D (gen) | D (+SMS "Cappy") | ? (help-center ref) |
| Descript Underlord | raw/long | D | D | M | ? | ? | M | ? | D (Claude) | ? |
| Veed | raw/long | M | D | ? | ? | ? | M | ? | ? | ? (+OpenEdit OSS) |
| Vizard | long → clips | M | D | M | ? | ? | D | ? | M ("Agent", unopened) | D (paid plans) |
| Klap | long → clips | D | D | ? | ? | ? | D | ? | ? | D |
| Munch | pivoted to done-for-you service | – | – | – | – | – | – | – | – | – |
| Premiere 26 | pro NLE | text-based | captions (static) | N | N | N | D | M (Generate Music beta) | N | plugins |
| Resolve 20 Studio | pro NLE | D (IntelliCut, IntelliScript) | D (Animated Subtitles) | N | N | N | D | ? | N | scripting |
| Kapwing (Kai) | raw/long/links | M | M | M | ? | ? | M | ? | D | ? |
| InVideo agent | raw + generation | M | M | M (gen + stock) | ? | ? | ? | M | M | ? |

**Per-product notes**

- **Opus AI Producer is the closest competitor.** Docs list filler/pause cuts, word-synced captions, motion graphics matched to the words, zooms, auto layout, B-roll from your own clips, SFX, ducked music, voice cleanup, and revisions in the same chat. Documented limits: single speaker only, no multicam or screen recordings, ≤5 min, 1080p30 export, SFX/music in beta, MCP for selected accounts, credit "slices". OpusClip 4.0 (Nov 2, 2026) claims "show it a style you like and it edits to match" (**M, unverified**). The clipping MCP **can't stitch segments**. Virality score is officially 0–99 (third parties say 0–100). Reviews (R): bad cut points about a third of the time (one reviewer's estimate), clips cut off mid-idea, credit and refund complaints. ~$15/mo and up.
- **Submagic** has the cleanest API. `POST /v1/projects` takes `templateName`, `magicZooms`, `magicBrolls` plus a percentage, `removeSilencePace`, `removeBadTakes`, `hookTitle`, `music`, and timed `items[]` (`ai-broll` with a prompt, ≤12 s). Opaque `aiEditTemplate` presets override everything else. Weakness (R): 4 of 10 auto B-roll inserts were mismatched in one test.
- **Captions**: AI Edit and chat on Max ($24.99/mo iOS). Generated (not stock) B-roll, SFX and music.
- **Descript Underlord** runs on Claude: a general agent over "dozens of low-level tools", evaluated by an LLM-as-judge calibrated to humans. A review step after every turn was added around May 2026, plus Revert. Weaknesses (R): too aggressive (cut a deliberate repetition as a retake), can't use custom fonts, weak at chaining tasks.
- **CapCut**: strongest template and caption ecosystem, with generative models inside. No public editing API found.
- **Premiere 26**: Object Mask, Generative Extend (≤2 s), media search. **No agent.** **Resolve 20** (2025): IntelliScript (script → timeline), IntelliCut, Animated Subtitles, Magic Mask v2, Audio Assistant. Speaker-aware Smart Reframe comes from a single source.
- **Kapwing Kai**: task checklist, interruptible. **InVideo**'s "watches footage, not just the transcript" is M. **Munch** pivoted to a done-for-you service.

## 2. What "pro" means today (baseline to match)

1. Filler, silence and bad-take removal with audio fades at cuts.
2. Word-timed animated captions: a template library, keyword emphasis/emoji, a custom brand theme, and a custom dictionary.
3. Hook: an AI title overlay at minimum (Submagic `hookTitle`).
4. Punch-ins/zooms on emphasis, plus transitions.
5. B-roll: stock, generated, or the user's own clips, with density control.
6. Music with ducking; SFX on key beats (still beta or marketing at most vendors).
7. Face-tracked reframe to 9:16/1:1/16:9; voice cleanup.
8. Chat revisions that modify the existing project rather than regenerate it, plus undo.
9. 1080p export in minutes; API/MCP access is increasingly expected (Opus, Submagic, Klap, Vizard).

## 3. Gaps and differentiation opportunities

Planning plus a review loop is no longer novel: Underlord has one and video-use has one. Compete on doing the following *well and verifiably*:

- **Story restructuring across non-contiguous segments.** Pull the strongest line from 0:47 to the open as a cold-open hook, reorder beats, and drop a tangent. The Opus MCP can't stitch, and most "hooks" are text overlays.
- **Visual QA of the rendered output.** Check caption and face collisions, B-roll relevance against the spoken line, punch-in framing and jump cuts by inspecting frames, not the transcript. The hit rate on B-roll is roughly 60% (R). *Captions over faces is a hypothesis; I found no documented complaint.*
- **Rhetorical-intent reasoning.** Tell deliberate repetition, comic pauses and callbacks apart from mistakes (Underlord's documented failure). Pace the edit to the genre (comedy, tutorial, testimonial).
- **Explainable edit decision list (EDL).** Give a one-line rationale per edit ("zoom: punchline", "cut: false start") that can be accepted or rejected. Today the closest anyone offers is Descript's links to the changed spot.
- **Verifiable style imitation from a reference reel.** Extract pacing (cuts/sec), caption style, zoom frequency, SFX density and grade, then report how closely the output matches. Opus claims this (M) but shows no evidence. Submagic's presets are opaque.
- **Editor personas** with editable style parameters, not black-box templates.
- **Footage Opus won't take:** multi-speaker, vlog and other non-talking-head reels.
- **Honest scoring.** Replace opaque virality numbers (Vizard's is "inconsistent" per R) with a checklist critique: hook in the first 1.5 s, retention risks, caption legibility.

## 4. Open-source projects worth studying

| Repo | Stars | License | Learn |
|---|---|---|---|
| browser-use/video-use | 31.2k | MIT | **Closest reference design.** ElevenLabs Scribe → word timestamps and audio events packed into ~12 KB `takes_packed.md`. A `timeline_view` tool renders a filmstrip + waveform PNG only at decision points. LLM → EDL → ffmpeg render (grade, 30 ms fades, captions) → self-eval at every cut, ≤3 re-render loops. Animations run in parallel sub-agents. No music handling. |
| veedstudio/open-edit | 1.8k | Apache-2.0 pipeline; renderer closed (PolyForm Shield) | The agent composes video as HTML/CSS and VEED Engine renders it locally. Apple Silicon and macOS 26 only. |
| heygen-com/hyperframes | 85.9k | Apache-2.0 | HTML → video renderer built for agents (motion graphics, captions). |
| remotion-dev/remotion | 73.9k | Custom (company license needed above a size threshold; verify) | React compositions for kinetic captions and overlays. |
| GVCLab/CutClaw | 1.0k | code license unconfirmed (paper CC BY-NC-SA) | Playwriter, Editor and Reviewer agents; beat-synced edits from narrative instructions. |
| mutonby/openshorts | 8.9k | MIT | Long → shorts pipeline: moment detection, face tracking, subtitles, MCP/API. |
| Anil-matcha/AI-Youtube-Shorts-Generator | 6.2k | MIT | Whisper + LLM highlights + vertical crop baseline. |
| WyattBlue/auto-editor | 6.0k | Unlicense | Fast silence and motion-based cutting; exports to NLE timelines. |
| video-db/Director | 1.6k | MIT | Multi-agent video framework. |
| NarratoAI (11.9k, MIT), FunClip (6.6k, MIT) | | | LLM narration and clipping (Chinese ecosystem). |

"social-video-agent" isn't on GitHub under that name. The closest matches are ronantakizawa/social-video-mcp (4★), taisly/agent and htekdev/vidpipe (237★, Copilot SDK). MoneyPrinterTurbo (144k★) generates video from a topic and doesn't edit footage, so it's out of scope.

**Sources (not counted):** producer.opus.pro/docs/getting-started · opus.pro/blog/opusclip-4-0 · opus.pro/blog/claude-video-editing-mcp · help.opus.pro/docs/article/virality-score · docs.submagic.co/llms-full.txt · claude.com/customers/descript · feedback.descript.com/changelog · captions.ai/llms.txt · veed.io/newsroom/openedit-by-veed · kapwing.com/help/release-notes-august-2026-2 · petapixel.com (Premiere 26) · blackmagicdesign.com (Resolve 20 PR) · docs.klap.app · GitHub API (star counts as of Nov 17–18, 2026).
