// Types for the Reel Studio local API — docs/product/studio-api.md (v1 + "v1.1 additions (web app)").

export const STAGES = [
  "ingest",
  "mezzanine",
  "perception",
  "tables",
  "broll",
  "reference",
  "story",
  "finish",
  "compile",
  "render",
  "overlay",
  "composite",
  "qa",
  "package",
  "variants",
] as const;
export type StageName = (typeof STAGES)[number];

export type StageStatus = "pending" | "queued" | "running" | "done" | "failed" | "skipped";
export type ProjectStatus = "draft" | "queued" | "running" | "sendable" | "hold" | "failed";
export type Verdict = "sendable" | "hold";

export interface ProjectSummary {
  id: string;
  name: string;
  created: string;
  updated: string;
  status: ProjectStatus;
  stage: string | null;
  progress: number;
  duration_s: number | null;
  cost_usd: number;
  verdict: Verdict | null;
  needs_attention: string[];
  thumb: string | null;
  // v1.1 additions (optional so a v1 API still type-checks at runtime)
  client?: string | null;
  delivered_at?: string | null;
}

export interface Stage {
  name: string;
  status: StageStatus;
  started: number | null;
  finished: number | null;
  meta: Record<string, unknown>;
  error?: string;
}

export interface Decision {
  at: number;
  kind: "story" | "finish" | "review" | "revision" | "qa";
  title: string;
  detail: string;
  knowledge: string[];
  // v1.1 (optional): cost of the Claude call that produced it, from log/runs.jsonl
  cost_usd?: number;
}

export interface Gate {
  name: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface ProofWord {
  i: number;
  text: string;
  suggestion: string | null;
  at: string;
  frame: number;
  why: string;
}

export interface ReviewIssue {
  at: string;
  category: string;
  text: string;
  // v1.1 (optional): severity and suggested fix, from the Reviewer's issue schema
  severity?: "blocker" | "major" | "minor";
  fix?: string;
}

export interface Version {
  n: number;
  created: string;
  label: string;
  final?: string;
  // v1.1 (optional)
  reply?: string;
  cost_usd?: number;
}

export interface Project extends ProjectSummary {
  brief: Record<string, unknown> | null;
  brand: string | null;
  stages: Stage[];
  decisions: Decision[];
  verdict_detail: { verdict: string; reasons: string[]; gates: Gate[] } | null;
  proof: ProofWord[];
  review: { summary: string; issues: ReviewIssue[] } | null;
  media: { final?: string; review_copy?: string; cover?: string; sheets: string[]; cut_strips: string[] };
  versions: Version[];
}

export interface HealthTool {
  name: string;
  ok: boolean;
  detail: string;
}

export interface Health {
  engine: "ok";
  version: string;
  tools: HealthTool[];
  claude: boolean;
  disk_free_gb: number;
  jobs: { running: number; queued: number; limit: number };
  memory_gb: { used: number; budget: number };
}

export interface Job {
  id: string;
  project: string;
  kind: string;
  started: string | null;
  status: string;
}

export interface Jobs {
  running: Job[];
  queued: Job[];
}

/** Engine brief (engine/src/reel/brief.py Brief, extra="forbid": send only these keys). */
export interface Brief {
  project: string;
  client?: string | null;
  platform?: string;
  goal?: string | null;
  audience?: string | null;
  genre_hint?: string | null;
  target_length_s?: [number, number];
  language?: "en" | "hi" | "hinglish" | null;
  caption_script?: "latin" | "devanagari" | "mixed";
  must_keep_lines?: string[];
  cta?: string | null;
  product_names?: string[];
  banned_claims?: string[];
  tone?: string | null;
  vocabulary?: string[];
  notes?: string | null;
  deliverables?: ("feed_4x5" | "square")[];
}

/** Engine brand kit (engine/src/reel/brief.py Brand, extra="forbid"). */
export interface Brand {
  client: string;
  fonts: Record<string, string>;
  colors: { primary?: string | null; secondary?: string | null; accent?: string | null; text?: string | null };
  logo?: string | null;
  caption_family?: string | null;
  caption_tokens: Record<string, string>;
  look?: string | null;
  end_card?: string | null;
  cta_style?: string | null;
}

/** v1.1: GET /api/brands returns the id beside the Brand body. */
export interface BrandEntry {
  id: string;
  brand: Brand;
}

export interface SfxItem {
  id: string;
  category: string;
  duration_ms: number;
  source: string;
  license: string;
}
export interface MusicItem {
  id: string;
  title: string;
  mood: string;
  bpm: number;
  duration_ms: number;
  source: string;
  license: string;
  attribution: string;
}
export interface BrollItem {
  id: string;
  description: string;
  shot: string;
  duration_ms: number;
  source: string;
  license: string;
}
export interface CaptionFamily {
  id: string;
  for: string[];
  mood: string;
}
export interface Libraries {
  sfx: SfxItem[];
  music: MusicItem[];
  broll: BrollItem[];
  caption_families: CaptionFamily[];
  // v1.1 (optional)
  unreadable?: { kind: string; file: string; reason: string }[];
}

export interface EvalRun {
  id: string;
  at: string;
  split: "tuning" | "holdout";
  primary: number;
  families: Record<string, number>;
}
export interface Calibration {
  agreement: number;
  n_labels: number;
  trusted: boolean;
  gates: { name: string; false_alarm_rate: number; mode: "warn" | "block" }[];
}
export interface ImproveEntry {
  at: string;
  change: string;
  outcome: "accepted" | "rejected" | "pending";
  gain?: number | null;
  reason?: string | null;
}
export interface GoldPair {
  id: string;
  split: "tuning" | "holdout";
  language: string;
  source: string;
}
export interface Lab {
  gold: { pairs: number; tuning: number; holdout: number; hinglish: number };
  release_locked: boolean;
  lock_reason: string | null;
  calibration: Calibration | null;
  improve_history: ImproveEntry[];
  // v1.1 (optional)
  runs?: EvalRun[];
  gold_pairs?: GoldPair[];
}

export interface Costs {
  total_usd: number;
  by_project: { id: string; usd: number }[];
  by_day: { date: string; usd: number }[];
}

export interface Settings {
  max_jobs: number;
  projects_dir: string;
  default_brief: Partial<Brief>;
  default_deliverables: ("feed_4x5" | "square")[];
  pexels_key_set: boolean;
  /** Write-only on PUT: a new Pexels key (never returned by GET). */
  pexels_key?: string;
}

export interface PackageFile {
  path: string;
  label: string;
  kind: "final" | "variant" | "review_copy" | "timeline" | "captions" | "stems" | "overlay" | "edit_list" | "other";
  bytes: number;
  thumb?: string | null;
}
export interface PackageListing {
  files: PackageFile[];
  warnings: string[];
}

/** v1.1: GET /api/projects/{id}/timeline */
export interface TimelineView {
  timeline: Timeline;
  reasons: Record<string, string>;
}

export interface Keyframe {
  f: number;
  v: number;
}
export interface Timeline {
  fps: string;
  width: number;
  height: number;
  duration_f: number;
  video: { id: string; at_f: number; dur_f: number; scale: Keyframe[]; src: { item: string; words: number[] } }[];
  audio: { id: string; at_f: number; dur_f: number; role: string; gain_db: number }[];
  grade: { look: string; strength: number; grain: number; vignette: number };
  captions: { family: string; pages: { start_f: number; end_f: number; words: { i: number; text: string; emph: boolean }[] }[] } | null;
  titles: { id: string; text: string; start_f: number; end_f: number; role: string }[];
  pips: { id: string; start_f: number; end_f: number }[];
  effects: { id: string; type: string; start_f: number; end_f: number }[];
  graphics: { id: string; kind: string; start_f: number; end_f: number; text: string }[];
}

export interface ValidatorIssue {
  code: string;
  path: string;
  message: string;
  fix: string;
}

export type AdjustKind =
  | "caption_family"
  | "caption_token"
  | "look"
  | "look_strength"
  | "music_track"
  | "music_gain_db"
  | "sfx_off"
  | "punch_ins_off"
  | "grain"
  | "vignette"
  | "max_pause_ms";

export interface NotesPreview {
  anchored: string[];
  unreadable?: string[];
}

export type SseEvent =
  | { type: "snapshot"; data: Project }
  | { type: "stage"; data: Stage }
  | { type: "decision"; data: Decision }
  | { type: "log"; data: { line: string } }
  | { type: "job"; data: { id: string; kind: string; status: string } }
  | { type: "revision"; data: { reply: string; version: number } }
  | { type: "done"; data: { status: string } };
