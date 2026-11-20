# Enterprise stock-media APIs and terms for automated/AI use, and indexing a multi-licence asset library for an AI video editor

All sources retrieved 2026-11-19 unless noted. **Quote caveat:** every "quote" below came through a fetch tool that summarises the page with a model. The wording is probably close to the original but is not guaranteed verbatim. Check each clause against the live primary page before relying on it legally. Several primary pages (Shutterstock API terms and licence, Getty EULA, Pond5 API) returned HTTP 403 to automated fetch. For those, the findings come from search-engine summaries and are marked as such.

## A1. Access model and pricing per provider (self-serve vs partner)

### Takeaway
Self-serve, free-key access still exists for Pixabay, Coverr and Shutterstock (free tier, search only), and for Envato Market (personal token). Pexels has paused new keys. Adobe Stock API has been Enterprise-only since Nov 2024. Storyblocks, Pond5 and Getty are sales-led partner deals with unpublished pricing. Per-asset API licensing prices were not published by any provider I checked.

### Cited Findings
- **Pixabay:** free API key. Default limit is "100 requests per 60 seconds", applied per key rather than per IP. Video endpoint `GET https://pixabay.com/api/videos/` returns `id, pageURL, tags, duration, videos{large,medium,small,tiny}, user`. `totalHits` is capped at 500 per query. "Large" is usually 3840x2160 and may be empty. — [Pixabay API docs](https://pixabay.com/api/docs/)
- **Pexels:** the help centre says "New API key issuance is currently paused" (article last updated 2026-11-19). — [Pexels Help: How do I get an API key?](https://help.pexels.com/hc/en-us/articles/900004904026-How-do-I-get-an-API-key). Rate-limit increases are also reported paused ([Pexels Help: unlimited requests](https://help.pexels.com/hc/en-us/articles/900005852323-How-do-I-get-unlimited-requests), via search summary). **Conflict:** the API documentation page still says "Anyone with a Pexels account can request an API key, which you will receive instantly" — [Pexels API docs](https://www.pexels.com/api/documentation/). Default limits are "200 requests per hour and 20,000 requests per month" (same page). Existing keys appear to keep working.
- **Pexels pause start date:** a third-party blog puts it at about 30 Sep 2026. It cites an archive capture showing the notice on 4 Oct but not on 28 Sep. The source is Pexafy, a competing service, so treat it as potentially biased. — [Pexafy blog](https://pexafy.com/blog/pexels-api-key-paused-alternative/). **Conflict with the task premise**, which says "Nov 2026".
- **Adobe Stock API:** "the Stock API will only be available to Stock for Enterprise customers" (as of November 2024). Enterprise customers can create server-to-server credentials. Everyone else must apply via the Adobe Prerelease program and is prioritised if they hold an active, non-trial Stock plan. Affiliates join via the Adobe Affiliate Program. Creative Cloud does not grant API access. Supported functions: search (keyword, similarity, etc.), licensing, download, and licence history. — [Adobe Stock API Getting Started](https://developer.adobe.com/stock/docs/getting-started/)
- **Shutterstock:** three API subscription tiers: Free ("Free library"), Standard ("Expanded library") and Enterprise ("Complete Shutterstock library"). "These API subscriptions are separate from the subscriptions that are available on the Shutterstock web site." AI search is unavailable on Free and Standard and "Custom" on Enterprise. Computer-vision endpoints cover image upload, similar images, similar videos and keyword suggestions. Reverse/similar search is "Limited" on Free and Standard. — [Shutterstock API reference](https://api-reference.shutterstock.com/). A free account can search and use the CV endpoints but cannot license or download (search summary) — [Shutterstock developers: computer vision](https://developers.shutterstock.com/solutions/computer-vision)
- **Storyblocks API:** sold to businesses and platforms. Test keys are free, with unlimited search and five free downloads per content type. Production requires a sales conversion. "Cost varies depending on your use case". Covers video, images, audio (music and SFX), "100% human-made", 8M+ assets. Two licence levels: the Standard API licence covers "web, social, digital, multimedia, and paid ads", and the Enhanced licence is needed for broadcast, film and OTT. Pictory.ai is listed as a customer. — [Storyblocks API](https://www.storyblocks.com/api)
- **Pond5:** the API serves "resellers, marketing affiliates, and other distribution partners". Licensing rights and pricing are customised per partner. I found no public self-serve signup. The direct page returned 403, so this is from a search summary. — [Pond5 API](https://www.pond5.com/api); [Pond5 GPP help](https://www.pond5.com/help/en/articles/10086186-what-is-gpp)
- **Getty Images / iStock:** "Your API credentials are configured to provide access to the content in your licensing or revenue share agreement" (search summary). Generative-AI endpoints are restricted to customers with an AI Generation licence. — [Getty developer portal](https://developer.gettyimages.com/); [Getty AI generation docs](https://developers.gettyimages.com/ai-generation/)
- **Envato:** the Envato Market API uses a personal token for public data such as item search, or OAuth apps (access token valid "up to an hour", HTTPS redirect required). It supports catalogue search, purchases and "Download purchases". Rate limits are dynamic, with HTTP 429 plus `Retry-After`. The page does not mention Envato Elements, the subscription product. — [Envato API](https://build.envato.com/api/)
- **Coverr:** self-service and free ("The key is ready instantly"). Limits: Free 50 req/h, Pro 2,000 req/h, Ultimate "Unlimited*", Enterprise custom. "Videos require Coverr attribution". "All content accessed through the API is commercially licensed". AI-generated clips are "licensed and filterable". Semantic search is a beta available on request. — [Coverr developers](https://coverr.co/developers)
- **Vecteezy:** the licence page links a "Developer API" but describes no API terms. — [Vecteezy licensing agreement](https://www.vecteezy.com/licensing-agreement) (last updated 22 June 2026)

### Inferences
- For a solo India-based freelancer, the realistic self-serve set today is Pixabay, Coverr, Pexels only if a key was issued before the pause, Shutterstock Free tier for search/preview only, and Envato Market for purchased items. Adobe is effectively closed (Enterprise-only). Storyblocks, Pond5 and Getty need a sales conversation and likely a minimum commitment.
- Storyblocks is the most "editor-tool-shaped" partner offer: a social-use API licence with music and SFX included. Its AI clause (A2) needs clarifying in any contract.

### Gaps
- None of the providers published per-asset API licensing prices. I found no Shutterstock Standard API price, Storyblocks quote range, Pond5 partner pricing or Getty API pricing. I did not fill these from memory.
- I found no current Envato Elements API, and no public API docs or terms for Vecteezy.
- I could not confirm whether Pexels pauses also affect higher-limit requests for existing keys, beyond the help-centre summary.

## A2. Clauses restricting AI/ML use, automated generation and competing services

### Takeaway
Most providers ban using assets or their metadata to train or otherwise feed ML/AI systems (Adobe, Getty, Shutterstock, Storyblocks, Vecteezy without an add-on, and Pixabay for scraping). Two clauses go further and hit an autonomous editor directly:
- Storyblocks bars use in "projects that are created entirely by AI platforms".
- Pixabay bars "lots of automated queries", systematic mass downloads and robots.

Competing-service clauses (Pexels, Pixabay) matter only if the tool exposes the catalogue to end users.

### Cited Findings
- **Storyblocks licence:** "You cannot use our stock files to train AI or machine learning models". It also prohibits use "as part of projects that are created entirely by AI platforms". The page shows no date (footer © 2026). — [Storyblocks license](https://www.storyblocks.com/license)
- **Pixabay API docs:** "Systematic mass downloads are not allowed." The API is for real user requests, so do not "send lots of automated queries". Pixabay may raise limits for properly implemented integrations. — [Pixabay API docs](https://pixabay.com/api/docs/)
- **Pixabay Terms §8** (last updated 20 Oct 2026):
  - Data mining and scraping is "strictly prohibited for all unauthorised purposes, including without limitation for machine learning purposes".
  - "Bulk, large-scale or systematic copying of Content is strictly prohibited" without explicit permission.
  - Users may not use "programs or robots for automatic data collection".
  - Users may not "use or compile any Content to replicate a similar or competing service to the Service", or access the service "for building or marketing a competitive product".
  - §7A: Pixabay itself may use uploaded content "through the use of machine learning technology".
  - Source: [Pixabay Terms](https://pixabay.com/service/terms/)
- **Pexels API docs:** "You may not copy or replicate core functionality of Pexels (including making Pexels content available as a wallpaper app)." The page has no AI/ML clause. — [Pexels API docs](https://www.pexels.com/api/documentation/)
- **Adobe Stock (PSLT 2023, Pro Edition):** "Customer will not use its access to Pro Assets or Adobe Stock API for machine learning as restricted in section 5.1 (G)." Also: "Customer will not license more Pro Assets than needed for immediate use in projects." Only the bookmark text was legible. The file metadata date is 14 Sep 2023. — [Adobe PSLT Stock WW 2023v1](https://adobe.com/content/dam/cc/en/legal/terms/enterprise/pdfs/PSLT-Stock-WW-2023v1.pdf)
- **Older Adobe Stock Additional Terms (2020):** these bar use of "the Works or any title, caption information, keywords, or other metadata associated with Works for any (1) machine learning or artificial intelligence purposes; or (2) technologies designed or intended for the identification of natural persons". This is a search-snippet quote. — [Adobe Stock Additional Terms 2020-04-16](https://wwwimages2.adobe.com/content/dam/cc/en/legal/servicetou/Adobe_Stock_Additional_Terms_en_US_20200416.pdf). The 2022 PSLT reportedly restricts using Stock assets to "create, train, test, or otherwise improve machine learning algorithms or AI systems" (search summary) — [PSLT Stock WW 2022v1](https://adobe.com/content/dam/cc/en/legal/terms/enterprise/pdfs/PSLT-Stock-WW-2022v1.pdf). The ML restriction is not mentioned on the public [Adobe Stock license-terms page](https://stock.adobe.com/license-terms), which is a summary page, so that silence is not evidence of a conflict. Which version of the ML clause currently governs is uncertain.
- **Getty content licence** (search summary only; the page itself returned 403):
  - Unless a Getty invoice, sales order or licence explicitly authorises it, content and its "captions, keywords, and metadata" cannot be used for machine learning.
  - The permitted AI uses exclude training, fine-tuning or other data ingestion.
  - The Indian version is marked "LAST UPDATED: April 2026" and has a section titled "No Machine Learning, AI, or Biometric Technology Use".
  - Sources: [Getty EULA (US)](https://www.gettyimages.com/eula); [Getty licence (IN)](https://www.gettyimages.in/license-info)
- **Shutterstock licence** (search summary; the page itself returned 403): visual content and licensed music may not be used as training data for AI, ML or generative AI. There is reportedly a carve-out for AI features of editing software, provided that software does not train on the content. Shutterstock sells training datasets separately. — [Shutterstock license](https://www.shutterstock.com/license); [Shutterstock data licensing help](https://submit.shutterstock.com/help/en/articles/10594694-shutterstock-data-licensing-and-the-contributor-fund). The API terms reportedly include a Platform User License (Schedule A) that "must be agreed to by each of your Users by way of an enforceable contract" (search summary) — [Shutterstock API terms](https://www.shutterstock.com/developers/api-terms). I could not retrieve the API terms text.
- **Vecteezy:** a separate Data Training License "Permits use of content to train, fine-tune, evaluate, or improve artificial intelligence and machine learning models" and is "Available only as an add-on to an Enterprise License". Training is otherwise not permitted under Free or Pro licences. — [Vecteezy licensing agreement](https://www.vecteezy.com/licensing-agreement) (22 Jun 2026)
- **Envato Elements** licence terms (updated 6 Oct 2026) contain no AI/ML clause. A separate "Envato – AI Product Terms" article is linked but was not retrieved. — [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- **Coverr:** no AI/ML restriction appears on the developer page. — [Coverr developers](https://coverr.co/developers)

### Inferences
- **Training bans vs automated assembly.** Most clauses ban *training/improving* ML systems. An editor that selects and composites licensed clips does not train a model, so it is most likely outside those bans. The exceptions:
  - **Storyblocks' "created entirely by AI platforms" clause.** An autonomous editor that produces client reels arguably fits it. The freelancer reviewing and approving each cut, and editing alongside client footage, may help, but this is untested. Get written clarification before using Storyblocks.
  - **Metadata clauses (Adobe 2020, Getty).** These bar using *titles, captions, keywords, metadata* for "machine learning or artificial intelligence purposes". Under a strict reading, these clauses would cover embedding a provider's previews or metadata into a local CLIP/CLAP vector index, or feeding catalogue metadata to an LLM for ranking. This is my interpretation, not settled law.
- **Safe design pattern for premium sources.** Call the provider's own search API live at edit time and pass results to Claude transiently. Index only *licence records* (id, licence, receipt) locally. Don't build content embeddings of premium catalogues. Locally embed only assets you own or that are licensed without ML restrictions.
- **Pixabay's automation rules.** Reasonable, user-triggered API calls by the agent are "authorised use". Bulk pre-fetching the catalogue to build an index is "systematic mass download". Keep Pixabay calls per-edit, cached for 24h, and download only the clips actually used.
- **Competing-service clauses** bite only if the product exposes a searchable stock catalogue to clients. The Studio's client review links should show the rendered reel, not browsable source assets.

### Gaps
- Verbatim current Shutterstock API Terms and Schedule A could not be retrieved (403; archive.org blocked).
- Current Getty EULA text could not be retrieved directly (403).
- The current version of Adobe's ML clause is uncertain. The 2023 PSLT body was not legible.
- I did not retrieve Envato's AI Product Terms, Pond5's licence AI clauses or Coverr's full licence/terms.
- All quotes need verification against the live pages (see caveat above).

## A3. Client deliverables, subscription dependence, caching, display and attribution

### Takeaway
Client delivery is generally allowed, but each provider scopes it differently:
- Adobe Standard: transfer to one client.
- Vecteezy: sublicense to the client, with the licensee staying liable.
- Envato Elements: per-project registration, and the project must be completed while subscribed.
- Storyblocks: perpetual coverage only on some tiers.

API display rules include Pixabay's 24h cache, no permanent hotlinking and a source credit on result displays, Pexels' prominent link, and Coverr's attribution requirement.

### Cited Findings
- **Adobe Stock Standard licence:**
  - "Transfer the license to your client or employer". Transfer to more than one client is not allowed "unless separately licensed for each".
  - "Reproduce up to 500,000 copies"; "Post the asset to a website or social media site with no limitation on views".
  - Editorial assets "May not be used for commercial purposes such as advertisements, promotions, endorsements".
  - The page shows no date.
  - Source: [Adobe Stock license terms](https://stock.adobe.com/license-terms)
- **Adobe PSLT Pro Edition:** "Customer will not use Pro Assets in work for its clients or permit its clients to use Pro Assets." This applies to Pro Edition only, not Standard. — [PSLT 2023v1](https://adobe.com/content/dam/cc/en/legal/terms/enterprise/pdfs/PSLT-Stock-WW-2023v1.pdf)
- **Vecteezy:**
  - You may grant your client a sublicense "as allowed by this License Agreement", and you remain liable for the client's use.
  - The Free licence requires attribution ("Attribution is required"). Pro allows use "without providing attribution".
  - No standalone redistribution, and end users may not extract the content.
  - Source: [Vecteezy licensing agreement](https://www.vecteezy.com/licensing-agreement)
- **Envato Elements** (6 Oct 2026):
  - 10(a)(i): "You can use an Item to create an End Product for yourself or for a client of yours."
  - Clause 4: "If you want to use the same Item for separate projects, you will need to create a new license for each end-use."
  - Clause 8: the licence is valid only if the End Product is completed while subscribed; it then becomes perpetual for that End Product.
  - 12(a): "You can't use an Item to create an End Product after your Envato Elements subscription ends."
  - 14(c): no claiming rights to music "through applying 'Content ID' or similar systems".
  - Source: [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- **Storyblocks:**
  - "You cannot stockpile assets for use after your Storyblocks subscription ends."
  - Internally inconsistent on perpetuity. One part says "Anything you create and publish during your time as a Storyblocks member will be covered by our license - forever". But the comparison table says perpetual use is "No" for Individual and Small Business and "Yes" for Business.
  - Client work is not explicitly addressed; the page says to contact sales.
  - Source: [Storyblocks license](https://www.storyblocks.com/license)
- **Pixabay:**
  - API: "requests must be cached for 24 hours". Image URLs may be used "for temporarily displaying search results", but "permanent hotlinking … is not allowed". Videos may be embedded, but storing them is recommended. "show your users where the images and videos are from, whenever search results are displayed." — [Pixabay API docs](https://pixabay.com/api/docs/)
  - Content licence: no attribution required. No "Standalone" redistribution, meaning "where no creative effort has been applied". Recognisable people and brands need care. — [Pixabay license summary](https://pixabay.com/service/license-summary/)
  - Terms §5: commercial use "in conjunction with the sale or promotion of a product or service" may require third-party consent. — [Pixabay Terms](https://pixabay.com/service/terms/)
- **Pexels:** "Whenever you are doing an API request make sure to show a prominent link to Pexels." "Always credit our photographers when possible." — [Pexels API docs](https://www.pexels.com/api/documentation/)
- **Coverr:** "Videos require Coverr attribution". The format was not specified on the page. — [Coverr developers](https://coverr.co/developers)
- **Storyblocks API:** the Standard API licence covers social and paid ads; the Enhanced licence covers broadcast and OTT. — [Storyblocks API](https://www.storyblocks.com/api)

### Inferences
- Envato and Storyblocks make a licence a function of project state plus subscription state. The index needs `subscription_required_until_completion`, a per-project registration id, and a render-time check that the subscription is active.
- Pixabay's "show your users where they are from" applies where search results are displayed, for example in Studio UI previews to the freelancer or client. It does not require an on-video credit. Keep a credit line in project metadata or the description anyway.
- Editorial-only assets (Adobe, Getty, Shutterstock) must be hard-blocked for promotional client reels.

### Gaps
- I did not retrieve Shutterstock's and Pond5's client-transfer clauses or Coverr's attribution format.
- The Storyblocks perpetuity conflict cannot be resolved from public pages.

## A4. Rate limits summary

### Takeaway
Published limits: Pixabay 100 req/60 s; Pexels 200/h and 20,000/month; Coverr Free 50/h and Pro 2,000/h. Shutterstock and Envato publish only a 429 mechanism. Adobe, Storyblocks, Pond5 and Getty publish nothing public.

### Cited Findings
- Pixabay: 100 per 60 s, per key; headers `X-RateLimit-*`; 429 "API rate limit exceeded." — [Pixabay API docs](https://pixabay.com/api/docs/)
- Pexels: 200/h and 20,000/month; 429 on excess. — [Pexels API docs](https://www.pexels.com/api/documentation/)
- Coverr: Free 50/h, Pro 2,000/h, Ultimate "Unlimited*", Enterprise custom. — [Coverr developers](https://coverr.co/developers)
- Shutterstock: "limited to a certain number of API requests per minute"; 429 with `RateLimit-*` headers. — [Shutterstock API reference](https://api-reference.shutterstock.com/)
- Envato: dynamic limits; 429 with `Retry-After`. — [Envato API](https://build.envato.com/api/)
- Storyblocks trial: unlimited search queries and 5 downloads per content type. — [Storyblocks API](https://www.storyblocks.com/api)

### Inferences
- A per-reel agent run makes tens of searches at most, which fits every published limit. The Pexels monthly cap (20k) is the binding one at scale.

### Gaps
- Exact Shutterstock per-minute numbers are not stated. Limits for Adobe, Getty, Pond5 and Storyblocks production are unknown.

## B1. Metadata schema, licence gate and provenance

### Takeaway
I found no standard schema for this; the schema below is my design, derived from the clauses in A1–A3. The key point is that the licence must be represented as structured, machine-checkable fields, with a gate before render. Free-text licence text alone is not enough.

### Cited Findings
These are the clause facts that drive the fields:
- Per-project registration (Envato cl. 4, 11) — [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- Completion while subscribed (Envato cl. 8, 12(a); Storyblocks "no stockpiling") — same; [Storyblocks license](https://www.storyblocks.com/license)
- Content ID claims prohibited on licensee side (Envato 14(c)) — [Envato](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- Client transfer scope (Adobe: one client per licence; Vecteezy: sublicense, licensee liable) — [Adobe](https://stock.adobe.com/license-terms); [Vecteezy](https://www.vecteezy.com/licensing-agreement)
- Attribution required (Vecteezy Free; Coverr; Pexels link; Pixabay display) — [Vecteezy](https://www.vecteezy.com/licensing-agreement); [Coverr](https://coverr.co/developers); [Pexels](https://www.pexels.com/api/documentation/); [Pixabay](https://pixabay.com/api/docs/)
- Copy/view caps (Adobe Standard 500,000) and editorial-only restrictions — [Adobe](https://stock.adobe.com/license-terms)
- API cache TTL and no permanent hotlinking (Pixabay 24h) — [Pixabay API docs](https://pixabay.com/api/docs/)
- ML/metadata-use restrictions (Adobe, Getty, Shutterstock, Vecteezy) — see A2
- "Created entirely by AI" restriction (Storyblocks) — [Storyblocks license](https://www.storyblocks.com/license)
- Pixabay's CC0 cutoff: content published before 9 Jan 2019 is under CC0 (Terms §4) — [Pixabay Terms](https://pixabay.com/service/terms/)

### Inferences
**Proposed record** (one row per asset; licence stored as a separate table so many assets can share a licence):

- **Identity:**
  - `asset_id` (stable, e.g. `pixabay:video:12345`)
  - `kind` (`broll | music | sfx | lottie | overlay | image`)
  - `source` (provider)
  - `source_item_id`
  - `source_url`
  - `contributor`
  - `sha256` of the local file
  - `local_path`
  - `downloaded_at`
- **Licence (FK to `licences` table):**
  - `licence_id` (e.g. `pixabay-content-2026-10-20`, `cc0`, `cc-by-4.0`, `envato-elements-2026-10-06`)
  - `licence_text_snapshot` (hash plus stored copy of the terms as of acquisition)
  - `licence_family` (`cc0 | cc-by | royalty-free-stock | subscription | owned`)
  - `blocked` (true for NC/SA/ND)
- **Use rights:**
  - `commercial_ok`
  - `client_transfer` (`none | single_client | sublicense`)
  - `editorial_only`
  - `allowed_platforms` (IG/YT/TikTok/paid ads/broadcast)
  - `view_or_copy_cap`
  - `sensitive_use_restrictions`
  - `people_or_brands_present` (needs release check)
  - `ai_project_restriction` (Storyblocks flag)
  - `ml_indexing_permitted` (whether you may embed it locally)
- **Attribution:**
  - `attribution_required`
  - `attribution_string` (pre-rendered)
  - `attribution_placement` (description, credits, none)
- **Subscription / expiry:**
  - `subscription_dependent`
  - `subscription_account`
  - `must_complete_while_subscribed`
  - `licence_expires_at`
  - `per_project_registration_required`
  - `registrations[]` (project_id, registered_at, licence certificate id/URL)
- **Content ID:**
  - `content_id_registered` (known claims risk)
  - `content_id_claim_prohibited`
  - `whitelist_procedure` (e.g. a clearance link)
- **Provenance:**
  - `acquired_via` (`api | manual | owned`)
  - `api_response_snapshot` (JSON)
  - `licence_receipt_id` (order/licence id)
  - `cache_ttl` (Pixabay 24h for search results, not downloaded files)
  - `first_used_in[]`
  - `is_ai_generated` (Coverr AI clips are "licensed and filterable"; Storyblocks markets "100% human-made")
- **Media facts (by kind):**
  - Common: `duration_s`, `width`, `height`, `fps`, `aspect` (9:16, 16:9, 1:1), `has_alpha`, `codec`, `loudness_lufs`.
  - Music: `bpm`, `key`, `energy` (0–1), `valence`/mood tags, `genre`, `has_vocals`, `stems_available`, `loop_points`, `sections` (intro/build/drop timestamps).
  - SFX: `category` (whoosh, hit, riser, UI, ambience), `onset_ms`, `peak_ms`, `tail_ms`, `is_loop`.
  - Video: `shot_size` (wide/medium/close), `subject`, `motion` (static/pan/handheld/drone), `camera_speed`, `dominant_colours`, `has_people`, `has_text_or_logos`, `setting`, `time_of_day`.
  - Lottie/overlay: `aspect`, `alpha`, `colour_editable`, `loopable`, `layers`.
- **Search text:**
  - `title`
  - `description` (LLM- or VLM-generated caption)
  - `tags[]`
  - `embedding` columns per modality

**Licence gate before render** (deterministic code, not the LLM):
1. Every timeline asset must resolve to an `asset_id` with a licence row. Unknown means fail.
2. `blocked` (NC/SA/ND) means fail.
3. If `editorial_only` and the project is promotional, fail.
4. If `client_transfer == single_client`, check `first_used_in` for other clients' projects.
5. If `subscription_dependent`, the subscription must be active now, and `per_project_registration` must exist for this project id.
6. Target platform must be in `allowed_platforms`. Also check the view cap.
7. If `attribution_required`, emit the credit string into the deliverable notes and the YT description.
8. If `content_id_registered`, warn and attach clearance info.
9. If `ai_project_restriction`, fail unless the account has a documented exception.
10. Write a per-render **licence manifest** (asset ids, licence ids, receipts, terms hashes) stored with the project. This is the provenance record for client disputes.

### Gaps
- I found no published industry-standard schema for multi-licence asset libraries. The schema above is a design proposal.
- I found no source on how to register per-project licences via API for Envato Elements.

## B2. Embedding models for semantic search (commercial-use licences, Apple silicon)

### Takeaway
Three of the suggested audio models fail the user's own NC-reject rule. **MuQ, MuQ-MuLan and MERT weights are CC-BY-NC 4.0**, and MS-CLAP weights have no stated licence (repo archived Sep 2026). **LAION-CLAP** is the only sourced audio–text model with a permissive tag:
- HF `laion/clap-htsat-unfused` is Apache-2.0, and the GitHub repo is CC0.
- Caveats: undisclosed training data, and the larger checkpoints are a "temporary release".

For images and video frames, **SigLIP 2** (Apache-2.0) is the cleanest option.

### Cited Findings
- **LAION-CLAP:**
  - Repo licence CC0-1.0.
  - Checkpoints: `630k-audioset-best.pt`, `630k-audioset-fusion-best.pt` (variable length), `music_audioset_epoch_15_esc_90.14.pt` (music), `music_speech_audioset_epoch_15_esc_89.98.pt` (general).
  - Input must be 48 kHz.
  - "Due to copyright reasons, we cannot release the dataset we train this model on". The larger checkpoints are a "temporary release… take your own risk".
  - Source: [LAION-AI/CLAP](https://github.com/LAION-AI/CLAP)
- **HF `laion/clap-htsat-unfused`:** licence tag apache-2.0. LAION-Audio-630K has 633,526 pairs. Parameter count and dimension are not shown. — [HF model card](https://huggingface.co/laion/clap-htsat-unfused)
- **MuQ / MuQ-MuLan:**
  - Code is MIT. Weights are "released under the CC-BY-NC 4.0 license".
  - MuQ is about 300M parameters (MSD-trained). MuQ-MuLan is about 700M, with an audio–text joint space in English and Chinese.
  - Inputs "strictly require 24 kHz". fp32 is recommended to avoid NaNs.
  - Source: [tencent-ailab/MuQ](https://github.com/tencent-ailab/MuQ)
- **MERT-v1-330M:** licence cc-by-nc-4.0; 330M parameters; 24 kHz; 1024-dim features per layer; audio-only, with no text retrieval. — [HF m-a-p/MERT-v1-330M](https://huggingface.co/m-a-p/MERT-v1-330M)
- **Microsoft CLAP:** code is MIT, and the README states no licence for the weights. The repository was "archived and read-only as of September 15, 2026". — [microsoft/CLAP](https://github.com/microsoft/CLAP)
- **SigLIP 2:** `google/siglip2-so400m-patch14-384` is Apache-2.0, listed at about 1B parameters (F32 tensors). The family has 36 checkpoints in the HF collection. The paper is arXiv 2502.14786 (20 Feb 2025), "Multilingual Vision-Language Encoders". — [HF SigLIP2 card](https://huggingface.co/google/siglip2-so400m-patch14-384)
- **Coverr** offers semantic search as a beta on request, a provider-side alternative to local embedding. — [Coverr developers](https://coverr.co/developers)

### Inferences
- **Audio:** use LAION-CLAP for text→SFX and text→music retrieval, pinned to the HF checkpoint `laion/clap-htsat-unfused` (Apache-2.0 verified). The GitHub `.pt` checkpoints (hosted at `lukewys/laion_clap`, including the music/fusion ones) have unverified weights licences; the repo's CC0 covers the code. Treat its training-data provenance as a known residual risk; using an embedding model for retrieval does not put the training audio into the reel. Pair it with deterministic DSP features rather than learned models for BPM, key, energy and onset/peak (e.g. librosa or essentia; check essentia's licence before choosing it).
- **Hard rule:** exclude MuQ, MuQ-MuLan and MERT from a commercial client pipeline unless a commercial licence is obtained from the authors.
- **Video:**
  - Sample 1 frame/s or shot keyframes (scene-cut detection), embed with SigLIP 2, and mean-pool or store per-keyframe vectors.
  - Also generate a text caption per clip with a VLM (e.g. Claude) and embed it with a text-embedding model.
  - The LLM reads captions far better than raw vectors, so captions become the `description` field.
- **Apple silicon (not benchmarked; inferred):**
  - CLAP-HTSAT and SigLIP2 base/so400m are sub-1B models and should run on M-series via PyTorch MPS or CoreML/MLX conversions.
  - Indexing is a one-off batch job per asset, so even CPU throughput is acceptable for libraries of 10^3–10^5 items.
  - Prefer smaller SigLIP2 variants (base/large) if memory is tight. The listed size of the so400m variant (about 1B) should be checked; it may include the text tower.
- **Licensing interplay:** per A2, run local embeddings only on owned or permissively licensed assets (Pixabay downloads in use, CC0/CC-BY, the user's own library). Don't build embeddings over premium provider catalogues.

### Gaps
- The weights licences of the LAION-CLAP music/fusion `.pt` checkpoints are unverified.
- I did not retrieve CLAP and SigLIP2 embedding dimensions or exact parameter counts for every variant, Apple-silicon throughput benchmarks, or the licence of the `laion/larger_clap_music` / `larger_clap_general` HF cards.
- I did not check text-embedding model options (licences and sizes) for caption embeddings.
- Whether the undisclosed CLAP training data creates any downstream licence obligation is unresolved. No source addresses it.

## B3. Local vector stores for a single Mac

### Takeaway
For roughly 10^3–10^5 assets on one Mac, an embedded store is enough:
- **sqlite-vec** (Apache-2.0/MIT, pure C, pre-v1) fits naturally next to a SQLite licence/metadata database, with metadata and partition columns in `vec0` tables.
- **LanceDB** (Apache-2.0, embedded) adds full-text search and multimodal blob storage.

### Cited Findings
- **sqlite-vec:**
  - Apache-2.0 and MIT.
  - "pre-v1, so expect breaking changes!"
  - `vec0` virtual tables store float, int8 and binary vectors, plus metadata, auxiliary and partition-key columns.
  - KNN uses `MATCH … ORDER BY distance LIMIT k`.
  - Pure C with no dependencies, runs on macOS. Bindings: Python, Node, Ruby, Go, Rust.
  - The repo contains IVF/DiskANN source files, but they are undocumented on the page.
  - Source: [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec)
- **LanceDB:** Apache-2.0. "LanceDB Embedded (open source)" runs in-process with data on local disk. It supports vector search, full-text search and SQL, and filtering of vectors and metadata, with multimodal data storage. SDKs: Python, TypeScript, Rust. — [lancedb/lancedb](https://github.com/lancedb/lancedb); [LanceDB SDK docs](https://lancedb.github.io/lancedb/)

### Inferences
- At this scale, brute-force KNN in sqlite-vec is fast enough, and a single SQLite file keeps the licence gate, provenance and vectors transactional together. That fits the existing local index.
- Pick LanceDB if you want built-in full-text plus vector search or plan to store frames and blobs. FAISS and Chroma were not evaluated (see Gaps).
- Use hybrid retrieval: BM25/FTS over tags and captions plus vector similarity, merged with reciprocal-rank fusion. SQLite FTS5 covers the lexical half if you stay on sqlite-vec.

### Gaps
- I did not fetch FAISS or Chroma docs, LanceDB hybrid-search specifics, sqlite-vec filtering semantics or benchmarks. FAISS and Chroma were not evaluated.

## B4. LLM tool-use `search_assets` pattern

### Takeaway
I did not research primary sources for this subsection, so everything below is design inference. The pattern that fits Claude:
- A single `search_assets` tool with structured filters plus a free-text query, run as hybrid search.
- It returns a small top-k of compact cards (id, short caption, key facts, licence summary, preview reference).
- A separate `get_asset` / `preview_asset` tool returns details or a contact sheet.
- Licence filtering is applied server-side before results reach the model.

### Cited Findings
- Provider APIs already structure search this way: filters plus query, paged hits, preview thumbnails and renditions (Pixabay `videos{large…tiny}` and thumbnails). — [Pixabay API docs](https://pixabay.com/api/docs/). Adobe's API supports search by keyword and by similarity. — [Adobe Stock API](https://developer.adobe.com/stock/docs/getting-started/)

### Inferences
- **Tool shape:**
  - `search_assets({query, kind, filters:{duration_range, aspect, has_alpha, bpm_range, mood[], energy_range, sfx_category, shot_size, motion, has_people, platform, client_id}, k: 8})`
  - It returns `[{asset_id, kind, caption (≤25 words), duration_s, aspect, bpm/key or onset_ms, licence_badge, attribution_required, preview_ref}]`.
- **Gate inside the tool:**
  - Hard filters run before ranking: licence blocked, editorial-only, subscription inactive, client conflict.
  - The model therefore never sees ineligible assets, which reduces both tokens and the risk of picking them.
- **Previews:**
  - For visual choices, return a contact-sheet image (3–4 keyframes per candidate, tiled) or let the model call `preview_asset(asset_id)` for frames.
  - For audio, return text descriptors (BPM, key, energy curve, onset/peak) rather than audio.
- **Federated live search:**
  - The same tool queries the local index plus live provider APIs (Pixabay, Coverr) in parallel.
  - Provider hits are tagged `remote` and licensed or downloaded only on selection (licence-on-use). This respects Pixabay's no-mass-download rule and the premium metadata-ML concerns.
- **Determinism:**
  - Log query, filters, returned ids and the chosen id in the render manifest for provenance and evals.

### Gaps
- I retrieved no Anthropic docs on tool design or tool search, and no published evaluations of LLM asset-retrieval tool patterns. The parent researcher or report writer should source these separately if needed.
