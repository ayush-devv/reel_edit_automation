# Council re-review (after council fixes + autonomous mode + Claude Code runtime) — 2026-11-18

Five fresh reviewers, told not to read the first review: **Pro editor**, **Systems/ML skeptic**, **Claude Code specialist** (checked official docs), **Scope pragmatist**, **Devil's advocate**.

## Verdicts
| Reviewer | Verdict |
|---|---|
| Pro editor | Approve with changes |
| Systems skeptic | Approve with changes |
| Claude Code specialist | Approve with changes |
| Scope pragmatist | Approve with changes |
| Devil's advocate | Fork social-video-agent at a pinned tag unless the spike shows a core schema can't carry a requirement |

## Validated by the panel
- Single mezzanine clock + shared time-map + conformance corpus (ADR-0015).
- ID-based plan, quote check, patch ops by stable ID, kept alternative hooks (ADR-0016).
- Gates measured on the render, warnings until calibrated; copy base audio; never ramp speech; brand kit over palette.
- Perception → IDs → compiler and the ffmpeg/Remotion split.

## Consensus issues
| # | Issue | Raised by | Severity |
|---|---|---|---|
| 1 | **Acceptance metric is broken.** 3 held-out reels → "≥ 70%" means 3/3; the owner recognises his own cut (not blind); scoring the holdout every build burns it; A/B and "sendable" merged. → ≥ 5–10 held-out reels (≥ 3 Hinglish), judge the tool's reel on its own, target as a count (e.g. ≥ 4/5), second rater if possible, tuning set for per-build scores, holdout only at release candidates. | Editor, Skeptic, Pragmatist, DA | Critical |
| 2 | **No sendable/hold verdict.** Autonomous mode can't know when a reel is NOT sendable; gates are warnings; Reviewer tested only on synthetic defects; after 3 fix loops the reel returns unflagged. → Explicit `sendable` / `hold(reasons)` verdict; measure its precision on the gold set; any false "sendable" is a release failure; calibrate the Reviewer on the tool's own rough renders. | Editor, DA | Critical |
| 3 | **Caption text correctness unchecked.** Proper nouns < 0.5 confidence; Hinglish WER unknown (Shruti self-reports 35%); captions are baked into the overlay so the NLE escape hatch can't fix a word. → Auto-correct only against brief/brand/OCR vocabulary; remaining low-confidence words → `hold` with a timecoded proof list; caption accuracy in the acceptance test; Hinglish timing pass/fail with phrase-level fallback. | Editor, Skeptic, DA | Critical |
| 4 | **Orchestration belongs in code, not the skill.** Skill-driven sequencing is non-deterministic (a skipped `reel validate` is silent), loses state on compaction (skills re-injected ≤ 5k tokens; images gone), and `-p` can exit 0 while a timed-out Bash job runs in background. ADR-0016 §7 already says the orchestrator owns compile/render/QA. → `reel run <folder>` state machine (idempotent stages keyed by input hash, temp-then-rename, lockfile, artifact gates); Claude called only at decision points via `claude -p --output-format json --json-schema … --append-system-prompt-file … --allowedTools Read`, `--resume` for chat revisions. Keep the skill for interactive use. | Claude Code specialist, Skeptic | High |
| 5 | **Fork case is stronger now.** social-video-agent already is a Claude Code skill + CLI with a pluggable transcription backend, continuous mode, rotation/HDR/VFR probing, per-item speed, brand contract, supervising-editor stage, FCPXML/OTIO export, SessionStart hook. Missing: Hinglish, speed ramps, palette captions, gold harness. → Spike rule: fork if (1) continuous mode runs headless end-to-end on an English gold reel, (2) a Hinglish backend registers with no schema change, (3) a real HDR/rotated/VFR clip passes frame-count + sync, (4) ramps fit as chained speed items or a contained patch. Timebox environment setup to ½ day. | DA, Pragmatist | High |
| 6 | **Local ffmpeg cannot tonemap HDR** (no zscale/libplacebo/tonemap_videotoolbox) — same class as missing libass. Alpha composite colour matrices unspecified. → Pinned ffmpeg build with libzimg + libplacebo + libass (or AVFoundation tonemap); explicit matrices; composite in RGB with straight alpha; brand-swatch + text-edge test through the overlay path. | Skeptic | Critical |
| 7 | **Build order not in dependency order; harness/plugin missing.** Editor (step 4) needs validator/compiler (step 5); assets needed before Editor and overlay; gold harness and headless smoke run aren't build steps. | Pragmatist | High |
| 8 | **Scope too large for one release.** Cut from the release: style imitation, palette-adaptive captions, client-note importer + review copies, text-behind-subject matte, delivery variants beyond master + SRT, stock APIs, SAM/TransNetV2/PaddleOCR; slim escape hatch (OTIO + adapter FCPXML + alpha MOV + SRT). Rule: build a feature only if ≥ 3 gold finals use it. | Pragmatist, Skeptic | Medium-High |
| 9 | **Music undecided** — blocks blinding (owner finals have music) and brand reels sit on beds. → Decide: owned library indexed by BPM/mood/endings with trim-to-length + beat-snapped montage, or compare with music stripped. | Editor, Pragmatist | High |
| 10 | **Stale docs:** §6 "structured output", §8/§12 API-style tools and "30 rules → system prompt" (contradicts ADR-0016), ADR-0005 cites Messages API, ADR-0013 cites superseded ADRs, FR-8 30 fps vs source fps, NFR-6 −1 vs −1.5 dBTP, "project-level plugin" wording, `${CLAUDE_PLUGIN_ROOT}` vs `$CLAUDE_PROJECT_DIR`, redundant skill + command. | Skeptic, DA, CC specialist, Pragmatist | Medium |
| 11 | **Headless run stalls untested.** lean-ctx blocked commands and switched roots during this very review. → Smoke test `claude -p` against a stub `reel` CLI; explicit `--allowedTools`/permission flags; `BASH_DEFAULT_TIMEOUT_MS`; pin Claude Code version and log model ID per run; "0 permission prompts" in acceptance. | CC specialist, DA | High |
| 12 | **Craft gaps:** structured brief (must-keep lines, CTA, banned claims, product names) + brief-compliance gate; client b-roll pool before stock; per-clip exposure/WB correction before a partial-strength LUT; skin-tone and highlight-clip gates; voice de-reverb, click removal, level match across jump cuts. | Editor | High |
| 13 | **Bench measures a rejected graph** (`split=6`, seconds trims, no `fps=`, `atempo` on speech); sample-accurate audio boundaries (29.97 fps = 1601.6 samples/frame); peak-memory test with Remotion concurrency capped; per-render sync/identity check by cross-correlation + perceptual hash against mapped mezzanine frames. | Skeptic | High |

## Effort (pragmatist, one person at 25 h/week, owner labelling excluded)
Fork + cut scope 8–11 weeks · build + cut scope 15–20 weeks · current full scope 22–28 weeks (3–6 weeks of each is open-ended tuning).

## Owner decisions needed
1. Acceptance test design (holdout size, solo vs second rater, count target).
2. Scope: accept the cut list for the release?
3. Low-confidence words: allow a `hold` with a 30-second proof check (breaks "no manual steps" only when needed)?
4. Music for the release.
