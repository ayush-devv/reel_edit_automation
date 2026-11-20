"""Reel Studio API (contract: docs/product/studio-api.md). Build with `create_app()`; serve with `reel studio`."""

from __future__ import annotations

import json
import re
import secrets
import shutil
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from reel import config
from reel.studio import auth, catalog, costs, events, projects, review_links
from reel.studio.jobs import ESTIMATE_GB, JobConflict, JobManager, estimate_render_gb, estimate_run_gb
from reel.studio.settings import MAX_JOBS_LIMIT, Settings, apply_prefs, load_prefs, save_prefs
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}  # FR-2
MAX_UPLOAD_FILES = 4  # a request larger than this many 4 GB files is refused before it is read
TOO_BIG_HINT = "for a long recording, name the file on this Mac instead of uploading it (it's used where it is, without a copy)"


def local_video(raw: str) -> Path | None:
    """A video file already on this Mac, used in place (no upload). Refuses links, folders and non-video files."""
    raw = raw.strip().removeprefix("file://")
    if not raw:
        return None
    if re.match(r"^[a-z]+://", raw):
        raise ApiError(400, "the video must be a file on this Mac (links are not supported)")
    p = Path(raw).expanduser().resolve()
    if not p.is_file():
        raise ApiError(400, f"no such file on this Mac: {raw}")
    if p.suffix.lower() not in VIDEO_EXT:
        raise ApiError(400, f"{p.name}: not a video file (mp4, mov, m4v, mkv, webm)")
    return p
ADJUST_KINDS = ("caption_family", "caption_token", "look", "look_strength", "music_track", "music_gain_db", "sfx_off",
                "punch_ins_off", "grain", "vignette", "max_pause_ms", "story_lines", "story_words", "beauty")
STORY_KINDS = ("max_pause_ms", "story_lines", "story_words")  # adjustments that change plan/story.json
PROJECT_JOBS = ("run", "retry", "revise", "notes", "proof", "adjust", "restore", "deliver")
GLOBAL_SLOTS = ("_lab", "_library")  # job slots that are not projects


class ApiError(Exception):
    def __init__(self, status: int, error: str, detail: Any = None, **extra):
        self.status, self.error, self.detail, self.extra = status, error, detail, extra


# ------------------------------------------------------------------ request bodies


class RetryBody(BaseModel):
    stage: str | None = None
    spend_anyway: bool = False


class ReviseBody(BaseModel):
    request: str = Field(min_length=1, max_length=4000)
    spend_anyway: bool = False


class NotesBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    spend_anyway: bool = False


class ProofWord(BaseModel):
    i: int
    text: str = Field(max_length=200)


class ProofBody(BaseModel):
    words: list[ProofWord] = Field(min_length=1)


class AdjustBody(BaseModel):
    kind: Literal[ADJUST_KINDS]  # type: ignore[valid-type]
    value: Any = None


class DeliverBody(BaseModel):
    variants: list[str] | None = None


class DeliveredBody(BaseModel):
    delivered: bool = True


class ReviewLinkBody(BaseModel):
    hours: float = Field(72, ge=1, le=24 * 30)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    client: str | None = Field(default=None, max_length=120)


class PreviewChoice(BaseModel):
    option: Literal["A", "B"]


class TemplatesBody(BaseModel):
    templates: dict[str, dict[str, Any]] = Field(default_factory=dict)


class PairwiseVoteBody(BaseModel):
    run: str = Field(min_length=1, max_length=120)
    reel: str = Field(min_length=1, max_length=200)
    choice: Literal["A", "B", "same"]


class CheckinBody(BaseModel):
    yes: list[str] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=2000)
    spend_anyway: bool = False


class VoteBody(BaseModel):
    pair: str = Field(min_length=1, max_length=80)
    choice: Literal["A", "B", "tie"]
    usable_a: bool = False
    usable_b: bool = False


class GateModeBody(BaseModel):
    mode: Literal["warn", "block"]


class MakeClipsBody(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=20)
    run: bool = True  # queue an edit of each new reel
    spend_anyway: bool = False


class LabelBody(BaseModel):
    sendable: bool
    reason: str = Field(default="", max_length=4000)


class IndexBody(BaseModel):
    kind: Literal["sfx", "music"]
    folder: str = Field(min_length=1)
    source: str = Field(min_length=1, max_length=200)
    license: str = Field(min_length=1, max_length=500)
    replace: bool = False


class SettingsBody(BaseModel):
    max_jobs: int = Field(ge=1, le=MAX_JOBS_LIMIT)
    projects_dir: str | None = None  # read-only: `reel studio --projects <folder>` sets it
    default_brief: dict = Field(default_factory=dict)
    default_deliverables: list[Literal["feed_4x5", "square"]] = Field(default_factory=list)
    pexels_key: str | None = Field(default=None, max_length=200)  # write-only; "" or absent keeps the saved key
    pixabay_key: str | None = Field(default=None, max_length=200)  # write-only; "" or absent keeps the saved key
    monthly_cap_usd: float | None = Field(default=None, ge=0, le=100_000)  # 4.1: 0 = no cap; absent keeps the saved cap
    public_review_url: str | None = Field(default=None, max_length=300)  # 4.3: https://… of the owner's tunnel; "" clears it


class PerformanceBody(BaseModel):
    """4.4: one reading as the platform showed it (any subset of the numbers)."""
    post_url: str | None = Field(default=None, max_length=500)
    platform: Literal["instagram", "youtube", "other"] | None = None
    views: float | None = None
    reach: float | None = None
    avg_watch_s: float | None = None
    skip_rate: float | None = None
    likes: float | None = None
    comments: float | None = None
    shares: float | None = None
    saves: float | None = None


class LabBody(BaseModel):
    set: Literal["tuning", "holdout"] = "tuning"
    release: bool = False
    budget: int = Field(default=100, ge=1, le=10000)  # reel runs (one edit of one gold reel), not dollars
    runs: int = Field(default=3, ge=1, le=20)
    rounds: int = Field(default=5, ge=1, le=50)
    dry_run: bool = False


# ------------------------------------------------------------------ app


def create_app(settings: Settings | None = None, launcher=None) -> FastAPI:
    s = settings or Settings()
    s.projects_root.mkdir(parents=True, exist_ok=True)
    token = auth.load_or_create_token(s.token_file)
    if s.prefs_file.exists():
        apply_prefs(s, load_prefs(s.prefs_file))
    doctor = catalog._Doctor(s.doctor)
    mgr = JobManager(s, launcher=launcher, on_finish=lambda job: _after_job(s, job))

    @asynccontextmanager
    async def lifespan(_app):
        if s.start_scheduler:
            mgr.start()
        yield
        mgr.stop()

    app = FastAPI(title="Reel Studio", version="1", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.settings, app.state.mgr, app.state.token = s, mgr, token
    app.add_middleware(auth.TokenMiddleware, token=token)
    if s.dev:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ApiError)
    async def _api_error(_req, exc: ApiError):
        body = {"error": exc.error, **({"detail": exc.detail} if exc.detail is not None else {}), **exc.extra}
        return JSONResponse(jsonable_encoder(body), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_req, exc: StarletteHTTPException):
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _bad_input(_req, exc: RequestValidationError):  # 422 is reserved for the engine's validator
        return JSONResponse({"error": "bad input", "detail": jsonable_encoder(exc.errors())}, status_code=400)

    # -------------------------------------------------------------- helpers

    def ws_of(pid: str) -> Path:
        ws = projects.project_dir(s.projects_root, pid)
        if ws is None:
            raise ApiError(404, f"no project {pid!r}")
        return ws

    def cli(*args) -> list[str]:
        return [s.python, "-m", "reel.cli", *[str(a) for a in args]]

    def need_toolchain() -> None:
        rep = doctor.get()
        if not rep.get("ok"):
            missing = [i["name"] for i in rep.get("items", []) if i.get("required", True) and not i["ok"]]
            raise ApiError(503, "the engine toolchain is missing", missing, hint="GET /api/health says what to install")

    def submit(pid: str, kind: str, argv: list[str], *, ws: Path | None = None, est_gb: float, label: str = "", after: dict | None = None,
               log: Path | None = None) -> dict:
        if kind in PROJECT_JOBS:
            need_toolchain()
        try:
            job = mgr.submit(pid, kind, argv, cwd=ws or config.REPO_ROOT, log=log or (ws / "log" / "studio_job.log"),
                             est_gb=est_gb, label=label, after=after)
        except JobConflict as exc:
            raise ApiError(409, "a job is already running for this project", exc.job.public()) from exc
        return job.public()

    def busy(pid: str, ws: Path | None = None, *, toolchain: bool = True) -> None:
        """Refuse before anything is written: toolchain missing (503), a studio job or a terminal `reel` run active (409)."""
        if toolchain:
            need_toolchain()
        if (j := mgr.active(pid)) is not None:
            raise ApiError(409, "a job is already running for this project", j.public())
        if ws is not None and projects.lock_alive(ws):
            raise ApiError(409, "another `reel` run holds this project (run.lock)", {"project": pid, "kind": "external"})

    def reel_s(ws: Path) -> float | None:
        return projects.summary(ws).get("duration_s")

    def baseline(ws: Path) -> None:
        """The edit as it was before the first change becomes version 1."""
        if not projects.has_snapshots(ws) and (ws / "render" / "final.mp4").exists():
            projects.snapshot(ws, "Original edit")

    def build_project(pid: str, ws: Path) -> dict:
        projects.ensure_cover(ws)
        return projects.detail(ws, mgr.project_state(pid))

    # -------------------------------------------------------------- health, projects

    @app.get("/api/health")
    def health():
        return catalog.health(s, doctor, mgr)

    @app.get("/api/projects")
    def list_projects():
        out = []
        for ws in projects.list_dirs(s.projects_root):
            projects.ensure_cover(ws)
            out.append(projects.summary(ws, mgr.project_state(ws.name)))
        return sorted(out, key=projects.attention_key)

    @app.post("/api/projects", status_code=201)
    async def create_project(request: Request):
        need_toolchain()
        size = int(request.headers.get("content-length") or 0)  # checked before the body is parsed (parsing buffers it to disk)
        if size > s.max_upload_bytes * MAX_UPLOAD_FILES:
            raise ApiError(413, "this upload is too large", hint=TOO_BIG_HINT)
        free = shutil.disk_usage(s.projects_root if s.projects_root.exists() else s.projects_root.parent).free
        if size and free < 2 * size + (2 << 30):  # the parser's buffer + the copy + headroom
            raise ApiError(507, "not enough free disk for this upload", hint=TOO_BIG_HINT)
        form = await request.form(max_files=100, max_fields=50)
        name = str(form.get("name") or "").strip()
        if not name or len(name) > 120:
            raise ApiError(400, "a project name (1–120 characters) is required")
        spend_guard(str(form.get("spend_anyway") or "").strip().lower() in ("1", "true", "on"))
        files = [f for f in [*form.getlist("files[]"), *form.getlist("files")] if isinstance(f, UploadFile)]
        source_path = local_video(str(form.get("source_path") or ""))
        if files and source_path:
            raise ApiError(400, "upload files or name a file on this Mac, not both")
        if not files and not source_path:
            raise ApiError(400, "upload at least one video file, or name a video file on this Mac")
        for f in files:
            if Path(f.filename or "").suffix.lower() not in VIDEO_EXT:
                raise ApiError(400, f"{f.filename}: not a video file (mp4, mov, m4v, mkv, webm)", {"file": f.filename})
            if f.size is not None and f.size > s.max_upload_bytes:
                raise ApiError(400, f"{f.filename}: larger than 4 GB", {"file": f.filename}, hint=TOO_BIG_HINT)
        brief = None
        if form.get("brief"):
            from reel.brief import Brief

            try:
                raw = json.loads(str(form["brief"]))
                brief = Brief.model_validate({"project": name, **raw})
            except (ValueError, ValidationError) as exc:
                raise ApiError(400, "the brief is not valid", jsonable_encoder(getattr(exc, "errors", lambda: str(exc))())) from exc
        brand_id = str(form.get("brand") or "").strip() or None
        brand_file = catalog.brand_path(s.brands_root, brand_id) if brand_id else None
        if brand_id and (brand_file is None or not brand_file.exists()):
            raise ApiError(400, f"no brand kit {brand_id!r}")
        broll_raw = str(form.get("broll_folder") or "").strip().removeprefix("file://")
        broll_folder = str(Path(broll_raw).expanduser().resolve()) if broll_raw else None
        if broll_raw and (re.match(r"^[a-z]+://", broll_raw) or not Path(broll_folder).is_dir()):
            raise ApiError(400, "the b-roll folder must be a folder on this Mac")
        reference = str(form.get("reference_url") or "").strip().removeprefix("file://") or None
        if reference and (re.match(r"^[a-z]+://", reference) or not Path(reference).expanduser().is_file()):
            raise ApiError(400, "reference_url must be a local video file (links are not supported)")
        match = str(form.get("match_project") or "").strip()
        if match:  # 3a.2 "edit like this past reel": its final becomes the reference reel
            past = projects.project_dir(s.projects_root, match)
            if past is None or not (past / "export" / "reel.mp4").exists():
                raise ApiError(400, f"no finished reel in project {match!r} to match")
            reference = str(past / "export" / "reel.mp4")

        pid = f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:48] or 'reel'}-{secrets.token_hex(2)}"
        ws = Workspace.create(s.projects_root / pid).root
        raw_dir = ws / "source" / "raw"  # not source/ itself: ingest symlinks its clips there
        raw_dir.mkdir(parents=True, exist_ok=True)
        footage = 0.0
        try:
            for f in files:
                safe = re.sub(r"[^\w.\- ]+", "_", Path(f.filename).name).lstrip(".")
                dst = raw_dir / (safe if Path(safe).suffix.lower() in VIDEO_EXT and Path(safe).stem else f"clip{Path(safe).suffix.lower()}")
                written = 0
                with open(dst, "wb") as out:
                    while chunk := await f.read(1 << 20):
                        written += len(chunk)
                        if written > s.max_upload_bytes:
                            raise ApiError(400, f"{f.filename}: larger than 4 GB", {"file": f.filename}, hint=TOO_BIG_HINT)
                        out.write(chunk)
                footage += _duration(dst)
        except ApiError:
            shutil.rmtree(ws, ignore_errors=True)
            raise
        if source_path:  # used where it is: no upload, no copy (a long recording can be tens of GB)
            footage = _duration(source_path)
        if brief:
            atomic_write_json(ws / "brief.json", brief.model_dump(mode="json"))
        projects.update_studio_meta(ws, name=name, created=time.time(), client=brief.client if brief else None, brand=brand_id,
                                    footage_s=round(footage, 2) or None, **({"source_path": str(source_path)} if source_path else {}))
        opts = {"input": str(source_path or raw_dir), "brief": str(ws / "brief.json") if brief else None, "brand": str(brand_file) if brand_file else None,
                "reference": str(Path(reference).expanduser().resolve()) if reference else None, "language": None,
                "stock": str(form.get("stock") or "").strip().lower() in ("1", "true", "on"),
                "preview_first": str(form.get("preview_first") or "").strip().lower() in ("1", "true", "on"),
                "story_checkin": str(form.get("story_checkin") or "").strip().lower() in ("1", "true", "on"),
                "broll": broll_folder}
        if str(form.get("mode") or "").strip() == "long":  # Clip Factory (G2.2): analyse once, then a board of candidate reels
            opts = {k: v for k, v in opts.items() if k not in ("preview_first", "story_checkin")} | {"mine": True}
            projects.update_studio_meta(ws, kind="source")
        job = submit(pid, "run", cli(*_run_args(ws, opts)), ws=ws, est_gb=estimate_run_gb(footage or None),
                     label="Find reels" if opts.get("mine") else "Edit")
        return {"id": pid, "job": job}

    @app.get("/api/projects/{pid}")
    def get_project(pid: str):
        return build_project(pid, ws_of(pid))

    @app.patch("/api/projects/{pid}", status_code=204)
    def patch_project(pid: str, body: ProjectPatch):
        """Rename / set the client (UI plan A2): the Studio's label only. The brief the Editor read is never edited, so
        nothing is re-planned; the licence gate falls back to this client when the brief names none."""
        ws = ws_of(pid)
        fields = body.model_dump(exclude_unset=True)
        if "name" in fields:
            fields["name"] = fields["name"].strip()
            if not fields["name"]:
                raise ApiError(400, "a project name (1–120 characters) is required")
        if "client" in fields:
            fields["client"] = (fields["client"] or "").strip() or None
        if fields:
            projects.update_studio_meta(ws, **fields)
        return Response(status_code=204)

    # brief templates (UI plan D1): server-side so they survive a cleared browser and follow the owner across browsers
    def templates_file() -> Path:
        return s.prefs_file.parent / "templates.json"

    @app.get("/api/templates")
    def get_templates():
        f = templates_file()
        return json.loads(f.read_text()) if f.exists() else {}

    @app.put("/api/templates")
    def put_templates(body: TemplatesBody):
        if len(body.templates) > 200 or any(len(k) > 120 or not k.strip() for k in body.templates):
            raise ApiError(400, "template names must be 1–120 characters (at most 200 templates)")
        f = templates_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(f, body.templates)
        f.chmod(0o600)
        return body.templates

    @app.post("/api/library/starter-packs")
    def starter_packs():
        """The built-in procedural + Kenney CC0 SFX and Incompetech CC BY music (UI plan C2), as a library job."""
        return {"job": submit("_library", "assets_fetch", cli("assets", "fetch"), est_gb=ESTIMATE_GB["library"], label="Get the starter packs",
                              log=s.projects_root / ".studio_logs" / "library.log")}

    @app.delete("/api/projects/{pid}", status_code=204)
    def delete_project(pid: str):
        ws = ws_of(pid)
        busy(pid, ws, toolchain=False)
        s.trash.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ws), str(s.trash / f"{pid}-{time.strftime('%Y%m%d-%H%M%S')}"))
        return Response(status_code=204)

    @app.get("/api/projects/{pid}/events")
    async def project_events(pid: str, request: Request):
        ws = ws_of(pid)
        return StreamingResponse(events.stream(request, ws, pid, mgr, s, lambda: build_project(pid, ws)), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/projects/{pid}/retry")
    def retry(pid: str, body: RetryBody | None = None):
        ws = ws_of(pid)
        stage = body.stage if body else None
        if stage and stage not in (*projects.STAGES, "mine"):
            raise ApiError(400, f"unknown stage {stage!r}", projects.STAGES)
        opts = projects.read_json(ws / "run_options.json")
        if not opts or not (opts.get("input") or opts.get("parent")):
            raise ApiError(400, "this project has never been started (no run_options.json)")
        busy(pid, ws)
        spend_guard(bool(body and body.spend_anyway))
        footage = projects.studio_meta(ws).get("footage_s")
        return {"job": submit(pid, "retry", cli(*_run_args(ws, opts, force=stage)), ws=ws, est_gb=estimate_run_gb(footage),
                              label=f"Retry from {stage}" if stage else "Resume")}

    @app.post("/api/projects/{pid}/preview/choose")
    def preview_choose(pid: str, body: PreviewChoice):
        """The A/B hook pick (roadmap G1.6): apply it to the plan, then render the full reel."""
        from reel import preview

        ws = ws_of(pid)
        opts = projects.read_json(ws / "run_options.json")
        if not opts or not opts.get("input"):
            raise ApiError(400, "this project has never been started (no run_options.json)")
        busy(pid, ws)
        try:
            preview.choose(Workspace(ws), body.option)
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        footage = projects.studio_meta(ws).get("footage_s")
        opts = {k: v for k, v in opts.items() if k != "preview_first"}
        return {"job": submit(pid, "run", cli(*_run_args(ws, opts)), ws=ws, est_gb=estimate_run_gb(footage), label=f"Edit with look {body.option}")}

    @app.get("/api/projects/{pid}/checkin")
    def checkin_get(pid: str):
        from reel import checkin

        c = checkin.load(Workspace(ws_of(pid)))
        if c is None:
            raise ApiError(404, "this edit has no story check-in")
        return c

    @app.post("/api/projects/{pid}/checkin")
    def checkin_answer(pid: str, body: CheckinBody):
        """3a.1: accept some of the questions (and/or a note), approve the story, and finish the edit as one job."""
        from reel import checkin

        ws = ws_of(pid)
        c = checkin.load(Workspace(ws))
        if not c or c.get("status") != "open":
            raise ApiError(409, "there is no open story check-in for this project")
        unknown = [q for q in body.yes if q not in {x["id"] for x in c["questions"]}]
        if unknown:
            raise ApiError(400, f"unknown question(s): {', '.join(unknown)}")
        busy(pid, ws)
        spend_guard(body.spend_anyway)
        args = ["checkin", "--project", ws, "--approve", "--continue"]
        if body.yes:
            args += ["--yes", ",".join(body.yes)]
        if body.note.strip():
            args += ["--note", body.note.strip()]
        footage = projects.studio_meta(ws).get("footage_s")
        return {"job": submit(pid, "run", cli(*args), ws=ws, est_gb=estimate_run_gb(footage), label="Story approved: finishing the edit")}

    @app.post("/api/projects/{pid}/cancel", status_code=204)
    def cancel(pid: str):
        ws_of(pid)
        mgr.cancel(pid)
        return Response(status_code=204)

    @app.get("/api/projects/{pid}/media/{path:path}")
    def media(pid: str, path: str):
        p = projects.media_path(ws_of(pid), path)
        if p is None:
            raise ApiError(404, "not found")
        return FileResponse(p)

    @app.get("/api/projects/{pid}/timeline")
    def timeline(pid: str):
        view = projects.timeline_view(ws_of(pid))
        if view is None:
            raise ApiError(404, "no timeline yet (the edit has not reached compile)")
        return view

    # -------------------------------------------------------------- changes: revise, notes, proof, adjust, versions

    @app.post("/api/projects/{pid}/revise")
    def revise(pid: str, body: ReviseBody):
        ws = ws_of(pid)
        _need_edit(ws)
        busy(pid, ws)
        spend_guard(body.spend_anyway)
        baseline(ws)
        req = " ".join(body.request.split())
        return {"job": submit(pid, "revise", cli("revise", "--project", ws, "--", body.request), ws=ws, est_gb=estimate_render_gb(reel_s(ws)),
                              label=f"Revision: {req[:80]}", after={"snapshot": f"Revision: “{req[:120]}”"})}

    @app.post("/api/projects/{pid}/notes/preview")
    def notes_preview(pid: str, body: NotesBody):
        from reel import notes

        ws = ws_of(pid)
        tl, story, words = _edit_inputs(ws)
        parsed = notes.parse(body.text)  # one note per non-empty line, so anchored[i] is the i-th line sent
        return {"anchored": [notes.anchor(n, tl, story, words).removeprefix("- ") for n in parsed],
                "notes": [{"t": n.t, "text": n.text} for n in parsed], "unreadable": []}

    @app.post("/api/projects/{pid}/notes/apply")
    def notes_apply(pid: str, body: NotesBody):
        from reel import notes

        ws = ws_of(pid)
        _need_edit(ws)
        if not notes.parse(body.text):
            raise ApiError(400, "no notes found in the text")
        busy(pid, ws)
        spend_guard(body.spend_anyway)
        baseline(ws)
        f = ws / "log" / f"notes_{time.strftime('%Y%m%d-%H%M%S')}.txt"
        atomic_write_bytes(f, body.text.encode())
        return {"job": submit(pid, "notes", cli("notes", "--project", ws, f), ws=ws, est_gb=estimate_render_gb(reel_s(ws)),
                              label="Client notes", after={"snapshot": "Client notes"})}

    @app.post("/api/projects/{pid}/proof")
    def proof(pid: str, body: ProofBody):
        ws = ws_of(pid)
        _need_edit(ws)
        known = {int(p["i"]): p for p in [*(projects.read_json(ws / "qa" / "proof_list.json", []) or []),
                                          *((projects.read_json(ws / "qa" / "verdict.json", {}) or {}).get("proof_open") or [])]}
        unknown = [w.i for w in body.words if w.i not in known]
        if unknown:
            raise ApiError(400, "these words are not on the proof list", unknown)
        busy(pid, ws)
        baseline(ws)
        path = ws / "qa" / "proof_confirmed.json"
        conf = projects.read_json(path, {}) or {}
        said = []
        for w in body.words:  # same file `reel proof` writes: ok as heard, or the corrected text
            text = w.text.strip()
            heard = known[w.i].get("text")
            conf[str(w.i)] = {"ok": True} if not text or text == heard else {"ok": True, "text": text}
            said.append(f"“{heard}” confirmed" if not text or text == heard else f"“{heard}” → “{text}”")
        atomic_write_json(path, conf)
        return {"job": submit(pid, "proof", cli("rerun", "--project", ws, "--from", "compile"), ws=ws, est_gb=estimate_render_gb(reel_s(ws)),
                              label=f"Proof: {len(body.words)} word(s)",
                              after={"snapshot": "Caption fix", "reply": "Caption words: " + ", ".join(said)})}

    @app.post("/api/projects/{pid}/adjust")
    def adjust(pid: str, body: AdjustBody):
        ws = ws_of(pid)
        _need_edit(ws)
        busy(pid, ws)
        if body.kind == "beauty":  # 3c.1: the project's own switch; no plan changes, so only the picture re-renders
            from reel import beauty

            if body.value not in ("off", "light"):
                raise ApiError(400, "beauty is off or light")
            baseline(ws)
            atomic_write_json(ws / beauty.OVERRIDE_FILE, {"mode": body.value})
            _log_adjustment(ws, body.kind, body.value)
            change = f"beauty pass → {body.value}"
            return {"job": submit(pid, "adjust", cli("rerun", "--project", ws, "--from", "render"), ws=ws,
                                  est_gb=estimate_render_gb(reel_s(ws)), label=f"Manual: {change}",
                                  after={"snapshot": "Manual", "reply": change})}
        story, fin, note = _apply_adjust(ws, body.kind, body.value)
        baseline(ws)
        if body.kind in STORY_KINDS:  # only then: a re-dumped story.json changes bytes, which the finish stage fingerprints
            atomic_write_json(ws / "plan" / "story.json", story.model_dump(mode="json"))
            if body.kind in ("story_lines", "story_words"):  # the Reviewer reads the read-back: keep it in step with the new story
                from reel import decide

                try:
                    atomic_write_bytes(ws / "plan" / "story_readback.txt", decide.readback(decide.load_inputs(Workspace(ws)), story).encode())
                except Exception:  # noqa: BLE001 — a stale read-back must never fail the owner's edit
                    import logging

                    logging.getLogger(__name__).exception("story read-back not refreshed for %s", pid)
        atomic_write_json(ws / "plan" / "finish.json", fin.model_dump(mode="json"))
        _log_adjustment(ws, body.kind, body.value)
        change = f"{body.kind.replace('_', ' ')} → {_show(body.value)}"
        job = submit(pid, "adjust", cli("rerun", "--project", ws, "--from", "compile"), ws=ws, est_gb=estimate_render_gb(reel_s(ws)),
                     label=f"Manual: {change}", after={"snapshot": "Manual", "reply": change})
        return {"job": job, **({"note": note} if note else {})}

    @app.get("/api/projects/{pid}/versions")
    def versions(pid: str):
        return projects.versions(ws_of(pid))

    @app.post("/api/projects/{pid}/versions/{n}/restore")
    def restore(pid: str, n: int):
        ws = ws_of(pid)
        vs = projects.versions(ws)
        if not any(v["n"] == n for v in vs):
            raise ApiError(404, f"no version {n}")
        if not projects.has_snapshots(ws) or n == vs[-1]["n"]:
            raise ApiError(400, f"version {n} is the current version")
        busy(pid, ws)
        if not projects.restore_plans(ws, n):
            raise ApiError(400, f"version {n} has no plans to restore")
        return {"job": submit(pid, "restore", cli("rerun", "--project", ws, "--from", "compile"), ws=ws, est_gb=estimate_render_gb(reel_s(ws)),
                              label=f"Restore version {n}", after={"snapshot": f"Restored v{n}", "reply": f"Restored version {n} as the current reel."})}

    # -------------------------------------------------------------- delivery, labels

    @app.post("/api/projects/{pid}/deliver")
    def deliver(pid: str, body: DeliverBody | None = None):
        from reel.variants import PROFILES

        ws = ws_of(pid)
        _need_edit(ws)
        wanted = (body.variants if body else None) or []
        bad = [v for v in wanted if v not in PROFILES]
        if bad:
            raise ApiError(400, f"unknown variant(s) {bad}", sorted(PROFILES))
        busy(pid, ws)
        opts = projects.read_json(ws / "run_options.json", {}) or {}
        opts["deliverables"] = list(dict.fromkeys([*(opts.get("deliverables") or []), *wanted]))
        atomic_write_json(ws / "run_options.json", opts)
        return {"job": submit(pid, "deliver", cli("rerun", "--project", ws, "--from", "package"), ws=ws, est_gb=estimate_render_gb(reel_s(ws)),
                              label="Deliver" + (f" ({', '.join(wanted)})" if wanted else ""))}

    @app.get("/api/projects/{pid}/package")
    def package(pid: str):
        return projects.package_listing(ws_of(pid))

    @app.get("/api/projects/{pid}/package.zip")
    def package_zip(pid: str):
        ws = ws_of(pid)
        pkg = ws / "export" / "package"
        if not pkg.exists() or not any(pkg.iterdir()):
            raise ApiError(404, "no package yet")
        (ws / "log").mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".package-", suffix=".zip", dir=ws / "log", delete=False) as tf:
            tmp = Path(tf.name)
            with zipfile.ZipFile(tf, "w") as z:
                for f in sorted(pkg.rglob("*")):
                    if f.is_file():  # media is already compressed: store it; text compresses
                        packed = f.suffix.lower() in (".md", ".srt", ".vtt", ".fcpxml", ".otio", ".json", ".txt")
                        z.write(f, f"{pid}/{f.relative_to(pkg)}", compress_type=zipfile.ZIP_DEFLATED if packed else zipfile.ZIP_STORED)
        return FileResponse(tmp, media_type="application/zip", filename=f"{pid}-package.zip",
                            background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))

    # -------------------------------------------------------------- Clip Factory (G2.2)

    @app.get("/api/projects/{pid}/clips")
    def clips_board(pid: str):
        ws = ws_of(pid)
        try:
            return projects.clips_view(ws, s.projects_root, mgr.project_state)
        except FileNotFoundError as exc:
            raise ApiError(404, "no candidates yet: the recording is still being analysed, or this is not a long recording") from exc

    @app.post("/api/projects/{pid}/clips/make")
    def clips_make(pid: str, body: MakeClipsBody):
        from reel import clipfactory

        ws = ws_of(pid)
        busy(pid, ws, toolchain=body.run)
        if body.run:
            spend_guard(body.spend_anyway)
        try:
            made = clipfactory.spawn(Workspace(ws), body.ids)
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        jobs = []
        for root in made:
            if body.run and mgr.active(root.name) is None:
                jobs.append(submit(root.name, "run", cli(*_run_args(root, projects.read_json(root / "run_options.json") or {})), ws=root,
                                   est_gb=estimate_render_gb(None), label="Edit"))
        return {"made": [p.name for p in made], "jobs": jobs}

    @app.post("/api/projects/{pid}/label", status_code=204)
    def label(pid: str, body: LabelBody):
        ws = ws_of(pid)
        atomic_write_json(ws / "qa" / "owner_label.json", {"sendable": body.sendable, "note": body.reason})  # as `reel label`
        delivered = bool(projects.studio_meta(ws).get("delivered"))
        _client_memory(ws, "owner_sendable" if body.sendable else ("delivered" if delivered else None))
        return Response(status_code=204)

    @app.post("/api/projects/{pid}/delivered", status_code=204)
    def delivered(pid: str, body: DeliveredBody | None = None):
        body = body or DeliveredBody()
        ws = ws_of(pid)
        projects.update_studio_meta(ws, delivered=time.time() if body.delivered else None)
        label = projects.read_json(ws / "qa" / "owner_label.json") or {}
        _client_memory(ws, "delivered" if body.delivered else ("owner_sendable" if label.get("sendable") else None))
        return Response(status_code=204)

    @app.get("/api/clients/{name}")
    def client_style(name: str):
        """3a.2: the client's style profile from approved reels, and those reels (for "match a past reel"); 4.4: how they did."""
        from reel import client_memory, performance

        s_ = client_memory.slug(name)
        f = s.projects_root / ".clients" / f"{s_}.json" if s_ else None
        data = client_memory._read(f)
        reels = sorted(data.get("reels", {}).values(), key=lambda r: -r.get("approved", 0))
        return {"client": data.get("client") or name, "profile": client_memory.profile_of(data),
                "reels": [{"id": r["project"], "name": projects.studio_meta(s.projects_root / r["project"]).get("name") or r["project"],
                           "why": r.get("why"), "has_video": (s.projects_root / r["project"] / "export" / "reel.mp4").exists()} for r in reels],
                "performance": performance.client_report(s.projects_root, name)}

    # -------------------------------------------------------------- performance after posting (4.4)

    @app.get("/api/projects/{pid}/performance")
    def performance_get(pid: str):
        from reel import performance

        ws = Workspace(ws_of(pid))
        data = performance.load(ws)
        e = None
        try:
            from reel import client_memory

            e = client_memory.entry(ws)
        except Exception:  # noqa: BLE001 — the numbers still show without the reel's own description
            e = None
        last = performance.latest(ws)
        return {**data, "hold_rate": performance.hold_rate(last, (e or {}).get("length_s")) if last else None,
                "length_s": (e or {}).get("length_s")}

    @app.post("/api/projects/{pid}/performance")
    def performance_add(pid: str, body: PerformanceBody):
        from reel import performance

        ws = Workspace(ws_of(pid))
        try:
            performance.record(ws, body.model_dump(exclude={"post_url", "platform"}, exclude_none=True),
                               post_url=body.post_url or None, platform=body.platform)
        except performance.PerformanceError as exc:
            raise ApiError(400, str(exc)) from exc
        return performance_get(pid)

    # -------------------------------------------------------------- libraries, brands

    @app.get("/api/libraries")
    def libraries():
        return catalog.libraries()

    @app.get("/api/libraries/{kind}/{item_id}/media")
    def library_media(kind: Literal["sfx", "music", "broll"], item_id: str):
        p = catalog.library_file(kind, item_id)
        if p is None:
            raise ApiError(404, f"no {kind} file for {item_id!r}")
        return FileResponse(p)

    @app.post("/api/libraries/index")
    def index_library(body: IndexBody):
        folder = Path(body.folder).expanduser()
        if not folder.is_dir():
            raise ApiError(400, f"not a folder: {body.folder}")
        args = ["library", body.kind, folder.resolve(), "--source", body.source, "--license", body.license] + (["--replace"] if body.replace else [])
        return {"job": submit("_library", "library", cli(*args), est_gb=ESTIMATE_GB["library"], label=f"Index {body.kind}: {body.source}",
                              log=s.projects_root / ".studio_logs" / "library.log")}

    @app.get("/api/brands")
    def brands():
        return catalog.list_brands(s.brands_root)

    @app.get("/api/brands/{bid}")
    def get_brand(bid: str):
        p = catalog.brand_path(s.brands_root, bid)
        if p is None or not p.exists():
            raise ApiError(404, f"no brand kit {bid!r}")
        return catalog.brand_entry(bid, json.loads(p.read_text()))

    @app.post("/api/brands", status_code=201)
    def create_brand(body: dict):
        if not isinstance(body.get("brand"), dict):
            raise ApiError(400, "send {id?, brand}")
        brand = _brand(body["brand"])
        bid = str(body.get("id") or catalog.brand_slug(brand.client))
        p = catalog.brand_path(s.brands_root, bid)
        if p is None:
            raise ApiError(400, "brand id: lowercase letters, digits, - and _ only")
        if p.exists():
            raise ApiError(409, f"brand kit {bid!r} already exists (PUT /api/brands/{bid} to change it)")
        return catalog.save_brand(s.brands_root, bid, brand)

    @app.put("/api/brands/{bid}")
    def put_brand(bid: str, body: dict):
        if catalog.brand_path(s.brands_root, bid) is None:
            raise ApiError(400, "brand id: lowercase letters, digits, - and _ only")
        return catalog.save_brand(s.brands_root, bid, _brand(body))

    # -------------------------------------------------------------- lab, costs, jobs

    @app.get("/api/lab")
    def lab():
        return catalog.lab(s)

    @app.post("/api/lab/{action}")
    def lab_action(action: Literal["eval", "calibrate", "improve", "bakeoff"], body: LabBody | None = None):
        body = body or LabBody()
        log = s.projects_root / ".studio_logs" / "lab.log"
        if action == "bakeoff":  # C5: which speech-to-text engine transcribes the owner's Hinglish clips best (ADR-0007)
            samples, out = catalog.bakeoff_paths()
            if not samples.is_dir():
                raise ApiError(400, f"no bake-off clips in {samples}", hint="Add <name>/clip.mp4 + transcript.txt for each Hinglish sample.")
            return {"job": submit("_lab", "bakeoff", cli("bakeoff", "--samples", samples, "--out", out), est_gb=ESTIMATE_GB.get("bakeoff", 4.0),
                                  log=log, label="Speech-to-text bake-off")}
        if action == "eval":
            holdout = body.release or body.set == "holdout"
            if holdout:
                locked, reason, _ = catalog.release_lock(s.eval_manifest)
                if locked:
                    raise ApiError(409, reason, {"release_locked": True})
            args = ["eval", "--set", "holdout", "--holdout"] if holdout else ["eval", "--set", "tuning"]
            return {"job": submit("_lab", "eval", cli(*args), est_gb=ESTIMATE_GB["eval"], log=log, label="Release check" if holdout else "Evaluate tuning set")}
        if action == "calibrate":
            return {"job": submit("_lab", "calibrate", cli("calibrate", "--projects", s.projects_root), est_gb=ESTIMATE_GB["calibrate"], log=log,
                                  label="Calibrate")}
        args = ["improve", "--budget", body.budget, "--runs", body.runs, "--rounds", body.rounds] + (["--dry-run"] if body.dry_run else [])
        return {"job": submit("_lab", "improve", cli(*args), est_gb=ESTIMATE_GB["improve"], log=log, label=f"Improve (budget {body.budget})")}

    # -------------------------------------------------------------- 3b.2 ours vs pro, the owner's blind picks

    @app.get("/api/lab/pairwise/{run}/{reel}/{side}")
    def pairwise_media(run: str, reel: str, side: Literal["A", "B"]):
        from reel.evalh import pairwise as pw

        files = catalog.pairwise_files(s, run, reel)
        if not files:
            raise ApiError(404, "no such pairwise item")
        f = Path(files["ours"] if side == pw.side_of_ours(run, reel) else files["pro"])
        if not f.is_file():
            raise ApiError(404, "the reel file is gone")
        return FileResponse(f)

    @app.post("/api/lab/pairwise/vote", status_code=204)
    def pairwise_vote(body: PairwiseVoteBody):
        from reel.evalh import pairwise as pw

        if not catalog.pairwise_files(s, body.run, body.reel):
            raise ApiError(404, "no such pairwise item")
        pw.record_owner(body.run, body.reel, body.choice, s.pairwise_log)
        return Response(status_code=204)

    @app.put("/api/lab/gates/{gate}")
    def set_gate_mode(gate: str, body: GateModeBody):
        """C3: switch a QA gate between warn and block. Block only when calibration cleared it (or the code already
        blocks it); every project's verdict is re-decided from its stored gate results, with no Reviewer call."""
        from reel import verdict as verdict_mod
        from reel.licences import config_dir

        if gate not in config.QA_GATES:
            raise ApiError(404, f"no gate {gate!r}", sorted(config.QA_GATES))
        cal = {g["name"]: g for g in ((catalog.calibration(s) or {}).get("gates") or [])}
        if body.mode == "block" and config.QA_GATES[gate] != "block" and not (cal.get(gate) or {}).get("promote_to_block"):
            raise ApiError(409, f"calibration hasn't cleared {gate} to block yet",
                           hint="Run Calibrate in the Quality lab; a gate blocks only after it shows few false alarms on good reels.")
        f = config_dir() / config.GATE_OVERRIDES_FILE
        cur = config.gate_overrides()
        if body.mode == config.QA_GATES[gate]:
            cur.pop(gate, None)
        else:
            cur[gate] = body.mode
        f.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(f, cur)
        f.chmod(0o600)
        n, skipped = 0, []
        for ws in projects.list_dirs(s.projects_root):
            if mgr.active(ws.name) is not None:
                continue
            try:  # one old or malformed project must not fail the switch for the rest
                n += verdict_mod.recompute(Workspace(ws)) is not None
            except Exception:  # noqa: BLE001
                skipped.append(ws.name)
        return {"gate": gate, "mode": body.mode, "recomputed": n, **({"skipped": skipped} if skipped else {})}

    # -------------------------------------------------------------- listening test (G2.5)

    @app.get("/api/listening/{kind}")
    def listening(kind: Literal["sfx", "music", "voice"]):
        from reel import listen

        pairs = listen.blind(kind)
        try:
            summ = listen.summary(kind) if pairs else None
        except (OSError, ValueError):
            summ = None
        return {"set": kind, "pairs": pairs, "summary": summ, "prompts": len(listen.PROMPTS[kind])}

    @app.post("/api/listening/{kind}/prepare")
    def listening_prepare(kind: Literal["sfx", "music", "voice"]):
        log = s.projects_root / ".studio_logs" / "lab.log"
        return {"job": submit("_lab", "listen", cli("listen", "prepare", "--set", kind), est_gb=ESTIMATE_GB.get("listen", 8.0), log=log,
                              label=f"Listening test: render {kind}")}

    @app.post("/api/listening/{kind}/vote", status_code=204)
    def listening_vote(kind: Literal["sfx", "music", "voice"], body: VoteBody):
        from reel import listen

        try:
            listen.vote(kind, body.pair, body.choice, body.usable_a, body.usable_b)
        except (listen.ListenError, FileNotFoundError) as exc:
            raise ApiError(400, str(exc)) from exc
        return Response(status_code=204)

    @app.get("/api/listening/{kind}/media/{path:path}")
    def listening_media(kind: Literal["sfx", "music", "voice"], path: str):
        from reel import listen

        base = (listen.ROOT / kind).resolve()
        f = (listen.ROOT / path).resolve()
        if "\x00" in path or not f.is_relative_to(base) or not f.is_file() or f.suffix.lower() not in (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aiff"):
            raise ApiError(404, "no such listening file")
        return FileResponse(f)

    @app.get("/api/costs")
    def cost_summary(days: int = 30):
        if not 1 <= days <= 3650:
            raise ApiError(400, "days must be 1–3650")
        return costs.summary(s.projects_root, days)

    # -------------------------------------------------------------- cost guard (roadmap 4.1)

    def _cap() -> float:
        return float(load_prefs(s.prefs_file).get("monthly_cap_usd") or 0.0)

    def spend_guard(spend_anyway: bool) -> None:
        """Before a new run that calls Claude: past the monthly cap, the owner must say "spend anyway". A run already
        going is never stopped."""
        from reel import spend

        cap = _cap()
        if not cap or spend_anyway:
            return
        st = spend.status(s.projects_root, cap)
        if st["over_cap"]:
            raise ApiError(409, f"this month's AI spend (${st['month']['total_usd']:.2f}) has reached the ${cap:.2f} cap",
                           over_cap=True, month_usd=st["month"]["total_usd"], cap_usd=cap,
                           hint="send it again with “spend anyway”, or raise the cap in Settings")

    @app.get("/api/spend")
    def spend_status():
        from reel import spend

        return spend.status(s.projects_root, _cap())

    @app.post("/api/spend/approve/{request_hash}")
    def spend_approve(request_hash: str):
        from reel import spend

        if not re.fullmatch(r"[0-9a-f]{24}", request_hash):
            raise ApiError(400, "not a request hash")
        try:
            return spend.approve(request_hash)
        except KeyError as exc:
            raise ApiError(404, "no such quote") from exc

    @app.get("/api/jobs")
    def job_list():
        return {"running": [j.public() for j in mgr.running()], "queued": [j.public() for j in mgr.queued()]}

    # -------------------------------------------------------------- settings (FR-12)

    def settings_view() -> dict:
        prefs = load_prefs(s.prefs_file)
        return {"max_jobs": s.max_jobs, "projects_dir": str(s.projects_root), "default_brief": prefs["default_brief"],
                "default_deliverables": prefs["default_deliverables"], "pexels_key_set": bool(prefs["pexels_key"]),
                "pixabay_key_set": bool(prefs.get("pixabay_key")), "monthly_cap_usd": float(prefs.get("monthly_cap_usd") or 0.0),
                "public_review_url": prefs.get("public_review_url") or ""}

    @app.get("/api/settings")
    def get_settings():
        return settings_view()

    @app.put("/api/settings")
    def put_settings(body: SettingsBody):
        from reel.brief import Brief

        if body.projects_dir and Path(body.projects_dir).expanduser().resolve() != s.projects_root.resolve():
            raise ApiError(400, "the projects folder is set when the studio starts: `reel studio --projects <folder>`")
        brief = {k: v for k, v in body.default_brief.items() if k != "project"}
        try:
            Brief.model_validate({"project": "defaults", **brief})
        except ValidationError as exc:
            raise ApiError(400, "the default brief is not valid", jsonable_encoder(exc.errors())) from exc
        prefs = load_prefs(s.prefs_file) | {"max_jobs": body.max_jobs, "default_brief": brief,
                                            "default_deliverables": list(dict.fromkeys(body.default_deliverables))}
        if body.pexels_key and body.pexels_key.strip():
            prefs["pexels_key"] = body.pexels_key.strip()
        if body.pixabay_key and body.pixabay_key.strip():
            prefs["pixabay_key"] = body.pixabay_key.strip()
        if body.monthly_cap_usd is not None:
            prefs["monthly_cap_usd"] = round(body.monthly_cap_usd, 2)
        if body.public_review_url is not None:
            url = body.public_review_url.strip().rstrip("/")
            if url and not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?(/[\w./-]*)?", url):
                raise ApiError(400, "the public address must be an https:// address (your tunnel's), or empty")
            prefs["public_review_url"] = url
        save_prefs(s.prefs_file, prefs)
        apply_prefs(s, prefs)
        mgr.tick()  # a higher limit starts queued jobs now
        return settings_view()

    # -------------------------------------------------------------- post copy (roadmap G1.1)

    @app.get("/api/projects/{pid}/copy")
    def post_copy(pid: str):
        """The credited copy the package wrote (hashtags + licence credits added by code) — never Claude's draft."""
        ws = ws_of(pid)
        f = ws / "export" / "package" / "copy.json"
        if not f.exists():
            draft = ws / "plan" / "copy.json"
            why = json.loads(draft.read_text()).get("reason", "") if draft.exists() else ""
            raise ApiError(404, "no post copy yet", hint=why or "it is written with the package at the end of the edit")
        return json.loads(f.read_text())

    # -------------------------------------------------------------- review links (owner side, token required)

    @app.get("/api/projects/{pid}/review-links")
    def review_links_list(pid: str):
        ws = ws_of(pid)
        links = review_links.for_project(s.projects_root, pid)
        if any(x["state"] == "active" for x in links):  # owner side only: keep what the client sees current (a link made
            try:  # at the check-in gets the reel once it renders)
                review_links.refresh_copies(ws)
            except Exception as exc:  # noqa: BLE001 — a failed transcode must not break the panel
                import logging

                logging.getLogger(__name__).warning("review copy refresh failed for %s: %s", pid, exc)
        return {"links": links, "notes": review_links.notes(ws), "ready": review_links.can_make(ws),
                "choices": review_links.current_choices(ws), "public_base": load_prefs(s.prefs_file).get("public_review_url") or None}

    @app.post("/api/projects/{pid}/review-links")
    def review_links_create(pid: str, body: ReviewLinkBody):
        ws = ws_of(pid)
        if not review_links.can_make(ws):
            raise ApiError(409, "nothing to show the client yet", hint="wait for the story check-in, the hook preview or the render")
        try:  # the small watermarked copies the client sees; (re)made from the current render / previews
            review_links.refresh_copies(ws)
        except Exception as exc:  # ffmpeg failed: say so, don't create a link that can't play
            raise ApiError(500, "couldn't make the review copy", str(exc)[-400:]) from exc
        return review_links.create(s.projects_root, pid, body.hours)

    @app.delete("/api/projects/{pid}/review-links/{link_id}", status_code=204)
    def review_links_revoke(pid: str, link_id: str):
        ws_of(pid)
        if not review_links.revoke(s.projects_root, pid, link_id):
            raise ApiError(404, "no such link")
        return Response(status_code=204)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def api_not_found(rest: str):
        raise ApiError(404, f"no endpoint /api/{rest}")

    # -------------------------------------------------------------- review links (client side, no token: the link is the key)

    from reel.studio.client_routes import add_client_routes

    add_client_routes(app, lambda: s.projects_root)  # the same code serves the client-only app (4.3, `reel share-server`)

    # -------------------------------------------------------------- the web app (studio/web/dist), SPA fallback

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str):
        dist = s.web_dist.resolve()
        index = dist / "index.html"
        if not index.exists():
            return HTMLResponse("<!doctype html><title>Reel Studio</title><p>The Reel Studio API is running. "
                                "The web app is not built yet (studio/web/dist).</p>")
        if path:
            f = (dist / path).resolve()
            if f.is_relative_to(dist) and f.is_file():
                return FileResponse(f)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


# ------------------------------------------------------------------ helpers outside the app


def _after_job(s: Settings, job) -> None:
    """A successful revision / notes / proof fix / adjustment / restore becomes a new version (FR-6 history), with the
    Editor's one-line reply (revise / notes) or what changed, and the AI cost of the job."""
    label = job.after.get("snapshot")
    if label and job.project not in GLOBAL_SLOTS:  # project ids may start with "_" too (e.g. _real_doac)
        ws = projects.project_dir(s.projects_root, job.project)
        if ws is not None:
            reply = job.after.get("reply", "")
            if job.kind in ("revise", "notes"):
                reply = (projects.last_revision(ws) or {}).get("reply") or reply
            reply = projects.with_measured_verdict(ws, reply)  # 3b.4: the claim next to what QA measured afterwards
            spent = sum(c["cost_usd"] for c in costs.calls(ws / "log" / "runs.jsonl") if (c.get("time") or 0) >= (job.started or time.time()))
            job.after["version"] = projects.snapshot(ws, label, reply=reply, cost_usd=round(spent, 4))


def _show(value) -> str:
    if isinstance(value, bool):
        return "off" if value else "on"
    if isinstance(value, dict):
        return f"{value.get('key')} {value.get('value')}"
    if isinstance(value, list):
        return ", ".join(map(str, value)) + " off"
    return str(value)


def _client_memory(ws: Path, why: str | None) -> None:
    """3a.2: learn from an approved reel (delivered / owner-sendable), or forget it when the approval is withdrawn.
    Never fails the request: the memory is derived and rebuildable."""
    from reel import client_memory

    try:
        if why:
            client_memory.learn(Workspace(ws), why)
        else:
            client_memory.forget(Workspace(ws))
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("client memory not updated for %s", ws.name)


def _log_adjustment(ws: Path, kind: str, value) -> None:
    """Kept adjustments (G2.4): a later chat revision is told about them and warns if it undoes one."""
    from reel import adjustments

    adjustments.log(Workspace(ws), kind, value)


def _run_args(ws: Path, opts: dict, force: str | None = None) -> list[str]:
    """`reel run` arguments that reproduce the stored options (run rewrites run_options.json from its argv)."""
    if opts.get("parent"):  # a Clip Factory reel project: edit stages only, options kept in its run_options.json
        args = ["run", "--project", str(ws)]
        if opts.get("skip_review"):
            args.append("--skip-review")
        if opts.get("story_checkin"):
            args.append("--story-checkin")
        return args + (["--force", force] if force else [])
    args = ["run", opts["input"], "--project", str(ws)]
    if opts.get("mine"):
        args.append("--mine")
        if opts.get("clip_target_s"):
            lo, hi = opts["clip_target_s"]
            args += ["--clip-length", f"{lo:g}-{hi:g}"]
    for key, flag in (("fps", "--fps"), ("encoder", "--encoder"), ("language", "--language"), ("brief", "--brief"), ("brand", "--brand"),
                      ("asr_repo", "--asr-repo"), ("broll", "--broll"), ("reference", "--reference")):
        if opts.get(key):
            args += [flag, str(opts[key])]
    if opts.get("skip_visual"):
        args.append("--skip-visual")
    if opts.get("stock"):
        args.append("--stock")
    if opts.get("preview_first"):
        args.append("--preview-first")
    if opts.get("story_checkin"):
        args.append("--story-checkin")
    elif "story_checkin" in opts:  # the owner's New edit choice is explicit: no brand default on top of it
        args.append("--no-story-checkin")
    if opts.get("skip_review"):
        args.append("--skip-review")
    if force:
        args += ["--force", force]
    return args


def _duration(path: Path) -> float:
    try:
        from reel.probe import probe

        return float(probe(path).duration_s or 0.0)
    except Exception:  # noqa: BLE001 — unknown length only weakens the memory estimate
        return 0.0


def _need_edit(ws: Path) -> None:
    for rel in ("plan/story.json", "plan/finish.json", "timeline/timeline.json"):
        if not (ws / rel).exists():
            raise ApiError(400, "the edit has not finished its plan yet", {"missing": rel})


def _edit_inputs(ws: Path):
    from reel import project
    from reel.schemas.plan import StoryPlan
    from reel.schemas.timeline import Timeline

    _need_edit(ws)
    w = Workspace(ws)
    return (Timeline.model_validate_json((ws / "timeline" / "timeline.json").read_text()),
            project.load_json_model(StoryPlan, ws / "plan" / "story.json"), project.word_table(w))


def _brand(body: dict):
    try:
        return catalog.validate_brand(body)
    except catalog.BrandError as exc:
        raise ApiError(400, "the brand kit is not valid", exc.args[0]) from exc


def _number(value, kind: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(400, f"{kind} takes a number")
    return float(value)


def _apply_adjust(ws: Path, kind: str, value):
    """Apply one guided adjustment (FR-8) to the plans and validate them; 422 with the validator's issues."""
    from reel import project
    from reel.schemas.plan import FinishPlan, StoryPlan, Token
    from reel.validate import errors, validate_finish, validate_story

    w = Workspace(ws)
    story = project.load_json_model(StoryPlan, ws / "plan" / "story.json")
    fin = project.load_json_model(FinishPlan, ws / "plan" / "finish.json")
    idx = project.indexes(w)
    from reel import licences
    from reel.brief import load_brief

    idx.refused = licences.refused(idx, licences.UseContext.from_brief(load_brief(project.brief_path(w)), ws.name, project.studio_client(w)))
    note = None

    def ids_off(items: list, what: str) -> list:
        if value is True:
            return []
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            return [x for x in items if x.id not in value]
        raise ApiError(400, f"{what} takes true (all off) or a list of ids")

    if kind == "caption_family":
        if not isinstance(value, str):
            raise ApiError(400, "caption_family takes a family id")
        fin.captions.family = value
        allowed = set(((idx.caption_families.get(value) or {}).get("tokens") or {}).keys())
        fin.captions.tokens = [t for t in fin.captions.tokens if t.key in allowed]  # the old family's overrides do not carry over
        opts = projects.read_json(ws / "run_options.json", {}) or {}
        brand = projects.read_json(Path(opts["brand"])) if opts.get("brand") else None
        if brand and brand.get("caption_family") and brand["caption_family"] != value:
            note = f"The brand kit locks captions to {brand['caption_family']}; the brand wins when the reel is compiled."
    elif kind == "caption_token":
        if not (isinstance(value, dict) and isinstance(value.get("key"), str) and isinstance(value.get("value"), str)):
            raise ApiError(400, "caption_token takes {key, value}")
        fin.captions.tokens = [t for t in fin.captions.tokens if t.key != value["key"]] + [Token(key=value["key"], value=value["value"])]
    elif kind == "look":
        if not isinstance(value, str):
            raise ApiError(400, "look takes a look id")
        fin.grade.look = value
    elif kind == "look_strength":
        fin.grade.strength = _number(value, kind)
    elif kind == "music_track":
        if not isinstance(value, str):
            raise ApiError(400, "music_track takes a track id or \"none\"")
        fin.music.track = value
        if value == "none":
            fin.beat_pulse = 0.0  # beat pulses need a music bed
    elif kind == "music_gain_db":
        fin.music.gain_db = _number(value, kind)
    elif kind == "sfx_off":
        fin.sfx = ids_off(fin.sfx, kind)
    elif kind == "punch_ins_off":
        fin.punch_ins = ids_off(fin.punch_ins, kind)
    elif kind == "grain":
        fin.grade.grain = _number(value, kind)
    elif kind == "vignette":
        fin.grade.vignette = _number(value, kind)
    elif kind == "max_pause_ms":  # a story setting (StoryPlan.max_pause_ms)
        v = _number(value, kind)
        if v != int(v):
            raise ApiError(400, "max_pause_ms takes whole milliseconds")
        story.max_pause_ms = int(v)
    elif kind == "story_lines":  # C4: drop or reorder kept lines; attached finish elements of dropped lines go too
        from reel import story_edit

        if not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            raise ApiError(400, "story_lines takes the kept line ids in their new order")
        try:
            story, fin, meta = story_edit.reorder(story, fin, value)
        except story_edit.StoryEditError as exc:
            raise ApiError(400, str(exc)) from exc
        note = story_edit.summary(meta)
    elif kind == "story_words":  # 3a.3: cut words out of one kept line; it splits around them
        from reel import story_edit

        ok = isinstance(value, dict) and isinstance(value.get("item"), str) and isinstance(value.get("remove"), list) and value["remove"] \
            and all(isinstance(r, list) and len(r) == 2 and all(isinstance(x, int) for x in r) for r in value["remove"])
        if not ok:
            raise ApiError(400, "story_words takes {item, remove: [[first word, last word], …]}")
        try:
            story, fin, meta = story_edit.cut_words(story, fin, value["item"], value["remove"], project.word_table(w))
        except story_edit.StoryEditError as exc:
            raise ApiError(400, str(exc)) from exc
        note = story_edit.summary(meta)

    words = project.word_table(w)
    manifest = projects.read_json(ws / "source" / "manifest.json", {}) or {}
    from reel.clipfactory import load_window

    issues = (validate_story(story, words, {c["id"] for c in manifest.get("clips", [])}, window=load_window(w))
              if kind in STORY_KINDS else [])
    if not errors(issues):
        issues += validate_finish(fin, story, words, idx)
    if errors(issues):
        raise ApiError(422, "the engine's validator refused this change", None, issues=[i.as_dict() for i in errors(issues)],
                       **({"hint": "This change needs the Editor: describe it in Revise instead."} if kind in ("story_lines", "story_words") else {}))
    return story, fin, note
