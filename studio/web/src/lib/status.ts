import type { ProjectSummary } from "../api/types";

/** The badge a project shows (design system "Status badge"). */
export type Badge = "hold" | "failed" | "sendable" | "editing" | "queued" | "delivered" | "draft" | "source";

export function badgeOf(p: Pick<ProjectSummary, "status" | "delivered_at">): Badge {
  // Same rule as the API's attention order: delivered counts once the edit is finished.
  if (p.delivered_at && (p.status === "sendable" || p.status === "hold")) return "delivered";
  switch (p.status) {
    case "running":
      return "editing";
    case "failed":
      return "failed";
    case "awaiting_choice":
      return "hold"; // needs you: the client picks the hook look before the full render
    default:
      return p.status;
  }
}

// FR-1: "needs me first" — Hold, Failed, Sendable not yet delivered, Editing, (Queued, Draft), Delivered.
const RANK: Record<Badge, number> = { hold: 0, source: 1, failed: 1, sendable: 2, editing: 3, queued: 4, draft: 5, delivered: 6 };

export function attentionRank(p: Pick<ProjectSummary, "status" | "delivered_at">): number {
  return RANK[badgeOf(p)];
}

/** Attention first, then most recently updated within a group. Does not mutate the input. */
export function sortByAttention<T extends Pick<ProjectSummary, "status" | "delivered_at" | "updated">>(list: readonly T[]): T[] {
  return [...list].sort((a, b) => attentionRank(a) - attentionRank(b) || Date.parse(b.updated) - Date.parse(a.updated));
}

export const STAGE_LABEL: Record<string, string> = {
  ingest: "Ingest",
  mezzanine: "Mezzanine",
  perception: "Perception",
  tables: "Tables",
  mine: "Find reels",
  stock: "Stock b-roll",
  broll: "B-roll",
  reference: "Reference",
  story: "Story",
  finish: "Finish",
  compile: "Compile",
  render: "Render",
  overlay: "Overlay",
  composite: "Composite",
  qa: "QA",
  package: "Package",
  variants: "Variants",
};

/** Plain-words description of the running stage (FR-3). */
export const STAGE_PLAIN: Record<string, string> = {
  ingest: "Ingest: checking and copying the raw footage",
  mezzanine: "Mezzanine: converting footage to a steady edit-friendly format",
  perception: "Perception: transcribing speech and finding faces, shots and beats",
  tables: "Tables: building the word and shot tables the Editor reads",
  mine: "Find reels: the Clip Miner is reading the whole recording for standalone moments",
  stock: "Stock b-roll: finding cutaways for this talk on Pexels",
  broll: "B-roll: matching your b-roll clips to what is said",
  reference: "Reference: studying the reference reel the client likes",
  story: "Story: the Editor is choosing the hook and the lines to keep",
  finish: "Finish: the Editor is picking captions, look, music and punch-ins",
  compile: "Compile: turning the plan into an exact timeline",
  render: "Render: rendering the base video and sound",
  overlay: "Overlay: rendering captions, titles and graphics",
  composite: "Composite: combining the overlay with the base video",
  qa: "QA: quality checks and the independent Reviewer",
  package: "Package: building the Final Cut / OTIO package",
  variants: "Variants: making the 4:5 and square versions",
};

/** Stage groups for the pipeline stage (design system: Analyse, Decide, Build, Check and Deliver). */
export const STAGE_GROUPS: { name: string; stages: string[] }[] = [
  { name: "Analyse", stages: ["ingest", "mezzanine", "perception", "tables", "stock", "broll", "reference"] },
  { name: "Decide", stages: ["story", "finish"] },
  { name: "Build", stages: ["compile", "render", "overlay", "composite"] },
  { name: "Check & deliver", stages: ["qa", "package", "variants"] },
];

/** A job is finished in any state other than queued/running (done | failed | cancelled | lost). */
export const isJobTerminal = (status: string | undefined): boolean => !!status && status !== "queued" && status !== "running";

export const RENDER_STAGES =new Set(["render", "overlay", "composite", "variants"]);

/**
 * Typical seconds per stage for a ~60 s reel. A fallback for the time-left estimate when the API
 * sends `eta_s: null`; the estimate is labelled as such on screen.
 */
export const TYPICAL_STAGE_S: Record<string, number> = {
  ingest: 6, mezzanine: 40, perception: 120, tables: 8, stock: 30, broll: 20, reference: 25, story: 75, finish: 60,
  compile: 4, render: 150, overlay: 90, composite: 30, qa: 70, package: 15, variants: 45,
};

/** Seconds left: the API's estimate if present, else typical durations of the remaining stages. */
export function estimateLeft(stages: { name: string; status: string; started: number | null }[], nowSec: number, apiEta?: number | null): number | null {
  if (typeof apiEta === "number") return apiEta;
  const running = stages.find((s) => s.status === "running");
  if (!running) return null;
  const spent = running.started ? nowSec - running.started : 0;
  const cur = Math.max(10, (TYPICAL_STAGE_S[running.name] ?? 30) - spent);
  const rest = stages.filter((s) => s.status === "pending" || s.status === "queued").reduce((a, s) => a + (TYPICAL_STAGE_S[s.name] ?? 30), 0);
  return cur + rest;
}
