# Experiment 1 — Can Claude see editing problems in frames?

Date: 2026-11-18. Setup: 9 clips cut from `samples/bathroom.mp4` (720x1280); 3 clean, 6 with injected defects. Each judged blind from one contact sheet (12 frames, 0.5 s apart, 240x426 tiles, ~1.7k tokens). Judges: fresh sub-agents on Haiku, Sonnet, Opus; same prompt; no hint of defect types. Answer key: `private/key.json`.

| Clip | Truth | Haiku | Sonnet | Opus |
|---|---|---|---|---|
| E | clean | ok ✓ | ok ✓ | ok ✓ |
| C | clean | ok ✓ | ok ✓ | ok ✓ |
| I | clean | ok ✓ | ok ✓ | ok ✓ |
| B | punch-in crops face out | ✓ | ✓ | ✓ |
| H | opaque graphic over face | ✓ | ✓ | ✓ |
| G | 0.6 s black at 1.8–2.4 s | ✓ (2.0–2.5) | ✓ (2.0) | ✓ (2.0) |
| F | squashed + letterboxed | ✓ letterbox only | ✓ letterbox only | ✓ letterbox **and** squash |
| D | pixelated / low-res | ✗ missed | ✓ | ✓ |
| A | frozen picture 1.6–4.6 s | ✗ missed | ✗ missed | ✓ (2.0–4.5, by comparing with clip I) |
| **Defects caught** | | **4/6** | **5/6** | **6/6** |
| **False alarms** | | 0/3 | 0/3 | 0/3 |

## Conclusions
- Claude can see framing and graphics problems from small contact sheets. All three models caught face crop, graphic over face, black frames and bad aspect; none raised false alarms.
- Opus was the only one to catch the freeze and to name the squash; it did so by comparing two sheets of the same footage.
- Freeze and black frames are cheaper and more reliable in code (`freezedetect`, `blackdetect`) → keep them as deterministic gates (ADR-0006).
- Reviewer persona: **Opus (or Sonnet) for visual review**, Haiku only for cheap pre-screening.

## Limits (do not over-read)
- 9 clips, obvious defects, one source reel. Subtle problems (caption timing, slight headroom errors, weak hook, pacing) were not tested.
- Editorial taste was not tested; that needs raw footage and human comparison.
