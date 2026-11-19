# Asset engine: what the Editor can use, and where it comes from (2026-11-19)

**The question:** can we take the asset libraries of CapCut, Premiere, After Effects or Resolve (music, stock footage, motion templates, b-roll), index them, and let Claude use them?

**The answer:** not by copying them. Their licences tie the assets to their own apps:
- CapCut's [Materials License Agreement](https://www.capcut.com/material-license-agreement) licenses even its "commercial" sounds only for content on CapCut, TikTok and TikTok for Business.
- Adobe's licences restrict standalone use outside their apps.
- The free libraries also forbid compiling them into a similar service: LottieFiles, Mixkit and Pixabay all do.

We get the same reach legally: **official APIs searched on demand, files the owner adds deliberately, and assets we make ourselves.** Every file carries its licence and credit. The editors' own effects stay usable only *inside* those editors, through a connector (step 4).

## Steps

| Step | What | Status |
|---|---|---|
| **1a** | **Stock b-roll at edit time (Pixabay and Pexels).** Pexels paused new API keys in Nov 2026, so Pixabay (free key) is supported too; whichever key exists is used, Pexels first. One search's clips come from one source. A new `stock` stage reads the talk and the brief, writes 3–5 visual searches, and downloads up to 2 clips per search (6 in total) into **this project only**; the Pexels licence forbids a shared library. The `broll` stage then describes them alongside the client's folder, and the Editor picks. | **Built.** Off unless switched on (`reel run --stock`, or "Find stock b-roll" in New edit). It needs the Pexels key (Settings). It never fails an edit: no key, a network error or no results is recorded in `stock/status.json`. |
| **1b** | **Lottie animations** (After Effects motion exported as JSON). There's a new graphic kind, `lottie`: the Editor places an animation on a word, small, medium or large, positioned off the face and captions, at most 3 per reel. The JSON is embedded in the render props, so the render never reads a file or the network. | **Built.** Six-animation starter pack made by us: check, arrow, pulse ring, sparkle, underline, heart. They recolour to the brand accent. Owners add more with `reel library lottie <folder> --source … --license …`. |
| 2 | **One searchable asset index.** Sound, music, b-roll, Lottie and fonts in one catalogue, each with licence, credit, tags and a text embedding. The Editor gets a `search_assets(query, kind, constraints)` tool instead of a full menu, and a licence gate runs before every render. | Next |
| 3 | **Epidemic Sound Partner API** for premium music and sound. Its [free tier can't publish](https://developers.epidemicsound.com/docs/FAQ); client work needs a paid partnership. | When there's a client who needs it |
| 4 | **Resolve or Final Cut connector**, so the Editor can use those apps' own effects and templates inside the app. | Later |

## Safety rules for downloaded files (Lottie)
- `lottie-web` evaluates After Effects **expressions** with JavaScript `eval`, so files with expressions are refused.
- Images fetched from the network are refused.
- Text layers are refused, because their fonts would be missing.
- Files larger than 512 KB or longer than 12 s are refused.
- ShareAlike, NonCommercial and NoDerivatives licences are refused (the existing licence check).

## Sources
- **LottieFiles free animations:** [Lottie Simple License](https://help.lottiefiles.com/hc/en-us/articles/900002438343-Can-I-use-a-free-animation-on-Lottiefiles-for-commercial-business-use). Commercial use is allowed and attribution isn't required; compiling a competing collection is not allowed. LottieFiles has no documented public search API (only a sign-in MCP), so the owner downloads the files.
- **Pexels:** free commercial use, no attribution required; no resale and no competing library (see `engine/src/reel/stock.py`).
- **Pixabay** (candidate): commercial use allowed. The API must [show the source in search results and cache for 24 h](https://pixabay.com/api/docs/). Check for logos and identifiable people.
- **Mixkit** (candidate): licence varies per asset; some videos are "restricted", meaning non-commercial use only. No API.

The licence terms above come from public summaries. Read each licence in full before relying on it for client work.
