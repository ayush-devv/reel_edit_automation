# ADR-0026: Claude Motion as an optional, opt-in fallback for full-frame cards

- **Status:** Accepted (owner decision, 2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Supersedes:** ADR-0025 (Remotion only). Remotion remains the default and the only automatic renderer; Capsule stays out.

## Context
The owner wants Claude Motion kept as an optional fallback. Its constraints (Anthropic artifact type, beta on Team/Enterprise; see social-video-agent ADR-005): a Claude session writes a "film"; MP4 export is **manual in the browser**; exports are **mute and opaque (no alpha)**; **full-frame scenes only**, each ≥ 1 s; fps 24/30/60; vertical 1080x1920 supported; no CLI/API export; using the logo/brand font requires uploading brand files. Not available in the current session's artifact types.

## Decision
- **Default:** every graphic is rendered by Remotion (ADR-0004, 0011, 0017). Claude Motion is never chosen automatically.
- **Opt-in only:** per project or per run (`reel run --motion-film hook_card,end_card` or a `brief` flag), and only if the Claude Code session reports the Motion type is available.
- **Scope:** full-frame scenes only — `hook_card`, `chapter`, `cta`, `quote`, `end_card`. Never captions, lower thirds or partial overlays.
- **Flow (modelled on social-video-agent ADR-005):**
  1. `reel motion spec` writes a film spec (stage size = project output, project fps if 24/30/60, scene durations from the plan, brand colours/fonts, safe zones).
  2. Claude authors the film in Claude Motion.
  3. The run ends **`hold(motion_export_pending)`** — the owner exports the MP4 in the browser.
  4. `reel motion import FILE` probes it as untrusted input, checks size/fps/length (± 1 frame), cuts scenes, records hashes, and swaps them in as full-frame base-layer segments; the matching Remotion element is removed so nothing is drawn twice.
  5. Re-render; normal QA and verdict apply (brand colour/font checks on the imported segments).
- **Fallback the other way:** if Motion is unavailable or the owner doesn't export, the Remotion version of the card is used and the run proceeds.
- **Uploads:** the client's recording is never uploaded; brand files (logo, font) only with an explicit per-project consent flag.

## Consequences
- **Good:** hand-designed, scrub-and-comment hook/end cards available when a client wants something special.
- **Bad:** any run using it is not hands-off (manual export); segments can't be re-rendered without the exported file; full-screen cards hide the speaker for their duration.
- **Revisit when:** Claude Motion offers API/CLI export with alpha → it could become an automatic option.
