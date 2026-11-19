# ADR-0035: Commercial-safe asset sourcing for SFX, music, emoji and motion graphics

- **Status:** Accepted (made overnight under the owner's delegation, 2026-11-19; owner to confirm)
- **Date:** 2026-11-19
- **Deciders:** Claude (delegated by the project owner)
- **Relates to:** ADR-0011 (asset libraries), ADR-0018 (NLE package), docs/research/gap-analysis.md

## Context
The SFX and music libraries were empty, so the Editor could never use sound design or a music bed. Motion graphics needed emoji art and animation recipes. Reels are delivered to paying clients, so every asset must be safe for commercial use, without surprise obligations on the client's post.

Research (2026-11-19, see gap-analysis §2, §2c, §4) found:
- **No music source** is both scriptable and attribution-free.
- **Sonniss GDC bundles** are excellent and commercial-use, but their licence heading says "NO AI TRAINING OR USAGE".
- **Freesound API** commercial use is negotiated case by case.
- **Pixabay and Mixkit** forbid scripted downloads.
- **OpenMoji** is CC BY-SA, so ShareAlike would reach the client's reel.
- **GSAP's "No Charge" licence** has clauses about no-code animation tools and paid end users.
- **Apple's emoji art** is not licensed for client videos.

## Decision
1. **SFX: procedural first.** 47 sounds are synthesised by us with ffmpeg (owned, no licence; deterministic, re-created by `reel assets fetch`). The other 205 are **Kenney CC0** packs. **Sonniss stays off** (`--include-sonniss` only) until the owner gets a legal read on the AI clause. Sonniss source files would never be delivered, only renders.
2. **Music: Incompetech (Kevin MacLeod, CC BY 4.0),** 33 tracks.
   - Each track's exact attribution text is stored.
   - The delivery package writes `CREDITS.txt`, and a README row tells the owner to paste it into the post caption whenever a credited track is used.
   - **No ShareAlike or NonCommercial source is ever indexed.**
3. **Provenance on every entry:** source, licence id and URL, attribution text, download URL, date, SHA-256. Records live in `assets/licenses/`. Audio is never committed; indexes are committed. The library offers only files present on disk.
4. **Emoji: Noto Emoji SVGs** (Apache-2.0, via `@iconify-json/noto`), rendered as images. Animated Noto (CC BY) and colour fonts are not used.
5. **Motion graphics:** bang-motion (MIT) timing numbers and design rules, re-implemented with Remotion `interpolate`/`Easing`. **No GSAP.**
6. **Voice enhancement:** the DeepFilterNet3 release binary (MIT/Apache-2.0), pinned by SHA-256.

## Options considered
| Option | Cost to the client | Risk | Chosen |
|---|---|---|---|
| Procedural + Kenney CC0 + Incompetech with credits | a credit line when music is used | low | ✅ |
| Add Sonniss by default | none | licence AI clause unclear | no (opt-in after legal read) |
| No music until a paid library | none | reels lack a bed | no |
| Paid library (Epidemic, Artlist) | subscription | low; per-channel licensing | later, if a client needs credit-free music |

## Consequences
- **Good:**
  - every asset is commercially safe today and traceable;
  - the Editor finally has sound and music to work with;
  - credits are automatic.
- **Bad:**
  - the CC BY music needs a credit on every post that uses it (some clients will not want this; offer "no music" or a paid library);
  - the procedural SFX were checked by numbers and spectrograms, not by ear yet;
  - booms are thin on phone speakers.
- **Owner actions:**
  - confirm this ADR;
  - decide on Sonniss after a legal read;
  - listen to a sample of the procedural SFX (`assets/sfx/procedural/`).
