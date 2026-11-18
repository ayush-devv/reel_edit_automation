# Asset sources for an in-app reel editor (2026-11-18; not legal advice)

"(3P)" means the claim comes from a third-party source and is not verified against the provider's own page.

**The test: does the source let you pass assets to end users?**
- **OK:** the source grants redistribution through an API. Pexels and Pixabay ToS §7A: "redistribute… including via an API". Coverr: "video editors can make Coverr stock available inside their product".
- **Risky:** you hold the license, so handing assets to users counts as redistribution.

**Cross-cutting: you can't build a local mirror of API stock.**
- Pexels: "Bulk, large-scale or systematic copying… strictly prohibited", and no ML data mining.
- Pixabay: "Systematic mass downloads are not allowed".
- Coverr: nothing may be used to "train, fine-tune, distill or evaluate AI models".
- Soundstripe: "Permanent downloading, caching, or long-term storage… strictly prohibited".

So the CLIP/CLAP index holds only owned, CC0 or generated assets, and API results are embedded at query time only. Whether even that counts as "evaluate"/mining: **legal review**.

## 1. B-roll video

| Source | API | Embedding OK? | Attribution | Cost/limits | Notes |
|---|---|---|---|---|---|
| [Pexels](https://www.pexels.com/api/documentation/) | Yes | **Yes** ([§7A](https://www.pexels.com/terms-of-service/); a combined new work isn't "Standalone") | "prominent link to Pexels" | Free; default 200/hr and 20k/mo; a raise needs a demo | `orientation=portrait`; no duration filter on search. No "replicate core functionality". |
| [Pixabay](https://pixabay.com/api/docs/) | Video and images only | **Yes** ([§7A](https://pixabay.com/service/terms/)) | Show the source | Free; 100/60s; 24h cache; no permanent hotlinking | **No video orientation filter**: check w/h yourself. |
| [Coverr](https://coverr.co/license) | Yes | **Yes, explicitly** | Free tier: credit Coverr and the creator. Pro: none. | [Free 50/hr (demo only); Pro $24/mo ($10.80/mo annual), 2,000/hr](https://coverr.co/developers) | Download-stats PATCH is mandatory. Shutterstock/iStock/PremiumBeat partner clips are "not covered". |
| [Storyblocks](https://www.storyblocks.com/business-solution/api) | Paid | **Yes**: end users distribute to "web, social… paid ads" | No | Quote | Built for this |
| [Shutterstock](https://developers.shutterstock.com/license) | Paid | **Yes**, Platform License; your EULA must pass on its restrictions or you "may be liable" | No | Sales | A new license for each use |
| [Mixkit](https://mixkit.co/terms/) | None | **No**: §9.10 bans "bots to mass download"; §9.5 bans "competitive product" | n/a | n/a | License text **unverified** |
| Videvo | None | Now [Freepik ToS](https://www.freepik.com/terms-of-service/); licenses mixed per clip | n/a | n/a | Avoid |
| Artlist | [Enterprise API](https://developer.artlist.io/use-cases) (music); no Artgrid API | Negotiated | n/a | Sales | n/a |

Not researched: Getty/iStock, and how much vertical footage each library has.

## 2. Music

- **Platform music libraries don't carry over.** Your app exports a rendered MP4, and in-app libraries don't license that.
  - Meta restricts [business accounts](https://help.instagram.com/402084904469945) from its library. Sound Collection is cleared for FB/IG only (3P).
  - YouTube Creator Music: "only… in videos uploaded to YouTube".
  - Unlicensed music gets muted or claimed. Licensed music can still be falsely claimed, so you need safelisting.

| Source | Embedding OK? | Cost | Notes |
|---|---|---|---|
| [Epidemic Partner API](https://developers.epidemicsound.com/docs/overview) | Free-tier users get a "personal user license" only. Commercial use needs the user's paid Epidemic subscription (ES Connect). | Custom, gated | Safelisting API for YouTube; best Content ID story |
| [Soundstripe API](https://www.soundstripe.com/api-terms-of-use) | **Yes**: "license end users to distribute Projects via any medium" | Negotiated | No caching |
| [ElevenLabs Music](https://elevenlabs.io/music-terms) | Free–Pro plans are "For Individual Use Only"; companies need Business (<50 staff) or Enterprise. Excludes "film, TV, radio, and Studio Games". §4.2 bans compiling a "Music Library". | $0.15–0.50/min (3P) | Delivering output to end users isn't covered in the terms: **legal review** |
| Stable Audio | [Open weights](https://stability.ai/news/license-update): commercial OK under $1M revenue. API output terms unverified. | ~$0.08–0.20/gen (3P) | Review |
| [Mubert](https://mubert.com/api) / [Uppbeat](https://uppbeat.io/api) | Mubert: sublicensing needs an Agency license (3P). Uppbeat: no public terms. | Custom | **Unverified** |
| [Jamendo](https://devportal.jamendo.com/api_terms_of_use) | Free API "for non-commercial uses" only; many tracks are CC-BY-NC | Needs a deal | n/a |
| Pixabay Music | No API. Some tracks are registered in Content ID (3P). | Free | Manual use only |
| YT Audio Library, FMA, Suno/Udio | No official APIs. YT tracks are YouTube-only (3P). | n/a | Avoid |

## 3. SFX

- **[Freesound](https://freesound.org/docs/api/terms_of_use.html):** the API is "free only for non-commercial purposes", so you need a **commercial deal**.
  - Filter `license:"Creative Commons 0"` ([docs](https://freesound.org/docs/api/resources_apiv2.html)). CC-BY sounds would push credits onto users' Reels.
  - Previews (~128 kbps MP3) work with a token. Originals need **per-user OAuth2**.
  - Limits: 60/min, 2,000/day.
- **[Sonniss GDC](https://sonniss.com/gdc-bundle-license/):** commercial use, no attribution, and "apps… all count". But you "may not… supply the sound effects as sound effects to any other person".
  - Baked into the render: likely fine. Sent to the client for previews: **legal review**.
- **Avoid:**
  - [ZapSplat](https://www.zapsplat.com/license-type/standard-license/): "Automated access… prohibited", and redistribution via "apps" is banned.
  - BBC RemArc: non-commercial; commercial use goes through Pro Sound Effects (3P).
  - Pixabay and Mixkit SFX: no API.

## 4. Generative b-roll

- **Google.** The Veo 3.1 Gemini API preview "has been shut down".
  - [Gemini Omni 1.2 Flash](https://aistudio.google.com/docs/omni): 3–15 s, **9:16**, up to 4K (upscaled). "All generated videos include SynthID watermarking". ~$0.07/s at 720p (3P).
  - [Terms](https://aistudio.google.com/docs/terms): "Google won't claim ownership". In the EEA, UK and Switzerland, use only Paid Services when serving users.
- **[Sora 2](https://developers.openai.com/api/docs/models/sora-2):** "shut down on September 24, 2026". **Drop.**
- **Runway:** [gen4_turbo 5 credits/s](https://docs.dev.runwayml.com/guides/pricing/), about $0.05/s (3P credit price).
  - "does not restrict your commercial use of your Outputs" ([help](https://help.runwayml.com/hc/en-us/articles/21668707517587)).
  - C2PA claimed (3P).
- **Kling:** $0.10–0.48/s (3P); terms **unverified**.
- **Luma:** [API Terms](https://lumalabs.ai/legal/api-terms-of-use) allow commercial API use; ~$0.50 per 5 s clip (3P).
- **Latency:** no official figures anywhere, so use async jobs.

## 5. Graphics

- **Icons:** [Tabler](https://github.com/tabler/tabler-icons) MIT, [Lucide](https://github.com/lucide-icons/lucide) ISC, [Phosphor](https://github.com/phosphor-icons/core) MIT.
- **[Lottie Simple License](https://lottiefiles.com/page/license):** commercial use, no attribution. It excludes compiling "to replicate… a competing service", so curate rather than mirror.
- **Emoji:**
  - [Twemoji](https://github.com/jdecked/twemoji): CC-BY 4.0, credit in About.
  - [Noto](https://github.com/googlefonts/noto-emoji): OFL fonts, Apache images.
  - **Apple: no license.**
- **[Google Fonts](https://developers.google.com/fonts/faq):** OFL, Apache or UFL, all commercial. Check per family.

## 6. Indexing

- **Video:** [SigLIP 2](https://huggingface.co/google/siglip2-so400m-patch14-384) (Apache-2.0) on keyframes, plus Claude captions and tags. Use hybrid search.
- **Audio:** [LAION-CLAP](https://huggingface.co/laion/larger_clap_general) (Apache-2.0 weights, CC0 code) or [MS-CLAP](https://huggingface.co/microsoft/msclap) (MS-PL weights; repo archived).

## Red flags

- Mixkit, ZapSplat: automation banned.
- BBC: non-commercial.
- YT Audio Library: YouTube-only.
- Videvo: mixed licenses.
- Jamendo and Freesound: API non-commercial without a deal.
- Suno/Udio wrappers.
- Sora: shut down.
- Apple emoji.
- Earshot: still unverified.
- Caching or indexing API stock.
- A shared generated-music cache across users.
- Auto-placing recognizable people next to brand copy: Pexels and Pixabay ban "misleading" or implied-endorsement use.

## Recommended stack

**v1**
- **B-roll:** Pexels plus Coverr Pro, called live, with attribution in the UI.
- **Own library:** generated (Omni/Runway) and CC0 assets, indexed with SigLIP/CLAP.
- **Music:** default to export without music; the user adds a platform sound. Optionally Stable Audio Open, if under $1M revenue.
- **SFX:** CC0 pack, plus Sonniss after review.
- **Graphics:** Lucide, Noto, Google Fonts, curated Lottie.

**v2**
- Epidemic (safelisting) or Soundstripe.
- Storyblocks or Shutterstock.
- Freesound commercial deal, CC0 only.
- ElevenLabs Business, after review.
