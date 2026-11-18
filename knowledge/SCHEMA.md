# Knowledge base schema (v1 drafts)

All research workers write YAML drafts to `knowledge/drafts/<file>.yaml` using exactly these shapes, so drafts merge into one graph (ADR-0027).

**Copyright rule:** paraphrase in your own words. No copied passages; quotes ≤ 15 words and only when essential. Always cite the source.

## 1. Capability catalog entry (`capabilities_*.yaml`)
```yaml
capabilities:
  - id: cap.transform.punch_in          # cap.<category>.<snake_name>, unique
    category: transform                 # cut | trim | transition | transform | speed | color | audio | text | graphics | compositing | effect | export | analysis
    name: Punch-in (digital zoom)
    description: Scale up a shot to tighten framing or add emphasis.   # ≤ 40 words, own words
    parameters:
      - {name: scale, type: float, typical_range: "1.05–1.25", unit: x}
      - {name: duration, type: float, typical_range: "0–0.3 (instant) or 1–4 (slow push)", unit: s}
      - {name: easing, type: enum, values: [linear, ease_in, ease_out, ease_in_out]}
    nle_names: {premiere: "Scale (Effect Controls)", resolve: "Zoom (Inspector)", capcut: "Scale/Keyframe", after_effects: "Scale"}
    renderer_owner: ffmpeg              # ffmpeg | remotion | both | unsupported (see docs/architecture/renderer-split.md)
    notes: "Supersample for slow push-ins to avoid whole-pixel stepping."
    sources:
      - {title: "Premiere Pro User Guide — Motion effects", url: "https://...", locator: "section name"}
```

## 2. Knowledge graph node (`graph_*.yaml`)
```yaml
nodes:
  - id: tech.hook.result_first           # principle.* | tech.* | anti.* | goal.* | genre.* | platform.* | example.*
    type: technique                      # principle | technique | anti_pattern | goal | genre | platform | example
    name: Result-first hook
    summary: Open on the payoff or outcome, then show how it happened.   # ≤ 60 words, own words
    when_to_use: "Transformations, tutorials, product demos where the end state is striking."
    how: ["Find the strongest outcome moment", "Place it in the first 1–2 s", "Caption the promise in ≤ 6 words"]
    parameters: {hook_window_s: "0–2"}
    avoid_when: "The outcome is the only reason to watch to the end (kills payoff)."
    genres: [genre.tutorial, genre.product, genre.transformation]
    goals: [goal.retention_first_3s]
    uses_capabilities: [cap.cut.reorder, cap.text.title]
    conflicts_with: [tech.hook.slow_build]
    requires: []
    evidence_level: practitioner         # platform | study | practitioner | theory | single_opinion
    confidence: medium                   # high | medium | low
    sources:
      - {title: "…", author: "…", url: "https://…", locator: "chapter/section/timestamp"}
```

## Canonical IDs to reuse (add new ones if needed)
- **Genres:** `genre.talking_head`, `genre.testimonial`, `genre.product`, `genre.tutorial`, `genre.vlog`, `genre.montage`, `genre.interview`, `genre.podcast_clip`, `genre.transformation`, `genre.event_recap`, `genre.brand_story`.
- **Goals:** `goal.retention_first_3s`, `goal.watch_through`, `goal.rewatch`, `goal.shares_saves`, `goal.clarity`, `goal.emotion`, `goal.energy`, `goal.trust`, `goal.brand_recall`, `goal.cta_conversion`.
- **Platforms:** `platform.instagram_reels`, `platform.youtube_shorts`, `platform.tiktok`.
