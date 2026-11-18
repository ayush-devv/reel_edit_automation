"""Where Reel Studio keeps things, and its limits. Paths are overridable (env or constructor) so tests use tmp dirs."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from reel import config


def _env_path(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v).expanduser().resolve() if v else default


@dataclass
class Settings:
    projects_root: Path = field(default_factory=lambda: _env_path("REEL_PROJECTS_ROOT", config.REPO_ROOT / "projects"))
    brands_root: Path = field(default_factory=lambda: _env_path("REEL_BRANDS_ROOT", config.REPO_ROOT / "brands"))
    token_file: Path = field(default_factory=lambda: _env_path("REEL_STUDIO_TOKEN_FILE", Path.home() / ".config" / "reel" / "studio_token"))
    web_dist: Path = field(default_factory=lambda: config.REPO_ROOT / "studio" / "web" / "dist")
    eval_manifest: Path = field(default_factory=lambda: config.EVAL_DIR / "manifest.yaml")
    scoreboard: Path = field(default_factory=lambda: config.EVAL_DIR / "scoreboard.jsonl")
    improve_log: Path = field(default_factory=lambda: config.EVAL_DIR / "improve_log.jsonl")
    python: str = sys.executable  # interpreter for job subprocesses (`python -m reel.cli …`)
    max_jobs: int = 3  # NFR-2
    memory_budget_gb: float = 12.0  # NFR-2: estimated memory of running jobs stays under this
    poll_s: float = 0.25  # SSE file polling (NFR-3: on screen in ≤ 1 s)
    keepalive_s: float = 15.0
    sse_max_s: float | None = None  # tests end the stream after this many seconds
    log_lines_per_s: int = 5
    max_upload_bytes: int = 4 << 30  # 4 GB per file (FR-2)
    dev: bool = False  # CORS for the Vite dev origin
    doctor: Callable[[], dict] | None = None  # injectable toolchain check (default reel.doctor.check)
    start_scheduler: bool = True  # tests drive the queue by hand

    @property
    def queue_file(self) -> Path:
        return self.projects_root / ".studio_queue.json"

    @property
    def trash(self) -> Path:
        return self.projects_root / ".trash"
