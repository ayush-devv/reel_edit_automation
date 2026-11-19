// Brief form ⇄ engine Brief (engine/src/reel/brief.py, extra="forbid": only these keys may be sent).
import type { Brief } from "../api/types";

export const PLATFORMS = [
  { id: "platform.instagram_reels", label: "Instagram Reels" },
  { id: "platform.youtube_shorts", label: "YouTube Shorts" },
  { id: "platform.tiktok", label: "TikTok" },
];
export const GOALS = [
  "goal.watch_through",
  "goal.retention_first_3s",
  "goal.cta_conversion",
  "goal.trust",
  "goal.shares_saves",
  "goal.brand_recall",
  "goal.emotion",
  "goal.energy",
  "goal.clarity",
  "goal.rewatch",
];
export const GENRES = [
  "genre.talking_head",
  "genre.podcast_clip",
  "genre.interview",
  "genre.testimonial",
  "genre.tutorial",
  "genre.product",
  "genre.brand_story",
  "genre.vlog",
  "genre.montage",
  "genre.event_recap",
  "genre.transformation",
];

export interface BriefForm {
  name: string;
  client: string;
  language: "auto" | "en" | "hi" | "hinglish";
  platform: string;
  goal: string;
  audience: string;
  genre: string;
  minLen: string;
  maxLen: string;
  script: "latin" | "devanagari" | "mixed";
  mustKeep: string;
  cta: string;
  products: string;
  banned: string;
  tone: string;
  vocabulary: string;
  notes: string;
  feed45: boolean;
  square: boolean;
}

export const EMPTY_FORM: BriefForm = {
  name: "",
  client: "",
  language: "auto",
  platform: "platform.instagram_reels",
  goal: "",
  audience: "",
  genre: "",
  minLen: "15",
  maxLen: "60",
  script: "latin",
  mustKeep: "",
  cta: "",
  products: "",
  banned: "",
  tone: "",
  vocabulary: "",
  notes: "",
  feed45: false,
  square: false,
};

/** The owner's defaults (Settings → default brief and deliverables, FR-12) applied to an empty form. */
export function formWithDefaults(d: Partial<Brief>, deliverables: string[]): BriefForm {
  const f: BriefForm = { ...EMPTY_FORM };
  if (d.platform) f.platform = d.platform;
  if (d.language === "en" || d.language === "hi" || d.language === "hinglish") f.language = d.language;
  if (d.caption_script) f.script = d.caption_script;
  if (d.goal) f.goal = d.goal;
  if (d.genre_hint) f.genre = d.genre_hint;
  if (d.target_length_s) [f.minLen, f.maxLen] = d.target_length_s.map(String);
  if (d.tone) f.tone = d.tone;
  if (d.cta) f.cta = d.cta;
  f.feed45 = deliverables.includes("feed_4x5");
  f.square = deliverables.includes("square");
  return f;
}

const lines = (s: string) => s.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
const csv = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
const opt = (s: string) => (s.trim() ? s.trim() : null);

export function formErrors(f: BriefForm): Partial<Record<keyof BriefForm, string>> {
  const e: Partial<Record<keyof BriefForm, string>> = {};
  if (!f.name.trim()) e.name = "Give the project a name.";
  const a = Number(f.minLen);
  const b = Number(f.maxLen);
  if (!Number.isFinite(a) || !Number.isFinite(b) || a <= 0 || b <= 0) e.maxLen = "Enter the length range in seconds.";
  else if (a >= b) e.maxLen = "The minimum must be shorter than the maximum.";
  else if (b > 180) e.maxLen = "Reels are at most 180 s.";
  return e;
}

export function toBrief(f: BriefForm): Brief {
  const brief: Brief = {
    project: f.name.trim(),
    client: opt(f.client),
    platform: f.platform,
    goal: opt(f.goal),
    audience: opt(f.audience),
    genre_hint: opt(f.genre),
    target_length_s: [Number(f.minLen), Number(f.maxLen)],
    language: f.language === "auto" ? null : f.language,
    caption_script: f.script,
    must_keep_lines: lines(f.mustKeep),
    cta: opt(f.cta),
    product_names: csv(f.products),
    banned_claims: lines(f.banned),
    tone: opt(f.tone),
    vocabulary: csv(f.vocabulary),
    notes: opt(f.notes),
    deliverables: [...(f.feed45 ? (["feed_4x5"] as const) : []), ...(f.square ? (["square"] as const) : [])],
  };
  return brief;
}

const TEMPLATES_KEY = "reel.briefTemplates";

/** Brief templates are a per-browser convenience (localStorage), minus the project name. */
export function loadTemplates(): Record<string, BriefForm> {
  try {
    return JSON.parse(localStorage.getItem(TEMPLATES_KEY) ?? "{}") as Record<string, BriefForm>;
  } catch {
    return {};
  }
}

export function saveTemplate(name: string, f: BriefForm): void {
  try {
    const all = loadTemplates();
    all[name] = { ...f, name: "" };
    localStorage.setItem(TEMPLATES_KEY, JSON.stringify(all));
  } catch {
    /* storage unavailable: templates are optional */
  }
}
