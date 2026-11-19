"""Where Reel Studio keeps things, and its limits. Paths are overridable (env or constructor) so tests use tmp dirs.

`Settings` is the server's configuration. The owner's preferences (GET/PUT /api/settings: edits at once, default
brief, default deliverables, Pexels key) persist in `prefs_file` (~/.config/reel/studio_settings.json, mode 0600).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from reel import config

MAX_JOBS_LIMIT = 3  # NFR-2: more than 3 edits at once risks running out of memory on a 16 GB Mac


def _env_path(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v).expanduser().resolve() if v else default


@dataclass
class Settings:
    projects_root: Path = field(default_factory=lambda: _env_path("REEL_PROJECTS_ROOT", config.REPO_ROOT / "projects"))
    brands_root: Path = field(default_factory=lambda: _env_path("REEL_BRANDS_ROOT", config.REPO_ROOT / "brands"))
    token_file: Path = field(default_factory=lambda: _env_path("REEL_STUDIO_TOKEN_FILE", Path.home() / ".config" / "reel" / "studio_token"))
    prefs_file: Path = field(default_factory=lambda: _env_path("REEL_STUDIO_SETTINGS_FILE", Path.home() / ".config" / "reel" / "studio_settings.json"))
    web_dist: Path = field(default_factory=lambda: config.REPO_ROOT / "studio" / "web" / "dist")
    eval_manifest: Path = field(default_factory=lambda: config.EVAL_DIR / "manifest.yaml")
    scoreboard: Path = field(default_factory=lambda: config.EVAL_DIR / "scoreboard.jsonl")
    improve_log: Path = field(default_factory=lambda: config.EVAL_DIR / "improve_log.jsonl")
    calibration_report: Path = field(default_factory=lambda: config.EVAL_DIR / "calibration" / "auto_latest.json")
    python: str = sys.executable  # interpreter for job subprocesses (`python -m reel.cli …`)
    max_jobs: int = MAX_JOBS_LIMIT  # NFR-2 (the owner's `max_jobs` preference overrides it at start-up)
    memory_budget_gb: float = 12.0  # NFR-2: estimated memory of running jobs stays under this
    poll_s: float = 0.25  # SSE file polling (NFR-3: on screen in ≤ 1 s)
    keepalive_s: float = 15.0
    sse_max_s: float | None = None  # tests end the stream after this many seconds
    log_lines_per_s: int = 5
    max_upload_bytes: int = 4 << 30  # 4 GB per file (FR-2)
    dev: bool = False  # CORS for the Vite dev origin
    doctor: Callable[[], dict] | None = None  # injectable toolchain check (default reel.doctor.check)
    start_scheduler: bool = True  # tests drive the queue by hand
    job_env: dict = field(default_factory=dict)  # extra environment for job subprocesses (PEXELS_API_KEY); never persisted with jobs

    @property
    def queue_file(self) -> Path:
        return self.projects_root / ".studio_queue.json"

    @property
    def trash(self) -> Path:
        return self.projects_root / ".trash"


# ------------------------------------------------------------------ the owner's preferences (studio_settings.json)

PREF_DEFAULTS = {"max_jobs": MAX_JOBS_LIMIT, "default_brief": {}, "default_deliverables": [], "pexels_key": "", "pixabay_key": ""}


def load_prefs(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    return {**PREF_DEFAULTS, **{k: v for k, v in (data if isinstance(data, dict) else {}).items() if k in PREF_DEFAULTS}}


def save_prefs(path: Path, prefs: dict) -> None:
    """Atomic write, mode 0600 from the first byte (the file holds the Pexels key)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps({k: prefs.get(k, v) for k, v in PREF_DEFAULTS.items()}, indent=2).encode())
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def apply_prefs(s: Settings, prefs: dict) -> None:
    """The preferences that change how the server runs: the job limit and the jobs' environment."""
    s.max_jobs = max(1, min(MAX_JOBS_LIMIT, int(prefs.get("max_jobs") or MAX_JOBS_LIMIT)))
    for pref, env in (("pexels_key", "PEXELS_API_KEY"), ("pixabay_key", "PIXABAY_API_KEY")):
        if prefs.get(pref):
            s.job_env[env] = prefs[pref]
        else:
            s.job_env.pop(env, None)
