// In-browser stand-in for the studio API (mock mode). Same interface as the HTTP client, with a small
// simulator so the live view, the queue and the job-driven screens behave like the real thing.
import type { Api, JobRef } from "../api";
import { ApiError } from "../errors";
import { STAGES, type AdjustKind, type BrandEntry, type Project, type ProjectSummary, type SseEvent, type Stage } from "../types";
import { parseNotes } from "../../lib/notes";
import { validateAdjust } from "../../lib/adjust";
import { BRANDS, COSTS, HEALTH, LAB, LIBRARIES, PACKAGE, SETTINGS, makeProjects, makeTimeline } from "./fixtures";

const clone = <T>(x: T): T => structuredClone(x);
const wait = (ms = 120) => new Promise((r) => setTimeout(r, ms));
const SKIP = new Set(["broll", "reference"]);
const TICK_MS = 2600;

export function createMockApi(opts: { engineDown?: boolean } = {}): Api {
  const projects = new Map<string, Project>(makeProjects().map((p) => [p.id, p]));
  const brands: BrandEntry[] = clone(BRANDS);
  let settings = clone(SETTINGS);
  const subs = new Map<string, Set<(ev: SseEvent) => void>>();
  let timer: ReturnType<typeof setInterval> | null = null;
  let jobSeq = 100;

  const job = (): JobRef => ({ job: `job-${++jobSeq}` });
  const emit = (id: string, ev: SseEvent) => subs.get(id)?.forEach((fn) => fn(clone(ev)));
  const must = (id: string) => {
    const p = projects.get(id);
    if (!p) throw new ApiError(404, `No project “${id}”.`);
    return p;
  };
  async function guard() {
    await wait();
    if (opts.engineDown) throw new ApiError(0, "Engine is not running.");
  }
  const touch = (p: Project) => (p.updated = new Date().toISOString());
  const running = () => [...projects.values()].filter((p) => p.status === "running");

  function setStage(p: Project, name: string, status: Stage["status"], error?: string) {
    const s = p.stages.find((x) => x.name === name)!;
    const now = Date.now() / 1000;
    s.status = status;
    if (status === "running") (s.started = now), (s.finished = null), delete s.error;
    if (status === "done" || status === "failed") s.finished = now;
    if (error) s.error = error;
    emit(p.id, { type: "stage", data: clone(s) });
  }

  function addDecisions(p: Project, stage: string) {
    const src = makeProjects().find((x) => x.id === "glow-serum-testimonial")!.decisions;
    const kind = stage === "story" ? "story" : stage === "finish" ? "finish" : stage === "qa" ? "qa" : null;
    if (!kind) return;
    for (const d of src.filter((x) => x.kind === kind || (kind === "qa" && x.kind === "review"))) {
      const nd = { ...d, at: Date.now() / 1000 };
      p.decisions.push(nd);
      p.cost_usd = +(p.cost_usd + (d.cost_usd ?? 0)).toFixed(3);
      emit(p.id, { type: "decision", data: nd });
    }
  }

  function finish(p: Project) {
    const ref = makeProjects().find((x) => x.id === "founder-story-cut-1")!;
    Object.assign(p, {
      status: "sendable",
      verdict: "sendable",
      stage: null,
      progress: 1,
      duration_s: 38.4,
      verdict_detail: clone(ref.verdict_detail),
      review: clone(ref.review),
      versions: [{ n: 1, created: new Date().toISOString(), label: "First edit", reply: "Initial cut from the brief.", cost_usd: p.cost_usd }],
    });
    emit(p.id, { type: "done", data: { status: "sendable" } });
    emit(p.id, { type: "snapshot", data: clone(p) });
  }

  function startQueued() {
    const limit = settings.max_jobs;
    for (const p of projects.values()) {
      if (running().length >= limit) return;
      if (p.status !== "queued") continue;
      p.status = "running";
      p.stages.forEach((s) => (s.status = "pending"));
      p.stage = "ingest";
      setStage(p, "ingest", "running");
      emit(p.id, { type: "snapshot", data: clone(p) });
    }
  }

  function tick() {
    for (const p of running()) {
      if (!subs.get(p.id)?.size) continue; // only animate what someone is watching
      const i = p.stages.findIndex((s) => s.status === "running");
      if (i === -1) continue;
      const cur = p.stages[i];
      setStage(p, cur.name, "done");
      addDecisions(p, cur.name);
      let j = i + 1;
      while (j < STAGES.length && SKIP.has(STAGES[j])) setStage(p, STAGES[j++], "skipped");
      p.progress = j / STAGES.length;
      if (j >= STAGES.length) {
        finish(p);
        startQueued();
        continue;
      }
      p.stage = STAGES[j];
      setStage(p, STAGES[j], "running");
      touch(p);
    }
  }

  function ensureTicker() {
    const watching = [...subs.values()].some((s) => s.size > 0);
    if (watching && !timer) timer = setInterval(tick, TICK_MS);
    if (!watching && timer) clearInterval(timer), (timer = null);
  }

  /** Re-render simulation for proof / revise / adjust / notes jobs (no stage animation). */
  function laterJob(p: Project, kind: string, after: () => void, ms = 1800): JobRef {
    const ref = job();
    emit(p.id, { type: "job", data: { id: ref.job, kind, status: "running" } });
    setTimeout(() => {
      after();
      touch(p);
      emit(p.id, { type: "job", data: { id: ref.job, kind, status: "done" } });
      emit(p.id, { type: "snapshot", data: clone(p) });
    }, ms);
    return ref;
  }

  function addVersion(p: Project, label: string, reply: string, cost: number) {
    const n = (p.versions.at(-1)?.n ?? 0) + 1;
    p.versions.push({ n, created: new Date().toISOString(), label, reply, cost_usd: cost });
    p.cost_usd = +(p.cost_usd + cost).toFixed(3);
    p.decisions.push({ at: Date.now() / 1000, kind: "revision", title: label, detail: reply, knowledge: [], cost_usd: cost });
    return n;
  }

  const summary = (p: Project): ProjectSummary => {
    const { id, name, created, updated, status, stage, progress, duration_s, cost_usd, verdict, needs_attention, thumb, client, delivered_at } = p;
    return { id, name, created, updated, status, stage, progress, duration_s, cost_usd, verdict, needs_attention, thumb, client, delivered_at };
  };

  return {
    mode: "mock",
    async health() {
      await guard();
      const h = clone(HEALTH);
      h.jobs = { running: running().length, queued: [...projects.values()].filter((p) => p.status === "queued").length, limit: settings.max_jobs };
      return h;
    },
    async jobs() {
      await guard();
      const all = [...projects.values()];
      const toJob = (p: Project) => ({ id: `job-${p.id}`, project: p.id, kind: "run", started: p.status === "running" ? p.updated : null, status: p.status });
      return { running: all.filter((p) => p.status === "running").map(toJob), queued: all.filter((p) => p.status === "queued").map(toJob) };
    },
    async projects() {
      await guard();
      return [...projects.values()].map(summary);
    },
    async project(id) {
      await guard();
      return clone(must(id));
    },
    async createProject(input, onProgress) {
      await guard();
      if (!input.name.trim()) throw new ApiError(400, "Project name is required.");
      const total = input.files.reduce((a, f) => a + f.size, 0) || 1;
      for (let k = 1; k <= 10; k++) {
        await wait(90);
        onProgress?.((total * k) / 10, total);
      }
      const id = input.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-" + (++jobSeq).toString(36);
      const slotFree = running().length < settings.max_jobs;
      const p: Project = {
        id,
        name: input.name,
        client: input.brief.client ?? null,
        created: new Date().toISOString(),
        updated: new Date().toISOString(),
        status: slotFree ? "running" : "queued",
        stage: slotFree ? "ingest" : null,
        progress: 0,
        duration_s: null,
        cost_usd: 0,
        verdict: null,
        needs_attention: [],
        thumb: null,
        delivered_at: null,
        brief: input.brief as unknown as Record<string, unknown>,
        brand: input.brand ?? null,
        stages: STAGES.map((name, i) => ({ name, status: slotFree ? (i === 0 ? "running" : "pending") : "queued", started: slotFree && i === 0 ? Date.now() / 1000 : null, finished: null, meta: {} })),
        decisions: [],
        verdict_detail: null,
        proof: [],
        review: null,
        media: { sheets: [], cut_strips: [] },
        versions: [],
      };
      projects.set(id, p);
      return { id };
    },
    async deleteProject(id) {
      await guard();
      must(id);
      projects.delete(id);
    },
    async retry(id, stage) {
      await guard();
      const p = must(id);
      const failed = p.stages.find((s) => s.status === "failed");
      const name = stage ?? failed?.name;
      if (!name) throw new ApiError(400, "Nothing to retry.");
      p.status = "running";
      p.stage = name;
      p.needs_attention = [];
      setStage(p, name, "running");
      touch(p);
      return job();
    },
    async cancel(id) {
      await guard();
      const p = must(id);
      const s = p.stages.find((x) => x.status === "running");
      if (s) setStage(p, s.name, "failed", "Cancelled by you. Press Retry to resume from this stage.");
      p.status = "failed";
      p.needs_attention = ["cancelled — resume"];
      emit(id, { type: "done", data: { status: "failed" } });
    },
    async timeline(id) {
      await guard();
      must(id);
      return makeTimeline();
    },
    async revise(id, request) {
      await guard();
      const p = must(id);
      if (!request.trim()) throw new ApiError(400, "Type what you want changed.");
      return laterJob(p, "revise", () => {
        const reply = /hook/i.test(request)
          ? "Shortened the hook to 2.6 s by cutting the breath before “then I tried”; the hook title now ends with the line."
          : `Applied: ${request.trim()} — changed the finish plan only; the story order is unchanged.`;
        const n = addVersion(p, `Revision: “${request.trim().slice(0, 48)}”`, reply, 0.088);
        emit(id, { type: "revision", data: { reply, version: n } });
      }, 2600);
    },
    async notesPreview(id, text) {
      await guard();
      must(id);
      const tl = makeTimeline();
      const fps = 30;
      const parsed = parseNotes(text);
      const anchored = parsed.notes.map((n) => {
        if (n.t === null) return `(whole reel) ${n.text}`;
        const f = Math.round(n.t * fps);
        const clip = tl.timeline.video.find((c) => c.at_f <= f && f < c.at_f + c.dur_f);
        if (!clip) return `at ${n.t.toFixed(2)}s (after the end) ${n.text}`;
        const page = tl.timeline.captions?.pages.find((pg) => pg.start_f <= f && f < pg.end_f);
        const caption = page ? `, caption on screen “${page.words.map((w) => w.text).join(" ")}”` : "";
        return `at ${n.t.toFixed(2)}s — item ${clip.src.item}${caption}: ${n.text}`;
      });
      return { anchored, unreadable: parsed.unreadable };
    },
    async notesApply(id, text) {
      await guard();
      const p = must(id);
      const { notes } = parseNotes(text);
      if (!notes.length) throw new ApiError(400, "No readable notes to apply.");
      return laterJob(p, "notes", () => {
        const reply = `Applied ${notes.length} client note${notes.length > 1 ? "s" : ""} in one revision.`;
        const n = addVersion(p, "Client notes", reply, 0.104);
        emit(id, { type: "revision", data: { reply, version: n } });
      }, 2600);
    },
    async proof(id, words) {
      await guard();
      const p = must(id);
      return laterJob(p, "proof", () => {
        const done = new Set(words.map((w) => w.i));
        p.proof = p.proof.filter((w) => !done.has(w.i));
        if (p.verdict_detail) {
          const g = p.verdict_detail.gates.find((x) => x.name === "Caption words confirmed");
          if (g && !p.proof.length) (g.status = "pass"), (g.detail = "all words confirmed");
          p.verdict_detail.reasons = p.verdict_detail.reasons.filter((r) => !/Dioma|misspelt/.test(r) || p.proof.some((w) => w.text === "Dioma"));
          if (!p.verdict_detail.reasons.length) {
            p.verdict_detail.verdict = "sendable";
            p.verdict = "sendable";
            p.status = "sendable";
          }
        }
        if (p.review) p.review.issues = p.review.issues.filter((x) => x.category !== "captions" || p.proof.some((w) => w.text === "Dioma"));
        p.needs_attention = p.proof.length ? [`${p.proof.length} proof word${p.proof.length > 1 ? "s" : ""}`] : [];
        addVersion(p, "Caption fix", `Fixed ${words.length} caption word${words.length > 1 ? "s" : ""}: ${words.map((w) => w.text).join(", ")}`, 0);
      });
    },
    async adjust(id, kind: AdjustKind, value) {
      await guard();
      const p = must(id);
      const issues = validateAdjust(kind, value, { families: LIBRARIES.caption_families.map((f) => f.id), tracks: LIBRARIES.music.map((m) => m.id) });
      if (issues.length) throw new ApiError(422, "The validator refused this change.", { issues });
      return laterJob(p, "adjust", () => {
        addVersion(p, "Manual", `${kind.replace(/_/g, " ")} → ${String(value)}`, 0);
      });
    },
    async versions(id) {
      await guard();
      return clone(must(id).versions);
    },
    async restore(id, n) {
      await guard();
      const p = must(id);
      return laterJob(p, "restore", () => addVersion(p, `Restored v${n}`, `Restored version ${n} as the current reel.`, 0));
    },
    async deliver(id) {
      await guard();
      return laterJob(must(id), "deliver", () => undefined, 900);
    },
    async packageListing(id) {
      await guard();
      must(id);
      return clone(PACKAGE);
    },
    async markDelivered(id) {
      await guard();
      const p = must(id);
      p.delivered_at = new Date().toISOString();
      touch(p);
    },
    async label() {
      await guard();
    },
    async libraries() {
      await guard();
      return clone(LIBRARIES);
    },
    async indexLibrary(_kind, folder) {
      await guard();
      if (!folder.trim()) throw new ApiError(400, "Pick a folder to index.");
      return job();
    },
    async brands() {
      await guard();
      return clone(brands);
    },
    async saveBrand(id, brand, isNew) {
      await guard();
      if (!brand.client.trim()) throw new ApiError(400, "Client name is required.");
      const i = brands.findIndex((b) => b.id === id);
      if (isNew && i !== -1) throw new ApiError(409, `A brand kit “${id}” already exists.`);
      if (i === -1) brands.push({ id, brand: clone(brand) });
      else brands[i] = { id, brand: clone(brand) };
    },
    async lab() {
      await guard();
      return clone(LAB);
    },
    async labAction(action, body) {
      await guard();
      if (action === "eval" && body?.release && LAB.release_locked) throw new ApiError(409, LAB.lock_reason ?? "Release check is locked.");
      return job();
    },
    async costs() {
      await guard();
      return clone(COSTS);
    },
    async settings() {
      await guard();
      return clone(settings);
    },
    async saveSettings(s) {
      await guard();
      if (s.max_jobs < 1 || s.max_jobs > 3) throw new ApiError(400, "Edits at once must be between 1 and 3 (memory guard).");
      settings = clone(s);
      startQueued();
    },
    mediaUrl: () => "",
    libraryMediaUrl: () => "",
    packageZipUrl: () => "",
    subscribe(id, onEvent) {
      const set = subs.get(id) ?? new Set();
      set.add(onEvent);
      subs.set(id, set);
      ensureTicker();
      const p = projects.get(id);
      if (p) setTimeout(() => onEvent(clone({ type: "snapshot", data: p })), 30);
      return () => {
        set.delete(onEvent);
        ensureTicker();
      };
    },
  };
}
