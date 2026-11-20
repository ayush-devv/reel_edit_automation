# Reel Studio: local API contract (v1)

**Shared by:** the API (`engine/src/reel/studio/`, FastAPI) and the web app (`studio/web/`, React + Vite + React Three Fiber).
**Product spec:** `docs/product/prd-reel-studio.md` (FR-1…FR-12, NFR-1…5, AC-1…17).
**Look:** `docs/product/design-system.md`.
**Types:** `studio/web/src/api/types.ts` is this contract in TypeScript. The web app's mock mode (`?mock=1`, `studio/web/src/api/mock/`) returns exactly these shapes.

**Change rule:** a change to this contract is a change to this file first, then both sides (API + tests, web types + mock).

## Running
- `reel studio [--port 8765] [--open] [--dev] [--projects <folder>]`:
  - serves the API and the built web app (`studio/web/dist`) on **127.0.0.1 only**;
  - any GET that is not under `/api/` and not a file in `dist` gets `index.html` (SPA fallback), so deep links such as `/p/<id>/review` survive a reload (AC-4);
  - prints `http://127.0.0.1:8765/?token=<token>`;
  - `--projects` (or `$REEL_PROJECTS_ROOT`) picks the projects folder (default `<repo>/projects`); brand kits live in `<repo>/brands/` (`$REEL_BRANDS_ROOT`).
- **Token:** a per-install secret, generated once (32 random bytes, hex), stored at `~/.config/reel/studio_token` with mode 0600.
  - Every `/api/*` request carries the header `X-Reel-Token: <token>`.
  - Only the URLs a browser loads directly may pass it as `?token=` instead: SSE (`…/events`), project media (`…/media/…`), `…/package.zip` and library previews (`/api/libraries/{kind}/{id}/media`).
  - A missing or wrong token gets 401.
  - CORS is off, except the Vite dev origin `http://127.0.0.1:5173` in `--dev`.
- **Dev:** run Vite on 127.0.0.1:5173 with the proxy `/api` → 127.0.0.1:8765.
- **Owner preferences** (GET/PUT `/api/settings`) persist in `~/.config/reel/studio_settings.json` (mode 0600; `$REEL_STUDIO_SETTINGS_FILE`), read at start-up.

## Jobs and concurrency
- **Each action is a subprocess:** `python -m reel.cli run …`, or `revise` / `notes` / `rerun` / `library` / `eval` / `calibrate` / `improve`.
  - It runs in the project workspace `projects/<id>/`.
  - Logs go to `projects/<id>/log/studio_job.log` (global jobs: `projects/.studio_logs/{library,lab}.log`).
  - Uploaded footage goes to `projects/<id>/source/raw/` (the run's input; `source/` itself holds the ingest links).
  - Changes made by the owner, not the Editor (proof, adjust, restore, deliver), re-render with `reel rerun --project <p> --from <stage>`: that stage forced, everything after it, **no Editor calls and no fix loop**, so the owner's change is rendered as-is.
  - The Pexels key from Settings reaches the subprocesses as `PEXELS_API_KEY` (never written to the queue file).
- **One job per project** (and one per global slot: `_lab`, `_library`); a second one gets 409 with `detail` = the active `Job`. A terminal `reel` run holding `run.lock` also gives 409 (`detail.kind = "external"`).
- **Cancel** stops the whole process group (SIGTERM, SIGKILL after 10 s); the job keeps its slot until it has exited. A stage the runner left `running` with no live run shows as `failed` with `error` "Interrupted: …"; retry resumes from it.
- **Resource guard (NFR-2):**
  - at most `max_jobs` jobs run at once (Settings, 1–3, default 3), and the rest queue (strict FIFO);
  - a new job starts only when the estimated memory in use stays under 12 GB, otherwise it waits;
    - "in use" is the sum of the running jobs' estimates (full edit: 3 GB + 0.5 GB per footage minute, max 8; re-render or revision: 2.5 GB + 0.25 GB per reel minute, max 6; eval/improve 6; library 1), not macOS "used" memory;
    - a job always starts when nothing else runs, so one large job never blocks the queue forever;
  - queued jobs survive an API restart (the queue lives in `projects/.studio_queue.json`).
- **Progress source of truth:**
  - the runner's `projects/<id>/state.json` (`stages.<name>.status` = running | done | failed, plus `meta`, `started` and `finished`);
  - plus `log/runs.jsonl`, the Claude calls (label, cost, duration).
  - The API polls both every 250 ms and pushes changes over SSE (NFR-3: on screen in ≤ 1 s).
- **Versions (FR-6):** before the first change the finished edit is a *virtual* version 1 ("Original edit", `final = render/final.mp4`). The first revise / notes / proof / adjust / restore snapshots it into `versions/1/`; each one that succeeds adds a version (plans + timeline + hard-linked final in `versions/<n>/`, `meta.json` with `label`, `reply`, `cost_usd`). A revise/notes job that ends `failed` without a `revision` event means the Editor's change failed the validator twice; nothing changed.

## Pipeline stages (display order)
`ingest, mezzanine, perception, tables, broll, reference, story, finish, compile, render, overlay, composite, qa, package, variants`. Each stage has a status of `pending | queued | running | done | failed | skipped`.

## Objects
```ts
type ProjectStatus = "draft" | "queued" | "running" | "sendable" | "hold" | "failed";
type ProjectSummary = {
  id: string; name: string; client: string | null;
  created: string /*ISO*/; updated: string /*ISO*/;
  status: ProjectStatus; stage: string | null; progress: number /*0..1*/;
  duration_s: number | null; cost_usd: number;
  verdict: "sendable" | "hold" | null;
  needs_attention: string[];   // e.g. "3 proof words", "failed: render", "hold: 2 reasons"
  thumb: string | null;        // media path (cover.jpg, frame at 1 s of the latest render)
  delivered_at: string | null; // ISO, set by POST …/delivered
};
type Stage = { name: string; status: StageStatus; started: number | null; finished: number | null /*epoch s*/;
  meta: Record<string, unknown>; error?: string };   // started is null for finished stages (the runner keeps only finished)
type Decision = { at: number /*epoch s*/; kind: "story" | "finish" | "review" | "revision" | "qa";
  title: string; detail: string; knowledge: string[]; cost_usd?: number };
type Gate = { name: string /*engine gate id, e.g. "reading_speed"*/; status: "pass" | "warn" | "fail"; detail: string; measured: object };
type Version = { n: number; created: string; label: string; final?: string /*media path*/; reply: string; cost_usd: number | null };
type Project = ProjectSummary & {
  brief: Brief | null; brand: string | null;
  stages: Stage[]; decisions: Decision[];
  verdict_detail: { verdict: string; reasons: string[]; warnings: string[]; gates: Gate[] } | null;
  proof: { i: number; text: string; suggestion: string | null; at: string /*"0:28.79"*/; frame: number; why: string }[];
  review: { summary: string; sendable: boolean | null; strengths: string[];
            issues: { at: string; category: string; text: string; severity: "blocker" | "major" | "minor" | null; fix: string }[] } | null;
  media: { final?: string; review_copy?: string; cover?: string; sheets: string[]; cut_strips: string[]; variants: string[] };
  versions: Version[];
  calls: { time: number | null; label: string; cost_usd: number; duration_s: number | null; ok: boolean }[];
  platform_notes: string[];   // the engine's platform warnings (e.g. over the 180 s Reels limit)
  eta_s: number | null;       // seconds left; null = unknown (the web app estimates from typical stage times, labelled "≈")
};
type Job = { id: string; project: string /*or "_lab" | "_library"*/; kind: string; label: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "lost";
  created: number; started: number | null; finished: number | null /*epoch s*/; est_gb: number; returncode: number | null };
type JobRef = { job: Job };   // what every POST that starts work returns; SSE `job` events carry the same job.id
```

- **Attention order (FR-1):** hold, failed, sendable, running, queued, draft, then delivered; most recently updated first within a group. "Delivered" = `delivered_at` set **and** the edit is finished (sendable or hold); a delivered reel that is re-editing shows as running.
- **`review.issues[].at`** is the Reviewer's free text: one timecode, a range, or several (`"0:03.2, 0:38.2–0:44.2"`); `""` means the whole reel. Seek to the first timecode.
- **`Decision`s** come from `plan/story.json` (hook + every kept line with its reason), `plan/finish.json` (captions, hook title, look, music, punch-ins, transitions, SFX, speeds, holds, effects, graphics, b-roll), `plan/history/*_request.json` (revisions), `qa/review.json` (the Reviewer's summary and each note) and `qa/verdict.json`. `cost_usd` sits on the hook (all `story*` calls), the captions decision (`finish*` calls) and the Reviewer summary (`review*` calls).
- **Version labels:** `"Original edit"`, `"Revision: “<request>”"`, `"Client notes"`, `"Caption fix"`, `"Manual"` (guided adjustment; `reply` = what changed, e.g. `"look strength → 0.5"`), `"Restored v<n>"`. `reply` is the Editor's one-line reply for revisions and notes.

## Endpoints
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | /api/health | — | `{ engine: "ok", version, toolchain_ok, tools: {name, ok, detail, required}[], claude, disk_free_gb, jobs: {running, queued, limit}, memory_gb: {used, budget, system: {total, available}}, projects_root }` (`doctor` is cached for 60 s) |
| GET | /api/jobs | — | `{ running: Job[], queued: Job[] }` |
| GET | /api/projects | — | `ProjectSummary[]`, attention first (FR-1) |
| POST | /api/projects | multipart: `files[]` (or `files`; mp4, mov, m4v, mkv, webm, ≤ 4 GB each), `name`, `brief` (JSON string, optional; `project` defaults to `name`), `brand` (id, optional), `reference_url` (optional: a **local** video file path; links are refused with 400) | 201 `{ id, job: Job }`; the job is queued. A non-video file is refused with 400 naming it |
| GET | /api/projects/{id} | — | `Project` |
| DELETE | /api/projects/{id} | — | 204 (moves to `projects/.trash/`) |
| GET | /api/projects/{id}/events | SSE (`?token=`) | events below |
| POST | /api/projects/{id}/retry | `{ stage?: string }` | `JobRef` (`reel run` with the stored options; re-runs from that stage with `--force` that stage, or resumes when no stage is given) |
| POST | /api/projects/{id}/cancel | — | 204 |
| GET | /api/projects/{id}/media/{path} | `?token=`; supports Range (206 + `Content-Range`); unknown query parameters (e.g. a `&v=` cache-buster) are ignored | the file. Allowed only under `render/`, `export/`, `qa/sheets/`, `qa/cuts/`, `versions/`, and `cover*.jpg`; 404 otherwise; no `..`, no absolute paths, no symlink escaping the project |
| GET | /api/projects/{id}/timeline | — | `TimelineView` (below). 404 before compile |
| POST | /api/projects/{id}/revise | `{ request: string }` | `JobRef`; when done, a `revision` event (FR-6) |
| POST | /api/projects/{id}/notes/preview | `{ text: string }` (one note per line) | `{ anchored: string[], notes: {t: number \| null, text}[], unreadable: string[] }`: `anchored[i]` belongs to the i-th non-empty line sent, tied to a time, line and caption (`reel.notes.anchor`); `t: null` = whole reel (FR-7). The web app drops lines it can't read before sending and shows them as "not sent" (AC-11) |
| POST | /api/projects/{id}/notes/apply | `{ text: string }` | `JobRef` |
| POST | /api/projects/{id}/proof | `{ words: {i: number, text: string}[] }` | `JobRef`: `text` equal to the heard word (or empty) confirms it, anything else is the fix; written to `qa/proof_confirmed.json` like `reel proof`, then `rerun --from compile`. 400 for an `i` not on the proof list (FR-4, AC-6) |
| POST | /api/projects/{id}/adjust | `{ kind, value }` (table below) | `{ job: Job, note?: string }` or 422 `{ error, issues: {code, path, message, fix, severity}[] }` from the engine's validator (FR-8, AC-12). Then `rerun --from compile` |
| GET | /api/projects/{id}/versions | — | `Version[]` (same as `Project.versions`) |
| POST | /api/projects/{id}/versions/{n}/restore | — | `JobRef` (plans copied back, `rerun --from compile`); 404 unknown version, 400 for the current version |
| POST | /api/projects/{id}/deliver | `{ variants?: ("feed_4x5" \| "square")[] }` | `JobRef` (`rerun --from package`); extra variants are kept in `run_options.json` `deliverables`, never in the brief (its fingerprint would re-ask the Editor) |
| GET | /api/projects/{id}/package | — | `{ files: PackageFile[], warnings: string[] }` (FR-9, below) |
| GET | /api/projects/{id}/package.zip | `?token=` | a zip of `export/package/` |
| POST | /api/projects/{id}/delivered | `{ delivered?: boolean }` (default `true`; `false` clears it) | 204; sets `delivered_at` (FR-9) |
| POST | /api/projects/{id}/label | `{ sendable: boolean, reason: string }` | 204 (the owner's "Would you post this?", ADR-0033 §3); writes `qa/owner_label.json` like `reel label` |
| GET | /api/libraries | — | `Libraries` (below, FR-10) |
| GET | /api/libraries/{kind}/{id}/media | `?token=`; Range; `kind` = `sfx \| music \| broll` | the indexed file (play buttons). 404 when the id isn't indexed or its file isn't on this Mac |
| POST | /api/libraries/index | `{ kind: "sfx" \| "music", folder, source, license, replace?: boolean }` | `JobRef` |
| GET | /api/brands | — | `{ id, brand: Brand }[]` (`Brand` = `engine/src/reel/brief.py`, `extra="forbid"`; the id is the file name, never inside `brand`) |
| GET | /api/brands/{id} | — | `{ id, brand }` |
| POST | /api/brands | `{ id?: string, brand: Brand }` (`id` defaults to a slug of `client`) | 201 `{ id, brand }`; 409 if the id exists; 400 for an invalid Brand or id |
| PUT | /api/brands/{id} | the bare `Brand` | `{ id, brand }`; stored in `brands/<id>.json` |
| GET | /api/lab | — | `Lab` (below, FR-11) |
| POST | /api/lab/{action} | `eval` \| `calibrate` \| `improve`; optional body `{ set?: "tuning" \| "holdout", release?: boolean, budget?: int, runs?, rounds?, dry_run? }` | `JobRef`. The release check (`release: true` or `set: "holdout"`) is refused with **409** `{ error: <lock reason>, detail: {release_locked: true} }` while locked (ADR-0031: holdout < 6 reels or < 2 Hinglish). `budget` counts **reel runs** (edits of one gold reel), not dollars |
| POST | /api/lab/bakeoff | — | `JobRef` (`reel bakeoff` on `samples/hinglish/`, C5); 400 when there are no sample clips. `Lab.bakeoff` = `{ engines_now, samples, latest: {at, summary} \| null }` |
| PUT | /api/lab/gates/{gate} | `{ mode: "warn" \| "block" }` | `{ gate, mode, recomputed }` (C3). Block only when calibration's `promote_to_block` is true (or the code already blocks it), else **409**. Stored in `~/.config/reel/gates.json`; every idle project's verdict is re-decided from its stored `qa/gates.json` + `qa/review.json`, with **no Reviewer call** |
| GET | /api/projects/{id}/clips | — | Clip Factory board (G2.2): `{ source_s, yield_cap, target_s, score_label: "Editor's estimate", score_rule, candidates: {id, rank, title, hook_text, family, scores, score, duration_s, status, why, reason, standalone_risks, warnings, excerpt, project: {id, status} \| null}[], estimate_per_reel: {low_usd, high_usd, from_edits} \| null }`. 404 before the source is mined |
| POST | /api/projects/{id}/clips/make | `{ ids: string[], run?: boolean = true }` | `{ made: string[], jobs: Job[] }`: one reel project per candidate (`<source>__<id>`, files shared by hard link), each edit queued when `run`. Picks are logged to `mine/picks.jsonl` |
| GET | /api/projects/{id}/checkin | — | 3a.1 story check-in `{ status: "open" \| "approved", summary, hook, lines, total_s, left_out, questions: {id, kind: "hook" \| "take" \| "drop", text, why}[], warnings }`; 404 when the edit has none. While open, the project status is `awaiting_story` |
| POST | /api/projects/{id}/checkin | `{ yes: string[], note?: string }` | `JobRef`: `reel checkin --approve --continue` applies the accepted questions (and the note: 1 Claude call), approves the story and finishes the edit. 409 when no check-in is open, 400 for an unknown question |
| GET | /api/lab/pairwise/{run}/{reel}/{side} | `?token=`; `side` = `A \| B` | 3b.2 one of the two reels of a judged eval pair, sides hidden (`pairwise.side_of_ours`) |
| POST | /api/lab/pairwise/vote | `{ run, reel, choice: "A" \| "B" \| "same" }` | 204: the owner's blind pick (`eval/pairwise_owner.jsonl`); `Lab.pairwise` = `{ last, last_run, agreement: {n, agree, rate}, pending }` |
| GET | /api/clients/{name} | — | 3a.2 `{ client, profile \| null, reels: {id, name, why, has_video}[] }`: the client's style from reels marked delivered or labelled sendable (`projects/.clients/<slug>.json`) |
| GET | /api/listening/{set} | `set` = `sfx \| music \| voice` | `{ set, prompts, pairs: {id, prompt, A, B, done}[], summary }` (G2.5): blind pairs, no model names; `summary` names models only with their votes |
| POST | /api/listening/{set}/prepare | — | `JobRef` (`reel listen prepare`) |
| POST | /api/listening/{set}/vote | `{ pair, choice: "A" \| "B" \| "tie", usable_a, usable_b }` | 204 |
| GET | /api/listening/{set}/media/{path} | `?token=` | a rendered file of that set only |
| GET | /api/costs | `?days=30` | `{ total_usd, calls, by_project: {id, usd}[], by_day: {date, usd}[] }`: `by_day` lists every day of the window, oldest first, zeros included (FR-12) |
| GET | /api/settings | — | `Settings` (below) |
| PUT | /api/settings | `Settings` (+ write-only `pexels_key`) | the saved `Settings` |

### Timeline view (FR-5, FR-8)
```ts
type TimelineView = {
  timeline: Timeline;                 // timeline/timeline.json with every default filled in (older files omit effects, graphics, grade.grain, …)
  reasons: Record<string, string>;    // the Editor's reason, keyed like the layer blocks:
  //   plan item id (k01…; the hook item also carries the hook reason), punch-in / speed / freeze → the item's video clip id (v_k04),
  //   dialogue clip id (a_k04), sfx / pip / effect / graphic / transition plan id, full-frame b-roll clip (br_<id>),
  //   and hook_title, grade, captions, music
  story: Record<string, { beat: string; text: string }>;   // kept lines: item id → beat and spoken text
  adjust: { caption_family: string | null; caption_tokens: Record<string, string>; look: string; look_strength: number;
            grain: number; vignette: number; music_track: string; music_gain_db: number;
            max_pause_ms: number | null; sfx: number; punch_ins: number };   // current value of every adjustment
};
```

### Adjust values (FR-8)
| kind | value |
|---|---|
| `caption_family` | string (family id); drops the old family's token overrides; `note` says when a brand kit's locked family will win |
| `caption_token` | `{ key: string, value: string }` (colours as `#RRGGBB`) |
| `look` | string (`reel.color.LOOKS` id) |
| `look_strength` | number 0–1 |
| `music_track` | string (music id or `"none"`; `"none"` also turns beat pulses off) |
| `music_gain_db` | number −30…−6 |
| `sfx_off`, `punch_ins_off` | `true` (all off) or a list of ids to remove |
| `grain` | number 0–0.6 |
| `vignette` | number 0–0.7 |
| `max_pause_ms` | integer: 0, or 300–3000 (a **story** setting, `plan/story.json`, validated with `validate_story` too) |
| `story_words` | `{ item, remove: [[first, last], …] }` (3a.3): cut words out of one kept line; it splits into `k07`, `k07b`… and attached elements follow their words (`TimelineView.story[id].words` lists `[index, text]`) |
| `story_lines` | the kept item ids in their new order; an id left out is dropped (C4). Finish elements bound to a dropped item go with it (`note` counts them); whole-reel graphics move to the new opener; 422 with `hint` "describe it in Revise" when the finish no longer fits |

Numbers must be JSON numbers (a string is 400). Every applied adjustment is logged to `plan/adjustments.jsonl`; a later chat revision is told to keep the ones still in force and warns (`adjustment_reverted`) when it changes one the request doesn't mention. Not available yet: trimming inside a line (AC-12).

`POST /api/projects` also takes `story_checkin=1` (3a.1: stop after the story pass) and `match_project=<id>` (3a.2: that project's finished reel becomes the reference to match; 400 when it has none). It also takes `mode=long`: a long recording that is analysed once and mined (`reel run --mine`); the project's `kind` is `source`, its status `source` once the board is ready. Reel projects made from it have `kind: "clip"` and `parent`.

### Package (FR-9)
`PackageFile = { path, label, kind, bytes, thumb }`:
- `path` is relative to the project folder and is a media path for files (a folder ends in `/` and is listed, not served);
- `kind` is `final | variant | review_copy | timeline | captions | stems | overlay | edit_list | other`;
- the final is `export/package/reel.mp4` (else `render/final.mp4`) with `thumb: "cover.jpg"`; variants are `export/variants/reel_<name>.mp4`; the review copy is `export/review/review.mp4`; `export/package/stems/` is one entry (bytes summed);
- `warnings` = the engine's platform notes + credit lines the music licence asks for.

### Libraries, lab, settings
```ts
type Libraries = {
  sfx: { id, category, duration_ms, source, license, file }[];
  music: { id, title, mood, bpm, duration_ms, source, license, attribution: string | null }[];
  broll: { id, description, shot, tags: string[], duration_ms, source, license, file }[];
  caption_families: { id, for: string[], mood, max_words: number | null, tokens: Record<string, string> }[];
  unreadable: { kind, file, reason }[];   // always [] until the indexer reports skipped files (AC-14 gap)
};
type Lab = {
  gold: { pairs, tuning, holdout, hinglish };
  gold_pairs: { id, split: "tuning" | "holdout", language, source /*channel*/ }[];
  release_locked: boolean; lock_reason: string | null;
  calibration: null | {                     // null before any owner label and any automatic calibration
    agreement: number | null /*0–1, Reviewer vs owner labels*/; n_labels: number; trusted: boolean; rule: string | null;
    gates: { name, mode: "warn" | "block", false_alarm_rate: number | null, catch_rate: number | null, promote_to_block: boolean }[];
    // false alarms from owner-sendable renders when labels exist, else from the automatic calibration on pro finals (ADR-0033)
  };
  runs: { id, at: string | null, split, primary /*0–1*/, families: Record<string, number>, vetoed: number,
          reels: { id, primary: number | null, verdict: string | null, vetoes: string[] }[] }[];   // scoreboard rows with a score
  improve_history: { at: string | null, round: number | null, change: string,
                     outcome: "accepted" | "rejected" | "invalid" | "dry_run", gain: number | null /*0–1 scale*/, reason: string | null }[];
};
type Settings = {
  max_jobs: 1 | 2 | 3;                       // feeds the job queue at once
  projects_dir: string;                      // read-only: the running server's folder (change it with `reel studio --projects`); 400 if a PUT changes it
  default_brief: Partial<Brief>;             // validated as a Brief; prefills New edit
  default_deliverables: ("feed_4x5" | "square")[];
  pexels_key_set: boolean;                   // the key itself is never returned; PUT `pexels_key` sets it, "" or absent keeps it
};
```
Scores: the engine's primary score is 0–100; the API divides by 100.

## SSE events (`/api/projects/{id}/events`)
- **Wire format:** `id: <n>`, `event: <type>`, then `data: <json>`.
- **Event types:**
  - `snapshot`, sent first: the `Project`;
  - `stage`: a `Stage` (sent when its status, `finished` or `error` changes);
  - `decision`: a `Decision` not sent before;
  - `log`: `{ line }`, capped at 5 per second (lines from the project's current job log; a backlog keeps the newest 500);
  - `job`: `{ id, kind, status, label }` (`id` = the `job.id` the POST returned);
  - `revision`: `{ reply, request, version }` (after a successful revise / notes job);
  - `done`: `{ status, job, kind }` when a job ends (`status` = the project status, `job` = the job's own end status), **followed by a fresh `snapshot`** (verdict, proof list, versions and media after the change).
- **Keepalive:** a comment every 15 s.
- **Reconnect:** the client reconnects with `Last-Event-ID` and gets a fresh `snapshot`.

## Errors
- JSON body: `{ error: string, detail?: unknown }` (422 adds `issues`, 503 adds `hint`).
- Codes:
  - 400: bad input (including request-body schema errors, which FastAPI would otherwise send as 422);
  - 401: token;
  - 404: not found (an unknown `/api/…` path too);
  - 409: a job is already running for that project, or the release check is locked;
  - 422: the engine validator's issues;
  - 503: the engine toolchain is missing (`/api/health` says what).

## Not available yet
The web app shows these as "not available yet"; no endpoint exists:
- review links that work outside this Mac (the studio binds 127.0.0.1; ui-backend-plan E3 is the owner's decision);
- "Open in Finder" / "Open in Final Cut Pro" (the web app offers "Copy path");
- b-roll files on project create (FR-2);
- a server-side `eta_s` (always `null`);
- the improve log has no timestamps yet (`at: null`), and the library indexer does not report unreadable files yet (`unreadable: []`).
