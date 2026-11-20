// Types for the Reel Studio local API — docs/product/studio-api.md (v1). Mock mode mirrors these exactly.

export const STAGES = [
  "ingest",
  "mezzanine",
  "perception",
  "tables",
  "stock",
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
export type ProjectStatus = "draft" | "queued" | "running" | "sendable" | "hold" | "failed" | "awaiting_choice" | "source" | "awaiting_story";

/** 3a.2 per-client style memory, learned from reels the owner delivered or labelled sendable. */
export interface ClientStyle {
  client: string;
  profile: {
    reels: number;
    caption_family: string | null;
    look: string | null;
    cuts_per_min: number | null;
    length_s: number | null;
    music_mood: string | null;
    hook_title: string | null;
    recurring_settings: { kind: string; value: unknown; reels: number }[];
  } | null;
  reels: { id: string; name: string; why: string; has_video: boolean }[];
}

/** 3a.1 story check-in: the plan in plain words before the finish pass and render are paid for. */
export interface StoryCheckin {
  status: "open" | "approved";
  summary: string;
  genre: string;
  hook: { item: string; text: string };
  lines: { id: string; beat: string; seconds: number; text: string }[];
  total_s: number;
  left_out: { seg_id: string; seconds: number; text: string }[];
  questions: { id: string; kind: "hook" | "take" | "drop"; text: string; why: string }[];
  warnings: string[];
}

/** Clip Factory (G2.2): a long recording analysed once ("source"), reels made from it ("clip"), or an ordinary reel. */
export type ProjectKind = "reel" | "source" | "clip";

export interface ClipCandidate {
  id: string;
  rank: number;
  title: string;
  hook_text: string;
  family: "hook" | "story" | "tip" | "hot_take" | "proof" | "myth";
  scores: { hook: number; standalone: number; payoff: number; energy: number; shareability: number };
  /** The engine's score from the miner's 1–5 marks: the Editor's estimate, never a "viral" prediction. */
  score: number;
  duration_s: number;
  status: "selected" | "rejected";
  why: string;
  reason: string;
  standalone_risks: string[];
  warnings: string[];
  excerpt: string;
  project: { id: string; status: ProjectStatus } | null;
}

export interface ClipsBoard {
  source_s: number;
  yield_cap: number;
  target_s: [number, number];
  score_label: string;
  score_rule: string;
  candidates: ClipCandidate[];
  estimate_per_reel: { low_usd: number; high_usd: number; from_edits: number } | null;
}

/** Hook preview in two looks (engine reel.preview): export/preview/preview.json. */
export interface HookPreview {
  frames: number;
  seconds?: number;
  chosen: "A" | "B" | null;
  options: Record<string, { caption_family: string | null; look: string; file: string }>;
}
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
  /** Absent from older engines: treat as "reel". */
  kind?: ProjectKind;
  /** For a Clip Factory reel: the source project's id. */
  parent?: string | null;
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

/** One quality check that didn't pass, in plain words (engine reel.verdict_plain). `at` = timecodes "m:ss.ss". */
/** 4.2: what the verdict did not check. `not_measured`: ran but couldn't measure (never a pass); `partial`: skipped some items;
 *  `never`: what no gate looks at. */
export interface Coverage {
  not_measured: { gate: string; why: string }[];
  partial: { gate: string; skipped: number; why: string }[];
  never: string[];
  reviewer: boolean;
}

export interface PlainCheck {
  gate: string;
  status: "fail" | "warn";
  title: string;
  sentence: string;
  at: string[];
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
  verdict_detail: { verdict: string; reasons: string[]; warnings: string[]; gates: Gate[]; plain?: PlainCheck[]; coverage?: Coverage | null } | null;
  proof: ProofWord[];
  review: { summary: string; sendable: boolean | null; strengths: string[]; issues: ReviewIssue[];
            /** 3b.1: the Reviewer's answers to the rubric fixed from the brief before the edit (older reviews: absent). */
            rubric?: { id: string; met: boolean; evidence: string }[] } | null;
  media: { final?: string; review_copy?: string; cover?: string; sheets: string[]; cut_strips: string[]; variants: string[] };
  versions: Version[];
  calls: Call[];
  platform_notes: string[];
  /** Seconds left in the run; null = unknown (the web app estimates from typical stage times). */
  eta_s: number | null;
  preview?: HookPreview | null;
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
  /** Licence gate (reel.licences): what the reel is for decides which library assets it may use. */
  use_categories?: UseCategory[];
  purpose?: "editorial" | "organic" | "promo" | "paid_ad";
  accept_credits?: boolean;
  /** 3c.1 beauty pass (opt-in). */
  beauty?: boolean;
}

export const USE_CATEGORIES = ["political", "dating", "drugs", "alcohol", "gambling", "religious", "adult"] as const;
export type UseCategory = (typeof USE_CATEGORIES)[number];

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
  /** How the client's posts read (copy pack). Optional: older kits have none. */
  voice?: BrandVoice;
  /** 3c.1 beauty pass default for this client's reels. */
  beauty?: "off" | "light";
  /** 3a.1: New edit starts with "Check the story first" ticked for this client. */
  story_checkin?: boolean;
}

/** engine/src/reel/brief.py BrandVoice. Hashtags are words without `#`. */
export interface BrandVoice {
  tone?: string | null;
  caption_language?: "en" | "hinglish_latin" | "hi_deva" | null;
  hashtags_always?: string[];
  hashtags_pool?: string[];
  banned_words?: string[];
  emoji?: "none" | "light" | "heavy";
  handles?: string[];
  cta_lines?: string[];
}

/** GET /api/brands returns the id beside the Brand body. */
export interface BrandEntry {
  id: string;
  brand: Brand;
}

/** Post copy pack (reel.postcopy): hashtags and licence credits already added by the engine. */
export interface PostCopy {
  ig_caption: string;
  first_comment: string;
  hashtags: string[];
  yt_title: string;
  yt_description: string;
  credits: string[];
  status: "ok" | "needs_review";
  problems: string[];
}

/** Licence gate fields (reel.licences): the registry row, and why every reel refuses it (null = usable). */
export interface LicenceFields {
  licence_id?: string | null;
  licence_problem?: string | null;
}
export interface SfxItem extends LicenceFields {
  id: string;
  category: string;
  duration_ms: number;
  source: string;
  license: string;
  file: string | null;
}
export interface MusicItem extends LicenceFields {
  id: string;
  title: string;
  mood: string;
  bpm: number;
  duration_ms: number;
  source: string;
  license: string;
  attribution: string | null;
}
export interface BrollItem extends LicenceFields {
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
  /** 3b.2: ours vs the pro, judged both ways round; kept out of the score until it agrees with the owner's blind picks. */
  pairwise?: {
    last: { win: number; tie: number; loss: number } | null;
    last_run: string | null;
    agreement: { n: number; agree: number; rate: number | null };
    pending: { run: string; reel: string }[];
  };
  /** C5: the latest speech-to-text bake-off and the engine each language uses now (absent from older engines). */
  bakeoff?: {
    engines_now: Record<string, string>;
    samples: number;
    latest: { at: string; summary: Record<string, Record<string, number | string | null>> | null } | null;
  };
}

/** G2.5 listening test: blind pairs (no model names) and, once votes exist, the per-model result. */
export type ListenSet = "sfx" | "music" | "voice";
export interface ListenPair {
  id: string;
  prompt: string;
  A: string;
  B: string;
  done: boolean;
}
export interface ListenModelResult {
  comparisons: number;
  win_rate: number;
  usable_rate: number;
  mean_generation_s: number;
  decision: "adopt" | "adopt (paid)" | "not yet" | "reference";
}
export interface Listening {
  set: ListenSet;
  prompts: number;
  pairs: ListenPair[];
  summary: { votes: number; pairs: number; rule: string; models: Record<string, ListenModelResult>; generators: Record<string, { status: string; why?: string }> } | null;
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
  pixabay_key_set?: boolean;
  /** Write-only on PUT: a new Pixabay key (never returned by GET). */
  pixabay_key?: string;
  /** 4.1: monthly AI spend cap in USD; 0 = no cap. */
  monthly_cap_usd?: number;
  /** 4.3: https address of the owner's tunnel to `reel share-server`; "" = review links work on this Mac only. */
  public_review_url?: string;
}

/** GET /api/spend (4.1 cost guard). */
export interface SpendStatus {
  month: { claude_usd: number; paid_usd: number; total_usd: number };
  cap_usd: number | null;
  /** One more edit's likely Claude cost, from past edits (null with fewer than 3). */
  estimate: { low_usd: number; high_usd: number; from_edits: number } | null;
  over_cap: boolean;
  /** Paid generator requests waiting for the owner's approval. */
  pending: { at: number; hash: string; generator: string; quote_usd: number; what?: string; project?: string | null }[];
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

/** The client's latest answers through a review link, to what is open now (an answer to an older check-in or preview is dropped). */
export interface ClientChoices {
  checkin: { at: number; yes: string[]; note: string; name: string } | null;
  hook: { at: number; option: "A" | "B"; name: string } | null;
}

/** GET /api/projects/{id}/review-links. `ready` = there is something to show the client (a check-in, a hook preview or a render). */
export interface ReviewLinks {
  links: ReviewLink[];
  notes: ReviewNote[];
  ready: boolean;
  choices?: ClientChoices;
  /** 4.3: the owner's public address for review links (their tunnel to `reel share-server`); null = this Mac only. */
  public_base?: string | null;
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
  /** 3c.1: what the last render applied. */
  beauty?: "off" | "light";
}

/** GET /api/projects/{id}/timeline */
export interface TimelineView {
  timeline: Timeline;
  /** Keyed like the layer blocks: plan item (k01), punch-in clip (v_k04), dialogue clip (a_k04), sfx/pip/effect/graphic id, hook_title, grade, captions, music. */
  reasons: Record<string, string>;
  /** Kept lines: item id → beat and spoken text. */
  story: Record<string, { beat: string; text: string; words?: [number, string][] }>;
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
  | "max_pause_ms"
  /** C4: the kept line ids in their new order; a line left out is dropped (with what was attached to it). */
  | "story_lines"
  /** 3a.3: `{ item, remove: [[first word, last word], …] }`: cut words out of one kept line. */
  | "story_words"
  /** 3c.1: "off" | "light" for this project (wins over the brief and the brand kit); only the picture re-renders. */
  | "beauty";

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
