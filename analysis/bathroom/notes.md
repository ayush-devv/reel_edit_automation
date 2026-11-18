# Sample analysis: samples/bathroom.mp4

Source file: `From Klickpin.com- 13 Practical bathroom storage solutions...mp4` (copied to `samples/bathroom.mp4`, original untouched).
Analysed: 2026-11-18.

## What it actually is

The filename is downloader metadata and is wrong. The video is a **finished, professionally edited brand testimonial reel**, not a raw reel and not about bathroom storage.

- Speaker: the founder of a maternity apparel brand ("DearMa", per on-screen text), talking about the creative agency that made her brand ("Wortham", per on-screen text and end card).
- Structure: hook line → intro (name + title card) → praise of the team with designer b-roll → USP line → fast product/brand montage → thank-you → credits end card → agency logo + URL.
- Speech in English (on-screen text matches speech); music bed underneath.

## Technical

| Field | Value |
|---|---|
| Duration | 73.73 s |
| Video | H.264 720x1280, 25 fps, 1843 frames |
| Audio | AAC stereo 44.1 kHz |
| Loudness | -13.7 LUFS integrated, LRA 6.9 LU |
| True peak | **+0.6 dBFS (clipping)** |
| Silence (< -40 dB, ≥ 0.4 s) | none |
| Black | 9.32–10.04 s (0.72 s, a dip transition) and 72.68–73.68 s (end) |

## Edit style vector (measured)

| Metric | Value | Our playbook baseline |
|---|---|---|
| Cuts detected (ffmpeg scdet, threshold 8) | 44 | – |
| Cuts per minute | **35.8** | ~25 (Reels/Shorts median) |
| Median shot | **1.08 s** | ~2.3 s |
| Mean shot | 1.64 s | – |
| Shot-length CV | 0.95 (very varied rhythm) | – |
| Shots under 1 s | 22 of 45 | – |
| First cut | 4.40 s | median 2.6 s |
| Longest shot | 8.64 s at 38.28 s (talking head carried by kinetic text) | ≤ 4 s unchanged framing |
| Text on screen at 0.3 s | yes ("Guys,") | 58% of top reels |
| Fast montage | 53–59 s: ten shots of 0.56–0.80 s | – |

Some 0.3–0.4 s "cuts" may be text-animation flashes rather than real cuts; verify with a second detector (TransNetV2) later.

## Craft observations (from the 2 s contact sheet)

- **Kinetic typography, not standard captions:** 1–4 words, mixed sizes and weights, key word enlarged ("Business", "Wortham.", "Creative", "Over Deliver."), placed beside the face, not bottom-centre.
- **Text continues over b-roll** so the line never stops ("This is a Team" over tablet shots).
- **B-roll illustrates the words:** designers sketching the logo while she says "team", "creative people".
- **Grade:** warm orange interview vs teal/green b-roll; a consistent two-tone look.
- **Social UI mock-up:** a fake YouTube subscribe bar at ~32 s.
- **Long talking shot is kept alive by text**, not cuts (38–47 s).
- **Ending:** credits card, then an agency logo flash, then the URL on black.

## What this sample is good for

- **Reference reel** for style imitation (style vector above) and for the "can Claude see editing quality" test.
- **Not** a raw reel: it cannot test cutting, filler removal or hook selection, because the edit is already done.
