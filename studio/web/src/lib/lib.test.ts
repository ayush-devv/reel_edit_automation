import { describe, expect, it } from "vitest";
import type { ProjectSummary } from "../api/types";
import { validateAdjust } from "./adjust";
import { EMPTY_FORM, formErrors, toBrief } from "./brief";
import { parseNotes } from "./notes";
import { screenFiles } from "./pendingFiles";
import { badgeOf, sortByAttention } from "./status";

const P = (id: string, status: ProjectSummary["status"], extra: Partial<ProjectSummary> = {}): ProjectSummary => ({
  id,
  name: id,
  created: "2026-11-01T00:00:00Z",
  updated: "2026-11-10T00:00:00Z",
  status,
  stage: null,
  progress: 0,
  duration_s: null,
  cost_usd: 0,
  verdict: null,
  needs_attention: [],
  thumb: null,
  client: null,
  delivered_at: null,
  ...extra,
});

describe("sortByAttention (FR-1, AC-1)", () => {
  it("orders Hold, Failed, Sendable, Editing, Queued, Delivered", () => {
    const list = [
      P("delivered", "sendable", { delivered_at: "2026-11-09T00:00:00Z" }),
      P("editing", "running", { stage: "story" }),
      P("queued", "queued"),
      P("sendable", "sendable"),
      P("failed", "failed"),
      P("hold", "hold"),
    ];
    expect(sortByAttention(list).map((p) => p.id)).toEqual(["hold", "failed", "sendable", "editing", "queued", "delivered"]);
    expect(list[0].id).toBe("delivered"); // input untouched
  });

  it("puts the most recently updated first within a group", () => {
    const a = P("old", "hold", { updated: "2026-11-01T00:00:00Z" });
    const b = P("new", "hold", { updated: "2026-11-12T00:00:00Z" });
    expect(sortByAttention([a, b]).map((p) => p.id)).toEqual(["new", "old"]);
  });

  it("maps statuses to badges", () => {
    expect(badgeOf(P("x", "running"))).toBe("editing");
    expect(badgeOf(P("x", "sendable", { delivered_at: "2026-11-01T00:00:00Z" }))).toBe("delivered");
    expect(badgeOf(P("x", "running", { delivered_at: "2026-11-01T00:00:00Z" }))).toBe("editing"); // re-editing a delivered reel
  });

  it("reads the first timecode of a Reviewer range", async () => {
    const { tcToSeconds } = await import("./format");
    expect(tcToSeconds("0:03.2, 0:38.2, 0:43.2–0:44.2 vs 0:08.2")).toBeCloseTo(3.2);
    expect(tcToSeconds("00:00:12.40")).toBeCloseTo(12.4);
    expect(tcToSeconds("")).toBe(0);
  });
});

describe("parseNotes (FR-7, AC-11)", () => {
  it("parses timed and whole-reel notes and lists unreadable lines", () => {
    const r = parseNotes("0:01 faster\ngibberish line ??\nlove it\n[0:04] cut this\n12s: bigger captions\n- 1:02.5 swap this line");
    expect(r.notes.map((n) => [n.t, n.text])).toEqual([
      [1, "faster"],
      [null, "love it"],
      [4, "cut this"],
      [12, "bigger captions"],
      [62.5, "swap this line"],
    ]);
    expect(r.unreadable).toEqual(["gibberish line ??"]);
  });
});

describe("validateAdjust (FR-8)", () => {
  const ctx = { families: ["bold_pop", "editorial_kinetic"], tracks: ["acoustic_morning"] };
  it("accepts valid values", () => {
    expect(validateAdjust("max_pause_ms", 400, ctx)).toEqual([]);
    expect(validateAdjust("max_pause_ms", 0, ctx)).toEqual([]);
    expect(validateAdjust("look_strength", "0.45", ctx)).toEqual([]);
    expect(validateAdjust("music_track", "none", ctx)).toEqual([]);
    expect(validateAdjust("caption_token", { key: "emph_color", value: "#FF5FA2" }, ctx)).toEqual([]);
  });
  it("explains invalid values in plain words", () => {
    expect(validateAdjust("max_pause_ms", 100, ctx)[0].message).toMatch(/between 300 and 3000/);
    expect(validateAdjust("grain", 0.9, ctx)[0].message).toMatch(/Grain must be between 0 and 0.6/);
    expect(validateAdjust("caption_family", "comic_sans", ctx)[0].code).toBe("unknown_family");
    expect(validateAdjust("caption_token", { key: "emph_color", value: "pink" }, ctx)[0].code).toBe("bad_color");
  });
});

describe("brief form → engine Brief", () => {
  it("sends only Brief keys, auto language as null, deliverables as ids", () => {
    const b = toBrief({ ...EMPTY_FORM, name: "Glow", language: "auto", genre: "genre.testimonial", mustKeep: "line one\n\nline two", vocabulary: "DearMa, niacinamide", square: true });
    expect(b).toMatchObject({ project: "Glow", language: null, genre_hint: "genre.testimonial", must_keep_lines: ["line one", "line two"], vocabulary: ["DearMa", "niacinamide"], deliverables: ["square"], target_length_s: [15, 60] });
    expect(Object.keys(b)).not.toContain("genre");
    expect(formErrors({ ...EMPTY_FORM })).toHaveProperty("name");
    expect(formErrors({ ...EMPTY_FORM, name: "x", minLen: "60", maxLen: "30" })).toHaveProperty("maxLen");
  });
});

describe("screenFiles (FR-2, AC-3)", () => {
  it("rejects non-video files with a message naming them", () => {
    const r = screenFiles([new File(["x"], "clip.MP4"), new File(["x"], "brief.pdf")]);
    expect(r.ok.map((f) => f.name)).toEqual(["clip.MP4"]);
    expect(r.rejected[0].reason).toContain("brief.pdf");
  });
});
