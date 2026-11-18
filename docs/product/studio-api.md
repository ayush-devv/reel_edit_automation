# Reel Studio: local API contract (v1)

**Shared by:** the API (`engine/src/reel/studio/`, FastAPI) and the web app (`studio/web/`, React + Vite + React Three Fiber).
**Product spec:** `docs/product/prd-reel-studio.md` (FR-1…FR-12, NFR-1…5, AC-1…17).
**Look:** `docs/product/design-system.md`.

**Change rule:** a change to this contract is a change to this file first, then both sides.

## Running
- `reel studio [--port 8765] [--open]`:
  - serves the API and the built web app (`studio/web/dist`) on **127.0.0.1 only**;
  - prints `http://127.0.0.1:8765/?token=<token>`.
- **Token:** a per-install secret, generated once (32 random bytes, hex), stored at `~/.config/reel/studio_token` with mode 0600.
  - Every `/api/*` request must carry the header `X-Reel-Token: <token>` (SSE and media may use the query string `?token=`).
  - A missing or wrong token gets 401.
  - CORS is off, except the Vite dev origin `http://127.0.0.1:5173` in `--dev`.
- **Dev:** run Vite on 127.0.0.1:5173 with the proxy `/api` → 127.0.0.1:8765.

## Jobs and concurrency
- **Each edit is a subprocess:** `python -m reel.cli run …`, or `revise` / `notes` / `proof` / … for the other actions.
  - It runs in the project workspace `projects/<id>/`.
  - Logs go to `projects/<id>/log/studio_job.log`.
- **Resource guard (NFR-2):**
  - at most **3** jobs run at once, and the rest queue (FIFO);
  - a new job starts only when the estimated memory in use stays under 12 GB, otherwise it waits;
  - queued jobs survive an API restart (the queue lives in `projects/.studio_queue.json`).
- **Progress source of truth:**
  - the runner's `projects/<id>/state.json` (`stages.<name>.status` = running | done | failed, plus `meta`, `started` and `finished`);
  - plus `log/runs.jsonl`, the Claude calls (label, cost, duration).
  - The API polls both every 250 ms and pushes changes over SSE (NFR-3: on screen in ≤ 1 s).

## Pipeline stages (display order)
`ingest, mezzanine, perception, tables, broll, reference, story, finish, compile, render, overlay, composite, qa, package, variants`. Each stage has a status of `pending | queued | running | done | failed | skipped`.

## Objects
```ts
type ProjectSummary = { id: string; name: string; created: string /*ISO*/; updated: string;
  status: "draft" | "queued" | "running" | "sendable" | "hold" | "failed";
  stage: string | null; progress: number /*0..1*/; duration_s: number | null; cost_usd: number;
  verdict: "sendable" | "hold" | null; needs_attention: string[] /*e.g. "3 proof words", "failed: render"*/;
  thumb: string | null /*media path*/ };
type Stage = { name: string; status: string; started: number | null; finished: number | null; meta: Record<string, unknown>; error?: string };
type Decision = { at: number; kind: "story" | "finish" | "review" | "revision" | "qa"; title: string; detail: string; knowledge: string[] };
type Project = ProjectSummary & { brief: Record<string, unknown> | null; brand: string | null; stages: Stage[];
  decisions: Decision[]; verdict_detail: { verdict: string; reasons: string[]; gates: {name: string; status: "pass"|"warn"|"fail"; detail: string}[] } | null;
  proof: { i: number; text: string; suggestion: string | null; at: string; frame: number; why: string }[];
  review: { summary: string; issues: { at: string; category: string; text: string }[] } | null;
  media: { final?: string; review_copy?: string; cover?: string; sheets: string[]; cut_strips: string[] };
  versions: { n: number; created: string; label: string; final?: string }[] };
```

## Endpoints
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | /api/health | — | `{ engine: "ok", version, tools: {name, ok, detail}[], claude: boolean, disk_free_gb, jobs: {running, queued, limit}, memory_gb: {used, budget} }` |
| GET | /api/projects | — | `ProjectSummary[]`, attention first (FR-1) |
| POST | /api/projects | multipart: `files[]` (video), `name`, `brief` (JSON string, optional: brief schema in `engine/src/reel/brief.py`), `brand` (id, optional), `reference_url` (optional) | `{ id }`; the job is queued |
| GET | /api/projects/{id} | — | `Project` |
| DELETE | /api/projects/{id} | — | 204 (moves to `projects/.trash/`) |
| GET | /api/projects/{id}/events | SSE (`?token=`) | events below |
| POST | /api/projects/{id}/retry | `{ stage?: string }` | `{ job }` (re-runs from that stage; `--force` that stage) |
| POST | /api/projects/{id}/cancel | — | 204 |
| GET | /api/projects/{id}/media/{path} | `?token=`; supports Range | the file. Allowed only under `render/`, `export/`, `qa/sheets/`, `qa/cuts/`, `package/`, `cover*.jpg`, `versions/`; 404 otherwise; no `..` |
| GET | /api/projects/{id}/timeline | — | `timeline/timeline.json` (layers view, FR-5) plus `plan/story.json` and `plan/finish.json` reasons, keyed by item / id |
| POST | /api/projects/{id}/revise | `{ request: string }` | `{ job }`; when done, a `revision` event `{ reply, version }` (FR-6) |
| POST | /api/projects/{id}/notes/preview | `{ text: string }` | `{ anchored: string[] }`: each note tied to a time, item and caption (`reel.notes.anchor`) (FR-7) |
| POST | /api/projects/{id}/notes/apply | `{ text: string }` | `{ job }` |
| POST | /api/projects/{id}/proof | `{ words: {i: number, text: string}[] }` | `{ job }`: confirms or fixes the words, then re-renders the captions (FR-4) |
| POST | /api/projects/{id}/adjust | `{ kind, value }`, where kind is one of `caption_family`, `caption_token`, `look`, `look_strength`, `music_track`, `music_gain_db`, `sfx_off`, `punch_ins_off`, `grain`, `vignette`, `max_pause_ms` | `{ job }` or 422 with validator issues `{ issues: {code, path, message, fix}[] }` (FR-8) |
| GET | /api/projects/{id}/versions | — | versions list |
| POST | /api/projects/{id}/versions/{n}/restore | — | `{ job }` |
| POST | /api/projects/{id}/deliver | `{ variants?: string[] }` | `{ job }`; then `package` lists the files (FR-9) |
| GET | /api/projects/{id}/package.zip | `?token=` | a zip of `package/` |
| POST | /api/projects/{id}/label | `{ sendable: boolean, reason: string }` | 204 (the owner's view, ADR-0033 §3) |
| GET | /api/libraries | — | `{ sfx: {id, category, duration_ms, source, license}[], music: {id, title, mood, bpm, duration_ms, source, license, attribution}[], broll: […], caption_families: {id, for, mood}[] }` (FR-10) |
| POST | /api/libraries/index | `{ kind: "sfx" \| "music", folder: string, source, license }` | `{ job }` |
| GET / POST / PUT | /api/brands, /api/brands/{id} | the Brand JSON (`engine/src/reel/brief.py`) | stored in `brands/<id>.json` |
| GET | /api/lab | — | `{ gold: {pairs, tuning, holdout, hinglish}, release_locked: bool, lock_reason, calibration: {...} \| null, improve_history: [...] }` (FR-11) |
| POST | /api/lab/{action} | action is `eval` \| `calibrate` \| `improve` | `{ job }` (`eval --release` is refused while locked, ADR-0031) |
| GET | /api/costs | `?days=30` | `{ total_usd, by_project: {id, usd}[], by_day: {date, usd}[] }` (FR-12) |
| GET | /api/jobs | — | `{ running: Job[], queued: Job[] }`, where `Job = {id, project, kind, started, status}` |

## SSE events (`/api/projects/{id}/events`)
- **Wire format:** `event: <type>` followed by `data: <json>`.
- **Event types:**
  - `snapshot`, sent first: the `Project`;
  - `stage`: a `Stage`;
  - `decision`: a `Decision`;
  - `log`: `{ line }`, capped at 5 per second;
  - `job`: `{ id, kind, status }`;
  - `revision`: `{ reply, version }`;
  - `done`: `{ status }`.
- **Keepalive:** a comment every 15 s.
- **Reconnect:** the client reconnects with `Last-Event-ID` and gets a fresh `snapshot`.

## Errors
- JSON body: `{ error: string, detail?: unknown }`.
- Codes:
  - 400: bad input;
  - 401: token;
  - 404: not found;
  - 409: a job is already running for that project (one job per project at a time);
  - 422: validator issues;
  - 503: the engine toolchain is missing (`/api/health` says what).
