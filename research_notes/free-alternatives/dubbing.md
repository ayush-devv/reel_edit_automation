# Free / self-hosted dubbing stack — research (2026-11-20)

Goal: replace ElevenLabs voice cloning/dubbing and VEED Lipsync on fal (~$0.07/s → ~$4.20 per 60 s reel) for paid client reels.
Input: 15–90 s talking-head reel in English / Hindi / Hinglish. Output: Hindi, English, ideally Tamil / Telugu / Bengali / Marathi, in the **speaker's own voice**, optionally re-lip-synced.
Target box: Apple-Silicon Mac (the local benchmark machine is an M5, 10 cores, **16 GB**), PyTorch MPS / CPU / MLX, Python 3.12. Rented GPU = fallback only.

Method: every licence below was read from the repo / Hugging Face model card (URL given). Where the primary page did not state something, it says **unclear** and why. Nothing was downloaded or run; all speed figures are **as reported by the source** or **estimated** (labelled). Not legal advice.

---

## 0. Key findings up front

1. **Only two open-weight TTS models found that clone a voice AND cover all five Indic targets AND have commercial-OK weights**: **Maya 2 Native** (Maya Research, Apache-2.0, released 2026-10-25) and **ZONOS3-Mini** (Zyphra, Apache-2.0 weights, ~Nov 2026). Both are weeks old, benchmarks are self-reported, training data is undisclosed. → Shortlist + run a native-speaker bake-off; do not crown one blind.
2. **Most of the famous names are non-commercial**: F5-TTS, MaskGCT, OmniVoice, DhVaani (all CC-BY-NC, mostly because of the Emilia dataset), XTTS-v2 (CPML, non-commercial *including outputs*), Spark-TTS (CC-BY-NC-SA), NLLB-200 (CC-BY-NC), Wav2Lip, Diff2Lip, Higgs Audio v3. Avoid.
3. **Lip-sync is the weak link.** MuseTalk 1.5 is the only commercially usable, Mac-feasible option (MLX port, ~34 face-frames/s), but it repaints only a **256×256 mouth region** — visibly soft on a 1080×1920 close-up — and its bundled face-parser is trained on a non-commercial dataset (swap it). LatentSync 1.6 is sharper (512²) but needs ~18 GB VRAM/CUDA → rented GPU, and its `FaceDetector` loads insightface `FaceAnalysis` weights (confirmed in source; insightface pretrained packs are non-commercial) → must be swapped before paid use.
4. **Source separation is mostly unnecessary for this product**: the engine already renders separate `dialogue / music / sfx` stems (`engine/src/reel/stages/edit.py` line ~396 outputs `render/stems/{dialogue,music,sfx}.wav`). Dub the dialogue stem and re-mix with the project's own music/SFX. Separation is only needed for client-supplied finished reels. Note: Demucs **weights** have no stated licence and were trained on MUSDB18-HQ (academic-only) → "unclear" (this contradicts the earlier "Demucs = safe" note in research-findings-2).
5. **Timing fit is a translation problem first**: have Claude write colloquial Hinglish/Hindi to a per-segment syllable/duration budget, then TTS speed control, then time-stretch ≤ ~±15%.

---

## 1. Translation (EN ↔ Indic, Hinglish)

| Candidate | Code licence | Weights licence | Langs | Notes | Verdict |
|---|---|---|---|---|---|
| **Claude (Sonnet/Opus 5.5)** | n/a (API) | n/a | All targets incl. Hinglish register | Already paid → no new cost. Can obey a per-segment *duration budget*, keep English loanwords the way Indian creators actually speak, keep brand names, write numbers as words for TTS. | **USE** (primary) |
| **IndicTrans2** (AI4Bharat) | MIT | MIT (checkpoints listed as MIT in repo licence table); data CC0 / CC-BY-4.0 | 22 scheduled Indic langs + English | 200M distilled En→Indic / Indic→En, 320M Indic↔Indic, 1B base; RoPE long-context variants (Jan 2025). Output is formal/"textbook" Hindi — stiff for reels. Source: https://github.com/AI4Bharat/IndicTrans2 | **USE WITH CONDITIONS** (offline fallback / back-translation QA check, not the creative pass) |
| **NLLB-200** (Meta) | — | **CC-BY-NC-4.0**; card: "research model … not released for production deployment". Source: https://huggingface.co/facebook/nllb-200-distilled-600M | 200 | Non-commercial. | **AVOID** |

---

## 2. Voice-cloning TTS that speaks Hindi / Indic

| Candidate | Code licence | Weights licence | Hindi? Other Indic? | Cloning / safeguards | Apple Silicon / size / speed | Verdict |
|---|---|---|---|---|---|---|
| **Maya 2 Native** (maya-research) | Apache-2.0 | **Apache-2.0**; upstream parts: Qwen3-1.7B-Base Apache-2.0, **Mimi codec CC-BY-4.0 (attribution required)**, ECAPA Apache-2.0. https://huggingface.co/maya-research/maya2-native | Hindi, Tamil, Telugu, Bengali, Marathi + Assamese, Gujarati, Kannada, Malayalam, Odia, Punjabi + English | Zero-shot from 3–10 s clean clip **+ exact transcript**; **cross-lingual** (Hindi ref → Tamil out). Self-reported: CER 2.35–3.49 % on 6k texts, mean ECAPA similarity 0.778; VoiceArena Hindi #2 in real-time-only view, ~#7 overall. No MOS. **No watermark.** Card: clone only voices you own/have permission for; disclose synthetic speech. Training data: "licensed and synthetic", not itemised. | Official engine = Linux + NVIDIA (≥12 GB). **Community Mac port `justanurag/maya-mac` (Apache-2.0)**: MLX + Metal kernels; RTF on M5 Pro 24 GB: MLX fp16 0.32, **MLX 8-bit 0.23**, torch-MPS 0.77; peak ~7 GB (8-bit) — fits 16 GB. Hindi CER 13.3 % (8-bit) on its Whisper check. https://huggingface.co/justanurag/maya-mac | **USE WITH CONDITIONS** — top candidate; brand-new, community Mac port, attribute Mimi, run bake-off |
| **ZONOS3-Mini** (Zyphra) | Runtime reported MIT by secondary sources — **official GitHub LICENSE not read → unclear** | **Apache-2.0** ("Model weights are released under Apache 2.0"). https://huggingface.co/Zyphra/ZONOS3-Mini | 43 langs; South Asia: Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Odia, Urdu | Clone from 5–10 s clip (no transcript needed on SGLang path; native runtimes accept up to 60 s or a speaker embedding). Watermark/safeguards: not mentioned. Benchmarks are Zyphra's own (ZTTS2-Eval). Training data not described. | ~800M total / ~100M active (MoE). **Native MLX server for Apple Silicon**, ggml CPU/Metal CLI, WebGPU browser build. No Mac RTF published. | **USE WITH CONDITIONS** — second candidate; confirm runtime licence + Indic quality yourself |
| **VoxCPM2** (OpenBMB) | Apache-2.0 | **Apache-2.0**, "free for commercial use". https://github.com/OpenBMB/VoxCPM , https://huggingface.co/openbmb/VoxCPM2 | Hindi yes; **no other Indic** listed (30 langs) | Short-clip cloning; "Ultimate Cloning" with ref transcript; voice design from text. Card forbids impersonation/fraud, asks to label AI content. No watermark. 2M+ h training data, unnamed. | 2B params, ~8 GB, 48 kHz out. `--device mps` supported; llama.cpp-omni Q8 **RTF ≈1.76 on M4 Pro** (slower than real time). | **USE WITH CONDITIONS** — Hindi/English only |
| **Chatterbox Multilingual V3** (Resemble AI) | MIT | **MIT** (HF card "License: mit"). https://github.com/resemble-ai/chatterbox , https://huggingface.co/ResembleAI/chatterbox | 23 langs incl. **Hindi**; dedicated **Hindi Single-Language Pack** (500M) — `ResembleAI/Chatterbox-Multilingual-hi`, tag **MIT**, not gated (https://huggingface.co/ResembleAI/Chatterbox-Multilingual-hi). No Tamil/Telugu/Bengali/Marathi. | **PerTh neural watermark on every output** (survives MP3) — the only candidate with built-in provenance. One anecdotal review: Hindi "very good". **README: "As of August 2026, Chatterbox is retired research and is no longer maintained."** | 500M. MPS works (`device="mps"`); community `chatterbox-mlx` reports MPS ~14 GB memory (tight on 16 GB); its RTF table direction is ambiguous — unverified. | **USE WITH CONDITIONS** — good Hindi/English fallback; unmaintained |
| **IndicF5** (AI4Bharat) | not stated on GitHub page | HF tag **MIT**, gated (accept conditions: "only clone voices for which you have explicit permission"). https://huggingface.co/ai4bharat/IndicF5 | 11 Indic incl. all 5 targets | Ref clip + ref transcript. Training data: Rasa (CC-BY-4.0), IndicVoices-R (CC-BY-4.0), **IndicTTS (IIT Madras — licence text not found; third-party says businesses need an MOU)**, **LIMMITS (unchecked)**. Whether it was initialised from CC-BY-NC F5-TTS weights: **not stated** (a third-party fine-tune claims it was). Card itself now recommends a newer "Indic-Speak" model (no specs found). | MLX port exists (`yogenghodke/indic-f5-mlx`, MIT): ~0.2–0.7× real-time on base M4 (i.e. slower than real time). | **USE WITH CONDITIONS / licence unclear** — data lineage; don't use for paid work until clarified |
| **Indic Parler-TTS** (AI4Bharat) | Apache-2.0 | Apache-2.0, gated. https://huggingface.co/ai4bharat/indic-parler-tts | 21 Indic | **No reference-audio cloning** — text-described voices / 69 named speakers only. | — | **AVOID** for own-voice dubbing (fine for generic VO) |
| **dots.tts** (rednote-hilab) | Apache-2.0 | Apache-2.0. https://huggingface.co/rednote-hilab/dots.tts-base | 24 langs; Hindi named only as a weaker case ("WER is higher"); no other Indic | Zero-shot cloning with ref audio+text. | 2B; Mac not documented (community MLX port exists) | **AVOID** (Hindi weak, no other Indic) |
| **F5-TTS** | MIT | **CC-BY-NC-4.0** (Emilia). https://huggingface.co/SWivid/F5-TTS | EN/ZH | — | — | **AVOID** |
| **OmniVoice** (k2-fsa) | Apache-2.0 | **CC-BY-NC** "due to constraints from its training data (e.g., Emilia)". https://huggingface.co/k2-fsa/OmniVoice | "600+" | Has explicit `duration` param + MPS support — would be ideal technically. | 0.6B | **AVOID** (NC weights) |
| **DhVaani-0.5** (ARTPARK-IISc) | — | **CC-BY-NC-4.0** ("weights derive from an NC base", ZipVoice). https://huggingface.co/ARTPARK-IISc/DhVaani-0.5 | 27 Indian langs | Ref clip + transcript; 0.1B | small | **AVOID** (NC) |
| **XTTS-v2** (Coqui) | Coqui TTS toolkit MPL-2.0 | **Coqui Public Model License**: non-commercial "uses of the model **or its output** … only so far as you do not receive any direct or indirect payment". Coqui shut down → no commercial licence to buy. https://huggingface.co/coqui/XTTS-v2/blob/main/LICENSE.txt | Hindi yes | — | — | **AVOID** |
| **OpenVoice v2** (MyShell) | MIT | MIT ("Free for commercial use", since Apr 2024). https://github.com/myshell-ai/OpenVoice | Native EN/ES/FR/ZH/JA/KO; tone-colour converter can sit on another TTS | Converter only copies timbre, not accent/prosody; would need a commercial Hindi base TTS (e.g. Indic Parler) — two-stage quality loss. | light | **USE WITH CONDITIONS** — last-resort "generic Indic voice → speaker timbre" path |
| **CosyVoice 2/3** (Alibaba) | Apache-2.0 | **unclear** — repo page doesn't state weights licence (ModelScope/HF pages not read) | 9 langs, **no Hindi/Indic** | — | Linux/NVIDIA docs | **AVOID** (no Hindi) |
| **IndexTTS 2 / 2.5** (bilibili) | bilibili Model Use License | same; **commercial use → contact indexspeech@bilibili.com**. https://github.com/index-tts/index-tts | ZH/EN/JA/ES/AR, no Hindi | 2.5 has `duration_factor` 0.5–2.0× | CUDA docs | **AVOID** |
| **Fish Speech / Fish Audio S2-Pro** | Fish Audio Community License | S2-Pro weights: **Fish Audio Research License**; commercial terms **unclear** from README | "~100 langs", Hindi not confirmed | — | — | **AVOID** |
| **Higgs Audio v3** (Boson) | Apache-2.0 | **Research & Non-Commercial License**; revenue use needs separate licence. https://github.com/boson-ai/higgs-audio | 100+ (unnamed) | — | — | **AVOID** |
| **MaskGCT** (Amphion) | MIT (Amphion) | **CC-BY-NC-4.0** (Emilia). https://huggingface.co/amphion/MaskGCT | EN/ZH | has `target_len` duration control | — | **AVOID** |
| **Spark-TTS** | Apache-2.0 | **CC-BY-NC-SA-4.0** (changed from Apache due to training data). https://huggingface.co/SparkAudio/Spark-TTS-0.5B | EN/ZH | — | — | **AVOID** |
| **Kokoro-82M** | Apache-2.0 | Apache-2.0. https://huggingface.co/hexgrad/Kokoro-82M | 4 Hindi voices (grade C) | **No cloning** | tiny, fast | **AVOID** for this use |
| **Sesame CSM-1B** | Apache-2.0 | Apache-2.0, gated; prohibits mimicking real people without explicit consent | English ("likely won't do well" otherwise) | — | — | **AVOID** |
| **Orpheus** (Canopy) | Apache-2.0 | **unclear** — weights licence not stated on repo; built on a Llama-3B backbone (Llama licence likely applies, not verified); multilingual research release languages not listed; cloning "not explicitly trained" | Hindi not confirmed | — | — | **AVOID** |

---

## 3. Timing fit

| Tool | Licence | Notes | Verdict |
|---|---|---|---|
| **Length-budgeted translation (Claude)** | n/a | Give Claude each segment's source duration and a target syllable count for the target language; ask for the shortest natural colloquial phrasing; re-ask if TTS overshoots > 15 %. Biggest lever — Hindi typically runs longer than English. | **USE** (step 1) |
| **TTS-native speed / duration** | per model | Maya / ZONOS3 / VoxCPM: check speed param during bake-off (not documented on cards read). OmniVoice & MaskGCT have exact-duration control but are NC. IndexTTS 2.5 `duration_factor` (not commercial). | **USE** where available |
| **Rubber Band Library** (via `pyrubberband` or ffmpeg `rubberband` filter) | **GPL** or paid commercial licence. https://breakfastquay.com/rubberband/ — "If you want to distribute it in a proprietary commercial application, you need to buy a licence." Running it in-house to produce client MP4s is not distribution; shipping it inside a distributed/closed app would be. | Best quality for speech stretch; keep within ~0.85–1.15× (estimate; larger ratios become audible). | **USE WITH CONDITIONS** (in-house only) |
| **ffmpeg `atempo`** / `librosa.effects.time_stretch` (ISC) | LGPL ffmpeg build / ISC | Non-GPL fallback; lower quality than Rubber Band on speech. | **USE** (fallback) |
| Also: trim/extend pauses between segments (silence edit) before stretching — free and inaudible. | — | — | **USE** |

---

## 4. Keeping music / SFX under the new voice

**First: you mostly don't need separation.** The edit stage already renders `render/stems/dialogue.wav`, `music.wav`, `sfx.wav` and has a per-clip voice-enhance stage with room-tone handling. Dub = replace the dialogue stem (keep room-tone bed), then re-run the existing mix (ducking, loudnorm). Separation only matters for (a) client-supplied *finished* reels with baked-in music, (b) ambient sound captured in the raw clip.

| Candidate | Code licence | Weights licence | Notes | Verdict |
|---|---|---|---|---|
| **Demucs v4 (htdemucs)** | MIT. https://github.com/facebookresearch/demucs | **Not stated separately**; trained on MUSDB18-HQ + 800 extra songs. MUSDB18 tracks "can only be used for academic purposes" (some CC-BY-NC-SA). https://sigsep.github.io/datasets/musdb.html → **unclear** | Repo archived 1 Jan 2025 (fixes in adefossez/demucs fork). Uses Metal/MPS automatically on Apple Silicon; ~1.5× track duration (htdemucs_ft ~4× slower). | **USE WITH CONDITIONS** — only for case (a)/(b); flag the weights-lineage risk |
| **SAM Audio** (Meta) | SAM License | SAM License: royalty-free, no field-of-use limit, no revenue cap; trade-control / military exclusions; must ship the licence if redistributing; outputs not expressly covered. Gated on HF. https://github.com/facebookresearch/sam-audio | Text/visual/span-prompted; speech/music/SFX. CUDA examples; no MPS notes. | **USE WITH CONDITIONS** (better licence than Demucs; Mac feasibility unverified → rented GPU) |
| **BandIt** (cinematic dialogue/music/effects) | Apache-2.0. https://github.com/kwatcharasupat/bandit | **unclear** — Zenodo weights licence not stated on repo; trained on DnR + MUSDB18-HQ | Exactly the right stem split (DME) | **AVOID until weights licence confirmed** |

---

## 5. Lip-sync

| Candidate | Code licence | Weights licence | Quality / speed | Mac feasibility | Verdict |
|---|---|---|---|---|---|
| **MuseTalk 1.5** (Tencent Lyra) | MIT ("no limitation for both academic and commercial usage") | Own model: "available for any purpose, even commercially". https://github.com/TMElyralab/MuseTalk . **But** `download_weights.sh` also pulls `79999_iter.pth` face-parser (BiSeNet; the face-parsing.PyTorch project trains on **CelebAMask-HQ = non-commercial research only**, https://github.com/switchablenorms/CelebAMask-HQ — filename/repo match is standard but not confirmed on the repo page), DWPose (weights licence not checked), whisper-tiny (MIT), sd-vae-ft-mse, LatentSync syncnet (openrail++). Test data non-commercial. | Single-step latent inpainting; **256×256 face region** → soft mouth on 1080×1920 close-ups. README suggests GFPGAN for sharpening — GFPGAN/CodeFormer licences **unclear (not checked)**; don't add them without checking. 30 fps+ on V100. | **MLX port `mlx-community/MuseTalk-1.5-fp16` (MIT)**: ~34 faces/s at batch 8, ~7 GB peak on "an M-series GPU"; face detect/crop/parse/blend still upstream **CPU** code. https://huggingface.co/mlx-community/MuseTalk-1.5-fp16 . Upstream `requirements.txt` pins **numpy 1.23.5 + tensorflow 2.12.0**, neither of which has Python 3.12 wheels → needs a separate 3.10/3.11 venv or a rewritten preprocessing path. (A user report says setup also pulls OpenMMLab libs for DWPose — not in requirements.txt; verify.) | **USE WITH CONDITIONS** — **replace the whole upstream preprocessing** (detection, landmarks/DWPose, BiSeNet parsing) with one commercially-licensed face-landmarker pass (e.g. MediaPipe, Apache-2.0 code — check its model card) or a jaw-ellipse mask. One change fixes the licence issue, the Py3.12 install issue and probably the CPU bottleneck. Verify before building. |
| **LatentSync 1.6** (ByteDance) | Apache-2.0. https://github.com/bytedance/LatentSync | **openrail++** tag (OpenRAIL family = commercial use with use-based restrictions; no LICENSE file in the HF repo — read the full OpenRAIL++-M text before use). https://huggingface.co/ByteDance/LatentSync-1.6 . **Confirmed:** `latentsync/utils/face_detector.py` does `from insightface.app import FaceAnalysis` → `FaceAnalysis(allowed_modules=["detection","landmark_2d_106"], root="checkpoints/auxiliary", providers=["CUDAExecutionProvider"])` (pack name not passed, so insightface's default pack is used). insightface: "pretrained models … available for non-commercial research purposes only" (https://github.com/deepinsight/insightface). → **As shipped, LatentSync loads non-commercial face weights.** | Multi-step latent diffusion, **512×512** (1.6) — sharper than MuseTalk; slower. 8 GB VRAM (1.5) / 18 GB (1.6). | CUDA-only docs, `onnxruntime-gpu`, CUDA provider hard-coded → **not practical on Mac**; rented GPU. | **USE WITH CONDITIONS** — rented GPU **and** replace `FaceDetector` (detection + 106-pt landmarks) with a commercially-licensed detector before any paid use |
| **Wav2Lip** | — | "personal/research/non-commercial purposes only … any form of commercial use is strictly prohibited" (LRS2). https://github.com/Rudrabha/Wav2Lip | 96×96 mouth, dated | — | **AVOID** |
| **VideoReTalking** (Tencent) | Apache-2.0 | **unclear** — weights on Google Drive, no licence stated; builds on Wav2Lip/GFP-GAN/GPEN components. https://github.com/OpenTalker/video-retalking | — | CUDA 11.1, PyTorch 1.9 | **AVOID** |
| **Diff2Lip** | **CC-BY-NC-4.0**. https://github.com/soumik-kanad/diff2lip | unclear (Drive) | — | — | **AVOID** |
| daVinci-MagiHuman (15B, Apache-2.0 per secondary source) / InfiniteTalk-class video models | — | not verified | Full talking-head regeneration, heavy GPU | No | not evaluated (too heavy; verify if pursuing) |

**Craft alternative to lip-sync (free, zero risk):** reels run ~25 cuts/min. Cover the worst mismatch stretches with b-roll / cutaways / punch-ins to text cards, and only lip-sync the on-camera segments that remain. This cuts lip-sync time and hides the 256 px softness.

---

## 6. Recommended end-to-end free stack

```
source reel (dialogue stem from edit stage, or Demucs/SAM-Audio for finished client reels)
  │
  0. ASR + word timestamps  → reuse the engine's existing transcription (segments, timings,
  │                           AND the reference-clip transcript the cloning models need).
  │                           NB: that is ElevenLabs Scribe today — already paid, no NEW cost,
  │                           but the stack is not 100 % free; a free ASR swap is out of scope here.
  1. Translate             → Claude, per segment, colloquial register, duration/syllable budget
  │                           (IndicTrans2 = offline fallback + back-translation sanity check)
  2. Voice-cloned TTS      → bake-off: Maya 2 Native (maya-mac, MLX 8-bit) vs ZONOS3-Mini (MLX)
  │                           Hindi/English-only jobs: + Chatterbox Multilingual V3 (Hindi pack, watermark) / VoxCPM2
  │                           reference = 5–10 s clean, single-speaker clip from the source + exact transcript
  3. Timing fit            → re-ask Claude if > 15 % over → TTS speed → silence trim → Rubber Band ≤ ±15 %
  4. Remix                 → replace dialogue stem; existing ducking + loudnorm mix with project music/SFX
  5. QA + captions         → run the engine's ASR on the dubbed track: CER gate AND new word timings
  │                           → re-time captions in the target script → re-render the overlay pass
  6. Lip-sync (optional)   → Mac: MuseTalk 1.5 MLX with replaced preprocessing (no BiSeNet/DWPose), on-camera shots only
                             Premium: LatentSync 1.6 on a rented 24 GB GPU with insightface FaceDetector replaced
```

Caption fonts: Devanagari (Hindi, Marathi), Tamil, Telugu and Bengali scripts need fonts with those glyphs + correct shaping available to the Remotion renderer (e.g. Noto Sans families, SIL OFL — licence not re-checked here).

**Bake-off protocol (do before committing):** 3 real client-style clips × {Hindi, Tamil, Bengali} × {Maya, ZONOS3} (+ Chatterbox/VoxCPM for Hindi). Blind A/B by at least one native speaker per language on: speaker similarity, pronunciation, Hinglish code-switch handling (English brand words inside Hindi sentences), naturalness. Also measure ASR-CER on the output (the engine's own ASR) as an automatic gate.

### Expected runtime, 60 s reel (~55 s of speech) on an M-series Mac — **estimates**, built from per-stage reported numbers

| Stage | Basis | Estimate |
|---|---|---|
| ASR | already in pipeline | 0 extra |
| Translation (Claude) | API round-trip | ~10–30 s |
| TTS, Maya MLX 8-bit | reported RTF 0.23 on **M5 Pro**; base M5 has fewer GPU cores → assume ~2× slower (unmeasured) | ~15–30 s per take; ×2–3 takes for timing retries → **~0.5–1.5 min** |
| TTS, VoxCPM2 | reported RTF ≈1.76 (llama.cpp, M4 Pro) | ~1.5–2 min per take |
| TTS, ZONOS3-Mini / Chatterbox | no reliable Mac RTF | unknown — measure |
| Time-stretch + remix | ffmpeg base pass measured ~11–14 s in the 2026-11-18 benchmark | ~15–20 s |
| ASR on dubbed track (CER gate + caption timings) | same ASR as step 0 | ~10–30 s (API latency; estimate) |
| Caption overlay re-render (target script) | measured 2026-11-18: ~43–74 s per 60 s reel depending on composite path | **~45–75 s** |
| Separation (only if needed) | Demucs ~1.5× duration | ~1.5 min |
| Lip-sync, MuseTalk MLX | 1,800 frames ÷ ~34 fps ≈ 55 s model time + CPU face detect/parse/blend (unmeasured, likely dominant) | **~2–6 min** |
| **Total** | | **~2.5–4 min audio dub + new captions; ~5–10 min with lip-sync** |

Rented-GPU fallback (LatentSync 1.6, ≥18 GB): RunPod RTX 4090 community **from $0.34/h**, secure $0.89/h; L40S $0.79/h (https://www.runpod.io/pricing, read 2026-11-20). Even a 15-min pod session (incl. model load) ≈ $0.09–0.22 per reel vs ~$4.20 at $0.07/s on fal. LatentSync per-clip speed not published — measure.

16 GB RAM note: Maya-mac (~7 GB) and MuseTalk-MLX (~7 GB) fit, but **run them sequentially**, not concurrently. Chatterbox on MPS reportedly ~14 GB — tight.

### Honest quality gap vs ElevenLabs / VEED

- **Voice:** zero-shot clones from a 5–10 s reference capture timbre well but carry less of the speaker's prosody and emotion than ElevenLabs' dubbing, which also handles segmenting, timing and multi-speaker automatically. Indic quality of the two Apache models is **unverified independently** (Maya: VoiceArena Hindi ~#7 overall / #2 real-time view; ZONOS3: vendor benchmark only). Hinglish code-switching is the biggest unknown — test it.
- **Timing:** you own the fit loop (translation budget + stretch). Expect occasional rushed or slowed phrases that ElevenLabs smooths.
- **Lip-sync:** MuseTalk's 256 px mouth on a full-HD vertical close-up will look soft/blurry next to VEED Lipsync; no commercially-clean face restorer was identified to fix it. LatentSync on a rented GPU narrows the gap. Use cutaways to hide it.
- **Ops:** these models are weeks old (Maya, ZONOS3) or retired (Chatterbox) — pin versions and keep the paid path as a fallback for premium clients.

---

## 7. Consent and disclosure (required)

- **Written consent from the speaker** before cloning, covering: (1) creating a synthetic copy of their voice, (2) each target language, (3) the specific reels/uses, (4) how long the reference clip and any speaker embedding are kept and when they are deleted, (5) right to revoke. Store it with the project (e.g. alongside the brief).
- Model terms require it anyway: IndicF5 gate ("only clone voices for which you have explicit permission"), Maya ("clone only voices you own or have permission"), CSM (no mimicking real people without explicit consent), VoxCPM2 (no impersonation/fraud), Spark-TTS disclaimer.
- Brand clients: if the person on camera is not the client (hired talent, employee), get consent from **that person**, not just the brand.
- Disclosure: Maya and VoxCPM ask to label AI-generated speech. Check Instagram/Meta's current "AI info" labelling rule for realistic altered audio/video before delivery (not re-verified here). Voice is likely personal data under India's DPDP Act 2023 — not verified here; confirm with counsel.
- Provenance: only Chatterbox embeds a watermark (PerTh). For the others, keep an internal log (input hash, model+version, consent ID) per dubbed render.

---

## 8. Sources (primary)

- Maya 2 Native: https://huggingface.co/maya-research/maya2-native · Mac port: https://huggingface.co/justanurag/maya-mac
- ZONOS3-Mini: https://huggingface.co/Zyphra/ZONOS3-Mini
- VoxCPM2: https://github.com/OpenBMB/VoxCPM · https://huggingface.co/openbmb/VoxCPM2
- Chatterbox: https://github.com/resemble-ai/chatterbox · https://huggingface.co/ResembleAI/chatterbox
- IndicF5: https://huggingface.co/ai4bharat/IndicF5 · https://github.com/AI4Bharat/IndicF5 · data: https://huggingface.co/datasets/ai4bharat/Rasa , https://huggingface.co/datasets/ai4bharat/indicvoices_r , https://www.iitm.ac.in/donlab/indictts/database
- Indic Parler-TTS: https://huggingface.co/ai4bharat/indic-parler-tts
- IndicTrans2: https://github.com/AI4Bharat/IndicTrans2 · NLLB: https://huggingface.co/facebook/nllb-200-distilled-600M
- F5-TTS: https://huggingface.co/SWivid/F5-TTS · OmniVoice: https://huggingface.co/k2-fsa/OmniVoice · DhVaani: https://huggingface.co/ARTPARK-IISc/DhVaani-0.5 · MaskGCT: https://huggingface.co/amphion/MaskGCT · Spark-TTS: https://huggingface.co/SparkAudio/Spark-TTS-0.5B
- XTTS-v2 CPML: https://huggingface.co/coqui/XTTS-v2/blob/main/LICENSE.txt
- OpenVoice: https://github.com/myshell-ai/OpenVoice · CosyVoice: https://github.com/FunAudioLLM/CosyVoice · IndexTTS: https://github.com/index-tts/index-tts · Fish: https://github.com/fishaudio/fish-speech · Higgs: https://github.com/boson-ai/higgs-audio · Orpheus: https://github.com/canopyai/Orpheus-TTS · Kokoro: https://huggingface.co/hexgrad/Kokoro-82M · CSM: https://huggingface.co/sesame/csm-1b · dots.tts: https://huggingface.co/rednote-hilab/dots.tts-base
- Rubber Band: https://breakfastquay.com/rubberband/
- Demucs: https://github.com/facebookresearch/demucs · mac: https://github.com/adefossez/demucs/blob/main/docs/mac.md · MUSDB18: https://sigsep.github.io/datasets/musdb.html · SAM Audio: https://github.com/facebookresearch/sam-audio · BandIt: https://github.com/kwatcharasupat/bandit
- MuseTalk: https://github.com/TMElyralab/MuseTalk · MLX: https://huggingface.co/mlx-community/MuseTalk-1.5-fp16 · face-parsing: https://github.com/zllrunning/face-parsing.PyTorch · CelebAMask-HQ: https://github.com/switchablenorms/CelebAMask-HQ
- LatentSync: https://github.com/bytedance/LatentSync · https://huggingface.co/ByteDance/LatentSync-1.6 · insightface: https://github.com/deepinsight/insightface
- Wav2Lip: https://github.com/Rudrabha/Wav2Lip · VideoReTalking: https://github.com/OpenTalker/video-retalking · Diff2Lip: https://github.com/soumik-kanad/diff2lip
- GPU prices: https://www.runpod.io/pricing

### Open items to verify before building
1. ZONOS3-Mini GitHub runtime LICENSE (MIT per secondary sources only).
2. LatentSync: full OpenRAIL++ text; build a drop-in `FaceDetector` (bbox + 106-pt landmarks) on a commercially-licensed model.
3. MuseTalk: replace upstream preprocessing (BiSeNet, DWPose) and confirm it runs on Py 3.12 / MLX.
4. Speed params in Maya / ZONOS3 for timing fit.
5. IndicF5 data lineage (IndicTTS licence, LIMMITS, F5 init) if it's ever needed.
