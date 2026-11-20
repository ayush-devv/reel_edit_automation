import type { Api, JobRef, NewProjectInput, UploadProgress } from "./api";
import { ApiError } from "./errors";
import { subscribeEvents } from "./sse";
import { getToken } from "./token";
import type { AdjustKind, Brand, Settings } from "./types";

type FetchLike = typeof fetch;

const enc = encodeURIComponent;

/** Build the real client. `fetchImpl` and `base` are injectable for tests. */
export function createHttpApi(fetchImpl: FetchLike = (...a) => fetch(...a), base = ""): Api {
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "X-Reel-Token": getToken(), Accept: "application/json" };
    let payload: BodyInit | undefined;
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    let res: Response;
    try {
      res = await fetchImpl(`${base}${path}`, { method, headers, body: payload });
    } catch {
      throw new ApiError(0, "Engine is not running.");
    }
    if (!res.ok) {
      let detail: unknown = null;
      let message = `${res.status} ${res.statusText}`.trim();
      try {
        detail = await res.json();
        if (detail && typeof detail === "object" && "error" in detail) message = String((detail as { error: unknown }).error);
      } catch {
        /* not JSON (e.g. the dev proxy's 502 page) */
      }
      // 4.1 cost guard: past the monthly cap the engine asks first. The owner can say "spend anyway" once, here.
      const over = res.status === 409 && detail && typeof detail === "object" && (detail as { over_cap?: boolean }).over_cap;
      if (over && method === "POST" && body && typeof body === "object" && !(body as { spend_anyway?: boolean }).spend_anyway
          && typeof window !== "undefined" && typeof window.confirm === "function"
          && window.confirm(`${message}. Spend anyway? (You can raise the cap in Settings.)`)) {
        return request<T>(method, path, { ...(body as object), spend_anyway: true });
      }
      throw new ApiError(res.status, message, detail);
    }
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  const get = <T>(p: string) => request<T>("GET", p);
  const post = <T>(p: string, b: unknown = {}) => request<T>("POST", p, b);
  const withToken = (p: string) => `${base}${p}${p.includes("?") ? "&" : "?"}token=${enc(getToken())}`;

  function createProject(input: NewProjectInput, onProgress?: UploadProgress): ReturnType<Api["createProject"]> {
    // XHR, not fetch: fetch has no upload progress, and FR-2 shows a bar per file.
    const form = new FormData();
    for (const f of input.files) form.append("files[]", f, f.name);
    form.append("name", input.name);
    form.append("brief", JSON.stringify(input.brief));
    if (input.brand) form.append("brand", input.brand);
    if (input.reference_url) form.append("reference_url", input.reference_url);
    if (input.stock) form.append("stock", "1");
    if (input.broll_folder) form.append("broll_folder", input.broll_folder);
    if (input.preview_first) form.append("preview_first", "1");
    if (input.mode === "long") form.append("mode", "long");
    if (input.story_checkin) form.append("story_checkin", "1");
    if (input.match_project) form.append("match_project", input.match_project);
    if (input.source_path) form.append("source_path", input.source_path);
    if (input.spend_anyway) form.append("spend_anyway", "1");
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${base}/api/projects`);
      xhr.setRequestHeader("X-Reel-Token", getToken());
      xhr.upload.onprogress = (e) => onProgress?.(e.loaded, e.total);
      xhr.onerror = () => reject(new ApiError(0, "Engine is not running."));
      xhr.onload = () => {
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* empty */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as Awaited<ReturnType<Api["createProject"]>>);
        else {
          const msg = body && typeof body === "object" && "error" in body ? String((body as { error: unknown }).error) : `Upload failed (${xhr.status})`;
          reject(new ApiError(xhr.status, msg, body));
        }
      };
      xhr.send(form);
    });
  }

  return {
    mode: "live",
    health: () => get("/api/health"),
    jobs: () => get("/api/jobs"),
    projects: () => get("/api/projects"),
    project: (id) => get(`/api/projects/${enc(id)}`),
    createProject,
    deleteProject: (id) => request("DELETE", `/api/projects/${enc(id)}`),
    updateProject: (id, patch) => request("PATCH", `/api/projects/${enc(id)}`, patch),
    templates: () => get("/api/templates"),
    saveTemplates: (all) => request("PUT", "/api/templates", { templates: all }),
    fetchStarterPacks: () => post<JobRef>("/api/library/starter-packs"),
    choosePreview: (id, option) => post<JobRef>(`/api/projects/${enc(id)}/preview/choose`, { option }),
    retry: (id, stage) => post<JobRef>(`/api/projects/${enc(id)}/retry`, stage ? { stage } : {}),
    cancel: (id) => post(`/api/projects/${enc(id)}/cancel`),
    timeline: (id) => get(`/api/projects/${enc(id)}/timeline`),
    revise: (id, req) => post(`/api/projects/${enc(id)}/revise`, { request: req }),
    notesPreview: (id, text) => post(`/api/projects/${enc(id)}/notes/preview`, { text }),
    notesApply: (id, text) => post(`/api/projects/${enc(id)}/notes/apply`, { text }),
    proof: (id, words) => post(`/api/projects/${enc(id)}/proof`, { words }),
    adjust: (id, kind: AdjustKind, value) => post(`/api/projects/${enc(id)}/adjust`, { kind, value }),
    versions: (id) => get(`/api/projects/${enc(id)}/versions`),
    restore: (id, n) => post(`/api/projects/${enc(id)}/versions/${n}/restore`),
    deliver: (id, variants) => post(`/api/projects/${enc(id)}/deliver`, variants ? { variants } : {}),
    packageListing: (id) => get(`/api/projects/${enc(id)}/package`),
    markDelivered: (id) => post(`/api/projects/${enc(id)}/delivered`, { delivered: true }),
    reviewLinks: (id) => get(`/api/projects/${enc(id)}/review-links`),
    postCopy: (id) => get(`/api/projects/${enc(id)}/copy`),
    createReviewLink: (id, hours) => post(`/api/projects/${enc(id)}/review-links`, { hours }),
    revokeReviewLink: (id, linkId) => request("DELETE", `/api/projects/${enc(id)}/review-links/${enc(linkId)}`),
    label: (id, sendable, reason) => post(`/api/projects/${enc(id)}/label`, { sendable, reason }),
    clientStyle: (client) => get(`/api/clients/${enc(client)}`),
    checkin: (id) => get(`/api/projects/${enc(id)}/checkin`),
    answerCheckin: (id, yes, note = "") => post(`/api/projects/${enc(id)}/checkin`, { yes, note }),
    clips: (id) => get(`/api/projects/${enc(id)}/clips`),
    makeClips: (id, ids, run = true) => post(`/api/projects/${enc(id)}/clips/make`, { ids, run }),
    libraries: () => get("/api/libraries"),
    indexLibrary: (kind, folder, source, license) => post("/api/libraries/index", { kind, folder, source, license }),
    brands: () => get("/api/brands"),
    saveBrand: (id, brand: Brand, isNew) =>
      isNew ? post(`/api/brands`, { id, brand }) : request("PUT", `/api/brands/${enc(id)}`, brand),
    lab: () => get("/api/lab"),
    labAction: (action, body) => post(`/api/lab/${action}`, body ?? {}),
    setGateMode: (gate, mode) => request("PUT", `/api/lab/gates/${enc(gate)}`, { mode }),
    votePairwise: (run, reel, choice) => post(`/api/lab/pairwise/vote`, { run, reel, choice }),
    pairwiseMediaUrl: (run, reel, side) => withToken(`/api/lab/pairwise/${enc(run)}/${enc(reel)}/${side}`),
    listening: (set) => get(`/api/listening/${set}`),
    prepareListening: (set) => post<JobRef>(`/api/listening/${set}/prepare`),
    voteListening: (set, vote) => post(`/api/listening/${set}/vote`, vote),
    listeningMediaUrl: (set, path) => withToken(`/api/listening/${set}/media/${path.split("/").map(enc).join("/")}`),
    costs: (days = 30) => get(`/api/costs?days=${days}`),
    spend: () => get("/api/spend"),
    approveSpend: (hash) => post(`/api/spend/approve/${enc(hash)}`),
    settings: () => get("/api/settings"),
    saveSettings: (s: Settings) => request("PUT", "/api/settings", s),
    mediaUrl: (id, path, v) =>
      withToken(`/api/projects/${enc(id)}/media/${path.split("/").map(enc).join("/")}`) + (v === undefined ? "" : `&v=${enc(String(v))}`),
    libraryMediaUrl: (kind, id) => withToken(`/api/libraries/${kind}/${enc(id)}/media`),
    packageZipUrl: (id) => withToken(`/api/projects/${enc(id)}/package.zip`),
    subscribe: (id, onEvent, onError) => subscribeEvents(withToken(`/api/projects/${enc(id)}/events`), onEvent, onError),
  };
}
