// Types for the Reel Studio local API — docs/product/studio-api.md (v1). Mock mode mirrors these exactly.

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
  client: string | null;
  /** ISO; set by POST …/delivered. Finished + delivered sorts last (FR-1). */
  delivered_at: string | null;
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
  /** AI cost of the Claude calls behind it (on the hook, captions and Reviewer decisions). */
  cost_usd?: number;
}

export interface Gate {
  /** Engine gate id, e.g. "reading_speed". */
  name: string;
  status: "pass" | "warn" | "fail";
  detail: string;
  measured: Record<string, unknown>;
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
  severity: "blocker" | "major" | "minor" | null;
  fix: string;
}

export interface Version {
  n: number;
  created: string;
  /** "Original edit" | "Revision: “<request>”" | "Client notes" | "Caption fix" | "Manual" | "Restored v<n>" */
  label: string;
  final?: string;
  /** The Editor's one-line reply (revisions), or what changed (Manual, Caption fix, Restored). */
  reply: string;
  cost_usd: number | null;
}

export interface Call {
  time: number | null;
  label: string;
  cost_usd: number;
  duration_s: number | null;
  ok: boolean;
}

export interface Project extends ProjectSummary {
  brief: Record<string, unknown> | null;
  brand: string | null;
  stages: Stage[];
  decisions: Decision[];
  verdict_detail: { verdict: string; reasons: string[]; warnings: string[]; gates: Gate[] } | null;
  proof: ProofWord[];
  review: { summary: string; sendable: boolean | null; strengths: string[]; issues: ReviewIssue[] } | null;
  media: { final?: string; review_copy?: string; cover?: string; sheets: string[]; cut_strips: string[]; variants: string[] };
  versions: Version[];
  calls: Call[];
  platform_notes: string[];
  /** Seconds left in the run; null = unknown (the web app estimates from typical stage times). */
  eta_s: number | null;
}

export interface HealthTool {
  name: string;
  ok: boolean;
  detail: string;
  required: boolean;
}

export interface Health {
  engine: "ok";
  version: string;
  toolchain_ok: boolean;
  tools: HealthTool[];
  claude: boolean;
  disk_free_gb: number;
  jobs: { running: number; queued: number; limit: number };
  memory_gb: { used: number; budget: number; system: { total?: number; available?: number } };
  projects_root: string;
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "lost";

export interface Job {
  id: string;
  /** Project id, or a global slot: "_lab", "_library". */
  project: string;
  kind: string;
  status: JobStatus;
  label: string;
  /** Epoch seconds. */
  created: number;
  started: number | null;
  finished: number | null;
  est_gb: number;
  returncode: number | null;
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

/** GET /api/brands returns the id beside the Brand body. */
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
  file: string | null;
}
export interface MusicItem {
  id: string;
  title: string;
  mood: string;
  bpm: number;
  duration_ms: number;
  source: string;
  license: string;
  attribution: string | null;
}
export interface BrollItem {
  id: string;
  description: string;
  shot: string;
  tags: string[];
  duration_ms: number;
  source: string;
  license: string;
  file: string | null;
}
export interface CaptionFamily {
  id: string;
  for: string[];
  mood: string;
  max_words: number | null;
  tokens: Record<string, string>;
}
export interface Libraries {
  sfx: SfxItem[];
  music: MusicItem[];
  broll: BrollItem[];
  caption_families: CaptionFamily[];
  unreadable: { kind: string; file: string; reason: string }[];
}

export interface EvalRun {
  id: string;
  at: string | null;
  split: "tuning" | "holdout";
  /** Mean primary score, 0–1. */
  primary: number;
  families: Record<string, number>;
  vetoed: number;
  reels: { id: string; primary: number | null; verdict: string | null; vetoes: string[] }[];
}
export interface CalibrationGate {
  name: string;
  mode: "warn" | "block";
  /** 0–1; null when it can't be measured yet. */
  false_alarm_rate: number | null;
  catch_rate: number | null;
  promote_to_block: boolean;
}
export interface Calibration {
  /** Reviewer agreement with the owner's labels, 0–1; null before any label. */
  agreement: number | null;
  n_labels: number;
  trusted: boolean;
  gates: CalibrationGate[];
  rule: string | null;
}
export interface ImproveEntry {
  at: string | null;
  round: number | null;
  change: string;
  outcome: "accepted" | "rejected" | "invalid" | "dry_run";
  /** Primary-score gain, 0–1 scale. */
  gain: number | null;
  reason: string | null;
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
  runs: EvalRun[];
  gold_pairs: GoldPair[];
}

export interface Costs {
  total_usd: number;
  calls: number;
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
  thumb: string | null;
}
export interface PackageListing {
  files: PackageFile[];
  warnings: string[];
}

/** A private client page (`path` is `/r/<id>`) with the review copy and a notes box. Times are epoch seconds. */
export interface ReviewLink {
  id: string;
  path: string;
  created: number;
  expires: number;
  state: "active" | "expired" | "revoked";
  notes: number;
}

export interface ReviewNote {
  at: number;
  /** First 8 characters of the link id it came through. */
  link: string;
  name: string;
  text: string;
}

/** GET /api/projects/{id}/review-links. `ready` = a review copy exists, so a link can be made. */
export interface ReviewLinks {
  links: ReviewLink[];
  notes: ReviewNote[];
  ready: boolean;
}

/** Current value of every guided adjustment (FR-8). */
export interface AdjustState {
  caption_family: string | null;
  caption_tokens: Record<string, string>;
  look: string;
  look_strength: number;
  grain: number;
  vignette: number;
  music_track: string;
  music_gain_db: number;
  max_pause_ms: number | null;
  sfx: number;
  punch_ins: number;
}

/** GET /api/projects/{id}/timeline */
export interface TimelineView {
  timeline: Timeline;
  /** Keyed like the layer blocks: plan item (k01), punch-in clip (v_k04), dialogue clip (a_k04), sfx/pip/effect/graphic id, hook_title, grade, captions, music. */
  reasons: Record<string, string>;
  /** Kept lines: item id → beat and spoken text. */
  story: Record<string, { beat: string; text: string }>;
  adjust: AdjustState;
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
  /** anchored[i] belongs to the i-th non-empty line sent. */
  anchored: string[];
  notes: { t: number | null; text: string }[];
  unreadable: string[];
}

export type SseEvent =
  | { type: "snapshot"; data: Project }
  | { type: "stage"; data: Stage }
  | { type: "decision"; data: Decision }
  | { type: "log"; data: { line: string } }
  | { type: "job"; data: { id: string; kind: string; status: JobStatus; label: string } }
  | { type: "revision"; data: { reply: string; request: string; version: number | null } }
  /** `status` = the project's status after the job; `job` = the job's own end status. A fresh snapshot follows. */
  | { type: "done"; data: { status: ProjectStatus; job: JobStatus; kind: string } };
