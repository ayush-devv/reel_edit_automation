"""Subprocess wrappers for ffmpeg / ffprobe with useful errors."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Sequence

from reel import config

log = logging.getLogger(__name__)


class ToolError(RuntimeError):
    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str):
        tail = "\n".join(stderr.strip().splitlines()[-15:])
        super().__init__(f"{Path(cmd[0]).name} exited {returncode}:\n{tail}")
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = stderr


def run(cmd: Sequence[str], *, timeout: float | None = None, capture_stdout: bool = True) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    log.debug("run: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise ToolError(cmd, proc.returncode, proc.stderr.decode(errors="replace"))
    return proc


def ffmpeg(args: Sequence[str], *, timeout: float | None = None) -> subprocess.CompletedProcess:
    return run([config.ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error", *args], timeout=timeout)


def ffprobe_json(path: Path, extra: Sequence[str] = ()) -> dict:
    proc = run(
        [
            config.ffprobe_path(),
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            *extra,
            str(path),
        ],
        timeout=120,
    )
    return json.loads(proc.stdout or b"{}")


def ffprobe_frame_times(path: Path, stream: str = "v:0") -> list[float]:
    """Presentation times (s) of every frame in a stream — used for VFR detection and checks."""
    proc = run(
        [
            config.ffprobe_path(),
            "-v", "error",
            "-select_streams", stream,
            "-show_entries", "frame=pts_time",
            "-of", "csv=p=0",
            str(path),
        ],
        timeout=600,
    )
    times = []
    for line in (proc.stdout or b"").decode().splitlines():
        line = line.strip().rstrip(",")
        if line and line != "N/A":
            times.append(float(line))
    return times
