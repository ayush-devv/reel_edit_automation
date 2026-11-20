# Harness comparison: our engine vs commercial and open-source agentic editors (2026-11-20)

**Question from the owner:** does our engine harness have potential, and which features do other engines and agentic video editors provide that we don't?

**Method.** Three web-research passes on 2026-11-20 (11 commercial products, about 20 open-source repos and MCP servers, about 20 papers), plus our own docs and code. It builds on, and does not repeat:
- `docs/research/competitor-teardown.md`: the craft-level capability matrix (auto-cut, captions, b-roll, SFX…);
- `research_notes/oss-reverse-engineering/`: OpenMontage, OpenEdit, CutClaw, vidpipe;
- `docs/product/oss-feature-gap-plan.md` and `docs/product/roadmap.md`.

This report is about the **harness**: how the agent is planned, checked, evaluated, steered and delivered.

**Evidence tags.**
- **[docs]**: official help centre or documentation.
- **[changelog]**: official changelog or release notes.
- **[eng-blog]**: engineering blog.
- **[paper]**: arXiv paper.
- **[README]**: repo README, not verified in code.
- **[marketing]**: vendor landing page, press release or press coverage.
- **[user-report]**: reviews.
- **[inference]**: my judgement.

What I re-fetched myself and confirmed:
- the Descript/Anthropic case study;
- Kapwing's August 2026 release notes;
- the Timeline-Bench abstract;
- Meta's Instagram Platform changelog;
- TechCrunch on Meta Edits.

The rest comes from the research passes, with links. **"?" (unknown) means "not public", not "absent".** Closed products may well have internal QA and evals that nobody outside can see. Read the matrix with that in mind; it is the main way a table like this flatters us.

---

## 1. Verdict

**Yes, the harness has real potential, but its edge is in *verifiability*, and that is not yet the same as *quality*.**

**Where no competitor publicly matches us:**
- Plans are checked in code before any render.
- QA gates measure the rendered pixels and audio, and there is a calibration *mechanism*: owner labels plus injected defects. Its real state is thin (checked 2026-11-20):
  - no owner labels exist on disk (0 `qa/owner_label.json` files);
  - the one auto-calibration run (`eval/calibration/auto_latest.json`, 2026-11-19) used one project and 6 pro finals as known-good;
  - only the `frozen` gate qualifies for promotion to blocking;
  - `black` raised 2 false alarms on the 6 pro finals;
  - the injected "caption wrong colour" defect was caught 0/10 times;
  - the caption gates can't be calibrated until a pro editor labels reels.
- A licence gate refuses assets before ranking and writes a per-reel manifest.
- Hindi/Hinglish is handled in depth: Hinglish ASR bake-off, Devanagari captions breaking at the danda, lakh/crore number checks.
- An FCPXML/OTIO package with stems.

Only Descript publishes anything comparable on evaluation: an LLM-as-judge "calibrated against human reviewers" over 100+ real-user test cases ([claude.com/customers/descript](https://claude.com/customers/descript), 2026, [marketing]). That is broader than our 6 English gold pairs and our zero owner labels. **Our lead is in the machinery, not yet in the evidence it has gathered.**

**The strongest outside evidence is a warning, not a compliment.** Timeline-Bench (arXiv 2609.35143, 2026-09-28) put 16 coding-agent harnesses through 56 raw-footage-to-final-cut tasks:
- the best resolved only 26.8%, the average 14%;
- most unresolved runs failed *only* the quality test;
- agents changed shots 0.72× as often as the reference edit;
- 93% of runs claimed full success, including 95.5% of runs that failed a test;
- only 5.5% of the problems their self-checks raised concerned pacing, story or shot choice, against 66% of human editors' notes.

All of these were verified in the paper's HTML on 2026-11-20 [paper].

Our gates are exactly the "technical defects" layer. They are necessary and they are where we lead, but they do not show the reels are good. The quality of our reels has still not been validated by a pro editor or by real clients.

**Where the market is clearly ahead:**
1. **Steering UX.** Text-based editing (Descript, Premiere, VEED, Submagic, Opus), plan approval before running (Firefly Plan Mode, Kapwing, InVideo), and credit estimates shown before running (Kapwing, Runway, Captions).
2. **Distribution.**
   - Long-video → many clips is table stakes at OpusClip, Vizard, Submagic, Captions, Kapwing and VEED.
   - Publish/schedule exists at OpusClip, Submagic and Vizard.
   - Review links work over the internet; ours work only on this Mac (`ui-backend-plan.md` E3).
3. **Generative add-ons.** Dubbing including Hindi/Hinglish (Captions, VEED), eye contact, AI b-roll.
4. **Per-client style memory.** "Edit like my last reel" (Vizard, Submagic Iris, Runway Skills).

**What nobody has: learning from post performance.**
- Every "virality score" (Opus, Vizard) is a pre-post guess.
- Submagic and Munch show analytics dashboards that don't feed back into edits.
- Meta's Edits AI assistant, which reads Instagram retention data, is only in invite-only testing (TechCrunch, 2026-06-11).

That is open ground for a freelancer whose clients care about Reels results.

**Net:** the harness is a good foundation for a *trustworthy, Hindi-capable, done-for-you* service, which no product sells well today:
- OpusClip doesn't list Hindi;
- CapCut is still blocked in India;
- romanised Hinglish captions are unverified in every Western tool.

It is not yet a better *editor*.

**Harness priority (§4):** prove quality before adding more gates:
- a bigger gold set, including Hindi;
- real owner and pro-editor labels;
- pairwise judging;
- pacing gates.

**Feature priority (§3, scored):**
1. review links that work outside the Mac;
2. a story-plan check-in;
3. per-client style memory;
4. the Clip Factory.

---

## 2. Capability matrix

Legend: **Y** has · **P** partial · **N** no / no evidence found · **?** unknown, not public. Numbers in brackets are sources in §5.

### 2a. Commercial agentic editors

| Harness capability | **Ours** | Descript (Underlord) | OpusClip | Captions | CapCut | Adobe Premiere/Firefly | VEED | Runway | Kapwing (Kai) | Submagic (Iris) | Vizard | InVideo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agent output is a structured plan, not free-form tool calls | **Y** JSON story + finish plans, schema-bound | P free tools; plain-language plan check-in since Oct 2026 [1] | P script/storyboard in Agent Opus only [3] | P "edit plan" in changelog [5] | ? (P per APK teardown [7]) | P Plan Mode in the Firefly assistant only [9] | P script approval [11] | Y workflow nodes shown for review [13] | P task checklist [15] | ? (API takes structured params [17]) | N "the agent should figure out the steps" [19] | P guided Workflows [21] |
| Plan validated in code before render | **Y** dozens of issue codes, repair loop | ? | ? | ? | ? | ? | ? | P declines unclear inputs [13] | ? | ? | ? | P flags missing footage [21] |
| QA on rendered pixels/audio | **Y** loudness, contrast, safe zone, dead air, cut pops, numbers… | ? | ? | ? | ? | ? (manual loudness tools only) | ? | N docs say check outputs yourself [13] | P "validates output, self-corrects"; method undisclosed [15, verified] | ? | P one vendor example [19] | ? |
| Vision self-review of own output | **Y** Reviewer on contact sheets and cut strips | P second pass checks the edit diff, not frames (May 2026) [1] | ? | ? | ? | ? | ? | N | P [15] | ? | P [19] | ? |
| Quality judge calibrated against human labels | **P** mechanism built; 0 owner labels on disk; 1 auto run (6 pro finals + injected defects), 1 gate eligible to block | **Y** LLM judge calibrated to human reviewers [2, verified] | ? | ? | ? | ? | ? | ? | ? (online thumbs-down only) | ? | ? | ? |
| Eval set and regression gating | **P** 6 English gold pairs; `reel improve` accepts only on eval gain | **Y** 100+ real-query cases; 3 axes; moving to multi-turn [2, verified] | ? | ? | ? | ? | ? | P external benchmark rank [14] | P online metrics [15] | ? | ? | ? |
| Cost shown or capped before running | **P** cost logged per Claude call; no pre-run estimate | Y always-on credit meter [1] | P minutes-credits; failed edits not refunded [3] | Y estimate range, max charged [5] | P | Y generative credits | P | Y "ask before generating" with cost estimate [13] | **Y** approve estimate, interrupt refunds unused [15, verified] | P monthly quotas | P | P (users complain it's opaque) |
| Caching / partial re-render | **Y** content-hash stage cache + changed-frame overlay splice and audio-only remux (G1.5, commit 6ab7999) | ? | ? | ? | ? | P NLE render cache | ? | P Aleph bills only the edited range [13] | P "Recreate with Kai" per asset | ? | ? | ? |
| Revision: text-based (edit transcript → video) | **N** (story-line toggles planned, C4) | Y core product | Y | Y | Y | Y | Y | N | ? | Y | Y | P cut-to-script |
| Revision: chat | **Y** `revise`, client notes | Y | P | Y | Y (EditPilot, PC) | Y (beta) | Y | Y | Y | Y | Y | Y |
| Revision: manual timeline | **P** Adjust panel; full timeline via NLE export | Y | Y | Y | Y | Y | Y | Y | Y | P | P | Y |
| Human checkpoints and revert | **Y** Sendable/Hold verdict, version restore, hook A/B preview (G1.6) | Y revert per agent turn [1] | P | P undo/versions | P | Y | P | Y | Y | ? | P | Y |
| Brand kit | **Y** brand kit with locks; voice (G1.1) | P Business tier | Y Brand Kit + Recipes [4] | P Enterprise | P | P | Y | Y | Y | Y | Y | P |
| Style learning from past edits / reference | **P** reference-video analysis per project; no per-client memory | N | P "edits to match a style" (4.0, marketing) | P reference videos as input [5] | ? | P reusable brand settings [9] | ? | P Skills from past conversations [13] | P claims "learns from your edits" [16] | P Iris copies a reference video [17] | P "edit like my last video" [20] | P persistent Context [21] |
| Licence/rights handling | **Y** registry, refusal before ranking, manifest, ledger | ? | P | ? | P C2PA on generations; broad ToS licence over user content [8] | Y Firefly "commercially safe" + C2PA export [10] | P stock + Epidemic | Y C2PA + watermark [14] | P | P | P | P |
| Hindi / Hinglish | **Y** Hinglish ASR, Devanagari, danda, lakh/crore (not yet client-tested) | P Hindi beta; sources conflict [1] | **N** not in the language list [4] | P Hindi + Hinglish dubbing; captions unverified [6] | **N** blocked in India [7] | P Hindi STT + translation; INR pricing [10] | P Hindi ASR + dub [12] | ? | ? | P Hindi ASR; ₹ pricing [18] | P | P Hinglish TTS (Sarvam) [22] |
| NLE export | **Y** FCPXML + OTIO + stems + alpha overlay | Y XML/FCPXML/AAF/EDL | Y XML (Pro) | N | N | Y (it is the NLE) | P subtitles only | P plugins, ProRes | N | ? | P subtitles only | ? |
| Review links / collaboration | **P** private review links + notes, **only on this Mac** | Y | P | P | ? | Y Frame.io | P Enterprise only | Y | Y frame-accurate comments | ? | P | Y |
| Publish / schedule | **N** | P YouTube, LinkedIn | Y 9 platforms [3] | P | P | P | ? | ? | ? | Y IG, TikTok, YT [17] | Y | ? |
| Learning from post performance | **N** | N | N (pre-post score only) | N | N | N | ? | N | ? | P dashboard, no feedback | N (pre-post score) | ? |
| Many clips from a long video | **N** (roadmap) | Y | Y core | Y | Y | N | Y | P | Y | Y | Y core | P |
| Aspect variants / reframe | **Y** 4:5 and 1:1 variants, face-tracked crop | Y | Y | P | Y | Y | Y | P | Y | ? | Y | Y |
| Generative (TTS, dub, lip-sync, AI b-roll, eye contact) | **N** (voice enhancement only) | Y | P | Y | Y | Y | Y | Y strongest | Y | P eye contact | P | Y |
| Price of the agent tier (checked 2026-11-20) | Claude cost per reel; one Mac, no GPU | Creator $24–35/mo | $15–29/mo | $24.99/mo (iOS) | ~$20/mo, unconfirmed | $22.99/mo; assistant needs CC Pro ($69.99) | $25–45/mo | $15–95/mo | $16–50/mo | ₹1,999/mo (Pro, 6 Iris edits) | ~$15/mo | $9–160/mo |

Notes:
- **Munch** pivoted to an AI social-media manager: strategy, approve, publish, performance dashboard. It is no longer a clipper ([munchstudio.com/pricing](https://www.munchstudio.com/pricing), 2026-11-19).
- **Meta Edits** is free and has no editing agent:
  - Its AI assistant, which reads Instagram retention data, is invite-only testing.
  - It already lets creators make "multiple versions" to test before publishing.
  - Source: TechCrunch, 2026-06-11.
- **DaVinci Resolve 21** (NAB 2026) adds IntelliScript (script → assembled timeline), IntelliSearch and AI face tools. Resolve 21.1 reportedly ships a native MCP server in Studio, per trade press only.

### 2b. Open-source agentic editors and benchmarks (harness rows only)

OpenMontage, OpenEdit, CutClaw and vidpipe come from our own code reading in `research_notes/oss-reverse-engineering/`. The other columns are from READMEs and papers.

| Harness capability | **Ours** | OpenMontage | OpenEdit (VEED) | vidpipe | CutClaw | video-use | Diffusion Studio editor | ffmpeg-skill | Timeline-Bench (benchmark) |
|---|---|---|---|---|---|---|---|---|---|
| Structured plan | Y | P YAML pipelines + prompt skills; free tool calls by the IDE agent | P an HTML page is the edit | P | P screenwriter → editor | P EDL | Y JSX with an id per node | Y typed tool contract, `--plan` dry run | n/a |
| Code-enforced validation | Y | P checkpoint gates | P tools report, never silently fix | P | P | P "12 hard rules" | Y `check` | Y typed errors; "unknown is not missing" | Y 153 programmatic tests |
| Pixel/audio QA | Y | P thin; docstring overclaims | P | N | P ±1 s tolerance | Y re-checks each cut boundary | P | P | Y |
| Vision self-review | Y | P (skill only) | Y frame review loop | N | P; aesthetic check never called | Y, ≤3 re-renders | P `capture` contact sheet | P | Y 3-VLM panel |
| Calibration against humans | P (mechanism; no labels yet) | N | N | N | N | N | N | N | Y 2,582 editor A/B judgments |
| Eval set | P | N | ? | N | P paper only | N | N | N | Y 56 tasks |
| Cost control | P | Y estimate → reserve → reconcile | Y quote → approve, bound to a hash; dedupe ledger | P cost report | ? | N | N | N | n/a |
| Caching / partial re-render | Y | Y content-addressed tool cache | Y 2 s segment re-render | ? | ? | N | N | Y plan fingerprints | n/a |
| Human edits survive a re-plan | ? (see §4 idea 7) | N | N | N | N | P `project.md` memory | Y UI edits written back to code | n/a | n/a |
| Licence gate | Y | P records only | ? | N | N | N | N | N | n/a |
| Hindi/Hinglish | Y | N | P generic translation | N | N | N | N | N | N |
| NLE export | Y | ? | N | N | N | N | N | N | n/a |
| Publish | N | N | N | Y schedule + Late API | N | N | N | N | n/a |

Other repos with traction, summarised in §4 where relevant:
- **openfilm**: user overrides kept separate from agent code. 8.5k★, MIT, README.
- **OpenChatCut**: agent changes arrive as proposals on an isolated draft. AGPL, README.
- **openmotion**: breaks a reference video down into `Motion.md` and rejects stale writes. Apache-2.0, README.
- **HyperFrames**: golden-MP4 regression tests. Apache-2.0.
- **davinci-resolve-mcp**: a verification block on every result, and an acknowledge-guard on irreversible operations. 4.2k★, MIT.

---

## 3. Features others have that we don't (ranked)

**Score = value × feasibility**, each scored 1 to 5:
- **Value** is the value to a freelance editor serving Indian creators and brands: client-visible wow, repeat business, and saved owner time.
- **Feasibility** follows effort and risk: S = 5, S–M = 4, M = 3, L = 2, XL or blocked = 1.

These are my judgements. The arithmetic is shown so the order can be re-weighted.

**Roadmap tag:**
- **ROADMAP**: already in `roadmap.md`, `oss-feature-gap-plan.md` or `ui-backend-plan.md`.
- **PARTLY**: a smaller version is planned.
- **NEW**: not planned anywhere.

| # | Feature | Who has it (evidence) | Our state | Value | Feas. | Score | Tag |
|---|---|---|---|---|---|---|---|
| 1 | **Review links that work outside this Mac**, with frame-accurate comments | Kapwing [docs], Frame.io/Adobe, Descript, Runway Team [changelog] | Links and notes exist, but the studio binds 127.0.0.1 only (`studio/server.py` `HOST`; `review_links.py` says a tunnel is needed) | 5 | 4 | **20** | PARTLY (E3 is an "owner decision"; frame-accurate comments are NEW) |
| 2 | **Story-plan check-in before the finish pass and render**: plain-language plan; ask only the open decisions | Firefly Plan Mode [marketing], Descript Oct 2026 [changelog], Kapwing checklist [changelog], InVideo [marketing] | Story plan exists as JSON but goes straight to finish and render | 4 | 4 | **16** | PARTLY (G1.6 hook A/B and C4 story edits are close; a plan approval stop is NEW) |
| 3 | **Per-client style memory: "edit like my last approved reel"** | Vizard [marketing], Submagic Iris [changelog], Runway Skills [changelog], InVideo Context [marketing], OpenStoryline/openmotion [README] | Reference-video analysis per project; brand kit locks; `improve` is global, not per client | 5 | 3 | **15** | **NEW** |
| 4 | **Many reels from one long recording (Clip Factory)** | OpusClip, Vizard, Submagic, Captions, Kapwing, VEED [docs] | None | 5 | 3 | **15** | ROADMAP (group 2) |
| 5 | **Text-based editing**: strike words or lines in the transcript to cut | Descript, Premiere, VEED, Submagic, OpusClip, Vizard [docs] | Only by chat or notes | 4 | 3 | **12** | PARTLY (C4 line-level drop/reorder; word-level is NEW) |
| 6 | **Pre-run cost estimate with a cap**, quote → approve for paid calls | Kapwing [verified], Runway, Captions [docs], OpenEdit [code] | Cost logged after each call | 2 | 5 | **10** | NEW (OpenMontage A2 was "just below the line", never scheduled) |
| 7 | **AI b-roll generation** when stock has no match | Submagic, Captions, Kapwing, Runway, InVideo | Stock + client folder only | 3 | 3 | **9** | ROADMAP (known gap: generative assets) |
| 8 | **Hindi/Hinglish dubbing and Indic TTS** | Captions (Hindi, Hinglish, Tamil dub) [docs], VEED [marketing], InVideo + Sarvam Bulbul v3 Hinglish TTS [marketing], Dubverse | None | 4 | 2 | **8** | ROADMAP (#11, group 3). Sarvam Bulbul is a NEW provider candidate to test against Maya 2 / ZONOS3 |
| 9 | **Post-performance feedback**: pull `reels_skip_rate` and retention per delivered reel, report to the client, feed the brand profile | Nobody closes this loop. Meta Edits assistant in testing [marketing]; dashboards at Submagic and Munch [changelog/docs]. Instagram API added `reels_skip_rate` and trial-reel publishing on 2025-12-03 [docs, verified] | None | 4 | 2 | **8** | **NEW** (needs the publishing account connection, roadmap group 4) |
| 10 | **Publish and schedule** to Instagram and YouTube | OpusClip, Submagic, Vizard, Munch | None | 3 | 2 | **6** | ROADMAP (#13, group 4) |
| 11 | **Eye-contact correction** | Descript, Captions, Submagic Pro [docs] | None | 3 | 2 | **6** | **NEW** (needs a commercial-safe model; the licence check comes first) |
| 12 | **Multiple versions for a real-audience test** (Instagram trial reels) | Meta Edits "multiple versions" [marketing]; IG `trial_params` [docs, verified] | Hook A/B for the client only (G1.6) | 3 | 2 | **6** | NEW (extends G1.6 once publishing exists) |
| 13 | **Public API/MCP** so other agents can drive us | OpusClip, Submagic, VEED, Runway, Descript | CLI only | 1 | 3 | 3 | NEW. Skip: no value for one owner on one Mac |

Not counted because the craft-level teardown already covers it and the feature is planned or present:
- beauty pass, partial re-render and SFX/music generation: roadmap;
- studio sound: we have DeepFilterNet;
- auto-reframe: have.

Why #1 sits first despite being "small":
- A freelancer's client is on a phone, not on the owner's Mac.
- Without remote review, the whole notes → revise loop runs through WhatsApp screenshots.
- Every commercial tool with collaboration ships this.
- It is a security decision (`ui-backend-plan.md` E3). Options: a tunnel the owner turns on, or uploading only the rendered MP4 and the notes page to a static host with expiring tokens.

---

## 4. Harness ideas worth stealing

Each idea is mapped to the stage where it would go. Ordered by expected effect on *proven quality*, which §1 found is our weakest point.

1. **Accept `reel improve` changes on statistics, not on score movement.**
   - Evidence: Timeline-Bench [paper]. Its VLM judges agree with humans barely per edit (κ ≈ 0.15) but well when ranking whole agents (ρ = 0.93). About 1.9k words of editing advice gave a gain that was not significant.
   - Map: in `improve.harness_evaluator`, require a paired, significance-tested win across the whole gold set.
   - Prerequisite: grow the gold set well beyond 6 English pairs and add Hindi/Hinglish pairs. With 6 pairs no delta can pass an honest test.
   - Collect *pairwise* or repeated owner labels: one-off labels are noisy (α ≈ 0.10 in their data).
2. **Pacing gates measured on the render.**
   - Evidence: Timeline-Bench [paper]. Agents' clearest measurable gap was cuts per minute (0.72× the reference) and the longest static stretch (1.5× the reference).
   - Map: QA gains `cut_rate` and `longest_static_s`, compared against the reference video's style analysis or a genre band, in warn mode, then calibrated like the other gates.
   - Give the Reviewer these numbers next to its contact sheet, as Timeline-Bench's judges get them.
3. **Pairwise judging in both orders, with order-dependent verdicts counted as ties.**
   - Evidence: Unified Agentic Video Editing, arXiv 2609.12769 [paper]. EditDuet [paper] shows a pairwise judge on keyframe grids matched human–human agreement (80.6% vs 78.7%).
   - Map: the `reel eval` scoreboard compares *ours vs pro* pairwise rather than with absolute scores. The same harness can pick between hook A/B (G1.6) when no client is waiting.
4. **A rubric frozen per brief, written before any output exists.**
   - Evidence: VideoArgus, arXiv 2608.05485 [paper].
   - Map: at the STORY stage, a cheap call (or code) turns the brief, transcript summary and brand into a rubric of 5–8 checkable criteria, saved in `plan/`.
   - The Reviewer at QA scores against that file and may not rewrite it. This stops the judge drifting toward whatever the Editor made, and makes "brief compliance" auditable.
5. **The verdict comes from gates, never from the agent's own claim.**
   - Evidence: Timeline-Bench [paper]: 93% of runs claimed full success, including 95.5% of runs that failed a test.
   - Map: the `revise` chat reply and the Studio summary must be built from the QA results (`verdict_plain.py`), not from Claude's summary text.
   - Check the current revise reply path for any place where Claude's prose can say "done" or "fixed" while a gate is open. [inference: not checked in code]
6. **"Unknown is not missing", plus an explicit unverified list.**
   - Evidence: ffmpeg-skill [README]; davinci-resolve-mcp's verification block [README].
   - Map: a gate that can't measure (no face found, OCR failed) returns `not_measured` and counts as Hold-worthy, never as a pass.
   - The verdict lists what was *not* checked (for example "music taste", "joke timing") so the owner knows where to look.
7. **Owner edits stored as an overrides layer that survives a re-plan.**
   - Evidence: openfilm `overrides` [README]; OpenChatCut draft and proposal sessions [README]; openmotion stale-write rejection [README].
   - Map: Studio Adjust and `proof` corrections write to a separate `plan/overrides.json`, applied after compile. When a revision re-runs the Editor, compile re-applies the overrides and reports any that no longer fit, instead of losing them.
   - Today `_apply_adjust` (`studio/app.py:872`) writes straight into `plan/finish.json` [code]. A later Editor re-plan of the finish pass regenerates that file, so manual adjustments are at risk of being lost [inference: the revise path was not traced].
8. **Revision evals: "don't break things".**
   - Evidence: Descript's three axes ("Don't break things / Do what I asked / Do it well") and its move to multi-turn evaluation [verified].
   - Map: add revision cases to the eval set: a project, a client note, and the expected region.
   - Use `rediff.py`, already being built for G1.5, to check that the revision changed **only** the frames the note asked about.
   - We are unusually well placed for this, because our timeline is declarative.
9. **Plain-language plan check-in that asks only the open decisions.**
   - Evidence: Descript changelog, Oct 2026.
   - Map: an optional stop after STORY, the same mechanism as G1.6's `awaiting_choice` status. It shows the kept lines, the hook and the order in one paragraph, plus at most 2 questions ("keep the joke at 0:41?").
   - It costs no extra Claude call if the questions come from the story pass's own low-confidence decisions.
10. **Sample a few story orders and select.**
    - Evidence: From Shots to Stories / StoryFlow, arXiv 2505.12237 [paper].
    - Map: the story pass returns 2–3 candidate orders, and the Reviewer, or the pairwise judge from idea 3, picks one.
    - It costs one more Claude call per edit, so keep it opt-in until evals show it helps.
11. **Quote → approve, bound to a hash, for paid calls.**
    - Evidence: OpenEdit [code]; Kapwing [verified].
    - Map: when the group 3 generative providers arrive, every paid call (TTS, AI b-roll, lip-sync) needs an approval tied to the input hash, plus a content-keyed ledger so an identical request is never bought twice.
    - Show the estimate in New Edit.

---

## 5. Sources and evidence notes

Commercial (pages undated unless a date is given; all accessed 2026-11-20):
1. Descript help and changelog. Underlord co-editor, plan check-in (2026-10-13), second-pass review (2026-05-14), revert bar (Feb 2026), credit meter (2026-06-11), Hindi (Beta), timeline exports:
   - https://help.descript.com/getting-started/underlord-beta-your-ai-co-editor-in-descript.md
   - https://feedback.descript.com/changelog
   - https://help.descript.com/export-and-share/timeline-exports.md
   - https://help.descript.com/hc/en-us/articles/10249408168845 [docs/changelog]
2. Descript × Anthropic case study: LLM judge calibrated to human reviewers, 100+ cases, three axes, multi-turn. https://claude.com/customers/descript [marketing; re-fetched and quoted]
3. OpusClip credits, scheduling, Agent Opus:
   - https://help.opus.pro/docs/article/plans-and-credits.md
   - https://help.opus.pro/docs/article/schedule-clips.md
   - https://help.opus.pro/agent-opus/prompt-guide.md [docs]
4. OpusClip languages (no Hindi), Brand Kit + Recipes, virality score:
   - https://help.opus.pro/docs/article/video-languages-supported.md
   - https://help.opus.pro/docs/article/how-do-recipes-and-brand-kit-work-together.md
   - https://help.opus.pro/docs/article/virality-score [docs]
5. Captions AI Edit, changelog and credit estimates:
   - https://captions.ai/help/docs/project/ai-edit
   - https://captions.ai/help/whats-new.md
   - https://captions.ai/help/docs/ai-usage [docs/changelog]
6. Captions dubbing (Hindi, Hinglish, Tamil): https://captions.ai/help/docs/captions/dubbing [docs]
7. CapCut EditPilot, https://www.capcut.com/tools/edit-pilot [marketing]. India block since 2020; no reinstatement found (Inc42, exchange4media 2025) [inference]. APK teardown from androidsage.com, 2026-10-23 [inference].
8. CapCut terms of service: https://capcut.com/resource/about-capcut-terms-of-service [docs]
9. Adobe Premiere AI Assistant beta (2026-06-18) and MAX 2026 (2026-11-10). Firefly Plan Mode reported by thenextweb:
   - https://news.adobe.com/news/2026/06/adobe-unveils-major-expansion
   - https://digitalproduction.com/2026/11/10/adobe-max-2026-ai-video-audio-premiere-creative-agent/ [marketing]
10. Adobe Content Credentials and Hindi STT/translation with INR pricing:
    - https://helpx.adobe.com/x-productkb/content-credentials.html
    - https://blog.adobe.com/en/publish/2024/10/14/generative-extend-in-premiere-pro
    - adobe.com/in/products/premiere/plans.html [docs/marketing]
11. VEED AI and AI Agent:
    - https://changelog.veed.io (2026-11-19)
    - https://veed.io/blog/introducing-ai-agent-by-veed
    - https://www.veed.io/pricing/plans.md [changelog/marketing/docs]
12. VEED Hindi translation and dubbing: https://www.veed.io/tools/video-translator/english-to-hindi-video [marketing]
13. Runway:
    - Agent (2026-05-13): https://runway.com/news/introducing-runway-agent
    - Aleph 2 and Edit Studio (2026-05-21): https://runway.com/news/introducing-aleph-2-and-edit-studio
    - Workflows help: https://help.runwayml.com/hc/en-us/articles/53645211363475
    - Aleph partial billing: https://help.runwayml.com/hc/en-us/articles/51683104370451
    - Changelog: https://runway.com/changelog [docs/changelog]
14. Runway engineering blog (2026-07-17) and C2PA:
    - https://runway.com/news/engineering/inside-building-runway-agent
    - https://runway.com/research/foundations-for-safe-generative-media [eng-blog/docs]
15. Kapwing release notes, August 2026 (updated 2026-09-01). Estimate approval, interrupt-refund, checklist, "validate the output after generating, self-correcting errors". https://www.kapwing.com/help/release-notes-august-2026-2/ [changelog; re-fetched and quoted]
16. Kapwing, "Giving AI a canvas to paint on" (2025-11-18): https://www.kapwing.com/blog/giving-ai-a-canvas-to-paint-on/ [eng-blog]
17. Submagic changelog (Iris, 2026-11-18; publishing, 2026-03-04 / 2026-06-08) and API docs:
    - https://submagic.canny.io/changelog
    - https://docs.submagic.co [changelog/docs]
18. Submagic pricing in INR and Hindi:
    - https://www.submagic.co/pricing
    - https://www.submagic.co/hi/languages-supported [docs/marketing]
19. Vizard Agent:
    - Launch post (2026-08-10): https://vizard.ai/blog/the-next-shift-in-ai-is-coming-to-video [eng-blog]
    - Self-check example (2026-10-10): https://agent.vizard.ai/how-to/have-a-new-video-edited-exactly-like-your-last-one.html [marketing]
20. Vizard "edit like my last video": same how-to page [marketing]
21. InVideo Agent Two Workflows (2026-08-08) and agentic editor:
    - https://invideo.io/news/introducing-workflows-invideo-agent-two/
    - https://invideo.io/make/agentic-video-editor/ [marketing]
22. InVideo with Sarvam Bulbul v3 (2026-08-06): https://invideo.io/blog/sarvam-bulbul-indian-tts/ [marketing]

Other platforms and context:
- Meta Edits AI assistant and desktop version (2026-06-11): https://techcrunch.com/2026/06/11/metas-edits-app-is-getting-an-ai-assistant-and-a-desktop-version/ [marketing; re-fetched]
- Instagram Platform changelog, 2025-12-03: `trial_params` in the Content Publishing API and the `reels_skip_rate` media insight. https://developers.facebook.com/docs/instagram-platform/changelog [docs; re-fetched]
- DaVinci Resolve 21 (NAB 2026): https://macrumors.com/2026/04/14/davinci-resolve-21-photo-editing-ai-search/ [marketing]
- Resolve 21.1 MCP: https://ymcinema.com/2026/09/17/davinci-resolve-21-1-mcp-ai-assistants-control-edit/ [marketing]
- Adobe MCP preview: https://techcrunch.com/2026/11/10/adobe-adds-more-ai-to-its-products-and-launches-an-mcp/ [marketing]
- Munch Studio: https://www.munchstudio.com/pricing [docs]
- India-focused captioners (Kalakar, Supercaptions, Dubverse) are known only from aggregator pages. None is an agentic editor, so they are left out of the matrix.

Open-source projects (stars from the GitHub API, 2026-11-19/20):
- https://github.com/browser-use/video-use (31.3k★, MIT)
- https://github.com/diffusionstudio/editor (3.5k★, MPL-2.0)
- https://github.com/kajisho5/ffmpeg-skill (8.3k★, MIT)
- https://github.com/openfilm/openfilm (8.5k★, MIT)
- https://github.com/0xsline/OpenChatCut (3.2k★, AGPL-3.0: ideas only)
- https://github.com/nexu-io/openmotion (12.8k★, Apache-2.0)
- https://github.com/FireRedTeam/FireRed-OpenStoryline (3.7k★, Apache-2.0)
- https://github.com/heygen-com/hyperframes (87k★, Apache-2.0)
- https://github.com/samuelgursky/davinci-resolve-mcp (4.2k★, MIT)
- https://github.com/hetpatel-11/Adobe_Premiere_Pro_MCP (900★, MIT)
- https://github.com/sun-guannan/VectCutAPI (2.4k★, Apache-2.0)

Papers:
- Timeline-Bench, https://arxiv.org/abs/2609.35143 (2026-09-28). The abstract and the HTML body (https://arxiv.org/html/2609.35143v1) were re-fetched. Verified:
  - 56 tasks, 16 agents, best 26.8%, average 14%;
  - 2,582 judgments from 43 editors;
  - κ = 0.15 per edit (human vs human 0.14), ρ = 0.93 across agents, α = 0.10 for single human judgments;
  - 0.72× the shot-change rate and 1.5× the longest static shot;
  - 93% / 95.5% overclaiming;
  - 5.5% vs 66% of issues about pacing or story;
  - editorial guidance gave 21.4% → 26.8% resolved, which is not significant (Holm p = 1.00).
- AgenticVBench, https://arxiv.org/abs/2605.27705
- Unified Agentic Video Editing, https://arxiv.org/abs/2609.12769
- EditDuet, https://arxiv.org/abs/2509.10761
- VideoArgus, https://arxiv.org/abs/2608.05485
- From Shots to Stories, https://arxiv.org/abs/2505.12237
- VEU-Bench, https://arxiv.org/abs/2504.17828: off-the-shelf VLMs are weak at editing grammar, which is a caution for our Reviewer.
- Engagement prediction:
  - SnapUGC / VQualA 2025: https://arxiv.org/abs/2410.00289 and https://arxiv.org/html/2509.02969v1
  - Best SROCC is about 0.71 for 5-second continuation rate. Usable for coarse ranking, **not** as a gate on one reel [inference].
  - This is why feature §3 #9 reports retention to the client and adjusts the brand profile slowly; it does not optimise edits against a predicted score.

**Our own column**, checked in code on 2026-11-20:
- `reel calibrate` (owner labels + `--auto` injected defects), `reel eval` and `reel improve` exist in `engine/src/reel/cli.py`;
- review links: `studio/app.py` `review_links_*`;
- version restore: `studio/projects.py` `restore_plans`;
- FCPXML/OTIO: `package.py`;
- per-call cost: `claude_call.py` `cost_usd`;
- variants: the `VARIANTS` stage;
- calibration state: `find` gave 0 `owner_label.json` files outside the venvs and worktrees;
- `eval/calibration/auto_latest.json` (2026-11-19):
  - `frozen` is the only gate with `promote_to_block` true; `loudness` is already in block mode;
  - `caption_contrast` caught 0/10 "wrong colour" defects;
  - `black` raised 2 false alarms on 6 pro finals.

Partial re-render, hook A/B preview and Studio phases 1–2 landed in commit 6ab7999 (G1.5–G1.7), so they count as built. "Only on this Mac" for review links comes from `docs/product/ui-backend-plan.md` E3.
