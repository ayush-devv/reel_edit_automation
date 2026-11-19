import type { Project, SseEvent, Stage } from "./types";

export const SSE_TYPES = ["snapshot", "stage", "decision", "log", "job", "revision", "done"] as const;

/** Turn one SSE message (`event: <type>` + `data: <json>`) into a typed event; null if unreadable. */
export function parseEventData(type: string, raw: string): SseEvent | null {
  if (!(SSE_TYPES as readonly string[]).includes(type)) return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!data || typeof data !== "object") return null;
  return { type, data } as SseEvent;
}

type EventSourceCtor = new (url: string) => EventSource;

/**
 * Subscribe with the browser's EventSource. It reconnects by itself and sends Last-Event-ID;
 * the API answers a reconnect with a fresh `snapshot`, so the reducer below needs no replay logic.
 */
export function subscribeEvents(
  url: string,
  onEvent: (ev: SseEvent) => void,
  onError?: () => void,
  ES: EventSourceCtor = EventSource,
): () => void {
  const es = new ES(url);
  const handlers = SSE_TYPES.map((type) => {
    const h = (msg: Event) => {
      const ev = parseEventData(type, (msg as MessageEvent<string>).data);
      if (ev) onEvent(ev);
    };
    es.addEventListener(type, h);
    return [type, h] as const;
  });
  const err = () => onError?.();
  es.addEventListener("error", err);
  return () => {
    for (const [type, h] of handlers) es.removeEventListener(type, h);
    es.removeEventListener("error", err);
    es.close();
  };
}

function mergeStage(stages: Stage[], s: Stage): Stage[] {
  const i = stages.findIndex((x) => x.name === s.name);
  if (i === -1) return [...stages, s];
  const next = stages.slice();
  next[i] = { ...stages[i], ...s };
  return next;
}

/** Apply one live event to the project state (FR-3). Pure: returns a new object or the same one. */
export function applyEvent(project: Project | null, ev: SseEvent): Project | null {
  if (ev.type === "snapshot") return ev.data;
  if (!project) return project;
  switch (ev.type) {
    case "stage": {
      const stages = mergeStage(project.stages, ev.data);
      const running = stages.find((s) => s.status === "running");
      const failed = stages.find((s) => s.status === "failed");
      const done = stages.filter((s) => s.status === "done" || s.status === "skipped").length;
      return {
        ...project,
        stages,
        stage: running?.name ?? failed?.name ?? project.stage,
        status: failed ? "failed" : running ? "running" : project.status,
        progress: stages.length ? done / stages.length : project.progress,
      };
    }
    case "decision":
      if (project.decisions.some((d) => d.at === ev.data.at && d.title === ev.data.title)) return project;
      return { ...project, decisions: [...project.decisions, ev.data] };
    case "done": {
      const s = ev.data.status;
      const status = s === "sendable" || s === "hold" || s === "failed" || s === "queued" ? s : project.status;
      return { ...project, status, stage: status === "failed" ? project.stage : null };
    }
    default:
      return project;
  }
}
