# Premium (paid) royalty-free music services for an autonomous AI reel editor

Research date: 2026-11-19. Use case: an autonomous editor that delivers vertical reels to paying freelance clients (Instagram Reels, YouTube Shorts, TikTok). The operator is a freelancer in India.

How to read the quotes in these notes:
- **"Excerpt as returned"**: a quote that came through a page fetcher which summarises and shortens text. The wording is very likely the vendor's, but check it on the live page before relying on it legally.
- **"Paraphrase via search summary"**: the official page was not fetched successfully. The point comes from a search engine's summary of it.
- **Fetch failures.** Several official pages could not be fetched because they returned a JS shell, a cookie wall or HTTP 403:
  - Epidemic Sound terms and pricing pages
  - artlist.io (licence and terms pages)
  - soundstripe.com
  - musicbed.com

---

## Q1. Does the licence cover a freelancer making videos for clients, and on which platforms (IG, YT, TikTok, paid ads)? Per-seat, per-client or per-channel?

### Takeaway
Every major subscription service gates client work behind a "Pro" or "commercial" tier. The entry "Creator/Social/Personal/Basic" tiers exclude clients and paid ads everywhere. Channel coverage is capped per platform (Epidemic 3 per platform, Uppbeat Pro 10 YouTube channels, Artlist Social 1 per platform). The licences are written for one human subscriber, not for a service delivering to many clients.

### Cited Findings
**Epidemic Sound (direct subscription)**
- Pro includes "Freelancer client work licensing", with full sublicensing rights to produce content your clients publish. — [Epidemic Sound, Commercial subscription page (fetched 2026-11-19)](https://www.epidemicsound.com/our-plans/commercial-subscription)
- Pro gives "Monetize 3 channels per platform" and "Digital ads licensing".
  - Paid ad campaigns are allowed only for online campaigns, and not for major corporations, publishers or government entities.
  - Source: the same commercial subscription page.
- Revenue caps (same page):
  - Publishers over USD 5M/yr and companies over USD 10M/yr are not eligible for Pro.
  - Business covers revenue up to USD 25M. Enterprise covers anything above that.
  - Business allows "up to three collaborator accounts".
  - Takeaway for clients: a client company above these thresholds may need its own Business or Enterprise coverage.
- The Creator plan ($9.99/mo annual) excludes client work. — [The Post Flow comparison (2026)](https://thepostflow.com/post-production/video-editing/music-subscriptions-compared/). A review cited in search results claimed that Pro also excludes client work. This conflicts with Epidemic's own page. Prefer the official page.

**Epidemic Sound (partner/API route, end-user terms)**
- elevate.io publishes end-user terms for Epidemic music used inside its own app. Elevate is one Epidemic API partner, so other partners' licences or Scale contracts may differ. The page timestamp is 2026-11-18, which is likely a render time; no revision date is shown. These are not Epidemic's direct subscription terms. — [Epidemic Sound End-User Rights, hosted by elevate.io](https://elevate.io/legal/epidemic-sound)
- That partner licence has three tiers: Starter (free), Creator (personal) and Commercial.
  - Permitted use is "within the Application and on your own social media channels, for one video or podcast production."
  - It bars productions made for others to use, license or sell.
  - It bars incorporating a production into "a software application or video game".
  - Starter bars advertising.
  - Excerpts as returned.
- This one observed partner licence is narrower than the direct Pro plan's "freelancer client work" grant ("your own social media channels"). End-user rights through a sublicensed API may be narrower than direct Pro.

**Artlist**
- Social licence (help-centre article, undated, fetched 2026-11-19):
  - "exclusively for personal content creators", for people "who don't create projects for clients or brands".
  - Covers "a single channel for each of the following platforms": YouTube, TikTok, Facebook, Instagram, Twitch.
  - Source: [Artlist Help, Understanding Artlist's license](https://help.artlist.io/hc/en-us/articles/29490991524253-Understanding-Artlist-s-license)
- Pro licence (same article):
  - "covers both personal and client use for the specific projects created".
  - "a Pro license allows you to create and deliver completed projects to clients".
  - But "you aren't allowed to share assets themselves" and "Clients are not permitted to modify or use the assets independently."
  - Pro is for creators "who need to Clearlist more than one channel per platform".
  - A Business/Enterprise licence is needed "if you're a broadcaster, or if you need more than 7 seats".
- The help article does not address paid ads for music. A third-party review says Social excludes paid ads and Pro is required. — [The Post Flow (2026)](https://thepostflow.com/post-production/video-editing/music-subscriptions-compared/)

**Uppbeat (own blog, dated 2026-10-19)**

| Tier | Licence type | Client work | Paid ads | YouTube safelisting |
|---|---|---|---|---|
| Free, Essentials, Creator | "Basic" | No | No | Free: none; Essentials: 1 channel; Creator: 3 channels |
| Pro | "Solo Professional" | Yes | Yes | 10 channels |
| Business | "Business & Team" | Yes | Yes | 10 channels |

- Basic covers only "a Solo Creator publishing their own material". It excludes "third-party client publishing" and "freelance or employee production".
- Pro "explicitly rules out use as an organization".
- Source: [Uppbeat blog, Commercial music licensing for client videos (2026-10-19)](https://uppbeat.io/blog/royalty-free-and-copyright-free-music/commercial-music-licensing-for-client-videos-what-freelancers-need-to-check)
- An older Uppbeat help-centre snippet describes "Premium" (3 YouTube channels) and "Business" (10 channels, required for client work and paid ads). Tiers appear to have been renamed since. Prefer the Oct 2026 blog. — [Uppbeat help centre, Premium and Business (undated)](https://fastly-f.uppbeat.io/help-center/premium-and-business)

**Storyblocks (Individual licence, last updated 2026-09-28)**
- §1.3: the licence "does not cover any other individual, entity, and/or company".
- §8.2: the indemnity "does not extend to and may not be relied upon [by] any employer, client, agency, or other entity".
- §2.1: sharing raw files with clients is not licensed unless you are on a Business licence.
- §1.2: excludes Broadcast, TV and OTT unless the plan allows it.
- Source (excerpts as returned): [Storyblocks Individual License](https://www.storyblocks.com/license/individual-license)
- Storyblocks' own guidance points to the Business or Enterprise licence for entity-level coverage. — [Storyblocks blog, How to license stock media for client work](https://www.storyblocks.com/resources/blog/how-to-license-stock-media-for-client-work) (seen in search results only)

**Envato Elements (licence terms, revised 2026-10-06)**
- Clause 10a(i): "You can use an Item to create an End Product for yourself or for a client of yours."
- Clause 4: "If you want to use the same Item for separate projects, you will need to create a new license for each end-use." Each reel must be registered as its own project.
- Source (excerpts as returned): [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)

**Motion Array**
- If a client gets a YouTube claim, they "can manage the claim as the end-user of your work". You provide them the asset licence. — [Motion Array Help, What if I get a copyright claim (undated)](https://help.motionarray.com/hc/en-us/articles/9442239143197)
- Motion Array calls its licence a sync licence. Tracks can't be used in "meditation or playlist videos" but can be used in "vlogs, TV commercials, short films, promotional videos". — [Motion Array Help, YouTube Content ID registered music](https://help.motionarray.com/hc/en-us/articles/9442210941341)

**Musicbed**
- A third-party-hosted copy of the MB subscription licence agreement ties the licence to a single project and a single end client. Co-branded projects need a custom written licence. — [MB subscription licence agreement PDF (third-party host, undated)](https://www.thurbo.ch/fileadmin/user_upload/PDF/MB-subscription-license-agreement__2_.pdf) (seen via search summary only)

**Mubert (AI music, licence page)**
- The FAQ says client work is covered "Yes, on the Ultra plan. It covers freelance and agency work, and apps and services."
- The pricing grid on the same page lists "Freelance & Agency Work" on Free, Creator and Pro, and the FAQ says Free and Creator are non-commercial. This is an internal contradiction.
- Monetized YouTube, TikTok and Instagram, ads and brand content are listed as allowed.
- Source: [Mubert Render License](https://mubert.com/render/license)

### Inferences
- The direct subscriptions (Epidemic Pro, Artlist Pro, Uppbeat Pro) cover *one freelancer* delivering finished videos to clients. The automated pipeline acting on the freelancer's behalf is the grey area: the licences assume a human subscriber.
- Channel caps matter: 3 channels per platform on Epidemic Pro, 10 YouTube channels on Uppbeat Pro. With many clients, each client posts to their own channels, which quickly exceeds the caps for *safelisting*. The client-work licence itself may still hold even when the client's channel is not safelisted, but claims will then need disputes.
- For a product that serves many freelancers or clients, the more defensible route is a partner/API contract (Epidemic Scale/Enterprise, Soundstripe partnership). Those contracts include sublicensing to end users. But the one partner end-user licence observed (Elevate's, for Epidemic music) is narrower ("your own social media channels", no productions for others). Client-delivery rights must be negotiated explicitly into a Scale/Enterprise contract.
- Envato's "new licence per end-use" rule means the pipeline would have to register each reel/client project in Elements. That needs a human in the loop, or an API that does not appear to exist.

### Gaps
- Musicbed's current direct subscription terms and tier names/prices: musicbed.com did not render for the fetcher.
- Motion Array's full licence text: [motionarray.com/license](https://MOTIONARRAY.COM/license/) not fetched.
- Audio Network's licence for client and social work: not researched in this pass.
- Artlist Pro paid-ads and per-platform channel count for Pro: the help article was silent on these.
- Whether the Epidemic Scale API contract grants client-work sublicensing: not public, needs a sales conversation.

---

## Q2. Clauses on AI/ML, automated tools, scraping, bulk download, caching/indexing, use inside automatic video-generation software

### Takeaway
- **AI training is banned by every vendor checked.** That covers Epidemic, Artlist, Storyblocks and Musicbed's contest terms. Using music in an AI *editing* pipeline (selection, cutting, mixing) is not training. Artlist's April 2026 licence now explicitly allows assets "as inputs in AI services" as long as they are not used for training.
- **Bulk/automated downloading and caching are restricted.** Storyblocks bans automated scraping and bulk downloading (500+ files without intended use is a material breach). Envato bans redistribution "in a tool" and "on-demand" apps.
- **Software embedding is restricted.** Epidemic's partner end-user licence bans putting productions into "a software application".

### Cited Findings
**Epidemic Sound**
- Direct Terms of Use (paraphrase via search summary; the page was a cookie wall and the indexed copy was about 428 days old): you may not use the Content for software development, "including training a machine learning or artificial intelligence system". Using Gen AI Features or their output to train AI models or build competing products is prohibited. — [Epidemic Sound Terms of Use](https://www.epidemicsound.com/policy/general-terms-and-conditions/)
- Partner end-user licence published by Elevate, one Epidemic API partner. Page timestamp 2026-11-18, likely render time. Excerpts as returned:
  - Bars use for "the development of any software program, including, but not limited to, training a machine learning [system]".
  - Bars "performing on the Licensed Work any form of text and/or data mining (TDM)".
  - Bars "uploading the Licensed Work to any music recognition system".
  - Bars making the track available "on a stand-alone basis".
  - Bars incorporating a production into "a software application or video game".
  - Bars editing beyond cutting, looping and fading.
  - Source: [elevate.io, Epidemic Sound End-User Rights](https://elevate.io/legal/epidemic-sound)
- Epidemic's single-track licence PDF references uploading tracks "to any machine learning application for any purpose". The snippet was truncated, but the context suggests a prohibition. — [Epidemic Single Track Licenses V9 PDF](https://www.epidemicsound.com/staticfiles/legacy/20/documents/SingleTrackLicensesV9.pdf) (search snippet only)
- The Developer API offers AI-assisted *discovery*: Soundmatch (recommends tracks from video frames), semantic search, Find similar, and "Highlights" (the best segment for short-form). This shows Epidemic sanctions automated selection through its API. — [Epidemic Sound Developers (fetched 2026-11-19)](https://developers.epidemicsound.com/)

**Artlist** (none of these documents were fetched; all points are paraphrases via search summary)
- Terms of Use, last updated 2026-07-02: "You are forbidden from using any Proprietary Content and/or data and/or information and/or the Site for purposes of machine learning and/or Artificial Intelligence ('AI') training." — [Artlist Terms of Use](https://artlist.io/help-center/privacy-terms/terms-of-use)
- Pro licence dated 2026-04-01, titled "current pro license permitting assets in ai":
  - "You may use Assets as inputs in AI services, provided they are not used to train or fine-tune AI models."
  - Assets may not be included in datasets for ML, AI training or AI development.
  - Source: [Artlist Pro License PDF (01-04-2026)](https://help-center.artlist.io/media/w5mglb2w/current-pro-license-permitting-assets-in-ai-clean-01042026.pdf). The PDF was downloaded but could not be text-extracted in this session.
- Conflict: the earlier Pro licence (Aug 2025 voice-clone version) reportedly said Assets cannot be input into AI systems for any purpose. The Apr 2026 version relaxed this. — [Artlist Pro License voice clones (21-08-2025)](https://help-center.artlist.io/media/g2tebxpm/pro-license-voice-clones-clean-version-21082025.pdf)
- Acceptable Use Policy, last updated 2026-10-15: prohibits using any Asset, Input, Output or Project "as part of a dataset, or to train, fine-tune, or otherwise support any AI or machine-learning system". — [Artlist Acceptable Use Policy](https://artlist.io/help-center/privacy-terms/acceptable-use-policy/)
  - "Otherwise support" is broad and may be in tension with the Pro licence's "inputs in AI services" permission.
- Artlist may "discontinue the license with regard to specific assets that have issues". — [Artlist Help, Understanding Artlist's license](https://help.artlist.io/hc/en-us/articles/29490991524253-Understanding-Artlist-s-license)

**Storyblocks** (Individual License, updated 2026-09-28; excerpts as returned) — [Storyblocks Individual License](https://www.storyblocks.com/license/individual-license)
- §2.9: you may not use any Stock File "for machine learning and/or artificial intelligence purposes (i.e., to train AI systems)". This includes metadata. Using AI to help *select* Stock Files, or to create projects that don't transform the files, is not restricted.
- §2.1: bars using automation to download or scrape high volumes of Stock Files. Example given: "downloading 500 or more files without intending to use them for any particular Subscriber Works" would be a material breach.
- §3: you may not "upload or share any portion of an audio-based Stock File with any digital streaming platform".
- Conflict: a Storyblocks help article reportedly says users can use stock files and metadata for ML/AI purposes. This contradicts §2.9 of the licence. Treat the licence as controlling. — [Storyblocks Help, limitations](https://help.storyblocks.com/en/articles/3622257-are-there-any-limitations-to-the-storyblocks-licenses) (search summary only)

**Envato Elements** (revised 2026-10-06; excerpts as returned) — [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- Clause 12b: "You can't redistribute an Item as stock, in a tool or template, or with source files."
- Clause 12c: prohibits on-demand or made-to-order applications.
- The licence-terms page itself does not mention AI training, scraping or bulk download. Envato's separate user terms may.

**Soundstripe** (via search summaries of Soundstripe API docs and third-party profiles; not fetched directly)
- Audio, stems and artist images must be served from Soundstripe's CDN, and client-side apps can't call the API directly.
- The API terms limit end users to using music inside their own Projects.
- Source: [Soundstripe API (context7 index of docs)](https://context7.com/websites/soundstripe), [api-evangelist profile](https://github.com/api-evangelist/soundstripe)

**Musicbed**
- 2025 MB Challenge contest terms prohibit use of the licensed content for "artificial intelligence, machine learning, or any form of algorithmic training, development, or creation". This covers the contest, not the standard subscription. — [Musicbed 2025 Challenge Contest License Terms PDF](https://res.cloudinary.com/musicbed-marketing/image/upload/v1739289336/Newsletters/2025/2025_MB_Challenge_Contest_License_Terms.pdf)

**Mubert**
- Bans "Registering Mubert tracks in Content ID, releasing them on music streaming services" on all plans. — [Mubert Render License](https://mubert.com/render/license)

### Inferences
- An AI editor that *selects and cuts* licensed tracks for a specific client reel is closest to the "AI helps select / no transformation" carve-out in Storyblocks §2.9 and to Artlist's April 2026 "inputs in AI services" permission. It is not training. Do not let the asset pipeline feed licensed audio into any model fine-tuning, embedding-for-training or dataset.
- **Pre-downloading and locally indexing the catalogue is the highest-risk pattern.** Storyblocks §2.1 (500+ files without intended use) is effectively a ban on it. Soundstripe's CDN-only serving rule implies no local caching. Epidemic's TDM and music-recognition bans point the same way.
  - Safe design: search through the vendor API or site, download only the track chosen for a specific reel, and keep a per-reel licence record.
- Computing embeddings, beat grids or audio fingerprints on vendor audio could arguably be "text and/or data mining" or uploading "to any music recognition system" (Epidemic partner terms). Prefer vendor-provided metadata (BPM, mood, beat markers, Highlights) over self-computed analysis. If self-analysis is needed, get written clearance.
- Envato 12b ("in a tool") and 12c ("on-demand") plus Epidemic's "software application" ban mean an editor offered *as a product* to other freelancers, built on one subscription, is very likely non-compliant. A single freelancer using their own subscription with the AI as their tool is more defensible.

### Gaps
- Verbatim current Epidemic Sound direct Terms of Use (fetch blocked by cookie wall).
- Full text of Artlist ToS (2026-07-02), AUP (2026-10-15) and Pro licence (2026-04-01): artlist.io returned 403, and the PDF text could not be extracted.
- Musicbed's standard subscription AI clause.
- Uppbeat and Motion Array AI/automation clauses: not found in this pass.
- No vendor states explicitly whether "an AI agent that autonomously picks and edits music for client videos" is permitted. Get written confirmation from the chosen vendor.

---

## Q3. Is there an API? Self-serve or partner-only? What does it return? Pricing?

### Takeaway
Only Epidemic Sound and Soundstripe have documented music-licensing APIs.
- **Epidemic** has a self-serve free key for prototyping only. Going live needs a sales-led Scale or Enterprise contract with custom pricing.
- **Soundstripe** is partnership-led with a 30-day trial key.
- **AI music generators** (Mubert, Soundraw, Beatoven) have APIs. Mubert and Soundraw quote custom prices. Beatoven has a public REST API with no API pricing found.

### Cited Findings
**Epidemic Sound Developer/Partner API** — [developers.epidemicsound.com (fetched 2026-11-19)](https://developers.epidemicsound.com/)
- Catalogue via API: "55,000 tracks and 250,000+ sound effects".
- Features: semantic search, Find similar (EAR), Soundmatch (recommendations from video frames), Highlights ("most relevant segment of a track for short-form content"), curated playlists by mood, theme and genre.
- Plans:

| Plan | Price | Terms |
|---|---|---|
| Free | $0 | "Prototyping only — you cannot go live on this plan"; up to 50 downloads; no commercial licence |
| Scale | Custom, based on download volume | Commercial licence, limited monthly downloads, "Sub-licensing for your end-users", use across social, websites and ads; safelisting is a paid add-on |
| Enterprise | Custom | For more than 1,000 monthly downloads; custom licence, SLA and download cap |

- The page's feature lists are internally inconsistent: the Free plan lists safelisting, but also "All endpoints except safelisting".
- Documented guides on the developer site (from the safelisting page nav): Authentication, Music, Metadata, Sound effects, Usage, Create versions (Beta), Find similar, Search by reference, Search by video, Soundtracking (Beta), Pagination. — [Epidemic Safelisting API docs](https://developers.epidemicsound.com/docs/safelisting/)

**Epidemic Safelisting API** (same page)
- Works for channels on YouTube, Instagram, Facebook, TikTok, Twitch, podcasts and websites. Video-level safelisting is YouTube-only.
- Channel licences "can have an expiration date" to match a subscription.
- Requires "safelisting enabled … configured as part of your partnership agreement".
- Uses API-key auth with an `X-Partner-User-Id` header.
- Returns 409 if the asset is already safelisted by another end user.

**Soundstripe API**
- Docs index (fetched): endpoints for Songs (retrieve), Sound effects (retrieve, list, categories), curated playlists, private playlists (CRUD), and "Supe Search".
  - Supe Search: "Search Soundstripe's music catalog using natural language, project context, and reference imagery".
  - It uses async asset uploads with results delivered by signed webhooks.
  - Assets are scoped per API key.
  - Source: [docs.soundstripe.com](https://docs.soundstripe.com/)
- Access is a conversation with the partnerships team (no public pricing). A self-serve 30-day trial key is mentioned. — [Soundstripe blog, Music licensing for apps](https://www.soundstripe.com/blogs/music-licensing-for-apps) (search summary; page didn't render)
- Third-party profile (not official): server-to-server REST at api.soundstripe.com, JSON:API, token auth, 25 req/sec, signed webhooks. — [api-evangelist/soundstripe](https://github.com/api-evangelist/soundstripe)
- Licensing model (search summary): the platform licenses each end user through its app, requires them to accept Soundstripe's Terms of Use, and is responsible for their use.
- Catalogue figures conflict: "60k+" on the API page, 116,000 in later blogs, 58,000 on an older page. — [Soundstripe API page](https://www.soundstripe.com/api)

**Mubert** (AI-generated)
- B2B API v3: track generation, HTTP/WebRTC streaming, a pre-generated library, and licence/subscription admin. — [Mubert API docs](https://mubert.com/ja/api/docs), [API Evangelist Mubert profile](https://providers.apievangelist.com/providers/mubert/)
- "Custom Plan / API": price not listed; contact business@mubert.com. — [Mubert Render License](https://mubert.com/render/license)
- Consumer tiers: Free and Creator ($14/mo) are non-commercial, Pro is $39/mo, Ultra "Apps & Agency" is $89/mo. — same page

**Soundraw** (AI-generated)
- API plan for "integrat[ing] SOUNDRAW's AI music API directly into your apps or services", with enterprise pricing. — [Soundraw Business](https://soundraw.io/business)
- Soundraw's own blog: "The moment music is generated or distributed through your app, you need an API license, which is a different price list entirely." — [Soundraw blog, AI music API under $50](https://soundraw.io/blog/post/ai-music-api-under-50-dollars-indie-developers)
- API price: custom-quoted. — [Costbench Soundraw](https://costbench.com/software/ai-music-generators/soundraw/) (aggregator)

**Beatoven.ai** (AI-generated, Bengaluru, India)
- Public REST composition API at public-api.beatoven.ai, plus an open-source Python SDK. `POST /api/v1/tracks/compose` returns a task id; poll `GET /api/v1/tasks/{task_id}`. — [API Evangelist Beatoven profile](https://providers.apievangelist.com/providers/beatoven/) (third-party)
- Consumer pricing is inconsistent across aggregators:
  - Pay-as-you-go: about $3 per download minute.
  - Creator: about $7–10/mo.
  - Source: [Costbench Beatoven](https://www.costbench.com/software/ai-music-apis/beatoven-ai/)

### Inferences
- **Epidemic's API is the best technical fit for an autonomous reel editor.** It offers semantic search, search-by-video (Soundmatch), Highlights for short-form segments and a programmatic Safelisting API covering IG, TikTok and YT. Its free tier cannot go live, so production needs a Scale contract (custom price, likely beyond a solo freelancer's budget).
- Soundstripe's API is comparable in concept (natural-language and reference-image search) but partnership-only. The CDN-serving requirement suits a web app streaming previews, but conflicts with a pipeline that downloads and renders locally. Clarify render-time download rights.
- No API was found for Artlist, Musicbed, Envato Elements, Motion Array or Uppbeat. With those, the pipeline would rely on manual or browser-driven downloads, which runs into the anti-automation clauses in Q2.

### Gaps
- Storyblocks API: a Storyblocks API exists for partners, but its audio coverage, pricing and terms were not retrieved. Storyblocks EULA templates with a placeholder for the API customer name suggest custom partner terms. — [Storyblocks EULA example hosted by Descript](https://www.descript.com/terms-storyblocks) (not fetched)
- Envato Elements API: none found for Elements downloads. Not verified.
- Epidemic Scale pricing, download caps and whether stems or beat-markers are returned: not public.
- Beatoven API pricing and API-specific licence terms: not found.
- Tracklib: not researched in this pass.

---

## Q4. Subscription pricing (individual vs business/pro), and what happens to published videos if the subscription lapses

### Takeaway
- **Price.** The client-capable tier costs about USD 15–25/mo on annual billing across Epidemic Pro, Artlist Pro and Uppbeat Pro. Monthly billing roughly doubles it.
- **Lapse rule.** Universally, content published *during* an active subscription stays licensed forever. Assets downloaded but not yet published lose coverage at lapse.
- **Client launch dates.** A reel delivered but published by the client *after* the freelancer cancels is uncovered under Artlist and Epidemic wording. Uppbeat advises keeping the subscription active until the client's launch.

### Cited Findings
**Epidemic Sound**
- Pro costs $16.99/mo billed annually ($203.88) or $39.99 monthly. Another source gives $30 monthly. — [The Post Flow (2026)](https://thepostflow.com/post-production/video-editing/music-subscriptions-compared/), [lesfm.net (2026-03-20)](https://lesfm.net/blog/epidemic-sound-pricing) (both third-party; the official pricing page did not render)
- Creator costs $9.99/mo annual and excludes client work. Its lapse wording is "completed, uploaded, and published" during the term. — [The Post Flow](https://thepostflow.com/post-production/video-editing/music-subscriptions-compared/)
- Official commercial page:
  - "All videos published during an active subscription will be cleared forever."
  - Videos published after the subscription ends are not cleared.
  - You stay covered until the next renewal date.
  - Source: [Epidemic Commercial subscription](https://www.epidemicsound.com/our-plans/commercial-subscription)
- Partner end-user licence: a permitted production "may remain published perpetually". — [elevate.io Epidemic End-User Rights](https://elevate.io/legal/epidemic-sound)

**Artlist**
- Pro (music) costs $16.58/mo annual for music only, or $24.92/mo for music + SFX. Social costs $9.99/mo and excludes client work and paid ads. "Artlist Max" costs $39.99/mo annual and bundles footage, templates, plugins and AI credits. — [Activepieces, Artlist Pricing 2026](https://www.activepieces.com/blog/artlist-pricing-2026-what-every-plan-costs.md), [The Post Flow](https://thepostflow.com/post-production/video-editing/music-subscriptions-compared/) (third-party)
- Lapse rules (help centre):
  - "Once your subscription expires, these assets cannot be used in new projects."
  - "Any project completed and published during an active subscription remains cleared for monetization."
  - If a project is published after expiry, "the license will not be valid".
  - "The Clearlist must be updated while your subscription is active."
  - Source: [Artlist Help](https://help.artlist.io/hc/en-us/articles/29490991524253-Understanding-Artlist-s-license)

**Uppbeat** (USD, own blog dated 2026-10-19)

| Plan | Monthly | Billed yearly |
|---|---|---|
| Essentials | $8.99 | $6.99 |
| Creator | $12.99 | $8.99 |
| Pro | $24.99 | $14.99 |
| Business | — | $34.99 (excl. tax) |

- Lapse rules (same post):
  - Videos first published while subscribed stay licensed.
  - Videos uploaded to safelisted channels before the end stay protected from claims.
  - Unused downloads can't be used afterwards.
  - "If a client's campaign launches after cancellation", keep the subscription active until first publication or agree the launch date in advance.
- Source: [Uppbeat blog (2026-10-19)](https://uppbeat.io/blog/royalty-free-and-copyright-free-music/commercial-music-licensing-for-client-videos-what-freelancers-need-to-check)

**Storyblocks**
- §1.2: the perpetual right "survives the expiration, non-renewal, or termination of your subscription but is limited to Stock Files incorporated into Subscriber Works that are completed during a paid subscription term."
- §5: once a subscription expires, you lose the right to download and use additional files.
- Note: Storyblocks keys on *completed* during the term, not *published*. This is friendlier for client launch delays than Artlist or Epidemic.
- Source: [Storyblocks Individual License (2026-09-28)](https://www.storyblocks.com/license/individual-license)

**Envato Elements**
- Clause 12a: "You can't use an Item to create an End Product after your Envato Elements subscription ends."
- Clause 8: the licence becomes perpetual once the item is in a completed End Product made during an active subscription.
- Client transfers are allowed if your subscription stays active.
- Source: [Envato Elements License Terms (2026-10-06)](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)

**Musicbed**
- Pricing is unverified:
  - One aggregator gives about $29.99/mo (Individual). — [Toolradar Musicbed pricing](https://toolradar.com/tools/musicbed/pricing)
  - Another gives a $10–25/mo range. — [frontdeskreview (updated Sept 2026)](https://frontdeskreview.com/software/music-licensing/musicbed/)
  - The two conflict, and the official page didn't render.
- A third party claims the "license does not survive cancellation for most plans". Unverified. — [licenseorg.com Musicbed guide](https://licenseorg.com/guide/music-audio/musicbed)
- Musicbed's own FAQ "How long is my license good for" exists but was not fetched. — [Musicbed support FAQ](https://support.musicbed.com/musicbed-faq/how-long-is-my-license-good-for)

**AI music**
- Mubert:
  - Pro $39/mo (commercial), Ultra $89/mo (apps and agency).
  - The page does not say whether the licence persists after cancellation.
  - The footer says music is "licensed by Mubert® Inc only for personal use", which contradicts the commercial plans.
  - Source: [Mubert Render License](https://mubert.com/render/license)
- Soundraw and Beatoven: aggregators say downloads carry a perpetual, non-exclusive commercial licence on paid plans. Prices vary widely across aggregators. — [Costbench Soundraw](https://costbench.com/software/ai-music-generators/soundraw/), [Costbench Beatoven](https://www.costbench.com/software/ai-music-apis/beatoven-ai/)

### Inferences
- For the freelancer: the "publish during subscription" rule (Epidemic, Artlist) creates a business risk if clients post late. Mitigations:
  - keep the subscription continuous, or
  - publish or schedule from the freelancer's side, or
  - choose a "completed during term" licence (Storyblocks, Envato).
- India pricing in INR was not found. Several vendors localise prices, so check in-region.

### Gaps
- Official INR or regional pricing for any vendor.
- Musicbed and Motion Array current official prices.
- Motion Array post-cancellation terms: its help pages don't state them, per search results.

---

## Q5. Catalogue size, metadata quality, Indian / Bollywood / desi / regional availability

### Takeaway
- **Size.** Epidemic is about 50–55k tracks and Soundstripe 60k–116k (conflicting figures). Epidemic has an explicit "India" genre covering classical, Bollywood-style, devotional, folk and fusion.
- **Indian music.** Beatoven.ai, an Indian AI-music company, is the only source found that markets an Indian genre in generation.

### Cited Findings
- Epidemic Sound:
  - Its "India" genre page covers traditional classical Indian music and modern Bollywood-style tracks, including devotional, folk, classical and fusion.
  - The catalogue is cited as 50,000 tracks / 200,000 SFX on the English page and 55,000 on the FR/IT pages.
  - Source: [Epidemic Sound India genre](https://epidemicsound.com/music/genres/india), [Exploring India theme](https://www.epidemicsound.com/music/themes/travel/exploring-india)
- The Epidemic API advertises "55,000 tracks and 250,000+ sound effects" and curated playlists by mood, theme and genre. — [Epidemic Developers](https://developers.epidemicsound.com/)
- Soundstripe catalogue: 60k+ (API page) vs 116,000 (later blogs) vs 58,000 (older page). Conflicting. — [Soundstripe API](https://www.soundstripe.com/api) (search summary)
- Beatoven.ai is a Bengaluru generative-music startup founded in 2021. A reviewer said "I am unaware of any other company that has implemented the Indian genre". Anecdotal. — [API Evangelist Beatoven](https://providers.apievangelist.com/providers/beatoven/), [AppSumo reviews](https://appsumo.com/products/beatovenai/reviews/?page=1)
- Other Indian-flavoured royalty-free sources seen:
  - PremiumBeat track "Vintage Bollywood (Desi Riddim)". — [PremiumBeat](https://www.premiumbeat.com/th/royalty-free-tracks/vintage-bollywood-desi-riddim)
  - Lickd "Sounds of India" collection. — [Lickd](https://app.lickd.co/browse/collection/included-sounds-of-india)

### Inferences
- For Hinglish reels, the realistic premium options are:
  - Epidemic's India genre and playlists, searchable via the API with mood metadata
  - general global genres (lo-fi, hip-hop, EDM), which suit Hinglish content anyway
  - AI generation (Beatoven) for desi-flavoured beds
- Unsourced inference: actual Bollywood film songs are owned by labels (e.g. T-Series, Saregama) and are unlikely to be in any royalty-free library.
- Trending Bollywood songs on Reels come from Instagram's in-app music library (label-licensed). That library is not available to a stock-library pipeline.

### Gaps
- Artlist, Musicbed, Soundstripe, Uppbeat and Envato Indian or regional catalogue depth: no results found.
- Track counts for Indian-genre tracks in any library.
- Artlist and Musicbed total catalogue sizes: not retrieved from primary sources.

---

## Q6. YouTube Content ID / Instagram claim handling: registration, whitelisting/safelisting, known problems

### Takeaway
- **Most premium libraries register tracks with Content ID and rely on channel safelisting** (Epidemic "safelisting", Artlist "Clearlist", Uppbeat safelisting). An unsafelisted client channel will get claims that need disputing.
- **Epidemic** has a Safelisting API for partners covering IG, TikTok and YT. Video-level safelisting is YouTube-only.
- **Motion Array** marks per track whether it is Content ID-registered.
- **Mubert** forbids Content ID registration of its tracks.

### Cited Findings
- Epidemic: "Safelisting is the process of connecting your videos and channels to an Epidemic Sound account." The help centre says it is "crucial to safelist the channel(s) or video(s) … before posting." — [Epidemic, What is safelisting](https://www.epidemicsound.com/how-it-works/music-licensing/what-is-safelisting/), [Epidemic Help, Safelisting](https://help.epidemicsound.com/hc/en-us/articles/26248340314258-Safelisting)
- Epidemic partner end-user licence: Epidemic may monetize unlicensed use and may demonetize uncleared productions without reimbursement. On the Starter tier, Epidemic keeps the sole right to monetize, and you agree not to dispute claims. — [elevate.io](https://elevate.io/legal/epidemic-sound)
- Epidemic has dedicated help articles on dispute processes ("Why was a Content ID claim received", "How to dispute a claim on YouTube"). — [Epidemic Help, Content ID claim](https://help.epidemicsound.com/hc/en-us/articles/26253712691730-Why-was-a-Content-ID-claim-received-from-Epidemic-Sound), [How to dispute](https://help.epidemicsound.com/hc/en-us/articles/26252460246802-How-to-dispute-a-claim-on-YouTube)
- Reported problems:
  - A complaint-focused site says safelisted paying customers still receive Epidemic claims, sometimes upheld after dispute. Anecdotal, single biased source. — [botcrawl.com](https://botcrawl.com/epidemic-sound-scam/)
  - A third-party guide notes Shorts, Reels and livestreams can still be flagged if not registered. — [culturaldaily.com (2026)](https://www.culturaldaily.com/how-creators-can-keep-videos-monetized-in-2026/)
- Artlist: Clearlist connects channels "ensuring YouTube recognizes your licensed music and helps prevent copyright claims." Artlist reserves the right to introduce "new clearance and enforcement mechanisms." — [Artlist Help](https://help.artlist.io/hc/en-us/articles/29490991524253-Understanding-Artlist-s-license)
- Uppbeat: safelisting "tells YouTube you have permission, which stops claims before they happen". There is a claim-release tool if a claim still appears. Safelisting covers 1, 3 or 10 YouTube channels depending on tier. — [Uppbeat blog (2026-10-19)](https://uppbeat.io/blog/royalty-free-and-copyright-free-music/commercial-music-licensing-for-client-videos-what-freelancers-need-to-check)
- Motion Array:
  - "Some tracks are registered with Content ID, and this information is always visible on the asset download page." It also has "a large selection of music that is not registered with any Content ID".
  - Its claim remover applies only when the claimant is HAAWK/Identifyy, Elite Alliance Music or Artlist.
  - Source: [Motion Array Help, Content ID registered music](https://help.motionarray.com/hc/en-us/articles/9442210941341), [Motion Array Help, copyright claim](https://help.motionarray.com/hc/en-us/articles/9442239143197)
- Mubert: "Registering Mubert tracks in Content ID, releasing them on music streaming services" is not allowed on any plan. — [Mubert Render License](https://mubert.com/render/license)
- Envato: Clause 14c says "You can't claim ownership of the Item", including through content identification systems. Whitelisting is not mentioned on the licence page. — [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- Musicbed is listed by one aggregator with "SyncID content ID clearance". Unverified. — [Toolradar](https://toolradar.com/tools/musicbed/pricing)

### Inferences
- **Safelisting limits are the binding constraint for client work.** Clients post to their own YT, IG and TikTok accounts. Each client channel uses one of the freelancer's limited safelist slots (3 per platform on Epidemic Pro). Beyond that, each claim needs a manual dispute with the licence.
- **Epidemic's partner Safelisting API** is the only programmatic answer found. It can create per-video YouTube licences, which sidesteps channel caps on YT. It is gated behind a partnership agreement and a paid add-on.
- **Content ID-free sources avoid claims entirely.** These are Motion Array's non-registered tracks, flagged per asset, and AI-generated music that is barred from Content ID, such as Mubert. For an automated pipeline, a "non-Content-ID only" filter is a strong design choice.
- Instagram and TikTok claims behave differently from YouTube (muting or reach restriction rather than revenue redirection). Only YouTube has video-level safelisting via the Epidemic API.

### Gaps
- No quantified data on claim rates for safelisted channels for any vendor.
- Instagram and TikTok claim mechanics per vendor, beyond Epidemic's channel safelisting: not documented in the sources found.
- Artlist and Soundstripe Content ID registration policy details.

---

## Q7. Attribution requirements

### Takeaway
None of the fetched Artlist, Envato, Uppbeat or Mubert pages states an attribution requirement. That is absence of evidence, not confirmation. Epidemic's direct terms were not verified. Elevate's partner licence for Epidemic music requires a credit line "where standard practice applies". Storyblocks requires retaining copyright notices in electronic files.

### Cited Findings
- Elevate's partner end-user licence for Epidemic music: credit is required when publishing where standard practice applies, in the form "Artist's Name / Title of Music Pieces / courtesy of Epidemic Sound", linked to epidemicsound.com where possible. — [elevate.io Epidemic End-User Rights (page timestamp 2026-11-18)](https://elevate.io/legal/epidemic-sound)
- Storyblocks §9.2: you must "retain the copyright symbol, the name of Storyblocks, the content identification number" in electronic files. — [Storyblocks Individual License](https://www.storyblocks.com/license/individual-license)
- Artlist's help article does not mention attribution requirements. — [Artlist Help](https://help.artlist.io/hc/en-us/articles/29490991524253-Understanding-Artlist-s-license)
- Envato's licence page sets out no attribution requirement. — [Envato License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- Uppbeat's Oct 2026 client-licensing post does not mention attribution for free or paid tiers. — [Uppbeat blog](https://uppbeat.io/blog/royalty-free-and-copyright-free-music/commercial-music-licensing-for-client-videos-what-freelancers-need-to-check)
- Mubert's licence page does not address attribution. — [Mubert Render License](https://mubert.com/render/license)

### Inferences
- For reels, a pipeline can append the Epidemic-style credit to the caption or description automatically when using an Epidemic partner licence. For direct paid subscriptions, no credit requirement was found, but this is unconfirmed, so verify per vendor. Either way, store a per-reel licence record (track ID, licence/certificate, channel, publish date) for disputes.

### Gaps
- Uppbeat free-tier attribution wording (historically the free tier required credit) was not verified in this pass.
- Epidemic direct-subscription attribution rules (the direct ToS was not readable).
- Soundstripe, Musicbed, Motion Array and Soundraw/Beatoven attribution rules: not found.
