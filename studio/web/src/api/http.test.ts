import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import { createHttpApi } from "./http";
import { captureUrlParams, getToken } from "./token";

function json(status: number, body: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("token", () => {
  it("captures ?token= into sessionStorage and strips it from the URL", () => {
    const replace = vi.fn();
    captureUrlParams({ href: "http://127.0.0.1:8765/p/x/live?token=abc123&tab=1#top" } as Location, { state: null, replaceState: replace } as unknown as History);
    expect(getToken()).toBe("abc123");
    expect(replace).toHaveBeenCalledWith(null, "", "/p/x/live?tab=1#top");
  });
});

describe("http client", () => {
  it("sends X-Reel-Token on every API call", async () => {
    sessionStorage.setItem("reel.token", "s3cret");
    const fetchMock = vi.fn(async (..._args: Parameters<typeof fetch>) => json(200, []));
    const api = createHttpApi(fetchMock as unknown as typeof fetch);
    await api.projects();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/projects");
    expect((init?.headers as Record<string, string>)["X-Reel-Token"]).toBe("s3cret");
  });

  it("posts JSON bodies for actions", async () => {
    const fetchMock = vi.fn(async (..._args: Parameters<typeof fetch>) => json(200, { job: "j1" }));
    const api = createHttpApi(fetchMock as unknown as typeof fetch);
    await expect(api.proof("p1", [{ i: 42, text: "DearMa" }])).resolves.toEqual({ job: "j1" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/projects/p1/proof");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ words: [{ i: 42, text: "DearMa" }] });
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("turns a 422 into validator issues", async () => {
    const issues = [{ code: "must_keep", path: "story.items", message: "This removes a must-keep line", fix: "Keep k04." }];
    const api = createHttpApi((async () => json(422, { error: "invalid", issues })) as unknown as typeof fetch);
    const err = await api.adjust("p1", "max_pause_ms", 100).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe("validation");
    expect(err.issues).toEqual(issues);
  });

  it("classifies engine down, proxy errors and auth", async () => {
    const down = createHttpApi((async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch);
    await expect(down.health()).rejects.toMatchObject({ kind: "offline" });
    const proxy = createHttpApi((async () => new Response("Bad gateway", { status: 502 })) as unknown as typeof fetch);
    await expect(proxy.health()).rejects.toMatchObject({ kind: "offline" });
    const auth = createHttpApi((async () => json(401, { error: "bad token" })) as unknown as typeof fetch);
    await expect(auth.health()).rejects.toMatchObject({ kind: "auth", message: "bad token" });
  });

  it("puts the token in media, zip and SSE URLs (they can't send headers)", () => {
    sessionStorage.setItem("reel.token", "t/k");
    const api = createHttpApi(vi.fn() as unknown as typeof fetch);
    expect(api.mediaUrl("p 1", "render/final.mp4")).toBe("/api/projects/p%201/media/render/final.mp4?token=t%2Fk");
    expect(api.packageZipUrl("p1")).toBe("/api/projects/p1/package.zip?token=t%2Fk");
    const off = api.subscribe("p1", () => {});
    off();
  });
});
