# ADR-0023: Pinned ffmpeg build and an explicit colour pipeline

- **Status:** Accepted (2026-11-18, council re-review issues #6, #12, #13)
- **Date:** 2026-11-18
- **Deciders:** project owner
- **Amends:** ADR-0015 (mezzanine), ADR-0004 (composite)

## Context
The local ffmpeg 9.0.2 build has no `zscale` (libzimg), no `libplacebo`, no `tonemap_videotoolbox`, and no libass — so HLG/Dolby Vision iPhone footage cannot be tonemapped to SDR correctly. Colour matrices in scale/lut3d/overlay were unspecified (brand colours and text edges shift/fringe). The pro-editor review found colour finishing thin (one LUT, no per-clip correction). The benchmark graph (`tools/bench/base.fg`) uses a design the architecture rejected.

## Decision
1. **Pinned ffmpeg build** for the engine (separate prefix, not the system one) with libzimg, libplacebo, libass, VideoToolbox; recorded in `reel doctor`. Fallback: AVFoundation-based tonemap.
2. **Colour pipeline:** S0 tonemap HDR → bt709 SDR (zscale/libplacebo); explicit `in/out` matrices and ranges on every `scale`, `lut3d`, `overlay`; per-clip exposure + white-balance correction and cross-phone matching **before** the look LUT; LUT applied at partial strength; composite in RGB with straight alpha.
3. **Colour gates:** skin-tone range check on face regions, highlight-clipping check, brand swatch ΔE + text-edge fringe test through the overlay path.
4. **Voice finishing additions** (to ADR-0017 §3): de-reverb, click removal, level match across jump cuts.
5. **Rebuild the benchmark** to the designed graph: per-segment frame-exact cuts from the mezzanine, `fps=` after retime, one sample-accurate audio graph from cumulative output frame boundaries (29.97 fps = 1601.6 samples/frame), two-pass linear loudnorm (verify linear mode) with a limiter before it; measure peak memory with Remotion concurrency capped; per-render check by audio cross-correlation (≤ 20 ms) and perceptual hash of output frame N vs its mapped mezzanine frame. Re-bench on real 4K HEVC HDR.

## Consequences
- **Good:** HDR phone footage handled; brand colours exact; colour quality at pro level.
- **Bad:** custom ffmpeg build to maintain; more perception/QA work.
