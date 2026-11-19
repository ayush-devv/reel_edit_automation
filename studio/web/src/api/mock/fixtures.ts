// Realistic fixture data for mock mode (?mock=1). Shapes follow docs/product/studio-api.md exactly (the real API's).
import {
  STAGES,
  type BrandEntry,
  type Costs,
  type Decision,
  type Gate,
  type Health,
  type Lab,
  type Libraries,
  type PackageListing,
  type Project,
  type Settings,
  type Stage,
  type StageStatus,
  type TimelineView,
} from "../types";
import { TYPICAL_STAGE_S } from "../../lib/status";

const NOW = Date.now();
const iso = (minsAgo: number) => new Date(NOW - minsAgo * 60_000).toISOString();
const sec = (minsAgo: number) => Math.round((NOW - minsAgo * 60_000) / 1000);


const SKIPPED_BY_DEFAULT = new Set(["broll", "reference"]);

/** Stages up to `current` done, `current` in `status`, the rest pending. Like the engine, finished stages keep only `finished`. */
export function makeStages(current: string | null, status: StageStatus, endedMinsAgo = 0, error?: string): Stage[] {
  const idx = current ? STAGES.indexOf(current as (typeof STAGES)[number]) : STAGES.length;
  let t = sec(endedMinsAgo) - STAGES.slice(0, idx + 1).reduce((a, s) => a + TYPICAL_STAGE_S[s], 0);
  return STAGES.map((name, i) => {
    const dur = TYPICAL_STAGE_S[name];
    if (i < idx) {
      const skipped = SKIPPED_BY_DEFAULT.has(name);
      const st: Stage = { name, status: skipped ? "skipped" : "done", started: null, finished: t + (skipped ? 0 : dur), meta: {} };
      if (!skipped) t += dur;
      return st;
    }
    if (i === idx) return { name, status, started: t, finished: status === "failed" ? t + 12 : null, meta: {}, ...(error ? { error } : {}) };
    return { name, status: "pending", started: null, finished: null, meta: {} };
  });
}

const STORY_DECISIONS = (t: number): Decision[] => [
  {
    at: t,
    kind: "story",
    title: "Hook: “I almost gave up on my skin — then I tried one thing.”",
    detail: "Opens on a confession plus a promise: it names the pain in the first 2 seconds and leaves a question open, which keeps viewers past 3 s.",
    knowledge: ["technique.hook_confession", "goal.retention_first_3s"],
    cost_usd: 0.142,
  },
  {
    at: t + 2,
    kind: "story",
    title: "Kept 6 lines in this order: hook → setup → proof → proof → payoff → CTA",
    detail: "Dropped the 40 s intro about her routine (no new information) and the second product tangent. Proof lines are the before/after and the dermatologist quote.",
    knowledge: ["genre.testimonial", "technique.cut_the_preamble"],
    cost_usd: 0.031,
  },
];

const FINISH_DECISIONS = (t: number): Decision[] => [
  {
    at: t,
    kind: "finish",
    title: "Captions: editorial kinetic, emphasis on 7 words",
    detail: "Premium, conversational testimonial; title-case words beside the face read as calm and trustworthy. Brand pink as the emphasis colour.",
    knowledge: ["caption.editorial_kinetic", "genre.testimonial"],
    cost_usd: 0.118,
  },
  {
    at: t + 1,
    kind: "finish",
    title: "Look: warm at 0.45, light grain 0.18",
    detail: "Warm skin tones suit a skincare testimonial; strength kept under 0.5 so the product colour stays true.",
    knowledge: ["look.warm"],
  },
  {
    at: t + 2,
    kind: "finish",
    title: "2 punch-ins, a soft whoosh on the reveal, music bed at −20 dB",
    detail: "Punch-in on “ten days later” to land the turn, and on the CTA. Music ducks 14 dB under speech.",
    knowledge: ["technique.punch_in_on_turn", "audio.duck_under_speech"],
  },
];

const REVIEW_DECISIONS = (t: number, verdict: "hold" | "sendable"): Decision[] => [
  {
    at: t,
    kind: "qa",
    title: verdict === "hold" ? "Quality checks: 1 warning, 1 unconfirmed word" : "Quality checks: all passed",
    detail: verdict === "hold" ? "Caption word 42 “Dioma” is not in the vocabulary and the ASR confidence is 0.41." : "Loudness −14.1 LUFS, captions inside the safe zone, no black frames.",
    knowledge: [],
  },
  {
    at: t + 30,
    kind: "review",
    title: verdict === "hold" ? "Reviewer: hold — brand name may be misspelt" : "Reviewer: sendable",
    detail: verdict === "hold" ? "The brand name appears as “Dioma” in the captions; the brief spells it “DearMa”." : "Clear story, strong hook, CTA lands on the final line.",
    knowledge: [],
    cost_usd: 0.094,
  },
];

const BRIEF_DEARMA = {
  project: "Glow serum testimonial",
  client: "DearMa Skincare",
  platform: "platform.instagram_reels",
  goal: "goal.trust",
  genre_hint: "genre.testimonial",
  target_length_s: [25, 45],
  language: "hinglish",
  caption_script: "latin",
  must_keep_lines: ["ten days later my skin felt calm"],
  cta: "Link in bio",
  product_names: ["DearMa", "Glow Serum"],
  banned_claims: ["cures acne"],
  tone: "warm, honest",
  vocabulary: ["DearMa", "niacinamide"],
  deliverables: ["feed_4x5", "square"],
};

function base(id: string, name: string, client: string, minsAgo: number) {
  return {
    id,
    name,
    client,
    created: iso(minsAgo + 60),
    updated: iso(minsAgo),
    thumb: null,
    brief: { ...BRIEF_DEARMA, project: name, client },
    brand: client === "DearMa Skincare" ? "dearma" : null,
    review: null,
    verdict_detail: null,
    proof: [],
    media: { sheets: [], cut_strips: [], variants: [] },
    versions: [],
    delivered_at: null,
    calls: [],
    platform_notes: [],
    eta_s: null,
  };
}

const gate = (name: string, status: Gate["status"], detail: string): Gate => ({ name, status, detail, measured: {} });

export function makeProjects(): Project[] {
  const hold: Project = {
    ...base("glow-serum-testimonial", "Glow serum testimonial", "DearMa Skincare", 18),
    status: "hold",
    stage: null,
    progress: 1,
    duration_s: 34.2,
    cost_usd: 0.61,
    verdict: "hold",
    needs_attention: ["1 proof word", "1 reviewer note"],
    stages: makeStages(null, "done", 18),
    decisions: [...STORY_DECISIONS(sec(30)), ...FINISH_DECISIONS(sec(28)), ...REVIEW_DECISIONS(sec(19), "hold")],
    verdict_detail: {
      verdict: "hold",
      reasons: ["proof_words: 1 unconfirmed caption word(s): 0:12.40 “Dioma” (unconfirmed name)", "Reviewer: the brand name may be misspelt in the captions."],
      warnings: ["reading_speed: max 21.4 chars/s (limit 20)"],
      gates: [
        gate("frame_count", "pass", "1026/1026 frames"),
        gate("loudness", "pass", "-14.2 LUFS, -1.4 dBTP"),
        gate("proof_words", "fail", "1 unconfirmed caption word(s): 0:12.40 “Dioma” (unconfirmed name)"),
        gate("safe_zone", "pass", "0 page(s) outside the safe zone"),
        gate("black", "pass", "0 black stretch(es)"),
        gate("reading_speed", "warn", "max 21.4 chars/s (limit 20)"),
      ],
      plain: [
        { gate: "proof_words", status: "fail", title: "Caption words to check", sentence: "1 caption word(s) the speech recogniser was unsure of — confirm or correct them.", at: ["0:12.40"], detail: "1 unconfirmed caption word(s)" },
        { gate: "reading_speed", status: "warn", title: "Reading speed", sentence: "Captions go by faster than people can read in one stretch.", at: [], detail: "max 21.4 chars/s (limit 20)" },
      ],
    },
    proof: [
      { i: 42, text: "Dioma", suggestion: "DearMa", at: "0:12.40", frame: 372, why: "unconfirmed name" },
      { i: 77, text: "niacinamide", suggestion: null, at: "0:21.08", frame: 632, why: "low confidence" },
    ],
    review: {
      summary: "Strong confession hook and a clean before/after arc. Hold only for the brand spelling.",
      sendable: false,
      strengths: ["The confession hook names the pain in the first 2 s.", "Clean before/after arc."],
      issues: [
        { at: "0:12.4", category: "captions", severity: "major", text: "Brand name shows as “Dioma”.", fix: "Fix the caption word to “DearMa”." },
        { at: "0:03.1, 0:03.4", category: "pacing", severity: "minor", text: "Hook title overlaps the first caption page by 0.3 s.", fix: "Shorten the hook title or start captions 0.3 s later." },
      ],
    },
    media: { final: "render/final.mp4", cover: "cover.jpg", sheets: ["qa/sheets/final_01.png"], cut_strips: [], variants: [] },
    versions: [
      { n: 1, created: iso(19), label: "Original edit", reply: "", cost_usd: null, final: "versions/1/final.mp4" },
      { n: 2, created: iso(18), label: "Revision: “make the hook snappier”", reply: "Trimmed 0.8 s of the opening breath and moved the hook title up.", cost_usd: 0.09, final: "versions/2/final.mp4" },
    ],
  };

  const sendable: Project = {
    ...base("founder-story-cut-1", "Founder story — cut 1", "Northwind Coffee", 95),
    status: "sendable",
    stage: null,
    progress: 1,
    duration_s: 41.6,
    cost_usd: 0.73,
    verdict: "sendable",
    needs_attention: [],
    stages: makeStages(null, "done", 95),
    decisions: [...STORY_DECISIONS(sec(110)), ...FINISH_DECISIONS(sec(108)), ...REVIEW_DECISIONS(sec(97), "sendable")],
    verdict_detail: {
      verdict: "sendable",
      reasons: [],
      warnings: [],
      gates: [
        gate("frame_count", "pass", "1248/1248 frames"),
        gate("loudness", "pass", "-14.0 LUFS, -1.6 dBTP"),
        gate("proof_words", "pass", "all caption words confirmed"),
        gate("safe_zone", "pass", "0 page(s) outside the safe zone"),
        gate("brief", "pass", "must-keep, banned claims, CTA ok"),
      ],
    },
    review: { summary: "Clear founder arc, warm look suits the café footage. Ready to send.", sendable: true, strengths: ["Clear founder arc."], issues: [] },
    media: { final: "render/final.mp4", cover: "cover.jpg", sheets: [], cut_strips: [], variants: [] },
    versions: [{ n: 1, created: iso(97), label: "Original edit", reply: "", cost_usd: null, final: "render/final.mp4" }],
  };

  const delivered: Project = {
    ...sendable,
    id: "gym-launch-promo",
    name: "Gym launch promo",
    client: "IronHaus Fitness",
    created: iso(60 * 50),
    updated: iso(60 * 26),
    delivered_at: iso(60 * 26),
    duration_s: 27.9,
    cost_usd: 0.58,
    brand: null,
  };

  const failed: Project = {
    ...base("podcast-ep12-clip", "Podcast ep. 12 — money clip", "The Rupee Pod", 7),
    status: "failed",
    stage: "render",
    progress: 0.6,
    duration_s: null,
    cost_usd: 0.38,
    verdict: null,
    needs_attention: ["failed: render"],
    stages: makeStages("render", "failed", 7, "The source file was moved or deleted (raw/ep12_cam_a.mov). Put it back, then press Retry."),
    decisions: [...STORY_DECISIONS(sec(14)), ...FINISH_DECISIONS(sec(12))],
  };

  const running = (id: string, name: string, client: string, stage: string, mins: number, costs: number, dec: Decision[]): Project => ({
    ...base(id, name, client, mins),
    status: "running",
    stage,
    progress: STAGES.indexOf(stage as (typeof STAGES)[number]) / STAGES.length,
    duration_s: null,
    cost_usd: costs,
    verdict: null,
    needs_attention: [],
    stages: makeStages(stage, "running", 0),
    decisions: dec,
  });

  const r1 = running("cafe-opening-reel", "Café opening reel", "Northwind Coffee", "story", 2, 0.04, []);
  const r2 = running("tutorial-lip-tint", "Lip tint tutorial", "DearMa Skincare", "render", 1, 0.44, [...STORY_DECISIONS(sec(9)), ...FINISH_DECISIONS(sec(7))]);
  const r3 = running("coach-qna-short", "Coach Q&A short", "Priya Mehta Coaching", "perception", 1, 0, []);

  const queued: Project = {
    ...base("dentist-faq-1", "Dentist FAQ #1", "SmileCare Clinic", 0),
    status: "queued",
    stage: null,
    progress: 0,
    duration_s: null,
    cost_usd: 0,
    verdict: null,
    needs_attention: [],
    stages: STAGES.map((name) => ({ name, status: "queued" as const, started: null, finished: null, meta: {} })),
    decisions: [],
  };

  return [delivered, r1, sendable, failed, queued, hold, r2, r3];
}

export function makeTimeline(): TimelineView {
  const fps = 30;
  const items = [
    { id: "k01", beat: "hook", text: "I almost gave up on my skin — then I tried one thing.", dur: 3.4 },
    { id: "k02", beat: "setup", text: "Two years of breakouts, nothing calmed it down.", dur: 4.6 },
    { id: "k03", beat: "proof", text: "My dermatologist said: keep it simple, niacinamide, every night.", dur: 6.2 },
    { id: "k04", beat: "proof", text: "Ten days later my skin felt calm.", dur: 5.4 },
    { id: "k05", beat: "payoff", text: "This is the only serum I've finished twice. DearMa Glow Serum.", dur: 8.8 },
    { id: "k06", beat: "cta", text: "Link in bio if you want to try it.", dur: 5.8 },
  ];
  let f = 0;
  let w = 0;
  const video = items.map((it, n) => {
    const dur_f = Math.round(it.dur * fps);
    const words = it.text.split(" ").length;
    const clip = {
      id: `v_${it.id}`,
      at_f: f,
      dur_f,
      scale: n === 3 || n === 5 ? [{ f: 18, v: 1 }, { f: 24, v: 1.18 }] : [],
      src: { item: it.id, words: [w, w + words - 1] },
    };
    f += dur_f;
    w += words;
    return clip;
  });
  const duration_f = f;
  const pages: { start_f: number; end_f: number; words: { i: number; text: string; emph: boolean }[] }[] = [];
  let wi = 0;
  for (const clip of video) {
    const it = items.find((x) => x.id === clip.src.item)!;
    const ws = it.text.split(" ");
    const per = clip.dur_f / Math.ceil(ws.length / 4);
    for (let p = 0; p < ws.length; p += 4) {
      const start_f = Math.round(clip.at_f + (p / 4) * per);
      pages.push({
        start_f,
        end_f: Math.round(start_f + per),
        words: ws.slice(p, p + 4).map((t) => ({ i: wi++, text: t, emph: /calm|DearMa|niacinamide|one/.test(t) })),
      });
    }
  }
  const at = (s: number) => Math.round(s * fps);
  return {
    timeline: {
      fps: "30/1",
      width: 1080,
      height: 1920,
      duration_f,
      video,
      audio: [
        { id: "a_voice", at_f: 0, dur_f: duration_f, role: "voice", gain_db: 0 },
        { id: "music", at_f: 0, dur_f: duration_f, role: "music", gain_db: -20 },
        { id: "sfx1", at_f: at(14.2), dur_f: at(0.8), role: "sfx", gain_db: -12 },
        { id: "sfx2", at_f: at(28.4), dur_f: at(0.5), role: "sfx", gain_db: -14 },
      ],
      grade: { look: "warm", strength: 0.45, grain: 0.18, vignette: 0.2 },
      captions: { family: "editorial_kinetic", pages },
      titles: [{ id: "t_hook", text: "One thing changed my skin", start_f: 0, end_f: at(3.4), role: "hook" }],
      pips: [{ id: "b1", start_f: at(8.6), end_f: at(12.4) }],
      effects: [{ id: "fx1", type: "light_leak", start_f: at(14.2), end_f: at(15.4) }],
      graphics: [
        { id: "g1", kind: "keyword_card", start_f: at(9.5), end_f: at(11.5), text: "niacinamide" },
        { id: "g2", kind: "cta_card", start_f: at(28.4), end_f: duration_f, text: "Link in bio" },
      ],
    },
    reasons: {
      k01: "Hook: a confession plus a promise names the pain in 2 s and leaves a question open.",
      k02: "Setup: two years of struggle makes the result matter; trimmed to one sentence.",
      k03: "Proof: an expert’s advice adds trust; keeps the product category without a hard sell.",
      k04: "Must-keep line from the brief, and the emotional turn of the story.",
      k05: "Payoff: “finished twice” is concrete social proof; the product name lands here.",
      k06: "CTA from the brief, kept short and spoken by her, not a card only.",
      v_k04: "Punch-in 1.18× on “ten days later” to land the turn.",
      v_k06: "Punch-in on the CTA to re-engage before the loop.",
      t_hook: "Hook title restates the promise for viewers watching muted.",
      b1: "B-roll of the serum bottle while she names the routine (pip, top right).",
      fx1: "Light leak on the reveal: warm and soft, matches the look.",
      g1: "Keyword card for the ingredient she names.",
      g2: "CTA card over the last line, from the brief.",
      music: "Calm acoustic bed (92 bpm); ducks 14 dB under speech.",
      sfx1: "Soft whoosh into the ‘ten days later’ turn.",
      sfx2: "Gentle pop as the CTA card appears.",
      grade: "Warm look at 0.45: friendly skin, product colour stays true.",
      captions: "Editorial kinetic: premium, conversational; emphasis on the 7 words that carry the story.",
      a_voice: "Dialogue, levelled to −16 LUFS before the mix.",
    },
    story: Object.fromEntries(items.map((it) => [it.id, { beat: it.beat, text: it.text }])),
    adjust: {
      caption_family: "editorial_kinetic",
      caption_tokens: { emph_color: "#FF5FA2" },
      look: "warm",
      look_strength: 0.45,
      grain: 0.18,
      vignette: 0.2,
      music_track: "acoustic_morning",
      music_gain_db: -20,
      max_pause_ms: null,
      sfx: 2,
      punch_ins: 2,
    },
  };
}

export const HEALTH: Health = {
  engine: "ok",
  version: "0.11.0",
  toolchain_ok: false,
  tools: [
    { name: "pinned ffmpeg", ok: true, detail: "ffmpeg 9.0.2", required: true },
    { name: "filter zscale", ok: true, detail: "ok", required: true },
    { name: "renderer node_modules", ok: false, detail: "Remotion packages missing — run: cd renderer && npm ci", required: true },
    { name: "claude CLI", ok: true, detail: "Claude Code logged in", required: true },
    { name: "pexels key", ok: false, detail: "not set (stock b-roll search off)", required: false },
  ],
  claude: true,
  disk_free_gb: 212,
  jobs: { running: 3, queued: 1, limit: 3 },
  memory_gb: { used: 9.4, budget: 12, system: { total: 16, available: 5.2 } },
  projects_root: "~/Reels/projects",
};

export const LIBRARIES: Libraries = {
  sfx: [
    { id: "whoosh_soft_01", category: "whoosh", duration_ms: 820, source: "Sonniss GDC 2024", license: "Royalty-free commercial use", file: null },
    { id: "whoosh_fast_02", category: "whoosh", duration_ms: 540, source: "Sonniss GDC 2024", license: "Royalty-free commercial use", file: null },
    { id: "pop_bubble_01", category: "pop", duration_ms: 310, source: "Sonniss GDC 2024", license: "Royalty-free commercial use", file: null },
    { id: "riser_short_01", category: "riser", duration_ms: 2100, source: "Self-recorded", license: "Owned", file: null },
    { id: "click_ui_03", category: "ui", duration_ms: 120, source: "Kenney UI Audio", license: "CC0", file: null },
    { id: "impact_low_01", category: "impact", duration_ms: 1400, source: "Sonniss GDC 2024", license: "Royalty-free commercial use", file: null },
  ],
  music: [
    { id: "acoustic_morning", title: "Acoustic Morning", mood: "calm, warm", bpm: 92, duration_ms: 148000, source: "Uppbeat", license: "Uppbeat free (credit)", attribution: "Music: Acoustic Morning — Uppbeat" },
    { id: "neon_drive", title: "Neon Drive", mood: "energetic", bpm: 124, duration_ms: 132000, source: "Self-produced", license: "Owned", attribution: null },
    { id: "soft_piano_02", title: "Soft Piano II", mood: "emotional", bpm: 70, duration_ms: 176000, source: "Free Music Archive", license: "CC BY 4.0", attribution: "Soft Piano II by K. Ito (CC BY 4.0)" },
  ],
  broll: [
    { id: "serum_bottle_closeup", description: "Hand turns a glass serum bottle on a marble counter, soft window light.", shot: "close-up", duration_ms: 6200, source: "Client upload", license: "Client-owned", tags: [], file: null },
    { id: "cafe_pour_overhead", description: "Overhead pour-over coffee, steam rising.", shot: "overhead", duration_ms: 8400, source: "Pexels", license: "Pexels licence", tags: [], file: null },
  ],
  caption_families: [
    { id: "bold_pop", for: ["genre.talking_head", "genre.podcast_clip", "genre.tutorial"], mood: "high energy, hooks", max_words: 4, tokens: { emph_color: "#FFD400" } },
    { id: "clean_phrase", for: ["genre.tutorial", "genre.product"], mood: "clear, explanatory", max_words: 4, tokens: { emph_color: "#FFD400" } },
    { id: "editorial_kinetic", for: ["genre.testimonial", "genre.brand_story", "genre.interview"], mood: "premium, conversational", max_words: 4, tokens: { emph_color: "#FFD400" } },
    { id: "minimal_calm", for: ["genre.vlog", "genre.montage", "genre.brand_story"], mood: "aesthetic, emotional", max_words: 4, tokens: { emph_color: "#FFD400" } },
    { id: "speaker_coded", for: ["genre.podcast_clip", "genre.interview"], mood: "multi-speaker clarity", max_words: 4, tokens: { emph_color: "#FFD400" } },
  ],
  unreadable: [],
};

export const BRANDS: BrandEntry[] = [
  {
    id: "dearma",
    brand: {
      client: "DearMa Skincare",
      fonts: { heading: "Plus Jakarta Sans" },
      colors: { primary: "#2A1B3D", secondary: "#F7E6EC", accent: "#FF5FA2", text: "#FFFFFF" },
      logo: "brands/dearma/logo.png",
      caption_family: "editorial_kinetic",
      caption_tokens: {},
      look: "warm",
      end_card: null,
      cta_style: "bar",
    },
  },
  {
    id: "northwind",
    brand: {
      client: "Northwind Coffee",
      fonts: { heading: "Inter" },
      colors: { primary: "#3B2416", accent: "#E8A33D", text: "#FFF8EE" },
      logo: null,
      caption_family: null,
      caption_tokens: {},
      look: "film",
    },
  },
];

export const LAB: Lab = {
  gold: { pairs: 18, tuning: 12, holdout: 6, hinglish: 7 },
  release_locked: true,
  lock_reason: "Held-out pairs are scored only by a release check (ADR-0031). Last release check 9 days ago; the next is allowed after 3 more tuning runs.",
  calibration: {
    agreement: 0.78,
    n_labels: 23,
    trusted: false,
    gates: [
      { name: "black", mode: "warn", false_alarm_rate: 0.333, catch_rate: 1, promote_to_block: false },
      { name: "frozen", mode: "warn", false_alarm_rate: 0, catch_rate: 1, promote_to_block: true },
      { name: "loudness", mode: "block", false_alarm_rate: null, catch_rate: 1, promote_to_block: false },
      { name: "reading_speed", mode: "warn", false_alarm_rate: 0.21, catch_rate: null, promote_to_block: false },
    ],
    rule: "block when false alarms ≤ 0 on the pro finals and catch rate ≥ 90%",
  },
  improve_history: [
    { at: null, round: 0, change: "edit technique.punch_in_on_turn", outcome: "accepted", gain: 0.031, reason: null },
    { at: null, round: 1, change: "edit caption.bold_pop", outcome: "rejected", gain: -0.004, reason: "mean gain -0.40 < δ_min 1.00" },
    { at: null, round: 2, change: "add technique.spoken_hook", outcome: "invalid", gain: null, reason: "unknown node goal.retention" },
  ],
  runs: [
    { id: "run-0912", at: iso(60 * 24 * 40), split: "tuning", primary: 0.61, families: { story: 0.58, captions: 0.71, style: 0.55, gates: 0.83, reviewer: 0.49 }, vetoed: 0, reels: [] },
    { id: "run-0926", at: iso(60 * 24 * 26), split: "tuning", primary: 0.64, families: { story: 0.62, captions: 0.72, style: 0.58, gates: 0.85, reviewer: 0.52 }, vetoed: 0, reels: [] },
    { id: "run-1010", at: iso(60 * 24 * 12), split: "holdout", primary: 0.66, families: { story: 0.63, captions: 0.74, style: 0.6, gates: 0.88, reviewer: 0.55 }, vetoed: 0, reels: [] },
    { id: "run-1104", at: iso(60 * 24 * 6), split: "tuning", primary: 0.69, families: { story: 0.68, captions: 0.76, style: 0.61, gates: 0.9, reviewer: 0.58 }, vetoed: 0, reels: [] },
    { id: "run-1116", at: iso(60 * 24 * 2), split: "tuning", primary: 0.72, families: { story: 0.71, captions: 0.79, style: 0.63, gates: 0.91, reviewer: 0.62 }, vetoed: 0, reels: [] },
  ],
  gold_pairs: [
    { id: "gold-01-testimonial", split: "tuning", language: "en", source: "@freelance_pro" },
    { id: "gold-02-podcast-hinglish", split: "tuning", language: "hinglish", source: "@freelance_pro" },
    { id: "gold-03-tutorial", split: "tuning", language: "en", source: "@cc_by_channel" },
    { id: "gold-04-vlog-hi", split: "tuning", language: "hi", source: "@freelance_pro" },
    { id: "gold-13-holdout", split: "holdout", language: "hinglish", source: "@freelance_pro" },
    { id: "gold-14-holdout", split: "holdout", language: "en", source: "@freelance_pro" },
    { id: "gold-15-holdout", split: "holdout", language: "en", source: "@freelance_pro" },
  ],
};

export const COSTS: Costs = {
  total_usd: 14.82,
  calls: 41,
  by_project: [
    { id: "glow-serum-testimonial", usd: 0.61 },
    { id: "founder-story-cut-1", usd: 0.73 },
    { id: "gym-launch-promo", usd: 0.58 },
    { id: "podcast-ep12-clip", usd: 0.38 },
    { id: "tutorial-lip-tint", usd: 0.44 },
  ],
  // Like the API: every day of the 30-day window, oldest first, zeros included.
  by_day: Array.from({ length: 30 }, (_, i) => ({
    date: new Date(NOW - (29 - i) * 86_400_000).toISOString().slice(0, 10),
    usd: i < 16 ? 0 : [0.4, 1.1, 0.0, 0.7, 1.9, 0.6, 0.2, 1.4, 2.1, 0.9, 0.0, 1.2, 1.6, 0.8][i - 16],
  })),
};

export const SETTINGS: Settings = {
  max_jobs: 3,
  projects_dir: "~/Reels/projects",
  default_brief: { platform: "platform.instagram_reels", language: "hinglish", caption_script: "latin", target_length_s: [15, 60] },
  default_deliverables: ["feed_4x5"],
  pexels_key_set: false,
};

export const PACKAGE: PackageListing = {
  files: [
    { path: "export/package/reel.mp4", label: "Final reel · 9:16 · 1080×1920", kind: "final", bytes: 48_200_000, thumb: "cover.jpg" },
    { path: "export/variants/reel_feed_4x5.mp4", label: "Feed · 4:5 · 1080×1350", kind: "variant", bytes: 41_900_000, thumb: null },
    { path: "export/variants/reel_square.mp4", label: "Square · 1:1 · 1080×1080", kind: "variant", bytes: 37_400_000, thumb: null },
    { path: "export/review/review.mp4", label: "Review copy · small, watermarked", kind: "review_copy", bytes: 6_100_000, thumb: null },
    { path: "export/package/README.md", label: "Read me", kind: "other", bytes: 1_300, thumb: null },
    { path: "export/package/captions.srt", label: "Captions · SRT", kind: "captions", bytes: 4_100, thumb: null },
    { path: "export/package/edit_list.md", label: "Edit list with reasons", kind: "edit_list", bytes: 9_800, thumb: null },
    { path: "export/package/overlay.mov", label: "Overlay with transparency (captions, titles, graphics)", kind: "overlay", bytes: 212_000_000, thumb: null },
    { path: "export/package/stems/", label: "Audio stems · dialogue, music, effects", kind: "stems", bytes: 31_000_000, thumb: null },
    { path: "export/package/timeline.fcpxml", label: "Final Cut Pro timeline", kind: "timeline", bytes: 182_000, thumb: null },
    { path: "export/package/timeline.otio", label: "OpenTimelineIO timeline", kind: "timeline", bytes: 96_000, thumb: null },
  ],
  warnings: ["Music “Acoustic Morning” needs a credit line in the post: “Music: Acoustic Morning — Uppbeat”."],
};
