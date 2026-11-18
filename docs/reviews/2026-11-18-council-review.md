# Council review of Architecture v1.0 — 2026-11-18

Five independent reviewers read the docs directly (not a summary): **Pro freelance editor**, **Systems/ML skeptic**, **LLM-application engineer**, **Scope pragmatist**, **Devil's advocate**. No "council" skill was installed; this is the equivalent run as parallel independent reviews.

## Verdicts
| Reviewer | Verdict |
|---|---|
| Pro editor | Revise — built for "technically correct", not "client accepts" |
| Systems/ML skeptic | Revise — media foundation (clock, colour, coordinates) unspecified |
| LLM-app engineer | Revise — no instrument for taste; context built for mechanics, not story |
| Scope pragmatist | Revise — roadmap automates everything before one sendable reel |
| Devil's advocate | Hybridise — "build from scratch" was never decided; spike social-video-agent first |

## Unanimously validated (keep)
- Claude references IDs; a compiler produces exact frames (ADR-0002).
- Code gates are the authority; Claude's judgment advisory (ADR-0006).
- One orchestrator on the Messages API, not a multi-agent graph (ADR-0005).
- Each effect has exactly one renderer owner; composite copies base audio (ADR-0004).
- Bounded caption style tokens rather than free CSS (ADR-0011).

## Consensus issues
| # | Issue | Raised by | Severity |
|---|---|---|---|
| 1 | **No ground truth for editorial quality.** All exit tests are proxies (gates pass, style vector ±20%); the system will converge on "correct but generic" (§14's top risk) with nothing to detect it. → Build a gold set of 10–15 raw→delivered pairs from the owner's own edits; score hook match, word-keep F1, order (Kendall τ), cut-rate ratio, blind A/B. | Editor, LLM eng, Pragmatist (+DA) | Critical |
| 2 | **Autonomy is the wrong target.** Freelance value = editor-minutes per delivered reel. → Assistant-first: strong first assembly + graphics, finished in an NLE. Export FCPXML/OTIO + ProRes 4444 alpha overlay + audio stems + SRT from M1 (OTIO alone loses the Remotion layer). | Editor, Pragmatist, DA | High |
| 3 | **No selects / story stage.** Claude can't hear performance; no take grouping, retake detection or delivery stats. → S2.5 selects: group repeated lines, flag restarts/stumbles, per-take rate/pitch/loudness/confidence; text paper edit with 2–3 hook options; plan in two passes (story → finish) with a `dry_run_compile` read-back. | Editor, LLM eng, DA | Critical/High |
| 4 | **No canonical ingest clock.** Real iPhone footage (HEVC HLG/Dolby Vision, rotation, VFR, 60/240 fps, mixed clips) untested; the only real sample is 25 fps; render bench used synthetic 1080p input. → S0 mezzanine per clip (CFR 30, bt709 SDR tonemapped, rotation baked, 48 kHz); everything reads only the mezzanine; golden corpus of real phone footage in the M1 exit test. | Skeptic | Critical |
| 5 | **Base graph won't survive real edits.** No `fps=` after `setpts` retime (likely cause of 1802 vs 1800 — unverified); `atempo` can't follow a ramp; `split`+trim breaks with reordering on 4K; punch-in supersampling not benchmarked. → Per-segment cuts from mezzanine, `fps=` after every retime, ramps as piecewise sub-segments or muted voice, one shared source→output time-map, re-bench on 4K HEVC. | Skeptic | High |
| 6 | **Hinglish word timing may have no reliable source.** Fine-tuned Whisper models may not emit usable word timestamps. → Pass/fail criterion vs hand-labelled onsets; add a commercial-safe CTC aligner candidate; phrase-level caption fallback; run in week 1. | Skeptic, Pragmatist | High |
| 7 | **Brand kit before palette adaptation.** Repeat clients need their brand on day one. → `brand.json` per client (fonts, colours, logo, end card, CTA, locked caption family) overrides palette tokens. | Editor, Pragmatist | High |
| 8 | **Audio finishing missing.** No voice chain (denoise, HPF, EQ, de-ess, compression, per-clip gain match), no room tone under cuts; never speed-ramp speech; music decision is blocking for deliverables. | Editor | High |
| 9 | **Gates will false-fail.** OCR(caption)=transcript unrealistic on animated text; A/V drift vs base is circular; face/contrast measured on source, not render. → Check text from timeline props, caption-over-face from overlay alpha vs faces on rendered base, contrast on final pixels, sync via beep+flash probe; measure each gate's false-positive rate before making it hard. | Skeptic | High |
| 10 | **Playbook as 30 rules will cause over-editing.** Density quotas become goals. → Mechanics into compiler/gates; give Claude ~8 judgment principles (Murch order) + 2–3 annotated human edits; density as post-plan feedback. | LLM eng | High |
| 11 | **No revision patch format.** → Stable item IDs; insert/replace/delete ops; require quoting first/last word of each range so off-by-N word IDs are rejected. | LLM eng | High |
| 12 | **Delivery profile + client loop missing.** Keep source fps (25 fps → 30 judders), master, textless, no-music, SRT, cover, 4:5; review copies with watermark/timecode, timecoded client-note importer, round counter, change log from `reason` fields. | Editor | High |
| 13 | **Build vs fork never decided.** competitor-teardown wrongly said social-video-agent isn't on GitHub; it is cloned locally (Apache-2.0, ~42k lines) and covers EDL compiler, ffmpeg+Remotion, QA, reframing, OTIO/FCPXML export, resumable stages. Missing: Hindi/Hinglish, speed ramps, palette-driven captions. → 2-day spike before M1 code. | DA | High |
| 14 | **Doc inconsistencies.** NFR-3 (≤ $0.25) vs $0.40–0.60 estimate (and 1-h cache write is 2×); NFR-1 "measured 43–74 s" vs "estimated"; NFR-7 byte-determinism impossible → frame count/timing + perceptual-hash tolerance. | Skeptic, LLM eng, Pragmatist | Medium |

## Disagreements
| Topic | Positions |
|---|---|
| Reviewer persona | Pragmatist: defer, the editor is the taste gate. LLM eng: keep but narrow — judge story from a read-back transcript and check the plan's own stated intents on frames; drop automatic pairwise preference. |
| Safe zone | Editor: hard gate for captions/CTA/logo with per-element override. Earlier review: warning only (pro reels place text outside on purpose). |
| Native-video perception (Gemini "moment notes") | DA: opt-in A/B experiment. Conflicts with C-9 (Claude only paid dependency) and NFR-8 (media to third parties). |
| Scope cuts | Pragmatist: drop TransNetV2, OCR gate, pose, beat_this, matte, SFX generation for now. Others silent. |

## Strongest dissent (to carry into ADRs)
> "Every feedback signal rewards conformity to rules, not good editing … the system will reliably converge on 'correct but generic' and has no instrument that would detect it." — LLM-app engineer (echoed by Pro editor)

> "Every accuracy promise assumes one clean CFR, SDR, upright clock that the design never creates." — Systems/ML skeptic

## Owner decisions needed
1. Product mode: assistant-first (NLE finish) vs fully autonomous.
2. Build path: social-video-agent spike first vs build from scratch.
3. Gold set: does the owner have raw→delivered pairs of their own edits?
