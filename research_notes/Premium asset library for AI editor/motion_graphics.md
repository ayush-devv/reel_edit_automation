# Motion-graphics / animation asset sources for an autonomous Remotion + ffmpeg reel editor

Accessed 2026-11-19. Each source's own "last updated" date is given next to its quotes where the page showed one. Quotes marked "(per page extract)" came through a WebFetch summariser that was told to quote verbatim, not through raw HTML; treat the exact punctuation as approximate. Quotes marked "(raw extract)" were pulled from the downloaded HTML and are high fidelity. Third-party summaries (licenseorg.com, aggregators) are labelled as such and are unverified.

Context: the pipeline is Remotion (React) + ffmpeg. It produces vertical reels for paying freelance clients. It already renders a 6-animation in-house Lottie pack through @remotion/lottie, plus Noto emoji SVGs, code-drawn graphics and ffmpeg effects. Recent repo commits add client review links that feed a "Revise" flow. That matters for the "on-demand / end-user customisation" clauses below.

---

## Q1. Licences for client work on social platforms: attribution, automated/"tool or template" restrictions, AI/ML clauses

### Takeaway
The cleanest licences for an automated client-work pipeline are permissive code-style ones: useAnimations (MIT Lottie icons), MIT Remotion animation libraries, and arguably the Lottie Simple License if the LottieFiles plan question below is resolved. Stock-marketplace subscriptions (Envato Elements, and by ownership probably Mixkit, plus Vecteezy/Videezy and Motion Array) all carry at least one of these clauses: per-End-Product registration, a ban on use in tools or templates, a ban on "on-demand" end-user customisation apps, a ban on bots or mass downloads, or AI clauses. Each of those bites on an autonomous editor that keeps a reusable local library. LottieFiles has an unresolved internal conflict between its free licence and its Terms & Conditions.

### Cited Findings

#### LottieFiles (Design Barn Inc.): free animations and premium/plan terms
- The Lottie Simple License ("FL 9.13.21", © 2021 Design Barn Inc.) grants the right "to download, reproduce, modify, publish, distribute, publicly display, and publicly digitally perform such Files, including for commercial purposes" (per page extract). — [LottieFiles Lottie Simple License](https://lottiefiles.com/page/license)
- Attribution: "Use of Files without attributing the creator(s) of the Files is permitted under this license." Attribution is "strongly encouraged", and if given it must be "visible to the end user" (per page extract). — [Lottie Simple License](https://lottiefiles.com/page/license)
- Restrictions in the same licence: redistributions must carry the same terms. You may not "impose any additional or different terms". And "This license does not include the right to collect or compile Files from LottieFiles to replicate or develop" [a similar/competing service] (per page extract). The licence text does not mention AI/ML or use inside software. — [Lottie Simple License](https://lottiefiles.com/page/license)
- **Conflict.** The LottieFiles Terms & Conditions (last modified 10 Nov 2026) state: "The Individual Plan and Free Plan are strictly for non-commercial use only." Users who want commercial use "are required to subscribe to the Team Plan, Team+ Plan or Enterprise Plan". The T&C's definition of commercial use ("Any use of animations created through or obtained from Lottiefiles that is intended for or directed toward…") includes "Product Sales: Incorporating animations into products that are sold or distributed, whether as part of a digital product (e.g., mobile apps, software, websites) or a physical product" (per page extract). The same T&C also say: "For the animation that is publicly and freely available, you agree to the Lottie Simple License." The document does not clearly say whether the non-commercial plan restriction overrides the Simple License for free public animations. Animations made with "Lottie AI … can be used commercially on every plan" (per page extract). — [LottieFiles Terms & Conditions](https://lottiefiles.com/page/terms-and-conditions)
- The T&C contain no explicit AI/ML-training clause and no licence terms for "premium"/marketplace animations; those are referenced to separate "Terms & Conditions for Sale", which were not retrieved. — [LottieFiles T&C](https://lottiefiles.com/page/terms-and-conditions)
- The pricing page markets the Team plan ($24.99/user/month, billed annually) "For teams working on commercial projects". Individual is $19.99/user/month (per page extract). — [LottieFiles Pricing](https://lottiefiles.com/pricing)

#### IconScout (also Design Barn Inc.)
- The "IconScout Simple License" is "Copyright © 2026 Design Barn Inc.", the same parent as LottieFiles. It grants the right "To download, modify, and use digitally such Files, for commercial purposes". Use "without attributing the creator(s) … is permitted". Edited assets you did not design "must have the original creator attributed and a link provided to the original animation in the description" (per page extract). — [IconScout Licenses](https://iconscout.com/licenses)
- Not allowed: "Re-distribute of Item as stock, in a tool or template". Also "not allowed to resell or republish (as a separate entity …) to any platform", and "This license does not include the right to collect or compile Files from IconScout". The comparison table lists video/production use with a "Budget below $10,000" under the Digital License and "Unlimited" under the Physical Unlimited License. There is no AI/ML clause (per page extract). — [IconScout Licenses](https://iconscout.com/licenses)

#### Lordicon
- Free licence: "Author attribution (credit needed) required." "The license allows commercial use." Standard PRO: "Does not require author attribution". It permits "video, graphical user interface (GUI), print, applications, computer games and presentations". Prohibited: distributing icons "as standalone files, whether for free or for profit", and using icons as "the core feature of a product, such as an icon library or icon pack". Inclusion in "HTML templates or themes" is prohibited unless the API terms are met. There is no AI/ML clause. Lordicon "may freely change the formats", and icons may be "in the static or Lottie JSON format" (per page extract). — [Lordicon Licenses](https://lordicon.com/licenses)

#### useAnimations
- "300 icons · zero dependencies · MIT". FAQ: "The icons and the react-useanimations package are MIT licensed: use, modify and redistribute them in personal and commercial work. Attribution is appreciated but not required." They are offered as a React component, via shadcn, or as SVG and Lottie JSON downloads (raw extract). — [useAnimations](https://useanimations.com/)

#### Rive
- Official Rive runtimes are MIT-licensed and free for commercial use with no runtime fees (search-result summary of Rive docs). — [Rive runtimes docs](https://rive.app/docs/runtimes)
- "Marketplace files are all shared under a CC BY license." The linked page is CC BY 4.0, which requires attribution (per page extract). — [Rive Marketplace overview](https://rive.app/docs/community/marketplace-overview)
- `@remotion/rive` (the `<RemotionRiveCanvas>` component) is "covered by the Remotion License" (per page extract). — [Remotion @remotion/rive docs](https://www.remotion.dev/docs/rive/)

#### Envato Elements (strongest negative finding)
- Elements License, last revised 6 Oct 2026. It "permits use of the Item for one project to create a specific End Product" (cl. 6). "you must first register the Item for each separate End Product" (cl. 11). Reusing an item for a separate project requires you to "create a new license" (cl. 4) (per page extract). — [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- Client work is allowed: "You can use an Item to create an End Product for yourself or for a client of yours." (cl. 10a.i). — [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- Prohibitions:
  - "You can't use an Item in any application allowing an end user to customize …", with examples of "on demand", "made to order" and "build it yourself" applications (cl. 12c).
  - "You can't redistribute an Item as stock, in a tool or template, or with source files." This applies even if modified or free (cl. 12b).
  - No letting the end user extract an Item (cl. 12e).
  - No broadcast use of music (cl. 14a).

  The Elements License does not itself mention AI; it links to separate "Envato – AI Product Terms" (not retrieved). — [Envato Elements License Terms](https://help.elements.envato.com/hc/en-us/articles/360000628966-License-Terms)
- User Terms, last revised 10 Nov 2026:
  - 14(b) bans access "through any unauthorized means, including through scripts, bots, automated tools".
  - 14(m) bans "use of scripts or bots to mass download Items or Output" and scraping or downloading "the entire library and/or database of Envato Assets".
  - 14(f) bans "data mining, robots, or other similar data and/or image gathering and extraction methods".
  - 14(d) restricts incorporating content into "any product or service provided to a third party".
  - After cancellation: "the applicable Item license will continue for the life of the End Product (even if your subscription ends)", but you cannot "use any Items as part of new project or unfinished End Product" (61(b)) (per page extract).

  — [Envato Elements User Terms](https://help.elements.envato.com/hc/en-us/articles/360000629006-User-Terms)

#### Mixkit (owned by Envato)
- The Mixkit licence page footer reads "Made by Envato" and promotes Envato Elements. Mixkit has separate licences: Stock Video Free, Stock Video Restricted, Video Templates Free, Music Free, SFX Free and Art Free. "On Mixkit, we have a specific license for each of our item types" (raw extract). The licence text itself loads in a JS modal and could not be retrieved. — [Mixkit License](https://mixkit.co/license/)
- Third-party summaries (unverified):
  - The Free License allows commercial use.
  - "Restricted" videos are personal use only.
  - Raw clips cannot be redistributed and must be incorporated into a larger project.
  - Clips cannot be used to build a competing stock service.

  One review claims clips can be sub-licensed to clients, which conflicts with the above. — [licenseorg Mixkit guide](https://licenseorg.com/guide/video/mixkit); [licenseorg Mixkit vs Videvo](https://licenseorg.com/compare/mixkit-vs-videvo)
- Mixkit's navigation lists Premiere Pro, After Effects, Final Cut Pro and DaVinci Resolve template categories: lower-thirds, titles, transitions, call-outs and Instagram (raw extract). — [Mixkit License page nav](https://mixkit.co/license/)

#### Vecteezy / Videezy (Eezy LLC)
- Vecteezy License Agreement, "Last updated: June 22nd, 2026" (raw extract). — [Vecteezy Licensing Agreement](https://www.vecteezy.com/licensing-agreement)
  - "Using Content within software applications which allow a third party to generate on-demand designs is also not permitted under this License Agreement. This includes (but is not limited to) print-on-demand software applications in which an end user has access to use the Content as they design or generate their end product."
  - "You may not allow the end user of your End Products to extract the Content … You may not publicly display, sell, license, or otherwise distribute the Content (or modified Content) as a standalone file."
  - AI: data-training rights are "Available only as an add-on to an Enterprise License … Content may not be used for data training purposes under Free, Pro S[tandard…]". Without that add-on, "content may only be used in traditional creative, editorial, marketing, or commercial applications."
  - Free License: "Attribution is required."
  - Pro Standard (single user, no attribution) allows "video, film, or production projects with budgets up to $10,000". Pro Business allows 2–6 users and "productions of any budget".
  - "Digital Use" includes social media (Facebook, Instagram, Snapchat …) and "templates".
- Videezy's licence page returned HTTP 403, so it is not confirmed that Videezy uses identical terms, even though both are Eezy LLC brands (the Vecteezy page footer lists "Our Network … Videezy"). — [Vecteezy Licensing Agreement](https://www.vecteezy.com/licensing-agreement)

#### Motion Array (Artlist group)
- Help centre (search-result summary): on any plan you can use assets "in a derivative work to distribute to clients", but not as standalone files and only if you are the sole account user. Companies with more than 50 employees need a Business licence. Projects not published before the subscription ends are not covered. — [Motion Array: Does the license cover client use?](https://help.motionarray.com/hc/en-us/articles/25247349475997-Does-the-license-cover-client-use); [Motion Array License FAQs](https://help.motionarray.com/hc/en-us/articles/37251636136605-License-FAQs)
- Terms of Service (secondhand and possibly stale: a search snippet of a ToS dated 9 Apr 2024; a direct fetch returned 403) prohibit using assets "for purposes of machine learning and/or Artificial Intelligence ('AI') training, and/or for creation of generative AI and any similar acts". — [Motion Array Terms of Service (adobe-panel mirror)](https://adobe-panel-api.motionarray.com/terms-of-service)

#### Footage Crate / ProductionCrate
- No primary licence text was found (several candidate URLs returned 404). Third-party claims (unverified):
  - FootageCrate is a ProductionCrate sub-brand.
  - The free tier requires attribution and has download limits.
  - Pro (~$12/month) removes attribution.
  - Assets cannot be used in competing stock products.
  - Some content is editorial-only.

  — [licenseorg ProductionCrate guide](https://licenseorg.com/guide/video/productioncrate)

#### Pixabay
- Allowed: "Use Content for free", "without having to attribute the author", "Modify or adapt Content into new works". Not allowed: "You cannot sell or distribute Content … on a Standalone basis", where Standalone means "no creative effort has been applied to the Content". The summary is silent on AI, software/templates and bulk download, and defers to the full ToS (per page extract). — [Pixabay License Summary](https://pixabay.com/service/license-summary/)

#### After Effects / MOGRT templates rendered headlessly
- A 2020 Adobe Community thread asked whether a company can run AE + nexrender on a server to render customer-edited templates. There is no Adobe staff answer. A community member said "You need one licence for this" and that render-farm nodes need no individual licence. A Community Expert forwarded the question to Adobe without resolution. — [Adobe Community thread (2020-09-03)](https://community.adobe.com/t5/after-effects/i-want-to-know-whether-our-service-will-have-license-problem-or-not/td-p/11407145)
- Forum and vendor claims (unverified; Adobe's own help page returned 403):
  - aerender (CS6+) can run in "non-royalty-bearing" render-only mode when `ae_render_only_node.txt` is present.
  - Render-only mode may not need an Adobe sign-in.
  - Third-party plugins need their own render-only licences.

  — [Adobe Community: licensing requirement to run aerender as background job](https://community.adobe.com/t5/after-effects-discussions/licensing-requirement-to-run-aerender-as-background-job/m-p/14339769); [Adobe Community: non-royalty-bearing mode](https://community.adobe.com/questions-529/how-do-i-get-non-royalty-bearing-mode-to-work-in-ae-41516); [aescripts render-only plugin licences](https://aescripts.com/plexus-3-render-only/)
- nexrender is an open-source Node.js framework for automating AE renders, local or farm (search-result summary). — [nexrender via context7](https://context7.com/inlife/nexrender)

#### Open-source Remotion animation code
- remotion-bits: MIT. It provides "charts, transitions, text reveals, and more" (AnimatedText, GradientTransition, particle-system, 3D scene bits). Install with `npm install remotion-bits` or copy-in via a jsrepo registry. It also has a CLI and an MCP server for searching and fetching bits. ~519 stars, 149 commits, no tagged releases (per page extract). — [av/remotion-bits](https://github.com/av/remotion-bits)
- remotion-animated (stefanwittwer): MIT, v1.0.0. — [remotion-animated](https://www.github.com/stefanwittwer/remotion-animated)
- remotion-open-fx: listed as MIT, with 30+ easings, springs, transitions, overlays and kinetic components (aggregator listing; verify on npm). — [pkgstats remotion-open-fx](https://www.pkgstats.com/pkg:remotion-open-fx)
- remotion-animate-text (per-character/word text animation): licence not confirmed. reactvideoeditor/remotion-templates: claimed MIT via a TypingMind listing, not verified. — [remotion-animate-text](https://github.com/pskd73/remotion-animate-text); [reactvideoeditor/remotion-templates](https://github.com/reactvideoeditor/remotion-templates)
- The official `@remotion/transitions` package (`<TransitionSeries>`, `useTransitionProgress()`, timing presets, audio transitions) is under the Remotion License (per page extract). — [Remotion transitions docs](https://www.remotion.dev/docs/transitions/)

### Inferences
- **Envato Elements, and probably Mixkit by ownership, fits an autonomous editor poorly in four ways:**
  1. Per-End-Product registration (cl. 4/11) means a pre-indexed local library reused across many client reels breaches the licence unless each use is registered.
  2. A bot-driven ingestion pipeline breaches User Terms 14(m)/14(b).
  3. Packaging items into the engine's own reusable template system risks cl. 12b ("in a tool or template").
  4. If clients can drive customisations through the app (the repo's review-link → Revise flow), cl. 12c ("application allowing an end user to customize … on demand") becomes a live risk. **Flagged, not concluded**: a human-operated agency delivering finished reels is the normal permitted case, while a self-serve client tool is the prohibited case. Where this product sits needs legal review.
- Vecteezy/Videezy's "software applications which allow a third party to generate on-demand designs" clause is a similar risk. Their AI clause covers *training* only, not using assets as raw material in an AI-operated edit, so a non-training pipeline is arguably fine. Pro Standard's $10k production-budget cap is unlikely to bind small reels.
- Motion Array's clause covers "creation of generative AI and any similar acts". Whether placing a stock overlay into a reel via an AI editor counts as "creation of generative AI" is ambiguous. It reads as aimed at training and generators, but the wording "any similar acts" is broad and the source is secondhand.
- LottieFiles: paid client reels are plainly commercial. The conservative reading of the T&C is that a Team plan or higher is required even for free public animations, despite the Simple License. The Lottie AI carve-out could be a cheaper path for generated animations. IconScout shares the same owner (Design Barn), so expect harmonised terms over time.
- Attribution-required sources (Lordicon Free, Rive Marketplace CC BY, Vecteezy Free, reportedly FootageCrate Free) conflict with clean client deliverables. They need either a paid tier or a credit line in the post caption, which clients may refuse.
- The lowest-risk breadth expansion is MIT code and assets (useAnimations Lottie JSON, remotion-bits and remotion-animated components, own code-drawn overlays and grain). These can be bundled into the engine with no per-use registration, attribution or tool/template restrictions. Remotion's own company licence still applies to the renderer.
- AE/MOGRT templates: even if headless aerender is licensable, the *template* licences (Envato 12b/12c, IconScout "in a tool or template") are the binding constraint. Converting a purchased AE template to Lottie with Bodymovin and folding it into the engine's reusable library plausibly falls under the "in a tool or template" prohibition (inference only, not tested against any licence text).

### Gaps
- The official Mixkit Stock Video Free and Video Templates Free licence texts could not be retrieved (JS modal). Mixkit's own page says to check the per-item licence.
- Footage Crate / ProductionCrate primary licence: not found.
- Videezy licence page (403): not confirmed whether it is identical to Vecteezy's.
- Current Motion Array ToS (403); only a 2024 snippet is available.
- Envato "AI Product Terms" not retrieved; Envato's explicit position on AI-driven editing of Items is unknown.
- LottieFiles "Terms & Conditions for Sale" (premium/marketplace licence) not retrieved. Whether the Free/Individual non-commercial restriction applies to downloads of free public animations is unresolved; ask LottieFiles support.
- Adobe's official automated/network-rendering licence terms (help page 403). There is no Adobe-staff statement on commercial rendering services.
- Licences for Lordicon PRO pricing, Jitter export and LottieLab export were not checked.
- Pixabay full Content License (AI, software, bulk download) not retrieved; only the summary page was.

---

## Q2. Bulk download and local indexing, API availability (self-serve vs partnership), pricing

### Takeaway
Only MIT or open repos (useAnimations, remotion-bits and other npm packages) can be bulk-ingested and indexed locally without restriction. LottieFiles and Envato expressly ban robots, scraping and mass download. LottieFiles' sanctioned programmatic route is an OAuth MCP whose tools are generic GraphQL, and its download and caching rights are undocumented. IconScout has a self-serve credit-based REST API, but the licence for API-served assets is undocumented.

### Cited Findings
- LottieFiles T&C (10 Nov 2026) prohibit: "Use any robot, spider, or other automatic device, process, or means to access the Website for any purpose", "Use any data mining, or similar data gathering and extraction methods", and "Use any manual process to monitor or copy any of the material on the Website" (per page extract). — [LottieFiles T&C](https://lottiefiles.com/page/terms-and-conditions)
- LottieFiles MCP: a remote hosted server that uses OAuth 2.1 with PKCE and no static API keys. Access tokens last 10 minutes. — [LottieFiles MCP security docs](https://docs.lottiefiles.com/en/platform/mcp/security)
- The MCP exposes four GraphQL workbench tools: `operations_list`, `schema_search`, `schema_details` and `graphql_execute`. Animation creation is separate ("Creator MCP", "Lottie Creator WebMCP"). Plans, rate limits and licensing of retrieved animations are not stated. Page last updated 10 Nov 2026 (per page extract). — [LottieFiles MCP docs](https://docs.lottiefiles.com/en/platform/mcp)
- The LottieFiles platform docs list the GraphQL/REST public API as "Coming soon" (search-result summary). — [LottieFiles Platform docs](https://docs.lottiefiles.com/en/platform)
- LottieFiles pricing (per page extract) — [LottieFiles Pricing](https://lottiefiles.com/pricing):
  - Individual $19.99/user/month (MCP "free to try during beta", 300 credits/month).
  - Team $24.99/user/month (600 credits/month).
  - Team+ is tailored and includes "Lottie AI & MCP".
  - Enterprise is custom with "Audit logs + API included".
- IconScout REST API v3: a free recurring plan with 2,000 credits/month (icons, illustrations, 3D) is mentioned in the developer FAQ. A Lottie animation costs 20 credits versus 1 per icon. Paid tiers appear at about $499/month for 10k–25k credits, but the tier-to-price mapping was unclear (search-result summary; verify). — [IconScout API](https://iconscout.com/api); [IconScout pricing](https://iconscout.com/pricing)
- IconScout help: "Our API plan provides access to icons, illustrations, 3Ds and Lottie assets." It offers custom integrations. It does not say whether API assets may be cached locally or used in automated products (per page extract). — [IconScout: what is included in the API plan](https://help.iconscout.com/what-is-included-in-the-api-plan)
- Envato Elements User Terms 14(m): no "scripts or bots to mass download Items" and no downloading "the entire library and/or database". Section 28(e) says GenAI tool access "may be subject to certain limits" under a Fair Use Policy. — [Envato Elements User Terms](https://help.elements.envato.com/hc/en-us/articles/360000629006-User-Terms)
- The Lottie Simple License excludes "the right to collect or compile Files from LottieFiles to replicate or develop" [a competing service]. IconScout has the same clause. — [Lottie Simple License](https://lottiefiles.com/page/license); [IconScout Licenses](https://iconscout.com/licenses)
- Lordicon: HTML templates or themes need the "Lordicon API Terms". Formats are hosted "in the static or Lottie JSON format … on the User's servers" (per page extract). Pricing is on a separate page (not retrieved). — [Lordicon Licenses](https://lordicon.com/licenses)
- useAnimations: `npm i react-useanimations`, or download SVG/Lottie JSON. MIT, so bulk vendoring is allowed. — [useAnimations](https://useanimations.com/)
- remotion-bits ships a CLI and an MCP server for searching and fetching bits, plus a jsrepo registry at `https://unpkg.com/remotion-bits/registry.json` (per page extract). — [av/remotion-bits](https://github.com/av/remotion-bits)
- Vecteezy Pro plans set a monthly download allowance and seats, and auto-renew (raw extract). — [Vecteezy Licensing Agreement](https://www.vecteezy.com/licensing-agreement)

### Inferences
- A defensible ingestion design:
  - **Vendor MIT assets at build time** (useAnimations, remotion-bits components, own Lottie pack) into a local index with tags.
  - **Fetch licensed marketplace assets per job** through sanctioned APIs (IconScout REST; LottieFiles MCP once download semantics are confirmed), logging asset ID, licence and job ID.
  - **Do not scrape** LottieFiles, Envato or Mixkit.
- Envato-style per-End-Product registration implies the engine would need to call "register" for each reel. No public API for that was found, so Envato is effectively human-in-the-loop only.
- The MCP's 10-minute OAuth tokens and per-plan credit limits suggest LottieFiles is aiming at interactive agent use, not unattended batch ingestion.

### Gaps
- Whether LottieFiles MCP `graphql_execute` can download Lottie JSON or dotLottie, and whether local caching or re-use across jobs is permitted.
- IconScout API licence terms for stored or cached assets and exact current pricing; aggregators conflict.
- Lordicon API pricing and terms; Rive Marketplace bulk-download policy; Footage Crate, Motion Array and Mixkit APIs (none found; likely none public).

---

## Q3. Format compatibility with Remotion/ffmpeg and conversion paths

### Takeaway
Lottie JSON plays directly through @remotion/lottie, which uses lottie-web (SVG, canvas or HTML renderer). The main incompatibility risk is After Effects expressions (only a subset is supported; native functions like `wiggle` are not) and AE effects or layer styles. Bake expressions to keyframes at export. Alpha overlays work as WebM VP8/VP9 `yuva420p` or ProRes 4444 `yuva444p10le` through Remotion's `<Video>` or `<OffthreadVideo transparent>`. Rive `.riv` has a dedicated `@remotion/rive` canvas component. AE/MOGRT templates need either licensed headless aerender or a Bodymovin-to-Lottie conversion.

### Cited Findings
- `<Lottie>` (@remotion/lottie) props (per page extract) — [Remotion <Lottie> docs](https://www.remotion.dev/docs/lottie/lottie):
  - `animationData`; memoise it, because changing its identity re-initialises the animation.
  - `renderer` `"svg" | "canvas" | "html"`; default svg, v4.0.105+.
  - `loop`, `playbackRate`, `direction`, `preserveAspectRatio`.
  - `assetsPath` (v4.0.138+): assets with `e: 0` load from it, and `e: 1` assets load from absolute URLs inside the JSON.
  - Sequence props (`from`, `durationInFrames`, `trimBefore`, …) from v4.0.528+.

  The page defers feature support to lottie-web's list.
- lottie-web expressions (per page extract) — [lottie-web wiki: Expressions](https://github.com/airbnb/lottie-web/wiki/Expressions):
  - "A subset of expressions is supported". Expressions are "similar to javascript but not quite the same".
  - Native AE functions such as `wiggle` are not supported.
  - `use javascript` as the first line skips parsing for performance.
  - Workarounds: the "Convert expressions to keyframes" export option, or a per-expression `// lottie:bake` comment.
- The lottie-web wiki has separate pages for Blend Modes, 3D, Expressions, Effects, Shapes, Text, Markers, "Stroke and Masks issue with SVGs", Renderer Settings and "Lottie Light" (per page extract). — [lottie-web wiki](https://github.com/airbnb/lottie-web/wiki/Supported-Features)
- Transparent video in Remotion (per page extract) — [Remotion: Transparent videos](https://www.remotion.dev/docs/transparent-videos):
  - Supported alpha inputs are WebM VP8/VP9 `yuva420p` ("Chrome and Firefox support WebM videos with alpha channels") and ProRes 4444/4444-XQ `yuva444p10le` (v2.1.7+).
  - `<Video>` from `@remotion/media` needs no flag. `<OffthreadVideo>` needs the `transparent` prop, which "slightly reduces the performance of the render".
  - To render alpha output: PNG image format plus VP8/VP9 `yuva420p`, or `prores` with profile `4444`.
  - On Lambda, WebM alpha can flicker at chunk boundaries, so ProRes is recommended there.
  - The page does not mention HEVC-with-alpha.
- `@remotion/rive` provides `<RemotionRiveCanvas>` to render Rive animations in Remotion (per page extract). — [Remotion @remotion/rive](https://www.remotion.dev/docs/rive/)
- IconScout animated icons come in GIF, JSON (Lottie), SVG and After Effects formats. MP4 appears in titles and previews. Free downloads are "some animated icons … in GIF format", and JSON/SVG may need a subscription (per page extract). — [IconScout animated icons](https://iconscout.com/animated-icons)
- IconScout: "90% of Lottie Animations are available with source file", meaning the AE "Editable Format" plus .JSON (per page extract). — [IconScout Licenses](https://iconscout.com/licenses)
- useAnimations: every icon is "a standard Lottie J[SON]" and usable without React (raw extract). — [useAnimations](https://useanimations.com/)
- Envato Elements: "you are not permitted to use preview files in any End Product" (User Terms §45). Watermarked previews cannot be used as stand-ins. — [Envato Elements User Terms](https://help.elements.envato.com/hc/en-us/articles/360000629006-User-Terms)
- AE automation: aerender plus nexrender (Node.js) can template-render AE projects, but needs AE installed on the node and matching plugins (forum and vendor sources; see Q1). — [nexrender via context7](https://context7.com/inlife/nexrender); [Super Renders Farm AE plugins note](https://superrendersfarm.com/article/after-effects-2025-plugin-render-farm-2026)

### Inferences
- An ingestion validator for third-party Lottie should:
  - reject or flag JSON containing expression strings (`"x":` expression fields) unless they were baked;
  - check for AE effects (`ef` arrays) and layer styles, which lottie-web renders partially or not at all;
  - check for image assets with `e: 1` (external URLs, which are non-deterministic at render time);
  - check for text layers that need fonts.

  Render a test frame strip, and diff it against the source preview, before admitting any asset to the index.
- Overlays (light leaks, film burns, dust, grain, glitch) are best normalised at ingest to WebM VP9 `yuva420p` (smaller, browser-native) or kept as ProRes 4444 for Lambda. Overlays shipped with no alpha (black or white backgrounds, common for light leaks) can instead be composited with screen or add blend modes in CSS or ffmpeg without conversion. That last point is general practice, not sourced here.
- PNG sequences convert to WebM alpha with ffmpeg (`-c:v libvpx-vp9 -pix_fmt yuva420p`). That is consistent with Remotion's required pixel format, but the command was not verified in this research.
- Rive gives interactive and state-machine assets, but CC BY marketplace terms and deterministic frame-accurate rendering through `<RemotionRiveCanvas>` both need checking before relying on it.
- AE templates as a source: headless aerender needs a Windows or macOS node with AE installed, which is a heavy dependency for a Remotion stack. A Bodymovin export to Lottie loses unsupported effects and expressions. Neither path is attractive compared with native Lottie or Remotion code.

### Gaps
- Per-feature lottie-web support table (masks, mattes, merge paths, gradients, time remap, 3D, blend modes per renderer). The LottieFiles supported-features page rendered empty and the wiki subpages were not fetched.
- HEVC-with-alpha support as a Remotion input: not mentioned in the docs.
- Whether `<RemotionRiveCanvas>` renders state machines deterministically per frame.
- Premiere MOGRT and Apple Motion headless rendering: no sources found. Both appear to require their host apps.
- Jitter and LottieLab export formats and fidelity were not checked.

---

## Q4. Catalogue size and coverage per asset type

### Takeaway
LottieFiles (600k–1M+ premium Lottie claimed) and IconScout (~335k animated icons, plus 123k+ stickers and 18k+ animated emoji claimed) dominate Lottie volume. Both are Design Barn properties, and their commercial and automation terms are restrictive or unclear. The fully permissive pool is small (useAnimations: 300 icons) and would need to be supplemented by in-house code-generated graphics and MIT Remotion component libraries. No reliable catalogue counts were obtained for alpha-video overlays on Mixkit, Footage Crate, Motion Array, Envato or Videezy.

### Cited Findings
- LottieFiles: "Access over 600,000 premium Lottie animations" (features section) and "1 Million+ premium Lottie library" (Individual plan). No free-animation count is given (per page extract). — [LottieFiles Pricing](https://lottiefiles.com/pricing)
- IconScout: "over 334,839 animated icons" ("335K+"). Separately counted are Stickers (123,000+), Animated Emoji (18,000+), Animated Stickers (9,000+) and Unicons (7,000+). Curated Lottie packs range from 9 to 90 items. It is unclear whether the counts overlap (per page extract). — [IconScout animated icons](https://iconscout.com/animated-icons)
- IconScout pricing page headline: "Unlock 14.4M+ customizable design assets", across all asset types. — [IconScout pricing](https://iconscout.com/pricing)
- useAnimations: 300 hand-crafted micro-animation icons with 6 built-in interactions; the player is about 8 kB gzipped (raw extract). — [useAnimations](https://useanimations.com/)
- Mixkit categories include video templates for Premiere Pro, After Effects, Final Cut Pro and DaVinci Resolve: lower-thirds, titles, transitions, call-outs, logo, openers, slideshows and Instagram (raw extract). — [Mixkit License page nav](https://mixkit.co/license/)
- Vecteezy navigation lists Motion Graphics: Titles, Logos, Backgrounds and Transitions (raw extract). — [Vecteezy Licensing Agreement page nav](https://www.vecteezy.com/licensing-agreement)
- remotion-bits covers text animation, transitions (GradientTransition), particle systems and 3D scene bits. The full component count was not shown (per page extract). — [av/remotion-bits](https://github.com/av/remotion-bits)

### Inferences
- A rough coverage map against the editor's asset-type list:
  - **Animated stickers, icons and emoji:** IconScout / LottieFiles (huge, licence-constrained), Lordicon (free tier needs attribution), useAnimations (small, MIT).
  - **Text animations and transitions:** best as code (remotion-bits, remotion-animated, @remotion/transitions, in-house), not assets.
  - **Overlays (light leaks, film burns, dust, grain, glitch):** stock marketplaces (Envato, Motion Array, Footage Crate, Mixkit, Videezy), all with restrictive or unverified licences for automated reuse. Procedural ffmpeg or shader generation is the licence-free alternative.
  - **Lower thirds, callouts, shape animations:** template marketplaces (AE/MOGRT), which are hard to automate, so Remotion code components are the practical route.
- The engine's Noto emoji (Apache-2.0 / OFL, per general knowledge; verify) plus a licensed animated-emoji source would cover reactions. Note that Google's Noto Animated Emoji exists as Lottie (general knowledge, not verified in this session).

### Gaps
- No verified catalogue counts for overlays and transitions at Mixkit, Footage Crate, Motion Array, Envato Elements, Videezy or Pixabay; their alpha-format share is also unknown.
- No count of free (Lottie Simple License) animations on LottieFiles.
- Rive Marketplace size, Lordicon library size, Jitter and LottieLab template counts: not retrieved.
- Remotion templates marketplace size and licences: not researched beyond the GitHub repos above.
