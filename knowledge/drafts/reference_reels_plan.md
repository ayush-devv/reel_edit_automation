# Reference reel library: sources, compliance, and measurement plan (draft v1)

Drafted 2026-11-18 from WebSearch/WebFetch. No videos were downloaded.
Follows `knowledge/SCHEMA.md`: own-words paraphrase, quotes of 15 words or fewer, every row cited.
**This is not legal advice.** It is an engineering reading of public terms and statutes. Before any commercial use, ask a lawyer (Indian counsel for India-market work).

---

## 0. TL;DR

- **Where "great" comes from.** Juried showcases list exemplary work: Webby *Creators: Best Editing* (the jury judges editing craft only), Webby *Social Video Short Form*, Shorty Awards, and Cannes Lions / Spikes Asia / Kyoorius / ABBY. Platform-curated ad galleries add more: TikTok Creative Center *Top Ads* and the Meta Ad Library. The rest comes from creators and studios that third-party articles name for editing quality (global and Indian).
- **What we may keep.** Our own measurements and notes are facts plus our own words, so we keep them. We do **not** keep third-party video files unless we own them, have written permission, or the content is CC-licensed and was obtained through a channel that allows downloading.
- **The current sample is non-compliant.** `samples/bathroom.mp4` came through a third-party downloader (Klickpin), which is exactly the pattern this plan rules out. See §2.4.
- **Measurement.** One protocol produces a style vector directly comparable to `analysis/bathroom/notes.md`. Mode A uses a file. Mode B is manual in-app viewing for reels we may watch but not keep.

---

## 1. Candidate reference sources (≥ 40)

Legend:
- **Type:** AWARD = juried award entry or category; SHOWCASE = platform-curated gallery or library; CREATOR = creator or studio; BREAKDOWN = published analysis or tutorial; GUIDE = official platform creative guidance (criteria, not exemplars).
- **Region:** IN = India, GL = global.
- **Breakdown?:** Y = a written breakdown of the editing exists at or next to the URL; P = partial (strategy or profile, little edit detail); N = no written breakdown, so we would have to measure it ourselves.
- **Verified:** ✓ = URL returned by WebSearch/WebFetch in this session. ⚠ = URL returned, but the genre or award outcome is inferred or unconfirmed (see note).
- **"Why exemplary"** paraphrases the source. "(vendor)" marks a source that sells editing tools or services. "no source statement" means no source explained why the work is good.

### 1.1 talking_head (`genre.talking_head`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 1 | Alex Hormozi editing style | https://riverside.com/blog/hormozi-style-videos | BREAKDOWN | GL | Vendor blogs credit the style with keeping sound-off viewers: bold all-caps word-by-word captions with a highlighted active word, jump cuts every 1–3 s, punch-in zooms, fillers removed (vendor) | Y | ✓ |
| 2 | Submagic: Hormozi captions | https://www.submagic.co/blog/how-to-make-alex-hormozi-captions | BREAKDOWN | GL | Caption spec (font, colour, highlighted word); one source names Montserrat Black (vendor) | Y | ✓ |
| 3 | Ali Abdaal: own editing course | https://www.skillshare.com/en/classes/video-editing-with-final-cut-pro-x-from-beginner-to-youtuber/317873419 | CREATOR | GL | First-party method: lock the A-cut, then layer B-roll, titles, lower thirds, screen recordings and hand-drawn animation | Y (paid) | ✓ |
| 4 | Adobe case study: Ali Abdaal | https://blog.adobe.com/en/publish/2024/09/05/how-ai-helps-ali-abdaal-save-hours-every-week | BREAKDOWN | GL | Many hours per video go to B-roll selection, titles and motion graphics, showing where the polish comes from | P | ✓ |
| 5 | Ankur Warikoo (English/Hindi) | https://www.exchange4media.com/influence-zone-news/ankur-warikoo-birthday-how-the-entrepreneur-creator-built-a-business-around-content-157598.html | CREATOR | IN | Built a business on content; a channel tool estimates ~88% of YouTube views come from Shorts (https://outlierkit.com/channel/warikoo); one summary says he shoots single takes with light editing | P | ✓ |
| 6 | Colin & Samir (Webby 2026, Best Duo/Group) | https://winners.webbyawards.com/2026/creators/creator-excellence/best-duo-or-group/365346/colin--samir | AWARD | GL | Webby Winner; creator-economy interview and talking format; no source statement on the edit | N | ✓ |
| 7 | Jenny Hoyos (Shorts storytelling) | https://rosetta.to/u/vidiq/how-jenny-hoyos-actually-makes-viral-shorts | BREAKDOWN | GL | vidIQ interview summaries: write the hook and last line first; shorts of roughly 34 s; trimming a single second measurably changes retention (secondhand) | P | ✓ |

### 1.2 testimonial (`genre.testimonial`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 8 | Local sample: DearMa founder on Wortham agency | `analysis/bathroom/notes.md` | BREAKDOWN (ours) | GL | Our measured breakdown: 35.8 cuts/min, kinetic keyword typography, B-roll that illustrates the words. **Provenance problem, see §2.4** | Y | local |
| 9 | TikTok Creative Center: Top Ads | https://ads.tiktok.com/help/article/creative-center | SHOWCASE | GL | TikTok says the ads clear its performance thresholds and are shown with advertiser authorization; filters for region, industry and objective; per-second frame analysis. *Our note:* TikTok has been unavailable in India since 2020 (not re-verified), so filter other regions | Y (per-ad analytics) | ✓ |
| 10 | Meta Ad Library | https://transparency.meta.com/researchtools/ad-library-tools | SHOWCASE | IN/GL | Public, no login, every active ad across Meta, including Reels placements; filter country = India to find D2C testimonial and UGC ads. Shows creative only, no performance data | N | ✓ |
| 11 | Testimonial.to examples | https://testimonial.to/resources/testimonial-video-examples | BREAKDOWN | GL | The best testimonials follow real customer problem → solution → measurable result, not vague praise (vendor) | Y | ✓ |
| 12 | Influencer Marketing Hub: 20 testimonial examples | https://influencermarketinghub.com/video-testimonial-examples/ | BREAKDOWN | GL | Annotated examples (Slack, Dropbox, and others): plain, specific customer phrasing and real customers | Y | ✓ |
| 13 | Vidico: testimonial examples | https://vidico.com/news/video-testimonial-examples/ | BREAKDOWN | GL | Production-house roundup of testimonial structures (vendor) | Y | ✓ |
| 14 | Chetmani Jewellers (Varanasi) | https://retailjewellerindia.com/video-testimonials-drive-real-customer-marketing-success-at-chetmani-jewellers | CREATOR (brand) | IN | Trade press covers a retail jeweller's "real customer" video-testimonial strategy | P | ✓ |
| 15 | Velocity: top D2C Instagram campaigns 2024 | https://blog.velocity.in/top-instagram-campaigns-of-the-year-d2c-brands-2024-india/ | BREAKDOWN | IN | Credits real-customer story campaigns with building trust and loyalty for Indian D2C brands | P | ✓ |

### 1.3 product (`genre.product`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 16 | Daniel Schiffer: dynamic tripod product video | https://fstoppers.com/video-editing/how-make-product-video-shot-tripod-more-dynamic-580985 | BREAKDOWN | GL | Makes static product shots feel kinetic in post with keyframed scale, masks and effects | Y | ✓ |
| 17 | LensVid: Daniel Schiffer tag | https://lensvid.com/tag/daniel-schiffer | BREAKDOWN | GL | Several write-ups of his product and food B-roll edits; warns against effects that bury the product | Y | ✓ |
| 18 | "This is not an iPhone" (Webby 2025 Best Editing nominee) | https://winners.webbyawards.com/2025/creators/creator-excellence/best-editing/321978/this-is-not-an-iphone | AWARD | GL | Nominated in a category judged solely on editing craft. ⚠ Product genre is inferred from the title | N | ⚠ |
| 19 | Shorty 18th, Short Form Video winner: Final Destination 4DX Death Chair | https://shortyawards.com/18th/final-destination-4dx-death-chair | AWARD | GL | Category winner; sells a new moviegoing experience in short form | Y (entry write-up) | ✓ |
| 20 | Shorty 18th finalist: The Weeknd × Nespresso "The First Sip" | https://shortyawards.com/18th/the-first-sip-a-cinematic-take-on-the-weeknd-nespresso | AWARD | GL | Cinematic take on an everyday coffee moment | Y (entry) | ✓ |
| 21 | Google ABCDs for YouTube Shorts | https://services.google.com/fh/files/misc/formarketingshortsabcdsonesheeters.pdf | GUIDE | GL | Attention / Branding / Connection / Direction. Top Shorts ads should feel native to the feed; direct-to-camera, conversational, lighter production | Y | ✓ |
| 22 | TikTok Creative Codes | https://ads.tiktok.com/business/library/Creative_Codes_ENG.pdf | GUIDE | GL | Six principles (TikTok-first, trends, production, structure, stimulation, sound); TikTok reports most ad recall lands within the first 6 s | Y | ✓ |

### 1.4 tutorial (`genre.tutorial`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 23 | Your Food Lab / Sanjyot Keer | https://yourstory.com/weekender/chef-sanjyot-keer-shares-his-recipe-creating-delicious-content | CREATOR | IN | Started one-minute videos because fast-paced Indian food content was scarce; shoots separate vertical setups for Reels; aims for recipe value plus visual appeal; billions of views reported | P | ✓ |
| 24 | Nat Geo Social (Webby 2025, Social Video Short Form, Education & Science) | https://winners.webbyawards.com/2025/social/social-video-short-form/education-science-video/324950/nat-geo-social-media | AWARD | GL | Webby-listed short-form explainer work; no source statement on the edit | N | ✓ |
| 25 | "I shrink 10x every 21s until I'm an atom" (Webby 2025 Best Editing nominee) | https://winners.webbyawards.com/2025/creators/creator-excellence/best-editing/322683/i-shrink-10x-every-21s-until-im-an-atom | AWARD | GL | Editing-craft nominee; an educational scale explainer built on a strict time structure | N | ✓ |
| 26 | Cannes Lions 2025 Social & Creator Grand Prix: Vaseline Verified | https://www.contagious.com/news-and-views/cannes-lions-2025-social-and-creator-winners | AWARD | GL | Lab-tested creator "hacks" and verified the safe ones; the jury praised its optimism and joy and that it built on behaviour already on social | Y | ✓ |
| 27 | Nick DiGiovanni (Webby 2026 Food & Drink creator; 2022 Best Creator) | https://winners.webbyawards.com/2022/social/features/best-creator/206034/nick-digiovanni | AWARD | GL | Repeat Webby winner for short-form cooking. ⚠ The 2026 category label is ambiguous in TheWrap's list (https://www.thewrap.com/media-platforms/tv/webby-awards-2026-creator-winners-webbys/) | N | ⚠ |
| 28 | The Spruce TikTok (Shorty 14th entry) | https://shortyawards.com/14th/the-spruce-tiktok | AWARD | GL | Practical home tips in short, easy-to-digest videos. ⚠ Award outcome not confirmed | Y (entry) | ⚠ |

### 1.5 vlog (`genre.vlog`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 29 | Casey Neistat (Artlist breakdown) | https://artlist.io/blog/editing-storytelling-techniques-casey-neistat/ | BREAKDOWN | GL | Cuts mid-sentence, B-roll that advances the story, music-driven pacing | Y | ✓ |
| 30 | Nerdwriter on Neistat (via Laughing Squid) | https://laughingsquid.com/an-insightful-analysis-showcasing-the-unique-style-of-casey-neistats-seemingly-effortless-daily-vlog/ | BREAKDOWN | GL | Video essay on how the "effortless" daily vlog is built | Y (video) | ✓ |
| 31 | No Film School: 7 Neistat storytelling techniques | https://nofilmschool.com/2016/08/7-storytelling-techniques-you-can-learn-filmmaker-youtube-star-casey-neistat | BREAKDOWN | GL | Itemised storytelling and edit techniques | Y | ✓ |
| 32 | Mumbiker Nikhil | https://yourstory.com/weekender/mumbiker-nikhil-content-creator-moto-vlogging-vlogger-biker | CREATOR | IN | Profiled as a moto-vlogger turned daily lifestyle vlogger; listicles call his reels cinematic | P | ✓ |
| 33 | Tanya Khanijow and other Indian travel vloggers | https://www.thebetterindia.com/287519/indian-travel-vloggers-youtube-plan-vacation | CREATOR | IN | Listicles praise cinematic visuals with a personal narrative. Low-confidence source | N | ✓ |

### 1.6 montage (`genre.montage`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 34 | Zach King (Webby 2025: Best Editing, People's Voice, Best Shortform) | https://winners.webbyawards.com/2025/creators/creator-excellence/best-editing/334701/zach-king | AWARD | GL | Won a creator category judged only on editing craft (technique, creativity, craft standards), plus Best Shortform | N | ✓ |
| 35 | Webby Creators: Best Editing (all years) | https://winners.webbyawards.com/winners/creators/creator-excellence/best-editing | AWARD (index) | GL | Jury shortlist: 2025 nominees include Shrimpdaddy and Euro Rhythms; 2026 has Macfarlane Bros (winner), AntsCanada, Queen Chelsea VFX, Phoning It In | N | ✓ |
| 36 | "Euro Rhythms: A Journey in Motion" (2025 nominee) | https://winners.webbyawards.com/2025/creators/creator-excellence/best-editing/328489/euro-rhythms-a-journey-in-motion | AWARD | GL | Travel/motion montage nominated for editing craft | N | ✓ |
| 37 | Macfarlane Bros (2026 Best Editing winner) | https://winners.webbyawards.com/2026/creators/creator-excellence/best-editing/363525/macfarlane-bros | AWARD | GL | Webby Winner, editing craft | N | ✓ |
| 38 | Sam Kolder (travel montage) | https://fstoppers.com/vfx/art-creating-captivating-travel-films-210692 | BREAKDOWN | GL | Seamless motion transitions, time-lapse bridges and a popularised luma fade; how-to at https://motionarray.com/learn/premiere-pro/sam-kolder-transition-premiere-pro/ | Y | ✓ |
| 39 | Shorty 18th finalist: "David Blaine in 60s" | https://shortyawards.com/18th/david-blaine-in-60s | AWARD | GL | Compresses a decades-long career into one minute | Y (entry) | ✓ |
| 40 | Gap "Better in Denim" (Webby 2026, Viral/Remix) | https://winners.webbyawards.com/2026/video-film/general-video-film/viral-video-remixes-mashups/369678/gap-better-in-denim-invisible-dynamics | AWARD | GL | Webby Winner, dance/music-led brand montage; no source statement on the edit | N | ✓ |

### 1.7 podcast_clip (`genre.podcast_clip`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 41 | Steven Bartlett / Diary of a CEO (Webby 2026, Podcast creator) | https://winners.webbyawards.com/2026/creators/individual-creator/podcast/364463/steven-bartlett | AWARD | GL | Webby Winner (Podcast creator); no source statement on the edit. *Our note:* a widely clipped podcast, worth measuring | N | ✓ |
| 42 | "Shirley You Can't Be Serious" podcast (Webby 2026 Best Editing nominee) | https://winners.webbyawards.com/2026/creators/creator-excellence/best-editing/376982/shirley-you-cant-be-serious-podcast | AWARD | GL | A podcast nominated in an editing-craft category | N | ✓ |
| 43 | Raj Shamani, Figuring Out (Hindi/Hinglish) | https://theeconomicdrift.beehiiv.com/p/how-raj-shamani-built-a-10-crore-podcast-empire | BREAKDOWN | IN | Third-party analysis of a long→short funnel: a 60–90 min episode cut into 10–20 clips for Reels/Shorts, with guest reach as distribution | P | ✓ |
| 44 | Sweetfish: "The only way to clip your podcast" | https://sweetfishmedia.com/b2b-growth/the-only-way-to-clip-your-podcast-in-2024 | BREAKDOWN | GL | Practitioner method for choosing and cutting podcast clips | Y | ✓ |
| 45 | Vidpros: editor's cut vs AI auto-clipper | https://vidpros.com/podcast-clips/ | BREAKDOWN | GL | Argues human clip selection and edits beat auto-clipping (vendor) | Y | ✓ |
| 46 | Hindi tutorial: "Podcast Shorts kaise banaye" (summary) | https://recapio.com/digest/how-to-make-podcast-shorts-like-a-pro-podcast-shorts-kaise-banaye-shorts-editing-kaise-kare-by-grow- | BREAKDOWN | IN | Hindi-language podcast-shorts editing walkthrough. Low-confidence AI summary of a video | P | ✓ |

### 1.8 transformation (`genre.transformation`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 47 | Prime "Boy Room" (Shorty 17th: Silver Honor, Branded Series) | https://shortyawards.com/17th/boy-room | AWARD | GL | Bite-sized TikTok episodes that turned into a room-renovation format | Y (entry) | ✓ |
| 48 | Prime "Girl Room" (Shorty 18th entry) | https://shortyawards.com/18th/girl-room | AWARD | GL | Extreme room makeover tied to fast delivery. ⚠ Award outcome not shown | Y (entry) | ⚠ |
| 49 | This Old House social (Shorty 14th finalist) | https://shortyawards.com/14th/this-old-house-social-media | AWARD | GL | Social team documented run-down homes being transformed | Y (entry) | ✓ |
| 50 | Lone Fox / Drew Scott (Shorty 15th: Gold Honor, YouTube Presence) | https://shortyawards.com/15th/drew-m-scott-of-lone-fox | AWARD | GL | DIY, home hacks and renovation videos | Y (entry) | ✓ |
| 51 | Glow-up hand-over-lens transition case | https://alici.ai/formulas/media/ariaaquin/cebcb32c-bdea-54f4-98a7-41d26f89894c-ariaaquin-glow-up-transition-reel | BREAKDOWN | GL | Before→after inside one continuous-looking shot, with the hand over the lens hiding the cut (third-party) | Y | ✓ |
| 52 | CapCut: Reel transition trends | https://www.capcut.com/create/instagram-reel-transitions-viral-edit-tips | BREAKDOWN | GL | Advises one transition language per reel, because mixed effects pull attention to the edit (vendor) | Y | ✓ |

### 1.9 event_recap (`genre.event_recap`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 53 | House on the Clouds (celebrity wedding films) | https://www.hollywoodreporterindia.com/features/interviews/featuresinterviewsalia-and-ranbir-to-rashmika-vijay-deverakonda-filming-the-great-indian-celebrity-wedding | CREATOR | IN | Known for filmic tones and soft-focus nostalgia; shot widely shared celebrity wedding reels (also https://www.bridestoday.in/weddings-planning/story/the-wedding-photographers-behind-every-viral-celebrity-shaadi-1232162-2025-06-29) | P (interview) | ✓ |
| 54 | WeddingSutra Influencer Awards: HOTC sangeet film | https://weddingsutra.com/blog/new-age-sangeet-video-weddingsutra-influencer-awards-winner-house-clouds | AWARD | IN | Award-winning sangeet film; praised for changing how Indian weddings are seen on screen | P | ✓ |
| 55 | The Quint: India's celebrity wedding filmers (The Wedding Filmer / Vishal Punjabi, Joseph Radhik, HOTC) | https://www.thequint.com/entertainment/celebrities/tell-me-all-video-wedding-filmers-joseph-radhik-vishal-punjabi-siddharth-sharma-virat-anushka-wedding-deepveer-katrina-vicky | BREAKDOWN | IN | Interviews with the studios behind India's most-shared wedding videos | P | ✓ |
| 56 | Rajasthan Royals IPL Reels (e4m Maddies case study) | https://design.exchange4media.com/e4mdesigner/abhishek/maddies2022/case-study/marketing-strategy-a1.html | AWARD (case) | IN | Season Reels reported at ~297M views, 24% up year on year, without influencers | Y | ✓ |
| 57 | Vimeo: the art of the event recap video | https://vimeo.com/blog/post/event-recap-video | BREAKDOWN | GL | Recaps of 2–4 min on one soundtrack with short quotes, from which social cutdowns are made | Y | ✓ |
| 58 | Red Hat Summit: "Recapping the recap" | https://redhat.com/en/blog/recapping-recap-red-hat-summit-2018 | BREAKDOWN | GL | First-hand account of cutting a conference recap on deadline, with shots over interview audio | Y | ✓ |
| 59 | Benson Boone Socials (Webby 2025, Social Video Short Form, Music & Performance) | https://winners.webbyawards.com/2025/social/social-video-short-form/music-performance/332321/benson-boone-socials | AWARD | GL | Webby Winner for performance-led short-form clips; no source statement on the edit | N | ✓ |

### 1.10 brand_story (`genre.brand_story`)

| # | Source | URL | Type | Region | Why exemplary (per source) | Breakdown? | Verified |
|---|---|---|---|---|---|---|---|
| 60 | Cadbury 5 Star "Erase Valentine's Day" (Cannes 2025 Gold, Social & Creator) | https://lovethework.com/work-awards/campaigns/erase-valentines-day-1620505 | AWARD | IN | India's Social & Creator Gold; counter-cultural "do nothing" V-Day idea. Case study at https://socialsamosa.com/indian-social-media-case-studies/case-study-5star-erased-v-day-4417479 | Y | ✓ |
| 61 | Cannes Lions 2025 Social & Creator Golds (Skoda "Redditor Edit", Ikea "U Up?", Nutter Butter, McDonald's "Olympic Curry") | https://www.contagious.com/news-and-views/cannes-lions-2025-social-and-creator-winners | AWARD | GL | Jury-awarded Gold Lions. The article gives no reason for each pick, so read entries on lovethework.com | P | ✓ |
| 62 | Apple × Raw Mango "Step Into the Light" (Diwali, Shot on iPhone) | https://theprint.in/feature/vigyapanti/apple-step-into-the-light-diwali-campaign-iphone-18-pro/3093090/ | CREATOR (brand) | IN | Review praises the textiles, dance, architecture and light, and says it doesn't feel like an ad. Edit credit (Anupam Sarkar) at https://www.adsoftheworld.com/campaigns/step-into-the-light. Measure its vertical cutdowns | P | ✓ |
| 63 | Asian Paints "Where the Heart Is" | https://thinkwithgoogle.com/intl/en-apac/marketing-strategies/video/how-asian-paints-found-its-home-youtube | BREAKDOWN | IN | Celebrity home-tour series, long-running (season 9). WARC reports wide reach and better completion rates (https://www.warc.com/en/article/asian-paints-corporate%3A-where-the-heart-is-467a5d7863d041c0976d525492146e47); 2017 webisodes averaged above 25% completion per BestMediaInfo (https://bestmediainfo.com/2017/4/asian-paints-webisodes-where-the-heart-is-portrays-celebs-homes). The Think with Google page was not fetched | Y | ✓ |
| 64 | Spikes Asia 2025: India winners (Savlon "Handwash Legend" Silver, Social & Influencer) | https://bestmediainfo.com/mediainfo/advertising/spikes-asia-2025-india-brings-home-5-grand-prix-8998701 | AWARD | IN | APAC jury awards for Indian social work | N | ✓ |
| 65 | ABBY 2025 (Goafest) Digital/Social winners (Wakefit "Gaddagiri" Silver, Moment Marketing) | https://manifest-media.in/advertising/220525/abby-awards-2025-fcb-india-wins-grand-prix-on-day-two.html | AWARD | IN | Indian jury awards, including Creative Use of Video (Spotify, KitKat) | N | ✓ |
| 66 | Kyoorius Creative Awards 2025 gallery | https://www.kca.kyoorius.com | AWARD | IN | Indian awards with a dedicated Digital Craft jury; full gallery of winning work | N | ✓ |
| 67 | Social Samosa: Top 50 campaigns of 2025 | https://www.socialsamosa.com/editors-pick/editors-pick-top-50-campaigns-of-2025-10956374 | BREAKDOWN | IN | Editorially curated list of standout Indian campaigns; filter it for Reels-native work | P | ✓ |

**Dropped:** a playpodcasts.com article on UK podcast clip engineering returned 404, and the Indiana Fever Webby page URL was never returned.

### 1.11 Counts

Counted by each row's primary genre. Several rows serve two genres; for example, #26 is tutorial and product, and #63 is brand_story and transformation.

| Genre | Rows | India rows |
|---|---|---|
| talking_head | 7 | 1 |
| testimonial | 8 (7 compliant; #8 is excluded, see §2.4) | 3 (incl. Meta Ad Library) |
| product | 7 | 0 |
| tutorial | 6 | 1 |
| vlog | 5 | 2 |
| montage | 7 | 0 |
| podcast_clip | 6 | 2 |
| transformation | 6 | 0 |
| event_recap | 7 | 4 |
| brand_story | 8 | 7 |
| **Total** | **67** (66 excluding #8) | **20** |

**Gaps:**
- *India transformation:* no credible source was found. The next step is a Meta Ad Library search with country = India and terms like "before after", "makeover", or salon and fitness brands.
- *India product and montage:* award galleries (Kyoorius, ABBY) should be mined entry by entry.

### 1.12 Top 10 to start with

These are ranked by credibility × measurability × relevance to India:

1. Webby Creators: Best Editing index (#35), juried on editing craft alone.
2. Zach King, Webby Best Editing 2025 (#34).
3. TikTok Creative Center Top Ads (#9), performance-qualified ads with per-second analytics.
4. Meta Ad Library, India filter (#10), for Indian testimonial and product ads.
5. Cannes Lions 2025 Social & Creator, Vaseline Verified GP plus Golds (#26, #61).
6. Cadbury 5 Star "Erase Valentine's Day" (#60), India's Cannes Gold, with a written case study.
7. Shorty Awards 18th Short Form Video category (#19, #20, #39).
8. Hormozi-style talking-head breakdowns (#1, #2), the dominant caption grammar.
9. Raj Shamani, Figuring Out (#43), the Indian podcast-clip funnel.
10. House on the Clouds (#53–55), the reference for Indian wedding and event recaps.

---

## 2. Legal and ethical note

### 2.1 What the primary sources say

| Source | What it says (paraphrased; short quotes only) | Implication |
|---|---|---|
| **YouTube Terms of Service**, "Permissions and Restrictions" (https://www.youtube.com/static?template=terms) | Item 1 bars you from "reproduce, download, distribute…" content unless YouTube expressly authorises it or gives prior written permission. Item 3 bars automated access "such as robots, botnets or scrapers" | No youtube-dl/yt-dlp downloads. Watching is fine. A CC-BY licence grants copyright permission but does not override the ToS on *how* the file is obtained (see 2.3) |
| **TikTok Terms of Service** §5 and §7A (https://www.tiktok.com/legal/page/row/terms-of-service/en) | §5 prohibits automated scripts that collect information and unauthorised copies. §7A says content "may not be downloaded, copied, reproduced, distributed" beyond what the service permits. An India supplemental section exists | Use the in-app save only where the creator enabled it, and only for personal viewing. No scrapers |
| **Instagram Terms of Use** (https://help.instagram.com/581066165581870, quoted via search results) | Prohibits collecting information "in an automated way without our express permission" | No scrapers or bulk downloaders. The in-app **Save** (bookmark) is a platform feature and is fine |
| **India, Copyright Act 1957 s.52(1)(a)** (text: https://future.indiankanoon.org/doc/257434; govt page: https://www.copyright.gov.in/Exceptions.aspx) | Fair dealing for private or personal use *including research*, criticism or review, and reporting is not infringement. "Fair dealing" is undefined and the list is closed | Personal study plus written critique is the strongest footing. Whether the *research* limb covers AI training is disputed (https://www.barandbench.com/columns/fair-dealing-cannot-be-presumed-why-ai-training-fails-the-purpose-test-under-indian-copyright-law) |
| **US fair use, 17 U.S.C. §107** (US Copyright Office Fair Use Index: https://www.copyright.gov/fair-use/) | Four factors (purpose, nature, amount, market effect); criticism, comment and research are illustrative purposes, not automatic passes | Notes and measurements are low-risk. Redistributing clips is high-risk |

Copyright protects expression, not ideas, techniques or facts. A style vector (cut rate, shot lengths, LUFS) and our own description of techniques are facts and ideas. Platform ToS, however, are contracts that govern how we *access and copy*, whatever copyright says.

### 2.2 Acceptable vs not

| Activity | Status | Notes |
|---|---|---|
| Watching a public reel in the official app or site and writing timecoded notes and measurements in our own words | ✅ OK | This is Mode B (§3.3). Cite the URL |
| Bookmarking with Instagram Save, YouTube playlists, or TikTok Favourites | ✅ OK | In-platform features, no file copy |
| Analysing **our own** or **client** reels (we hold the master export) | ✅ OK | Get written client consent covering analysis and storage |
| Analysing files shared **with written permission** by the creator or agency | ✅ OK | Keep the permission email with the record |
| CC-BY video obtained from a source that *offers* the download (Vimeo download button, Wikimedia Commons, Internet Archive, the creator's own link) | ✅ OK, with attribution | Verify the licence in the description; the YouTube CC filter is not always accurate (https://support.google.com/youtube/answer/2797468) |
| Sending frames or audio of permitted files to Claude for analysis | ✅ OK if the file is permitted | Check the provider's data-use terms; never send frames of files we're not allowed to hold |
| Downloading third-party reels with yt-dlp, "Klickpin"-style sites, or browser extensions | ❌ Not OK | Breaches YouTube, TikTok and Instagram ToS |
| Screen-recording third-party reels as a workaround | ❌ Not OK | Still a copy made outside platform-provided means; same ToS problem |
| Scraping or bulk collection of reels or metadata | ❌ Not OK | Explicitly barred by all three platforms |
| Redistributing clips or frames (repo, demo, artifact, slide) | ❌ Not OK | Except our own content or with a licence |
| Training or fine-tuning models on third-party reels | ❌ Not OK | ToS problems plus a disputed copyright position. Use examples only as *retrieval context* (style vectors plus own-words notes) |

### 2.3 Recommended compliant collection process

1. **Source register.** Every `example.*` node carries `provenance` (one of `own`, `client_permission`, `creator_permission`, `cc_by`, `public_view_only`) and `file_held: true|false`.
2. **Tier 1, files we own.** The user's and clients' own reels, from project exports or Instagram's "Download your information" for their *own* account.
3. **Tier 2, permission.** Email the creator or agency for a master file, permitting private analysis and storage of derived measurements, with no redistribution and no training. Store the reply.
4. **Tier 3, Creative Commons.** Use YouTube with the Creative Commons filter only to *find* candidates. Obtain the file from a channel that offers a download, record the attribution, and re-check the licence text.
5. **Tier 4, public view only (most of §1).** Watch in the official app or site and run the Mode B manual protocol. No file, no frames, no screen recording. Bookmark with Save.
6. **Storage hygiene.** Keep files in `samples/` excluded from git and never published. Delete them when permission lapses. Derived measurements and notes may stay.
7. **No training.** The library is reference context for Claude's planning, not a training set.

### 2.4 The existing `samples/bathroom.mp4`

Per `analysis/bathroom/notes.md`, the file came from a third-party downloader site ("From Klickpin.com…"). That is the non-compliant pattern described above. Options, in order:

- (a) Ask Wortham (the agency) or DearMa for permission and a master file, then reclassify as `creator_permission`.
- (b) If permission isn't granted, delete the local copies (`samples/bathroom.mp4` and the original download). Keep `notes.md` as a Mode-A-derived record marked `provenance: third_party_download_unverified` and `file_held: false`. Never publish frames from it.
- (c) Replace it as the "can Claude see editing quality" test asset with an owned or permissioned testimonial reel.

---

## 3. Measurement protocol

### 3.1 Style vector

These fields are a superset of the metrics in `analysis/bathroom/notes.md`, so every new example compares directly with that one.

| Group | Metric | Mode A (file) method | Mode B (manual) method |
|---|---|---|---|
| Format | duration_s, fps, resolution, aspect | ffprobe | Player UI |
| Cuts | cuts, cuts_per_min, median/mean shot_s, shot_cv, shots_under_1s, first_cut_s, longest_shot (s and at_s) | ffmpeg `scdet` threshold 8, confirmed with TransNetV2; flag 0.3–0.4 s "cuts" as possible text flashes | 3 viewing passes, cuts tallied per 10 s window, ±0.25 s precision. YouTube desktop allows 0.25× speed and `,`/`.` frame-step while paused; Instagram does not |
| Hook | text_on_screen_at_0_3s, hook_type, hook_end_s, payoff_at_s | Frame at 0.3 s plus OCR; transcript | First-watch notes |
| Captions | words_per_card (median), position (bottom, centre, beside_face), emphasis method (colour, size, weight, word-by-word), case, font class, on-screen words/min, % of runtime with text | OCR every 0.5 s; ASR (Whisper) words/min to compare | Note 5 sample cards with timestamps |
| Audio | integrated LUFS, true peak, LRA, music_bed (y/n), silence gaps, SFX hits per min | ffmpeg `ebur128`, `silencedetect` | Qualitative only (music y/n, SFX y/n) |
| Music sync | bpm, cuts_on_beat_pct (cuts within ±1 frame / ±40 ms of a beat), drop-aligned moments | librosa or madmom beat track × cut list | "Feels on-beat" yes/partial/no, with a count of obvious beat cuts |
| Colour | look (e.g. warm/teal split), mean saturation, warm:cool ratio per shot, contrast, consistency across shots | Per-shot mean HSV from mid-shot frames; 2 s contact sheet | Description only |
| Transitions | hard-cut %, dips to black (count, durations), named transitions | `blackdetect`; contact sheet | Count named ones |
| Structure | beats with t_start/t_end and labels | Transcript plus contact sheet | Timecoded notes |

**Mode A pipeline (permitted files only):** ffprobe → `scdet` and TransNetV2 → `blackdetect`/`silencedetect`/`ebur128` → 2 s contact sheet → OCR every 0.5 s → Whisper → beat track → per-shot colour stats → Claude reviews the contact sheet and transcript and writes beats, techniques and lessons in its own words.

**Mode B (view-only):** fill the same fields, set `measurement_mode: manual`, and leave Mode-A-only fields `null`. Mark confidence `low` unless two passes agree.

### 3.2 `example.*` node YAML

This extends SCHEMA §2: same core keys, plus example-specific fields. `tech.*` ids marked `# proposed` don't exist yet; only `tech.hook.result_first` and `tech.hook.slow_build` exist today.

```yaml
nodes:
  - id: example.testimonial.dearma_wortham          # example.<genre>.<slug>
    type: example
    name: DearMa founder on Wortham (agency testimonial)
    summary: Founder testimonial for a creative agency, kept fast by kinetic keyword typography and literal B-roll.  # ≤ 60 words, own words
    genres: [genre.testimonial, genre.brand_story]
    platforms: [platform.instagram_reels]
    goals: [goal.trust, goal.brand_recall]
    url: null                                        # public URL if known
    provenance: third_party_download_unverified      # own | client_permission | creator_permission | cc_by | public_view_only | third_party_download_unverified
    file_held: true                                  # see §2.4: resolve or set false
    measurement_mode: file                           # file | manual
    language: en                                     # en | hi | hinglish | ...
    region: GL                                       # IN | GL
    style_vector:
      duration_s: 73.73
      fps: 25
      resolution: 720x1280
      cuts: 44
      cuts_per_min: 35.8
      shot_median_s: 1.08
      shot_mean_s: 1.64
      shot_cv: 0.95
      shots_under_1s: 22
      first_cut_s: 4.40
      longest_shot: {s: 8.64, at_s: 38.28, carried_by: kinetic_text}
      text_on_screen_at_0_3s: true
      loudness: {lufs_i: -13.7, true_peak_dbfs: 0.6, lra_lu: 6.9}
      dips_to_black: [{at_s: 9.32, dur_s: 0.72}]
      detector: {scdet_threshold: 8, second_pass: null}   # TransNetV2 pending
    beats:                                 # approx: true = boundary estimated, not measured
      - {t: [0.0, 4.4],  label: hook_line, approx: true}            # ends at measured first cut
      - {t: [4.4, 10.0], label: intro_name_title_card, approx: true} # dip at 9.32–10.04 measured
      - {t: [10.0, 53.0], label: praise_team_usp_with_broll, approx: true}  # includes USP line and ~32 s subscribe-bar mock-up
      - {t: [53.0, 59.0], label: fast_brand_montage}       # measured: ten shots of 0.56–0.80 s
      - {t: [59.0, 73.7], label: thanks_credits_logo_url, approx: true} # black 72.68–73.68 measured
    techniques:
      - {id: tech.caption.kinetic_keyword, at_s: null, note: "throughout; 1–4 words, key word enlarged, beside face"}   # proposed
      - {id: tech.text.carry_long_shot, at_s: [38.28, 46.92]}       # proposed; measured longest shot
      - {id: tech.broll.literal_illustration, at_s: null, note: "designers sketching while she says 'team'"}  # proposed
      - {id: tech.montage.burst_sub_1s, at_s: [53, 59]}             # proposed; measured
      - {id: tech.end.logo_url_card, at_s: null, note: "credits → logo flash → URL on black (ends 73.68)"}  # proposed
    caption_style:
      words_per_card_range: [1, 4]           # from notes.md; median not measured
      words_per_card_median: null
      position: beside_face
      emphasis: [size, weight]
      word_by_word: false
      case: mixed
      font_class: sans_bold_mixed_weights
      runtime_with_text_pct: null
    music_sync:
      music_bed: true
      bpm: null
      cuts_on_beat_pct: null              # Mode A beat-tracking pending
      notes: "Montage burst likely beat-cut; unmeasured"
    colour:
      look: warm_interview_vs_teal_broll
      warm_cool_ratio: null
      mean_saturation: null
      consistency: high
    lessons:                               # own words, actionable for the editor
      - "A long talking shot survives if text keeps changing every ~1 s."
      - "Sub-1 s montage bursts work as a 'proof' beat after the USP line."
      - "Fix true peak: +0.6 dBFS clips; target ≤ -1 dBTP."
    evidence_level: single_opinion         # SCHEMA enum; award/showcase-sourced examples → practitioner
    confidence: medium
    sources:
      - {title: "Local measurement", url: "analysis/bathroom/notes.md", locator: "Edit style vector"}
```

**Proposed new `tech.*` ids** seen in §1 sources (to be added to a `graph_*.yaml` draft later):

`tech.caption.word_by_word_highlight` (Hormozi), `tech.caption.kinetic_keyword`, `tech.cut.jump_cut_tighten`, `tech.transform.punch_in_emphasis`, `tech.broll.literal_illustration`, `tech.text.carry_long_shot`, `tech.montage.burst_sub_1s`, `tech.montage.beat_synced_cut`, `tech.transition.hand_over_lens` (transformation), `tech.transition.luma_fade` (Kolder), `tech.transition.match_motion_whip`, `tech.vlog.mid_sentence_cutoff` (Neistat), `tech.color.two_tone_split`, `tech.end.logo_url_card`, `tech.podcast.split_reframe_9x16`.

### 3.3 Workflow per reference reel

1. Pick a row from §1 and record `provenance` and `file_held`.
2. Run Mode A if a file is permitted, otherwise Mode B.
3. Fill the YAML and link techniques. Add new `tech.*` ids marked proposed.
4. Write 3–5 own-words lessons and a 1-paragraph notes.md in the `analysis/bathroom/notes.md` format.
5. Target 3–5 examples per genre: at least 1 India (Hindi/Hinglish where relevant) and at least 1 global award or showcase entry.
