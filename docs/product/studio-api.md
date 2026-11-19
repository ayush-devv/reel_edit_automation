# Reel Studio: local API contract (v1)

**Shared by:** the API (`engine/src/reel/studio/`, FastAPI) and the web app (`studio/web/`, React + Vite + React Three Fiber).
**Product spec:** `docs/product/prd-reel-studio.md` (FR-1…FR-12, NFR-1…5, AC-1…17).
**Look:** `docs/product/design-system.md`.

**Change rule:** a change to this contract is a change to this file first, then both sides.

## Running
- `reel studio [--port 8765] [--open] [--dev] [--projects <folder>]`:
  - serves the API and the built web app (`studio/web/dist`, any unknown non-`/api` path falls back to `index.html`) on **127.0.0.1 only**;
  - prints `http://127.0.0.1:8765/?token=<token>`;
  - `--projects` (or `$REEL_PROJECTS_ROOT`) picks the projects folder (default `<repo>/projects`); brand kits live in `<repo>/brands/` (`$REEL_BRANDS_ROOT`).
- **Token:** a per-install secret, generated once (32 random bytes, hex), stored at `~/.config/reel/studio_token` with mode 0600.
  - Every `/api/*` request must carry the header `X-Reel-Token: <token>` (SSE and media may use the query string `?token=`).
  - A missing or wrong token gets 401.
  - CORS is off, except the Vite dev origin `http://127.0.0.1:5173` in `--dev`.
- **Dev:** run Vite on 127.0.0.1:5173 with the proxy `/api` → 127.0.0.1:8765.

## Jobs and concurrency
- **Each edit is a subprocess:** `python -m reel.cli run …`, or `revise` / `notes` / `rerun` / … for the other actions.
  - It runs in the project workspace `projects/<id>/`.
  - Logs go to `projects/<id>/log/studio_job.log` (global jobs: `projects/.studio_logs/{library,lab}.log`).
  - Uploaded footage goes to `projects/<id>/source/raw/` (the run's input; `source/` itself holds the ingest links).
  - Changes made by the owner, not the Editor (proof, adjust, restore, deliver), re-render with `reel rerun --project <p> --from <stage>`: that stage forced, everything after it, **no Editor calls and no fix loop**, so the owner's change is rendered as-is.
- **One job per project** (and one per global slot: `_lab`, `_library`); a second one gets 409 with `detail` = the active `Job`.
- **Cancel** stops the whole process group (SIGTERM, SIGKILL after 10 s); the job keeps its slot until it has exited. A stage the runner left `running` with no live run shows as `failed` with `error` "Interrupted: …"; retry resumes from it.
- **Resource guard (NFR-2):**
  - at most **3** jobs run at once, and the rest queue (strict FIFO);
  - a new job starts only when the estimated memory in use stays under 12 GB, otherwise it waits;
    - "in use" is the sum of the running jobs' estimates (full edit: 3 GB + 0.5 GB per footage minute, max 8; re-render or revision: 2.5 GB + 0.25 GB per reel minute, max 6; eval/improve 6; library 1), not macOS "used" memory;
    - a job always starts when nothing else runs, so one large job never blocks the queue forever;
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

**Additive fields** (present in responses; nothing above is renamed or removed):
- `ProjectSummary`: `client: string | null`, `delivered: string | null` (ISO; set by `POST …/delivered`, sorts the card after "Sendable").
  "Attention first" order: hold, failed, sendable (not delivered), running/queued, draft, delivered; then most recently updated.
- `Project`:
  - `calls: {time, label, cost_usd, duration_s, ok}[]`: every Claude call, `cost_usd` per call (see Costs);
  - `package: {path, name, bytes}[]`: files in `export/package/` (`path` is a media path);
  - `platform_notes: string[]`: the engine's platform warnings (e.g. over the 180 s Reels limit);
  - `media.variants: string[]`: `export/variants/reel_<name>.mp4` media paths;
  - `verdict_detail.warnings: string[]`, `verdict_detail.gates[].measured: object`;
  - `review.sendable: boolean`, `review.strengths: string[]`, `review.issues[].severity`, `review.issues[].fix`.
- `Stage.started` is `null` for finished stages (the runner keeps only `finished`). `skipped` = an optional stage with nothing to do (no b-roll folder, no reference reel).
- `Decision`s come from `plan/story.json` (hook + every kept line with its reason), `plan/finish.json` (captions, hook title, look, music, punch-ins, transitions, SFX, speeds, holds, effects, graphics, b-roll), `plan/history/*_request.json` (revisions), `qa/review.json` (Reviewer notes) and `qa/verdict.json`.

## Endpoints
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | /api/health | — | `{ engine: "ok", version, toolchain_ok: boolean, tools: {name, ok, detail, required}[], claude: boolean, disk_free_gb, jobs: {running, queued, limit}, memory_gb: {used, budget, system: {total, available}}, projects_root }` (`doctor` is cached for 60 s) |
| GET | /api/projects | — | `ProjectSummary[]`, attention first (FR-1) |
| POST | /api/projects | multipart: `files[]` (or `files`; mp4, mov, m4v, mkv, webm, ≤ 4 GB each), `name`, `brief` (JSON string, optional: brief schema in `engine/src/reel/brief.py`; `project` defaults to `name`), `brand` (id, optional), `reference_url` (optional: a **local** video file path; links are refused with 400) | 201 `{ id, job }`; the job is queued. A non-video file is refused with 400 naming it |
| GET | /api/projects/{id} | — | `Project` |
| DELETE | /api/projects/{id} | — | 204 (moves to `projects/.trash/`) |
| GET | /api/projects/{id}/events | SSE (`?token=`) | events below |
| POST | /api/projects/{id}/retry | `{ stage?: string }` | `{ job }` (`reel run` with the stored options; re-runs from that stage with `--force` that stage, or resumes when no stage is given) |
| POST | /api/projects/{id}/cancel | — | 204 |
| GET | /api/projects/{id}/media/{path} | `?token=`; supports Range (206 + `Content-Range`) | the file. Allowed only under `render/`, `export/` (the NLE package is `export/package/`), `qa/sheets/`, `qa/cuts/`, `cover*.jpg`, `versions/`; 404 otherwise; no `..`, no absolute paths, no symlink escaping the project |
| GET | /api/projects/{id}/timeline | — | `{ timeline, story: {[item_id]: {beat, reason, text, clip, word_start, word_end}}, hook: {id, item, rank, reason} \| null, finish: {[id]: {kind, reason, …the plan entry}} }`: `timeline` is `timeline/timeline.json` (layers view, FR-5); `finish` is keyed by entry id for punch-ins, speeds, transitions, sfx, broll, effects, graphics and holds, and by `hook_title`, `captions`, `grade`, `music` for the singletons. 404 before compile |
| POST | /api/projects/{id}/revise | `{ request: string }` | `{ job }`; when done, a `revision` event `{ reply, request, version }` (FR-6) |
| POST | /api/projects/{id}/notes/preview | `{ text: string }` | `{ anchored: string[], notes: {t: number \| null, text}[] }`: each note tied to a time, item and caption (`reel.notes.anchor`); `t: null` = whole reel (FR-7) |
| POST | /api/projects/{id}/notes/apply | `{ text: string }` | `{ job }` |
| POST | /api/projects/{id}/proof | `{ words: {i: number, text: string}[] }` | `{ job }`: `text` equal to the heard word (or empty) confirms it, anything else is the fix; written to `qa/proof_confirmed.json` like `reel proof`, then captions re-render (`rerun --from compile`). 400 for an `i` not on the proof list (FR-4) |
| POST | /api/projects/{id}/adjust | `{ kind, value }`, where kind is one of `caption_family`, `caption_token`, `look`, `look_strength`, `music_track`, `music_gain_db`, `sfx_off`, `punch_ins_off`, `grain`, `vignette`, `max_pause_ms` | `{ job, note? }` or 422 `{ error, issues: {code, path, message, fix, severity}[] }` from the engine's validator (FR-8). Values: ids are strings; `caption_token` is `{key, value}`; numbers for strengths/gains/grain/vignette/`max_pause_ms` (whole ms, 0 or 300–3000); `sfx_off` / `punch_ins_off` take `true` (all off) or a list of ids. `max_pause_ms` lives in `plan/story.json` (validated with `validate_story` too); switching `caption_family` drops the old family's token overrides; `note` says when a brand kit's locked family will win. Then `rerun --from compile` |
| GET | /api/projects/{id}/versions | — | versions list (`Project.versions`). Version 1 ("Original edit") is snapshotted before the first change; each successful revise / notes / adjust / restore adds one (plans + timeline + hard-linked final in `versions/<n>/`) |
| POST | /api/projects/{id}/versions/{n}/restore | — | `{ job }` (plans copied back, `rerun --from compile`) |
| POST | /api/projects/{id}/deliver | `{ variants?: string[] }` (`feed_4x5`, `square`) | `{ job }` (`rerun --from package`); extra variants are kept in `run_options.json` `deliverables`, never in the brief (its fingerprint would re-ask the Editor). Then `Project.package` lists the files (FR-9) |
| POST | /api/projects/{id}/delivered | `{ delivered: boolean }` | 204 (FR-9 "Delivered": records the date) |
| GET | /api/projects/{id}/package.zip | `?token=` | a zip of `export/package/` |
| POST | /api/projects/{id}/label | `{ sendable: boolean, reason: string }` | 204 (the owner's view, ADR-0033 §3); writes `qa/owner_label.json` like `reel label` |
| GET | /api/libraries | — | `{ sfx: {id, category, duration_ms, source, license, file}[], music: {id, title, mood, bpm, duration_ms, source, license, attribution}[], broll: {id, description, shot, tags, duration_ms, source, license, file}[], caption_families: {id, for, mood, max_words, tokens}[] }` (FR-10) |
| POST | /api/libraries/index | `{ kind: "sfx" \| "music", folder: string, source, license, replace?: boolean }` | `{ job }` |
| GET / POST / PUT | /api/brands, /api/brands/{id} | the Brand JSON (`engine/src/reel/brief.py`), plus `id` on POST (default: a slug of `client`) | stored in `brands/<id>.json`; responses are `{ id, …Brand }`; POST of an existing id is 409; invalid Brand is 400 |
| GET | /api/lab | — | `{ gold: {pairs, tuning, holdout, hinglish, reels: {id, split, language, genre, channel, has_final}[]}, release_locked: bool, lock_reason, calibration: {...} \| null, improve_history: [...], scores: {run_id, time, split, mean_primary, vetoed, commit, knowledge, families, reels: {id, primary, verdict, vetoes}[]}[] }` (FR-11) |
| POST | /api/lab/{action} | action is `eval` \| `calibrate` \| `improve`; optional body `{ set?: "tuning" \| "holdout", release?: boolean, budget?, runs?, rounds?, dry_run? }` | `{ job }`. The release check (`release: true` or `set: "holdout"`) is refused with **409** `{ error: <lock reason>, detail: {release_locked: true} }` while locked (ADR-0031: holdout < 6 reels or < 2 Hinglish) |
| GET | /api/costs | `?days=30` | `{ total_usd, calls, by_project: {id, usd}[], by_day: {date, usd}[] }` (FR-12) |
| GET | /api/jobs | — | `{ running: Job[], queued: Job[] }`, where `Job = {id, project, kind, started, status, label, created, finished, est_gb, returncode}` (`started`/`created`/`finished` are epoch seconds; `status`: queued \| running \| done \| failed \| cancelled \| lost) |

**Costs:** per-call cost comes from `log/runs.jsonl`. Claude Code's `total_cost_usd` is cumulative over a resumed session, so a call costs `cum − cum(last call of the session it resumed)`, with `cum = cost_cum_usd` when logged, else `cost_usd` (older rows stored the running total there).

## SSE events (`/api/projects/{id}/events`)
- **Wire format:** `id: <n>`, `event: <type>`, then `data: <json>`.
- **Event types:**
  - `snapshot`, sent first: the `Project`;
  - `stage`: a `Stage` (sent when its status, `finished` or `error` changes);
  - `decision`: a `Decision` not sent before;
  - `log`: `{ line }`, capped at 5 per second (lines from the project's current job log; a backlog keeps the newest 500);
  - `job`: `{ id, kind, status, label }`;
  - `revision`: `{ reply, request, version }` (after a successful revise / notes job);
  - `done`: `{ status, job, kind }` when a job ends (`status` = the project status, `job` = the job's own end status).
- **Keepalive:** a comment every 15 s.
- **Reconnect:** the client reconnects with `Last-Event-ID` and gets a fresh `snapshot`.

## Errors
- JSON body: `{ error: string, detail?: unknown }` (422 adds `issues`, 503 adds `hint`).
- Codes:
  - 400: bad input (including request-body schema errors, which FastAPI would otherwise send as 422);
  - 401: token;
  - 404: not found;
  - 409: a job is already running for that project (one job per project at a time);
  - 422: validator issues;
  - 503: the engine toolchain is missing (`/api/health` says what).
