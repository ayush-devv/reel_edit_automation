# Short-form craft brain: research report

Tags: [platform] (incl. Netflix), [platform-ad] (ad docs only), [study], [practitioner], [theory], [heuristic] (my tunable default). UNVERIFIED = not confirmed on a primary page.

## 1. Platform guidance
- **TikTok** (ad docs, [Ads Help](https://ads.tiktok.com/help/article/creative-best-practices?lang=en)): state the proposition in the first 3s; hook within 6s; 9:16 at ≥720p; use sound or music; use transitions, stickers and graphics; DIY over polished; text at "5–10 words per second", which is faster than broadcast reading speeds.
- **Instagram** ([Reels tips](https://creators.facebook.com/reels-best-practices-tips-tricks), [originality](https://creators.instagram.com/original-content-guidelines/)): open with the point; give it a payoff (reveal, punchline, twist); transitions drive rewatches; no watermarks, recycled clips or low-res footage.
  - Mosseri's signals (watch time, likes per reach, sends per reach) are secondhand.
  - Reels over 3 min are not recommended to non-followers.
  - Buffer, 2.7M reels ([link](https://buffer.com/resources/instagram-reels-length)) [study]: every bucket under 90s fell within ±3% of baseline reach; 180s+ was −49%.
- **YouTube** ([Help 12220281](https://support.google.com/youtube/answer/12220281)): "Stayed to watch" = the share who stayed past the initial seconds. Shorts can run up to 3 min (secondary).
- **Safe zones:** no platform publishes one for organic posts. The ad templates below are pixel values from third-party sites:
  - Meta Reels: 14% top / 35% bottom / 6% sides.
  - TikTok: about 240 top / 660 bottom / 120 sides.
  - Google Shorts: 288 top / 672 bottom / 48 left / 192 right.
  - Their intersection on 1080×1920 is **x 120–888, y 288–1248**.

## 2. Hook craft
- **Channels** [practitioner] ([captions.ai](https://captions.ai/blog/video-hooks-how-to-write-a-scroll-stopping-opening), [vidico](https://vidico.com/news/best-video-hooks/)): stack visual, verbal (5–8 words) and written (3–5 words).
- **Types:**
  - Specific question (not yes/no)
  - Bold or contrarian claim, backed up fast
  - Result-first or proof-first
  - Pattern interrupt that relates to the content
  - Statistic
  - Pain point
  - Value promise
  - In medias res

  Unpaid open loops get swipe-backs.
- **Data:**
  - [shortformkit](https://github.com/shortformkit/short-form-video-hook-study-2026) (167 videos from 21 large creators, self-published 2026-11-17): 58% had text on the 0.3s frame; 84% of talking videos had speech within 2s.
  - Facebook IQ 2016 ([summary](https://www.socialmediatoday.com/news/facebook-releases-new-guide-to-help-advertisers-maximize-video-ad-performan/450818)): 0.25s of exposure is enough for recall; mobile dwell averages 1.7s.
  - Hook objective: SnapUGC's ECR = P(watch > 5s) ([arXiv 2410.00289](https://arxiv.org/abs/2410.00289)).

## 3. Pacing & retention
- **shortformkit** [study], hard cuts only (zooms excluded): median shot 2.3s (Reels 2.2, Shorts 2.3, TikTok 3.1); about 25 cuts/min (TikTok 17); first cut at a median of 2.6s; 13% of videos have no cut.
- **Hollywood:** average shot length was about 3–4s by 2005 ([Cutting 2010](https://doi.org/10.1177/0956797610361679)).
- **Timeline-Bench (0.72× pace, slowness penalized):** this comes from your brief. The [abstract](https://arxiv.org/abs/2609.35143) reports only that editors prefer the reference edit in 83.5% of judgments. The pacing figures are UNVERIFIED.
- **TikTok brand study** ([arXiv 2606.16053](https://arxiv.org/abs/2606.16053), about 10K Estonian brand videos): a search snippet marked editing pace significant on all four metrics, but the effect sizes and direction are UNVERIFIED, and most other variables were null.
- **Cut mechanics:** [video-use](https://github.com/browser-use/video-use) SKILL.md (rules 9–10).
- **Punch-ins** [practitioner]: 110–120% on jump cuts; +20% instant on emphasis. No data found for speed ramps.

## 4. Captions
- **Netflix English** ([guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-USA-Timed-Text-Style-Guide)): 20 cps for adults, 17 for children; 42 characters per line; 2 lines; never split article+noun; events last 5/6–7s.
- **BBC** (via secondary sources): 160–180 wpm, about 3 words/s.
- **Social style** [practitioner]: word-by-word with karaoke highlighting of the active word; 1–3 words; all-caps bold sans; one colored emphasis word; sparse emoji. The Hormozi package is called saturated.
- **Font size:** no authoritative source (UNVERIFIED).

## 5. Sound design
- **Loudness:** no platform publishes a target. −14 LUFS / −1 dBTP is the consensus [practitioner]. YouTube's −14 normalization is widely reported but undocumented; AES TD1008 suggests about −17 for mixed speech and music.
- **Ducking** [practitioner]: estimates run from −12 to −25 dB. video-use ducks 12–15 dB below the unducked bed; tutorials start the bed 18–22 dB under voice.
- **Music choice:** in the brand-TikTok study, trending songs were associated with fewer likes (−0.38) and saves (−0.55, log scale), and original spoken audio with more shares (+0.45) [study].
- **SFX** [practitioner]: whoosh on whip transitions; pop on text; riser into a reveal; hit on punch-ins. About 8 SFX reads as designed; about 20 reads as generic (video-use).

## 6. B-roll & visuals
- **J/L cuts:** a 6–12 frame lead at 30fps ([CapCut](https://www.capcut.com/create/j-cuts-and-l-cuts-dialogue-edits), single vendor source).
- **Cut on action:** Smith's AToCC ([2012](https://ualresearchonline.arts.ac.uk/id/eprint/21187/)) reports that viewers missed about a third of match-action cuts versus a tenth of scene cuts.
- **B-roll duration:** 1.5–3s is a convention (UNVERIFIED).
- **Color:** no authoritative norms; platforms only penalize blur and low resolution.

## 7. Film theory
Murch's Rule of Six weights emotion 51%, story 23%, rhythm 10%, eye-trace 7%, 2D 5%, 3D 4%. Never sacrifice a higher criterion for a lower one ([summary](https://cloud.wikis.utexas.edu/wiki/spaces/rtf318/pages/80022510/Murch+s+Rule+of+Six)). Encoded as rules 13, 24, 26 and 27: pick the peak-emotion take and cut at phrase boundaries.

## 8. Measuring reference reels
- **Cut detection:** [PySceneDetect](https://www.scenedetect.com) (AdaptiveDetector); [TransNetV2](https://arxiv.org/abs/2008.04838) (F1 0.967 vs 0.889); ffmpeg `scdet` at threshold 8 with a 0.4s merge (the shortformkit method).
- **Cut types:** [MovieCuts](https://github.com/PardoAlejo/MovieCuts) has 10 cut types across about 174K clips.
- **Learned style:** ESA (energy-based shot assembly) claims to learn style from references (UNVERIFIED).
- **Speech:** word timestamps from Whisper or Scribe give speech rate and pauses. First-word times from Whisper are unreliable.
- **Zooms:** scene detectors miss them. Detect them from jumps in face-box scale.
- **Style vector:** shot-length median and CV, cuts/min, first cut, first word, text at 0.3s, words/cue, caption y, zooms/min, SFX/min, LUFS.

## Playbook rules for Claude
1. Hook text (3–5 words) on screen by 0.3s. [study/practitioner]
2. First spoken word ≤0.3s; hard limit 2.0s. [heuristic; study: 84% <2s]
3. Proposition stated by 3.0s. [platform-ad]
4. Hook reads with sound off. [platform-ad]
5. Every open loop is paid off; the payoff matches the hook. [platform/practitioner]
6. Hard cuts ≥17–25/min; median shot 2–3s. [study]
7. Visual changes including punch-ins and b-roll ≥20/min; no unchanged framing longer than 4s. [practitioner]
8. If unsure, cut tighter. [brief: Timeline-Bench, UNVERIFIED]
9. Remove silences ≥400ms; review 150–400ms; never cut inside a word or a gap under 150ms. [practitioner]
10. Pad cut edges 30–200ms; 30ms audio fade at every cut. [practitioner]
11. Alternate jump-cut scale 100% ↔ 110–120%. [practitioner]
12. Emphasis: instant +15–25% punch-in, at most one every 4s. [practitioner; rate is heuristic]
13. Across a jump cut, the face center moves ≤10% of frame width. [heuristic from eye-trace theory]
14. Prefer cut points on gestures or motion. [study]
15. Captions: 1–3 words per cue, word-synced; cue ≥0.35s; break at punctuation or pauses ≥0.3s. [practitioner]
16. Static text: ≤20 cps, ≤42 characters per line, ≤2 lines, on screen 0.83–7s. [platform]
17. Text and faces inside x 120–888, y 288–1248. [platform-ad, pixel values secondary]
18. ≤1 highlighted word per cue; ≤1 emoji per sentence. [practitioner]
19. Master to −14 LUFS integrated, ≤−1 dBTP, with two-pass loudnorm. [practitioner]
20. During speech, the music stem's short-term LUFS is ≥18 dB below the voice stem's. [practitioner]
21. Prefer original audio or a neutral bed over trending songs. [study, brand-only]
22. SFX only on visible events; ≤8 per 60s; never the same SFX on consecutive cuts. [practitioner]
23. Whoosh length = transition length ±100ms; riser ends on the reveal frame; hit on the punch-in frame; pop on text-in. [practitioner]
24. B-roll on concrete nouns, numbers or claims that need proof; 1.5–3s each; never over peak emotion. [practitioner/theory]
25. J-cut audio leads new sections by 6–12 frames. [practitioner]
26. Delete restatements; each segment adds new information. [theory]
27. Never trade a stronger performance for smoother rhythm. [theory]
28. Length set by content; cap at 180s. [platform/study]
29. End ≤0.5s after the last word; prefer a loopable ending. [practitioner]
30. QA: output style vector within ±20% of the reference reel's. [heuristic]
