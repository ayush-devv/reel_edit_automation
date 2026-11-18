import type {
  AdjustKind,
  BrandEntry,
  Brand,
  Brief,
  Costs,
  Health,
  Jobs,
  Lab,
  Libraries,
  NotesPreview,
  PackageListing,
  Project,
  ProjectSummary,
  Settings,
  SseEvent,
  TimelineView,
  Version,
} from "./types";

export interface JobRef {
  job: string;
}

export interface NewProjectInput {
  files: File[];
  name: string;
  brief: Brief;
  brand?: string | null;
  reference_url?: string | null;
}

/** Bytes sent so far, for the per-file progress bars (FR-2). */
export type UploadProgress = (loaded: number, total: number) => void;

/** Everything the screens need. Implemented by the HTTP client and by the mock. */
export interface Api {
  readonly mode: "live" | "mock";
  health(): Promise<Health>;
  jobs(): Promise<Jobs>;
  projects(): Promise<ProjectSummary[]>;
  project(id: string): Promise<Project>;
  createProject(input: NewProjectInput, onProgress?: UploadProgress): Promise<{ id: string }>;
  deleteProject(id: string): Promise<void>;
  retry(id: string, stage?: string): Promise<JobRef>;
  cancel(id: string): Promise<void>;
  timeline(id: string): Promise<TimelineView>;
  revise(id: string, request: string): Promise<JobRef>;
  notesPreview(id: string, text: string): Promise<NotesPreview>;
  notesApply(id: string, text: string): Promise<JobRef>;
  proof(id: string, words: { i: number; text: string }[]): Promise<JobRef>;
  adjust(id: string, kind: AdjustKind, value: unknown): Promise<JobRef>;
  versions(id: string): Promise<Version[]>;
  restore(id: string, n: number): Promise<JobRef>;
  deliver(id: string, variants?: string[]): Promise<JobRef>;
  packageListing(id: string): Promise<PackageListing>;
  markDelivered(id: string): Promise<void>;
  label(id: string, sendable: boolean, reason: string): Promise<void>;
  libraries(): Promise<Libraries>;
  indexLibrary(kind: "sfx" | "music", folder: string, source: string, license: string): Promise<JobRef>;
  brands(): Promise<BrandEntry[]>;
  saveBrand(id: string, brand: Brand, isNew: boolean): Promise<void>;
  lab(): Promise<Lab>;
  labAction(action: "eval" | "calibrate" | "improve", body?: Record<string, unknown>): Promise<JobRef>;
  costs(days?: number): Promise<Costs>;
  settings(): Promise<Settings>;
  saveSettings(s: Settings): Promise<void>;
  mediaUrl(id: string, path: string): string;
  /** v1.1: preview a library file (sfx/music/broll). "" when unavailable. */
  libraryMediaUrl(kind: "sfx" | "music" | "broll", id: string): string;
  packageZipUrl(id: string): string;
  /** Live events for one project (SSE). Returns an unsubscribe function. */
  subscribe(id: string, onEvent: (ev: SseEvent) => void, onError?: () => void): () => void;
}
