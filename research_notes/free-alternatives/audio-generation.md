# Free, self-hosted alternatives to ElevenLabs SFX and ElevenLabs/Suno music

Researched 2026-11-20. Use case: a paid freelance service that delivers Instagram reels to Indian creators and brands. It runs locally on an Apple-Silicon Mac (MPS, MLX or CPU; no NVIDIA) with Python 3.12.
Method: I read licences from each project's LICENSE file, Hugging Face model card, or HF API licence tag. I did not download any weights or run any code. Download sizes come from the HF tree API metadata only. Where a primary source was missing or contradictory, the entry says **unclear**.

> Not legal advice. "Commercial OK" means the primary licence text permits it. Before shipping, have someone read the full licence for whichever pick we adopt.

---

## 1. Candidate table

Legend: **USE** means licence-clean and practical on a Mac. **USE WITH CONDITIONS** means legal for us with obligations, or legal but with practical caveats. **AVOID** means non-commercial, unclear, or territory-restricted.

### 1a. Text-to-SFX

| Candidate | Code licence | Weights licence | Commercial use of outputs | Training data (authors' statement) | Apple Silicon | Size / speed | Output | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Stable Audio 3 Small-SFX** (May 2026) | MIT ([LICENSE](https://github.com/Stability-AI/stable-audio-3/blob/main/LICENSE)) | Stability AI Community License ([HF card](https://huggingface.co/stabilityai/stable-audio-3-small-sfx), [licence](https://stability.ai/community-license-agreement)), plus **Gemma Terms of Use** for the bundled T5Gemma text encoder ([terms](https://gemma.ai/resources/terms/)). HF-gated. | Yes. The licence says "You own any outputs". Free while you and your affiliates have < US$1M annual revenue. Commercial use requires **registration with Stability**. If you offer a product using the materials, you must display **"Powered by Stability AI"**. Outputs may not be used to build or improve a *foundational* generative model. | AudioSparx (806k licensed) + Freesound CC0/CC-BY/CC-Sampling+ (472k). Copyrighted music was filtered out (PANNs + content-ID). The small-sfx final stage uses a higher-quality Freesound subset. | **Yes, documented.** Official MLX route (Metal), CoreML, and TFLite CPU. M1 8 GB: about 1 s per 10 s clip, 1.6 GB peak RAM. | 433M–0.6B params; **3.5 GB** download | 44.1 kHz **stereo**, up to 120 s | **USE WITH CONDITIONS**: best SFX pick |
| **Stable Audio 3 Medium** (also does SFX) | MIT | Same as above ([card](https://huggingface.co/stabilityai/stable-audio-3-medium)) | Same as above | Same as above (AudioSparx + Freesound) | Yes, MLX. M1: about 5 s per 10 s clip, 3.8 GB RAM. M4 Pro: 30 s audio in 5 s. | 1.4B; **10.5 GB** | 44.1 kHz stereo, up to 380 s | **USE WITH CONDITIONS** |
| Stable Audio Open 1.0 / Open Small | MIT ([stable-audio-tools](https://github.com/Stability-AI/stable-audio-tools)) | Stability Community License, gated ([1.0](https://huggingface.co/stabilityai/stable-audio-open-1.0), [Small](https://huggingface.co/stabilityai/stable-audio-open-small)) | Same as SA3 | Freesound + FMA, all CC0/CC-BY/CC-Sampling+ | Small: Arm CPU (TFLite). 1.0: CPU/MPS, not benchmarked. | 1B (47 s max) / 0.5B (11 s max) | 44.1 kHz stereo | USE WITH CONDITIONS, but **superseded by SA3**, which beats both in Stability's eval |
| **MOSS-SoundEffect v2.0** (OpenMOSS, May 2026) | Apache-2.0 ([MOSS-TTS LICENSE](https://github.com/OpenMOSS/MOSS-TTS/blob/main/LICENSE)) | **Apache-2.0** ([HF card](https://huggingface.co/OpenMOSS-Team/MOSS-SoundEffect-v2.0)). Not gated. | Yes. No caps, registration or attribution beyond Apache NOTICE. | **Not disclosed.** The card says only "English and Chinese captions". | **Unverified.** Instructions are CUDA-only (bf16, CUDA 12.8, compile step). The community MLX 4-bit port is of **v1** (the 8B MossTTSDelay model), not v2. | 1.3B DiT + Qwen3 text encoder; **11.2 GB** | 48 kHz (channels not stated), up to 30 s | **USE WITH CONDITIONS**: licence-clean fallback; Mac support needs a spike |
| TangoFlux | unclear (repo LICENSE covers "the Model") | "non-commercial, research-only… under the UK data copyright exemption" + Stability Community + WavCaps academic-only ([LICENSE.md](https://github.com/declare-lab/TangoFlux/blob/main/LICENSE.md)) | **No** | WavCaps (academic-only) | Not mentioned | 515M | 44.1 kHz stereo, 30 s | **AVOID** |
| Tango / Tango 2 | Repo LICENSE is **CC BY-NC-ND 4.0** ([LICENSE.md](https://github.com/declare-lab/tango/blob/master/LICENSE.md)) | Same | **No** | AudioCaps ("cannot distribute… copyright issues") | – | 866M | 16 kHz | **AVOID** |
| AudioLDM 2 | not verified (moot) | **CC BY-NC-SA 4.0** ([HF](https://huggingface.co/cvssp/audioldm2)) | **No** | Card lists training hours only (1150k/665k "h" column), no source licences | – | 1.1–1.5B | 16 kHz (examples) | **AVOID** |
| AudioGen / MAGNeT (AudioCraft) | MIT | **CC BY-NC 4.0** ([repo](https://github.com/facebookresearch/audiocraft), [audiogen-medium](https://huggingface.co/facebook/audiogen-medium)) | **No** | – | – | – | not verified | **AVOID** |
| Sony Woosh (Apr 2026) | MIT / Apache-2.0 | **CC BY-NC** (official repo, per [Sony AI blog](https://ai.sony/blog/introducing-woosh-sony-ais-sound-effect-foundation-model)/[paper](https://arxiv.org/abs/2604.01929)) | **No** | Public model trained on public data; the licensed-data model is internal | – | – | 44.1 kHz | **AVOID** |

### 1b. Music generation

| Candidate | Code licence | Weights licence | Commercial use of outputs | Training data (authors' statement) | Apple Silicon | Size / speed | Output / control | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Stable Audio 3 Small-Music / Medium** | MIT | Stability Community License + Gemma ToU, gated ([small-music](https://huggingface.co/stabilityai/stable-audio-3-small-music), [medium](https://huggingface.co/stabilityai/stable-audio-3-medium)) | Yes, with the same conditions as SA3 SFX: < $1M revenue, register, "Powered by Stability AI", no foundation-model training on outputs. Stability's announcement: "you own your outputs and can distribute and commercialize them freely" ([news](https://stability.ai/news-updates/meet-stable-audio-3-the-model-family-built-for-artistic-experimentation-with-open-weight-models)). | AudioSparx (licensed) + Freesound CC. Small-music final stage uses AudioSparx. | **Yes, documented** (MLX). M4 Pro: small 30 s in 1.5 s; medium 30 s in 5.1 s at 3.9 GB RAM. MLX LoRA training on Mac is supported. | small 3.5 GB / medium 10.5 GB | 44.1 kHz stereo; small up to 120 s, medium up to 380 s; **BPM only as prompt text** ("124 BPM"); variable length to the second; **inpainting / continuation** of given second ranges | **USE WITH CONDITIONS**: recommended default |
| **ACE-Step 1.5** (2026) | **MIT** ([LICENSE](https://github.com/ace-step/ACE-Step-1.5/blob/main/LICENSE)) | **MIT** (HF tag on [Ace-Step1.5](https://huggingface.co/ACE-Step/Ace-Step1.5) and the XL repos). Not gated. A secondary blog claims "weights CC-BY-NC". That claim is **contradicted** by the primary HF tag and the card text. | Yes. The card says: "You can strictly use the generated music for **commercial purposes**." No caps or registration. | "Licensed data: professionally licensed music tracks", "royalty-free / no-copyright data", "synthetic data… MIDI-to-Audio". **No sources or counts named.** | Yes. macOS launch scripts use the **MLX** backend; MPS/CPU also supported; a portable mac package is available. **No Mac speed published; benchmark required.** v1 (3.5B) measured RTF 2.27× on M2 Max. | Main repo (2B turbo DiT + 1.7B LM + VAE) **10.1 GB**; XL 4B DiT +20 GB | 48 kHz; 10 s–10 min; **explicit duration, BPM, key, time-signature** fields; `instrumental=True`; repaint/edit regions; LoRA from about 8 songs | **USE** (most permissive), runner-up on quality |
| Magenta RealTime 2 (Google, 2026) | Apache-2.0 | **CC BY 4.0** ([HF card](https://huggingface.co/google/magenta-realtime-2)) | Yes. "Google claims no rights in outputs you generate." CC-BY attribution is owed when redistributing the weights, not for outputs. | About 71k h of stock music, mostly instrumental. v1 card: "primarily Western instrumental music… world music traditions incompletely covered." | **Best Mac support**: built for Apple Silicon (MLX + C++ engine); small runs real-time on any M-series. | small 0.46 GB MLX / base 2.77 GB MLX; repo 15.6 GB total (includes JAX checkpoints) | 48 kHz stereo; streaming 2 s chunks; text/style steering, **no tempo/duration control**, no long-term structure (10 s context) | **USE WITH CONDITIONS**: licence fine, but control is weak for fitting a cut |
| HeartMuLa-oss-3B | Apache-2.0 | **Apache-2.0** (changed 20 Jan 2026; [repo](https://github.com/HeartMuLa/heartlib), [HF](https://huggingface.co/HeartMuLa/HeartMuLa-oss-3B)) | Yes (no extra terms) | **Not disclosed** | Not mentioned; CUDA examples; recommends Python 3.10; RTF ≈ 1 on GPU | 15.8 GB | 48 kHz stereo, up to 4 min; lyrics+tags driven, instrumental not documented | USE WITH CONDITIONS (licence OK; impractical on Mac, song-oriented) |
| DiffRhythm (1.x) | Apache-2.0 | DiT: Apache-2.0. **VAE: Stability Community License** (fine-tuned from SAO; [VAE card](https://huggingface.co/ASLP-lab/DiffRhythm-vae)) | Yes, under Stability conditions (because of the VAE) | "Coming soon" (not disclosed) | "can now run on MacOS" (no numbers) | ≥ 8 GB VRAM | up to 4m45s, instrumental mode | USE WITH CONDITIONS, but weakest quality (see §3); no reason to prefer it over SA3 |
| YuE (v1) | Apache-2.0 | Apache-2.0 (HF tag, [YuE-s1-7B](https://huggingface.co/m-a-p/YuE-s1-7B-anneal-en-cot)) | Licence permits it | not disclosed | Large multi-stage LLM pipeline, NVIDIA-oriented; Mac not documented (VRAM not verified) | 7B stage-1 (size of other stages not verified) | Lyrics-to-song | **AVOID** (impractical; second-lowest SongBench score in the 2026 bench) |
| YuE2-3B (Sep 2026) | Apache-2.0 | **CC BY-NC 4.0 + "additional creator permission"** ([README licence section](https://github.com/multimodal-art-projection/YuE#license)) | Individual "creators and musicians" may monetize outputs. "**Commercial use by companies**: contact us." A paid editing service for brands sits in a grey zone. | not disclosed | Linux + 24 GB NVIDIA; Apple Silicon "experimental" | 3B | 48 kHz stereo; best open song quality (self-reported) | **AVOID** unless licensed (ambiguous for a business) |
| MusicGen / MusicGen-Style / JASCO (+ all fine-tunes) | MIT | **CC BY-NC 4.0** ([musicgen-small](https://huggingface.co/facebook/musicgen-small)) | **No** | 20k h licensed (Shutterstock, Pond5, Meta) | – | – | 32 kHz mono | **AVOID** (fine-tunes inherit NC) |
| SongBloom (Tencent) | unclear | **unclear**: official GitHub repos (tencent-ailab / Cypress-Yang) return 404 and the main HF repo is unavailable as of 2026-11-20. Remaining `SongBloom_long` is tagged `license: other` with no text. Mirrors disagree (Apache vs CC BY-NC-SA). | unclear | – | – | – | – | **AVOID** (cannot verify) |
| SongGeneration / LeVo (Tencent) | unclear | **unclear**: custom Tencent "License Terms of SongGeneration". Official GitHub 404, HF repo unavailable to anonymous fetch. Text not retrievable. | unclear | – | – | – | – | **AVOID** (cannot verify) |
| Riffusion | MIT ([repo](https://github.com/riffusion/riffusion-hobby), unmaintained) | CreativeML OpenRAIL-M ([HF](https://huggingface.co/riffusion/riffusion-model-v1)). The card says "intended for research purposes only". | OpenRAIL-M generally allows it with use-restrictions, but the card's research-only framing makes it unclear | Fine-tuned SD 1.5 (LAION-5B base); fine-tune data not stated | MPS works with CPU fallback | SD 1.5-sized (not verified) | short spectrogram clips (length not verified) | **AVOID** (unmaintained + ambiguity) |
| MiniMax Music 3 | – | Reported CC BY-NC (secondary source only, not verified) | – | – | – | – | – | AVOID (not verified) |

### 1c. Procedural / MIDI scoring (exact hits on cut times)

| Component | Licence (primary source) | Notes | Verdict |
|---|---|---|---|
| **FluidSynth** (synth engine) | **LGPL-2.1** ([repo](https://github.com/FluidSynth/fluidsynth)) | Fine for us: we call the binary/library and don't ship a modified static build. Homebrew `fluid-synth`; Python via `pyfluidsynth` or just the CLI `fluidsynth -F out.wav sf2 song.mid`. | **USE** |
| **GeneralUser GS v2.0.x** (SoundFont) | Custom permissive ([LICENSE.txt](https://github.com/mrbumpy409/GeneralUser-GS/blob/main/documentation/LICENSE.txt)): "use… without restriction for your own music creation, private or commercial"; samples allow "ability to make profit from musical recordings" | The author admits he "cannot be 100% sure where all of the samples originated". No complaints since 2000. 261 presets + 13 kits, about 31 MB RAM. GM includes **Sitar (105), Shanai (112)**, Koto, Kalimba, Taiko, but **no tabla/dhol** in GM drums. | **USE** (note the provenance caveat) |
| **FluidR3_GM** (SoundFont) | **MIT** ([Debian copyright](https://metadata.ftp-master.debian.org/changelogs/main/f/fluid-soundfont/unstable_copyright)) | GM set (file size not verified); cleanest licence | **USE** |
| Magenta RT 2 as MIDI-ish "jam" | see above | Note-control "Jam" app | optional |

### 1d. Video-to-audio / Foley (optional)

| Candidate | Weights licence | Verdict |
|---|---|---|
| MMAudio | **CC BY-NC 4.0** ([HF](https://huggingface.co/hkchengrex/MMAudio)). Code MIT. Linux-only tested, about 6 GB VRAM. | **AVOID** |
| ThinkSound / PrismAudio | README: "**Commercial use is NOT permitted**". Also bundles the SAO VAE ([repo](https://github.com/FunAudioLLM/ThinkSound)). | **AVOID** |
| HunyuanVideo-Foley | **Tencent Hunyuan Community License** ([LICENSE](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley/blob/main/LICENSE)). The territory **excludes EU, UK, South Korea**, and you "must not use, reproduce, … distribute, or display… **Output**… outside the Territory". It also has a > 100M MAU clause and bans using outputs to improve other models. Tencent claims no rights in outputs. Needs 8–20 GB CUDA VRAM; Linux. | **AVOID**: Instagram reels are displayed worldwide, including the EU and UK, which the Output-territory clause appears to forbid. Also not Mac-runnable. |
| Woosh VFlow / DVFlow | CC BY-NC | **AVOID** |

There is no licence-clean, Mac-runnable V2A model today. The practical substitute is: detect cut/motion events in the edit, then call text-to-SFX (SA3) per event and place it at the timestamp. Our pipeline already knows cut times, so this is cheap.

---

## 2. Recommendations

### Best free SFX generator: **Stable Audio 3 Small-SFX** (upgrade to SA3 Medium when quality matters)
- **Why:** It is the only candidate with (a) a documented Apple-Silicon path with measured numbers (MLX: about 1 s per 10 s clip on an M1 8 GB), (b) disclosed licensed and CC training data, and (c) the best numbers on Stability's BBC-SFX eval (§3). Output is 44.1 kHz stereo, which matches our delivery format.
- **Licence conditions:** [Stability AI Community License](https://stability.ai/community-license-agreement) (weights: [HF card / LICENSE.md](https://huggingface.co/stabilityai/stable-audio-3-small-sfx)) + [Gemma Terms of Use](https://gemma.ai/resources/terms/) for T5Gemma. Code is MIT.
  - Free while our total annual revenue, including affiliates, is **< US$1M**. Above that we need an Enterprise licence.
  - **Register** with Stability for commercial use (free form).
  - Conservative reading of §IV(a): put **"Powered by Stability AI"** on our about page or product docs, and keep the licence + Notice file in the repo.
  - Do not use outputs to train or improve a foundation generative model. A LoRA on SA3 itself is allowed, because Derivative Works are excluded from that restriction.
  - Gemma §3.2: follow the Gemma Prohibited Use Policy. Google "claims no rights in Outputs".
- **What we'd need to do:** Create an HF account and accept the gate, which asks for name, email, country, organisation and intended use. Download **3.5 GB** (Small-SFX) or **10.5 GB** (Medium). Use the `optimized/mlx` route (`./sa3 --prompt … --seconds N`, or `scripts/sa3_mlx.py`) as a **subprocess / sidecar in its own `uv` venv**, so our engine stays on Python 3.12. The CUDA path pins cp310 wheels and doesn't apply to us anyway.
- **Known gap:** human vocal SFX such as *"crowd gasp"*, laughter or cheering. The SAO cards state "cannot generate realistic vocals", and the SA3 cards are silent on this. Keep a curated CC0 library (Freesound/our `assets/sfx` index) for vocal reactions, and use generation for whooshes, risers, impacts, dings, ambiences and foley.
- **Licence-clean fallback:** **MOSS-SoundEffect v2.0** (Apache-2.0, [HF card](https://huggingface.co/OpenMOSS-Team/MOSS-SoundEffect-v2.0), no gate, 48 kHz, ≤ 30 s, 11.2 GB). It has no revenue cap or attribution requirement. However, the training data is **undisclosed**, there are no published evals, and **Mac support is untested** (CUDA-only instructions). Run a 1-day spike on MPS before relying on it.

### Best free music generator: trade-off between **SA3 (default)** and **ACE-Step 1.5**

| | Stable Audio 3 Small-Music / Medium | ACE-Step 1.5 |
|---|---|---|
| Licence | Community License + Gemma ToU (cap, registration, attribution) | **MIT, no strings** |
| Training-data transparency | Named sources with counts (AudioSparx licensed + Freesound CC) | "Licensed + royalty-free + synthetic", no sources named |
| Mac | Official MLX route, **measured** (medium 30 s in about 5 s on M4 Pro, 3.9 GB) | MLX scripts exist, **no published Mac numbers** |
| Control | Duration to the second, BPM only via prompt text, inpainting by time range | **Explicit BPM/key/time-sig/duration fields**, `instrumental=True`, repaint |
| Quality (instrumental 120 s, Stability's paper) | Medium: FAD 0.107, CLAP 0.390, listening OVL 4.20 / MUS 4.15 | XL-turbo: FAD 0.193, CLAP 0.321, OVL 3.35 / MUS 3.15 |
| Output | 44.1 kHz stereo, ≤ 120 s (small) / 380 s (medium) | 48 kHz, 10 s–10 min |
| Download | 3.5 GB / 10.5 GB | 10.1 GB (turbo) / +20 GB (XL) |

**Caveat on the quality row:** the paper scored **ACE-Step 1.5 XL-turbo**, the 4B DiT. That variant is a 20 GB download and needs ≥ 12 GB with offload. The Mac-practical default is the 2B turbo in the 10.1 GB repo, which was **not** the variant scored. Its quality is likely at or below these numbers.

**Default: SA3 Medium**, with Small-Music for fast drafts. Data provenance decided it. For a paid client service, the stronger defence is a model whose authors name licensed sources and that has a measured Mac path. The Community-License strings are cheap for a sub-$1M freelancer. **Switch to ACE-Step 1.5** if (a) revenue approaches $1M, (b) we refuse the Stability/Gemma terms, or (c) explicit BPM/key control proves essential in testing. Note that SA3 leads ACE-Step on quality in Stability's paper, but Stability is not a neutral evaluator (see §3).

**What we'd need to do (music):**
- SA3: use the same gate, download and sidecar as SFX. Licence URLs: [stable-audio-3-medium](https://huggingface.co/stabilityai/stable-audio-3-medium), [Community License](https://stability.ai/community-license-agreement).
- ACE-Step: no gate. `git clone` + `start_api_server_macos.sh` gives an MLX REST API that we call from the engine. Licence URLs: [LICENSE (MIT)](https://github.com/ace-step/ACE-Step-1.5/blob/main/LICENSE), [HF card](https://huggingface.co/ACE-Step/Ace-Step1.5). Keep the MIT notice.

### Fallback (music, and the only way to get exact cut hits): **MIDI + FluidSynth + GeneralUser GS / FluidR3_GM**
- Licences: [FluidSynth LGPL-2.1](https://github.com/FluidSynth/fluidsynth), [GeneralUser GS licence](https://github.com/mrbumpy409/GeneralUser-GS/blob/main/documentation/LICENSE.txt), [FluidR3_GM MIT](https://metadata.ftp-master.debian.org/changelogs/main/f/fluid-soundfont/unstable_copyright). Downloads are small, tens of MB (exact sizes not verified). No gating, fully deterministic.
- Quality is clearly "General MIDI". It works for pulses, risers, stingers and simple lo-fi/desi-flavoured loops (sitar/shanai presets), but a client will not mistake it for a produced track.
- **Magenta RealTime 2** ([CC BY 4.0](https://huggingface.co/google/magenta-realtime-2)) is the second neural fallback: clean licence, best Mac support, but no tempo/duration control.

### Fitting music to a cut (hits on timestamps)
- **Exact:** Only MIDI does this. Build a tempo map whose beats land on the cut times (`mido`/`pretty_midi`), place hits/stingers on those beats, render with FluidSynth.
- **Neural beds (SA3 / ACE-Step):**
  1. Derive a BPM from the cut spacing (e.g. cuts every 0.75 s → 80 or 160 BPM).
  2. Ask for that BPM (ACE-Step: `bpm=` field; SA3: "… 120 BPM" in the prompt) and the exact duration.
  3. Beat-track the result (librosa) and nudge cuts by ±1–2 frames to the nearest beat, or time-stretch the bed slightly (ffmpeg `atempo`). Note that `rubberband` is GPL. That's fine as a separate CLI process; avoid linking it.
  4. Layer generated SFX hits (impact / riser / whoosh) exactly on the cut times. This is what sells "the music hits the cut".
  5. **Untested idea:** SA3 / ACE-Step inpainting to regenerate a 1–2 s window around a key cut with a prompt like "big drum hit". It's worth a spike, but no source shows it landing hits precisely.

---

## 3. How far are the free options from ElevenLabs / Suno? (honest)

- **No primary source compares any of these to ElevenLabs SFX (v2/v3) or Eleven Music.** The SA3 paper compares against TangoFlux, Woosh, SAO, ACE-Step and DiffRhythm, plus Stability's own commercial Stable Audio 2.5. ElevenLabs SFX today: up to 30 s, 48 kHz WAV, looping, and v3 "follows multi-part prompts more closely and handles vocal and musical sounds better" ([docs](https://elevenlabs.io/docs/capabilities/sound-effects)).
- **SFX:** SA3 tables, self-reported on 5 s BBC-SFX. Medium FAD 0.369 / CLAP 0.369 / OVL 3.65; small-sfx 0.395 / 0.351 / 3.35; SAO 0.501 / 0.263 / 2.95; TangoFlux 0.760 / 0.179 / 2.35. So SA3 is a big step over 2024 open models.
  - My judgement, not measured: on single-event, non-vocal prompts ("cash register ding", "whoosh riser 2 s"), expect usable-to-good results after picking from 3–5 seeds. On multi-event or human-voice prompts ("crowd gasp then applause"), expect it to fall clearly short of ElevenLabs v3.
  - Plan for **generate N → CLAP-rank → human pick**, and a curated library for anything vocal.
- **Music, two conflicting sources:**
  - **Stability's SA3 paper** (instrumental, 120 s): SA3 Medium is listening-rated above ACE-Step 1.5 XL-turbo (OVL 4.20 vs 3.35) and on par with Stability's commercial Stable Audio 2.5.
  - **YuE2 authors' WildSongBench** (songs *with vocals*, Sep 2026, a competing team): ACE-Step 1.5 scores 6.01 vs Suno v5 6.87, HeartMuLa 6.25, DiffRhythm 2 5.24, YuE2 6.73.
  - **ACE-Step's own claim** is "between Suno v4.5 and Suno v5". That contradicts the YuE2 table, which puts it below both.
  - Reading: for **instrumental 15–60 s beds** (our case), the open models are probably "good stock-library" quality. For full songs with vocals they are roughly a Suno generation behind, and the most competitive open song model (YuE2) isn't commercially licensable for a business.
- **Indian / desi / Bollywood coverage is untested everywhere.** No card claims it. SAO and Magenta cards explicitly flag Western bias. ACE-Step mentions multilingual vocals only. The SA3 MLX README demo uses "arabic maqam oud taqsim", which hints at some non-Western coverage but proves nothing.
  - Before committing, run an A/B with 3 seeds each on SA3 Medium vs ACE-Step 1.5:
    1. "lo-fi hip hop with sitar melody and tabla groove, 85 BPM, warm vinyl"
    2. "Bollywood dance instrumental, dhol and shehnai, festive, 128 BPM"
    3. "Punjabi bhangra beat, dhol, tumbi riff, energetic, 100 BPM"
    4. "Indian classical fusion, bansuri flute over ambient pads, calm, 70 BPM"
    5. "Carnatic-inspired percussion, mridangam and ghatam, cinematic build"
    6. "desi trap beat, 808 bass, harmonium chops, 140 BPM"
  - Score each for instrument authenticity, groove, and whether the "BPM" request was honoured (beat-track it).
  - If both fail, a LoRA is possible (SA3 MLX LoRA on Mac; ACE-Step LoRA from about 8 songs). **We would need rights to the training tracks.** Buying licensed desi stems is the clean route.

---

## 4. Practical integration notes
- Python versions:
  - **ACE-Step 1.5** lists Python 3.11–3.12, so it *can* share the engine's venv. A sidecar via `start_api_server_macos.sh` is still cleaner because it isolates heavy dependencies.
  - **SA3** has to be separated. Its CUDA route pins cp310 wheels, and the `optimized/mlx` route ships its own bootstrap and CLI. Call it as a subprocess.
  - **HeartMuLa** recommends 3.10 if it's ever used.
- **Delivering to clients:** brands receive *outputs* (rendered reels), not model files. Neither the Stability Community License nor the Gemma ToU requires passing terms on to recipients of outputs. Gemma §3.1's pass-through applies only when distributing Gemma or a Model Derivative, and Stability says "You own any outputs". Our own obligations (registration, "Powered by Stability AI" on our site/docs, revenue cap) stay with us.
- Log the provenance of each generated file (model id, weights revision, licence id, prompt, seed) into the asset index. This is consistent with the existing licence-gate work (`engine/src/reel/licences.py`, `assets/licenses/registry.yaml`). Suggested registry entries: `stability-community-license` (conditions: revenue < $1M, registered, "Powered by Stability AI" shown), `gemma-tou`, `mit`, `apache-2.0`, `cc-by-4.0` (Magenta weights; outputs unencumbered).
- Total disk if we adopt everything recommended: SA3 small-sfx + medium about 14 GB (they share T5Gemma, so less after dedupe), ACE-Step about 10 GB, soundfonts about 0.2 GB.

## 5. Sources consulted (primary)
- Stable Audio 3: https://github.com/Stability-AI/stable-audio-3 (README + LICENSE + optimized/mlx/README), https://huggingface.co/stabilityai/stable-audio-3-small-sfx, https://huggingface.co/stabilityai/stable-audio-3-medium, https://arxiv.org/abs/2605.17991 (eval tables §5), https://stability.ai/news-updates/meet-stable-audio-3-the-model-family-built-for-artistic-experimentation-with-open-weight-models
- Stability Community License: https://stability.ai/community-license-agreement ; Gemma ToU: https://gemma.ai/resources/terms/
- Stable Audio Open: https://huggingface.co/stabilityai/stable-audio-open-1.0 , https://huggingface.co/stabilityai/stable-audio-open-small
- ACE-Step: https://github.com/ace-step/ACE-Step-1.5 (LICENSE, README, docs/en/INFERENCE.md, INSTALL.md), https://huggingface.co/ACE-Step/Ace-Step1.5 , https://huggingface.co/ACE-Step/ACE-Step-v1-3.5B
- MOSS-SoundEffect: https://huggingface.co/OpenMOSS-Team/MOSS-SoundEffect-v2.0 , https://github.com/OpenMOSS/MOSS-TTS
- Magenta RT: https://github.com/magenta/magenta-realtime , https://huggingface.co/google/magenta-realtime-2 , https://huggingface.co/google/magenta-realtime
- HeartMuLa: https://github.com/HeartMuLa/heartlib ; YuE/YuE2: https://github.com/multimodal-art-projection/YuE ; DiffRhythm: https://github.com/ASLP-lab/DiffRhythm , https://huggingface.co/ASLP-lab/DiffRhythm-vae
- AudioCraft: https://github.com/facebookresearch/audiocraft , https://huggingface.co/facebook/musicgen-small ; AudioLDM2: https://huggingface.co/cvssp/audioldm2
- Tango/TangoFlux: https://github.com/declare-lab/tango , https://github.com/declare-lab/TangoFlux ; Riffusion: https://huggingface.co/riffusion/riffusion-model-v1
- MMAudio: https://huggingface.co/hkchengrex/MMAudio ; ThinkSound: https://github.com/FunAudioLLM/ThinkSound ; HunyuanVideo-Foley: https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley ; Woosh: https://arxiv.org/abs/2604.01929
- FluidSynth: https://github.com/FluidSynth/fluidsynth ; GeneralUser GS: https://github.com/mrbumpy409/GeneralUser-GS ; FluidR3: Debian copyright file above
- ElevenLabs SFX: https://elevenlabs.io/docs/capabilities/sound-effects
