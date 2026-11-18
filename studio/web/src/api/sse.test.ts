import { describe, expect, it, vi } from "vitest";
import { makeProjects } from "./mock/fixtures";
import { applyEvent, parseEventData, subscribeEvents } from "./sse";
import type { Project, SseEvent } from "./types";

class FakeES extends EventTarget {
  static last: FakeES | null = null;
  url: string;
  closed = false;
  constructor(url: string) {
    super();
    this.url = url;
    FakeES.last = this;
  }
  emit(type: string, data: string) {
    this.dispatchEvent(new MessageEvent(type, { data }));
  }
  close() {
    this.closed = true;
  }
}

const running = (): Project => structuredClone(makeProjects().find((p) => p.id === "cafe-opening-reel")!);

describe("parseEventData", () => {
  it("parses known event types and rejects junk", () => {
    expect(parseEventData("stage", '{"name":"story","status":"done"}')).toEqual({ type: "stage", data: { name: "story", status: "done" } });
    expect(parseEventData("stage", "not json")).toBeNull();
    expect(parseEventData("mystery", "{}")).toBeNull();
    expect(parseEventData("log", "42")).toBeNull();
  });
});

describe("subscribeEvents", () => {
  it("dispatches typed events from the wire and closes on unsubscribe", () => {
    const got: SseEvent[] = [];
    const off = subscribeEvents("/api/projects/p1/events?token=x", (e) => got.push(e), undefined, FakeES as unknown as new (u: string) => EventSource);
    const es = FakeES.last!;
    expect(es.url).toBe("/api/projects/p1/events?token=x");
    es.emit("decision", JSON.stringify({ at: 1, kind: "story", title: "Hook", detail: "why", knowledge: [] }));
    es.emit("log", JSON.stringify({ line: "ffmpeg ok" }));
    es.emit("stage", "{broken");
    expect(got.map((e) => e.type)).toEqual(["decision", "log"]);
    off();
    expect(es.closed).toBe(true);
    es.emit("log", JSON.stringify({ line: "after close" }));
    expect(got).toHaveLength(2);
  });

  it("reports errors so the UI can show 'Reconnecting'", () => {
    const onError = vi.fn();
    subscribeEvents("/x", () => {}, onError, FakeES as unknown as new (u: string) => EventSource);
    FakeES.last!.dispatchEvent(new Event("error"));
    expect(onError).toHaveBeenCalledOnce();
  });
});

describe("applyEvent", () => {
  it("starts from a snapshot and ignores events before it", () => {
    const p = running();
    expect(applyEvent(null, { type: "stage", data: p.stages[0] })).toBeNull();
    expect(applyEvent(null, { type: "snapshot", data: p })).toBe(p);
  });

  it("moves the running stage and marks failures (AC-5)", () => {
    let p: Project | null = running();
    p = applyEvent(p, { type: "stage", data: { name: "story", status: "done", started: 1, finished: 2, meta: {} } });
    p = applyEvent(p, { type: "stage", data: { name: "finish", status: "running", started: 2, finished: null, meta: {} } });
    expect(p!.stage).toBe("finish");
    expect(p!.status).toBe("running");
    p = applyEvent(p, { type: "stage", data: { name: "finish", status: "failed", started: 2, finished: 3, meta: {}, error: "The footage has no audio track" } });
    expect(p!.status).toBe("failed");
    expect(p!.stages.find((s) => s.name === "finish")!.error).toBe("The footage has no audio track");
    expect(p!.stages.find((s) => s.name === "story")!.status).toBe("done");
  });

  it("appends decisions once and applies the final verdict", () => {
    const d = { at: 5, kind: "story" as const, title: "Hook: x", detail: "y", knowledge: [] };
    let p = applyEvent(running(), { type: "decision", data: d });
    p = applyEvent(p, { type: "decision", data: d });
    expect(p!.decisions.filter((x) => x.title === "Hook: x")).toHaveLength(1);
    p = applyEvent(p, { type: "done", data: { status: "hold" } });
    expect(p!.status).toBe("hold");
    expect(p!.stage).toBeNull();
  });
});
