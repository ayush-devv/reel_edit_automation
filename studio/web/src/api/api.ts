import type {
  AdjustKind,
  BrandEntry,
  Brand,
  Brief,
  ClientStyle,
  ClipsBoard,
  Listening,
  ListenSet,
  StoryCheckin,
  Costs,
  Health,
  Job,
  Jobs,
  Lab,
  Libraries,
  NotesPreview,
  PackageListing,
  PostCopy,
  Project,
  ProjectSummary,
  ReviewLink,
  ReviewLinks,
  Settings,
  SpendStatus,
  SseEvent,
  TimelineView,
  Version,
} from "./types";

/** Every POST that starts work answers `{ job }`; the SSE `job` events carry the same `job.id`. */
export interface JobRef {
  job: Job;
}

export interface NewProjectInput {
  files: File[];
  name: string;
  brief: Brief;
  brand?: string | null;
  reference_url?: string | null;
  /** Find stock b-roll on Pexels for this talk at edit time (needs the Pexels key in Settings). */
  stock?: boolean;
  /** A folder of the client's own b-roll on this Mac (absolute path). */
  broll_folder?: string | null;
  /** Stop after rendering the hook in two looks for the client to pick (A/B). */
  preview_first?: boolean;
  /** "long": a long recording → analysis + a board of candidate reels (Clip Factory). Default "reel". */
  mode?: "reel" | "long";
  /** 3a.1: stop after the story pass so the owner checks the story first. */
  story_checkin?: boolean;
  /** 3a.2: a past project whose finished reel becomes the reference to match. */
  match_project?: string | null;
  /** A video already on this Mac (absolute path), used where it is instead of uploading `files` (long recordings). */
  source_path?: string | null;
  /** 4.1: the owner already said "spend anyway" for this month's cap. */
  spend_anyway?: boolean;
}

/** Saved brief templates (server-side, ~/.config/reel/templates.json): name → form values. */
export type Templates = Record<string, Record<string, unknown>>;

/** Bytes sent so far, for the per-file progress bars (FR-2). */
export type UploadProgress = (loaded: number, total: number) => void;

/** Everything the screens need. Implemented by the HTTP client and by the mock. */
export interface Api {
  readonly mode: "live" | "mock";
  health(): Promise<Health>;
  jobs(): Promise<Jobs>;
  projects(): Promise<ProjectSummary[]>;
  project(id: string): Promise<Project>;
  createProject(input: NewProjectInput, onProgress?: UploadProgress): Promise<{ id: string; job: Job }>;
  deleteProject(id: string): Promise<void>;
  /** Rename a project or set its client (the Studio's label; the brief the Editor read is not changed). */
  updateProject(id: string, patch: { name?: string; client?: string | null }): Promise<void>;
  templates(): Promise<Templates>;
  saveTemplates(all: Templates): Promise<Templates>;
  /** Apply the hook-preview pick (A/B) and render the full reel. */
  choosePreview(id: string, option: "A" | "B"): Promise<JobRef>;
  /** Fetch the built-in SFX and music packs (`reel assets fetch`) as a job. */
  fetchStarterPacks(): Promise<JobRef>;
  retry(id: string, stage?: string): Promise<JobRef>;
  cancel(id: string): Promise<void>;
  timeline(id: string): Promise<TimelineView>;
  revise(id: string, request: string): Promise<JobRef>;
  notesPreview(id: string, text: string): Promise<NotesPreview>;
  notesApply(id: string, text: string): Promise<JobRef>;
  proof(id: string, words: { i: number; text: string }[]): Promise<JobRef>;
  adjust(id: string, kind: AdjustKind, value: unknown): Promise<JobRef & { note?: string }>;
  versions(id: string): Promise<Version[]>;
  restore(id: string, n: number): Promise<JobRef>;
  deliver(id: string, variants?: string[]): Promise<JobRef>;
  packageListing(id: string): Promise<PackageListing>;
  markDelivered(id: string): Promise<void>;
  reviewLinks(id: string): Promise<ReviewLinks>;
  /** The credited post copy (404 until the package has been written). */
  postCopy(id: string): Promise<PostCopy>;
  createReviewLink(id: string, hours: number): Promise<ReviewLink>;
  revokeReviewLink(id: string, linkId: string): Promise<void>;
  label(id: string, sendable: boolean, reason: string): Promise<void>;
  /** 3a.2: the client's style profile and approved reels. */
  clientStyle(client: string): Promise<ClientStyle>;
  /** 3a.1 story check-in (404 when the edit has none). */
  checkin(id: string): Promise<StoryCheckin>;
  /** Accept some questions and/or a note; approves the story and finishes the edit as one job. */
  answerCheckin(id: string, yes: string[], note?: string): Promise<JobRef>;
  /** Clip Factory board of a mined long recording (404 while it is still being analysed). */
  clips(id: string): Promise<ClipsBoard>;
  /** Make reel projects from the picked candidates; `run` queues an edit of each. */
  makeClips(id: string, ids: string[], run?: boolean): Promise<{ made: string[]; jobs: Job[] }>;
  libraries(): Promise<Libraries>;
  indexLibrary(kind: "sfx" | "music", folder: string, source: string, license: string): Promise<JobRef>;
  brands(): Promise<BrandEntry[]>;
  saveBrand(id: string, brand: Brand, isNew: boolean): Promise<void>;
  lab(): Promise<Lab>;
  labAction(action: "eval" | "calibrate" | "improve" | "bakeoff", body?: Record<string, unknown>): Promise<JobRef>;
  /** 3b.2: the owner's blind pick between our reel and the pro's (sides are hidden; the engine keeps the key). */
  votePairwise(run: string, reel: string, choice: "A" | "B" | "same"): Promise<void>;
  pairwiseMediaUrl(run: string, reel: string, side: "A" | "B"): string;
  /** G2.5 listening test. */
  listening(set: ListenSet): Promise<Listening>;
  prepareListening(set: ListenSet): Promise<JobRef>;
  voteListening(set: ListenSet, vote: { pair: string; choice: "A" | "B" | "tie"; usable_a: boolean; usable_b: boolean }): Promise<void>;
  listeningMediaUrl(set: ListenSet, path: string): string;
  /** C3: switch a QA gate between warn and block (block only once calibration cleared it). */
  setGateMode(gate: string, mode: "warn" | "block"): Promise<{ gate: string; mode: string; recomputed: number }>;
  costs(days?: number): Promise<Costs>;
  /** 4.1 cost guard: month to date, the cap, one edit's estimate, pending paid quotes. */
  spend(): Promise<SpendStatus>;
  approveSpend(hash: string): Promise<unknown>;
  settings(): Promise<Settings>;
  saveSettings(s: Settings): Promise<Settings>;
  /** `v` busts the browser cache when a re-render rewrites the same path (e.g. the version number). */
  mediaUrl(id: string, path: string, v?: string | number): string;
  /** Preview a library file (sfx/music/broll). "" when unavailable. */
  libraryMediaUrl(kind: "sfx" | "music" | "broll", id: string): string;
  packageZipUrl(id: string): string;
  /** Live events for one project (SSE). Returns an unsubscribe function. */
  subscribe(id: string, onEvent: (ev: SseEvent) => void, onError?: () => void): () => void;
}
