# Features other open-source editors have that we don't: gap list and build plan (2026-11-19)

**Method.** I read the source code of four open-source tools and ran none of them:
- OpenMontage (AGPL-3.0)
- VEED OpenEdit (Apache-2.0)
- vidpipe (ISC per its package.json; no LICENSE file)
- CutClaw (no licence, so all rights reserved)

The full reports, with mechanisms, file paths and what was read in code versus only claimed in a README, are in `research_notes/oss-reverse-engineering/`.

**Rules for reuse:**
- OpenMontage and CutClaw: we rebuild the ideas clean-room; no code is copied.
- OpenEdit and vidpipe: we may port code with attribution and their NOTICE text.

**What we already do better.** Their talking-head pipelines are shallower than ours:
- OpenMontage's is marked beta: it transcribes, cuts silences, adds subtitles and renders.
- CutClaw makes no captions and does no finishing.
- Our vertical crop tracks the face throughout the shot, where CutClaw uses one averaged box per shot.
- None of them has an NLE hand-off, a licence gate, client review links or Hinglish support.

Their advantage is the **features around the edit**.

## Ranked gap list

Score = wow for clients × fit for an Indian reel freelancer ÷ effort. Effort: S is under half a day, M is 1–2 days, L is 3 days or more.

| # | Feature | Seen in | What the client sees | Effort | Cost to run | Notes |
|---|---|---|---|---|---|---|
| 1 | **Ready-to-post copy pack + client brand profile** | vidpipe | Every reel arrives with its Instagram caption, hashtags, first comment, and YouTube title/description in the brand's voice | S–M | about 1 small Claude call | Extends our `Brand`: voice, hashtag banks, banned words, ASR vocabulary. |
| 2 | **Hook preview in two looks** | OpenMontage | Within minutes, "pick A or B" for the opening 3 s before the full render | S | 2 short renders | Uses our overlay plus a short base render. |
| 3 | **Wrong-number check** | OpenEdit | QA catches "₹5 lakh" on screen when the speaker said "50 thousand" | S | free | Must handle lakh/crore, ₹, and Hindi number words, which OpenEdit doesn't. |
| 4 | **B-roll ranked by meaning + variety** | OpenMontage | Cutaways that match the words, and no three near-identical clips | S | free (local CLIP/SigLIP) | Same work as asset-library phase D; do them together. |
| 5 | **Beauty pass (opt-in)** | OpenMontage | Gentle skin smoothing, brighter eyes on the speaker | S | free (MediaPipe, Apache-2.0) | Off by default, per brand; never on minors; capped so it never looks "filtered". |
| 6 | **Partial re-render on revision** | OpenEdit (+ OpenMontage cache) | A caption or SFX note is turned around in about a minute instead of a full re-render | M | free | OpenEdit: fixed 2 s keyframe-aligned segments, stream-copy join, silent video plus a separate audio pass; the agent says which stretch changed. **We can detect it**: compare old and new `timeline.json` to get the changed frame ranges. |
| 7 | **Many reels from one long recording (Clip Factory)** | vidpipe, OpenMontage | A 40-min podcast in, 5–8 ranked standalone reels out | M | 1 Claude ranking pass + N edits | vidpipe: weighted viral score (keep ≥ 8/20), hook types, payoff-first, multi-segment clips. **Enforce limits in code** (they only ask for them in the prompt). New revenue line (batch pricing). |
| 8 | **Real song structure** | CutClaw (idea) | Music that drops exactly after the hook; chorus under the payoff | S–M | free | Replace the "every 4th beat" downbeat guess with **Beat This!** (MIT, weights included). madmom (non-commercial models) and aubio (GPL) are ruled out. Enables a cold open. |
| 9 | **AI sound effects when the library has no match** | OpenMontage | Any sound on demand (a crowd "wow", a cash ding) | S | ElevenLabs Starter, about $6/mo | Same as asset-library phase E; generated files become owned assets with a licence row. |
| 10 | **Music generated to fit the finished cut** | OpenMontage | A score whose hits land on every cut | S–M | ElevenLabs (paid) | Its local fallback is a simple score with a change on every cut. |
| 11 | **Translation + dubbing (+ lip-sync)** | OpenMontage, OpenEdit | The same reel in Hindi / Tamil / English, in the speaker's own voice | L | about $0.07 per output second for VEED lip-sync (≈ $4 per language for a 60 s reel) + TTS | New paid add-on. Neither tool really implements timing fit; we'd have to. Wav2Lip has commercial-use limits. Needs a design spike first. |
| 12 | **Beat-grid montage mode** | CutClaw (idea) | B-roll / product montages cut exactly on the beat | M–L | free | Speech cuts stay untouched. CutClaw's ±1 s tolerance drifts; we'd snap frame-exact. |
| 13 | **Approve → schedule → publish** | vidpipe | One click posts to Instagram / YouTube at the best time | L | free (official APIs) | Use Meta's and YouTube's own APIs, not the paid Late service. Needs each client's account connection: a trust and security project. |

Already partly here: captions already avoid faces and the safe zones (`overlay.build_props` passes faces and SAFE).

From the same reading, a fix that is ours: Hindi captions should break at the danda `।`.

## Proposed order

**Wave 1: quick wins that clients notice (about 2 days in total)**
- #1 copy pack + brand profile
- #2 hook preview
- #3 number check
- #8 song structure

**Wave 2: the two big multipliers (about 3–4 days)**
- #6 partial re-render, which makes every revision faster
- #7 Clip Factory, which is a new product to sell
- Bundle #4 (b-roll by meaning) with asset-library phase D

**Wave 3: paid and generative, once you have a key and a client asking**
- #9 and #10, with ElevenLabs
- #11 translation and dub, as a priced add-on after a spike
- #5 beauty pass, when a client asks for it

**Later:**
- #12 beat-grid montage mode
- #13 publishing

## Free replacements for the paid items (researched 2026-11-20)

Licences were checked separately for code and weights, against primary sources. Full reports:
- `research_notes/free-alternatives/audio-generation.md`
- `research_notes/free-alternatives/dubbing.md`

Nothing has been downloaded or tested yet. Every pick needs a short A/B listening test with desi/Hindi prompts before we rely on it.

| Paid item | Free pick | Licence / conditions | Fallback |
|---|---|---|---|
| #9 AI SFX (ElevenLabs) | **Stable Audio 3 Small-SFX** | Code MIT; weights under the Stability Community Licence (free under $1M revenue a year; register once; credit "Powered by Stability AI"). Hugging Face download gated, 3.5 GB; about 1 s per 10 s clip on Mac (MLX) | MOSS-SoundEffect v2 (Apache-2.0) |
| #10 music to fit the cut (ElevenLabs/Suno) | **ACE-Step 1.5** | MIT; outputs commercial; tempo, key and duration control; 10 GB; Mac speed unknown | Stable Audio 3 Medium. For hits exactly on each cut: a MIDI score rendered by FluidSynth with the GeneralUser GS soundfont (free; basic sound, exact timing) |
| #11 voice-cloned dubbing (ElevenLabs) | **Maya 2 Native** or **ZONOS3-Mini**: the only commercial-OK cloners covering Hindi, Tamil, Telugu, Bengali and Marathi. Both are only weeks old: blind-test them | Commercial OK (see report); **written consent from the speaker** to be cloned, per language | Hindi/English only: Chatterbox Multilingual V3 (watermarks every output), VoxCPM2 |
| #11 translation | **Claude** (no new cost) | — | IndicTrans2 (MIT, offline) |
| #11 timing fit | Retranslate to fit the length, then use the model's speed control, then trim pauses, then Rubber Band stretch within ±15% | Rubber Band is GPL: fine in-house; needs a commercial licence if shipped inside an app | — |
| #11 keeping the music | **Not needed for our own edits**: the engine already renders separate dialogue, music and SFX stems | — | Demucs only for clients' finished reels (its weights have no stated licence) |
| #11 lip-sync (VEED at $0.07/s) | **MuseTalk 1.5** on Mac (MLX port) | Redraws only a 256 px mouth area, so it looks soft on full-HD close-ups. Its face-parsing model is non-commercial and must be swapped | LatentSync 1.6 on a rented GPU (about $0.10–0.20 per reel against about $4.20); its insightface detector is non-commercial and must be swapped |

**Ruled out (non-commercial or restricted):**
- MusicGen/AudioGen, AudioLDM 2, Tango/TangoFlux, MMAudio
- HunyuanVideo-Foley (its output can't be shown in the EU or UK)
- YuE (company licence)
- F5-TTS, XTTS-v2, MaskGCT, Spark-TTS, Higgs Audio v3
- NLLB-200, Wav2Lip, Diff2Lip
- IndicF5 (licence unclear)

The remaining features (#1–8, #12, #13) are free already. They use local open models plus the Claude calls the engine already makes; publishing goes through the official Instagram and YouTube APIs.

## Red flags to avoid (from the code reading)

- **Licences:**
  - madmom (non-commercial models), aubio (GPL), Wav2Lip (commercial limits).
  - OpenMontage's Suno tool calls a reseller, not Suno.
  - OpenMontage's music tool scrapes Pixabay's website (against its terms of service).
- **Unchecked self-checks:**
  - OpenMontage's "slideshow risk" score rates the plan the agent wrote itself, not the pixels.
  - Its post-render QA docstring claims caption and transition checks that the code doesn't do.
  - Our QA must keep measuring rendered frames.
- **Unwired README claims:**
  - vidpipe's Gemini clip suggestions are never used for shorts.
  - CutClaw's vlog mode is broken, and its aesthetic check is never called.
