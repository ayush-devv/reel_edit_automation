"""Project workspace: layout, atomic writes, hashing and the run lock (ADR-0020)."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

LAYOUT = ("source", "mezz", "perception", "tables", "plan", "timeline", "render", "qa", "export", "log")


class LockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class Workspace:
    root: Path

    @classmethod
    def create(cls, root: Path) -> "Workspace":
        root = root.resolve()
        for name in LAYOUT:
            (root / name).mkdir(parents=True, exist_ok=True)
        return cls(root)

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    @property
    def lock_file(self) -> Path:
        return self.root / "run.lock"

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Exclusive run lock; a stale lock (dead PID on this host) is taken over."""
        lf = self.lock_file
        if lf.exists():
            try:
                info = json.loads(lf.read_text())
            except (ValueError, OSError):
                info = {}
            if info.get("host") == socket.gethostname() and _pid_alive(int(info.get("pid", 0))):
                raise LockedError(f"Another run holds {lf} (pid {info.get('pid')}).")
            lf.unlink(missing_ok=True)
        fd = os.open(lf, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "since": time.time()}).encode())
        finally:
            os.close(fd)
        try:
            yield
        finally:
            lf.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, (json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n").encode())


def tmp_path_for(path: Path) -> Path:
    """Temp sibling for tools that write files themselves (e.g. ffmpeg); keep the extension."""
    return path.with_name(f".{path.stem}.tmp{path.suffix}")


def file_fingerprint(path: Path, *, full: bool = False, chunk: int = 4 << 20) -> str:
    """Content fingerprint. Default: size + first/last 4 MB (fast for large media)."""
    h = hashlib.sha256()
    size = path.stat().st_size
    h.update(str(size).encode())
    with open(path, "rb") as f:
        if full or size <= 2 * chunk:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        else:
            h.update(f.read(chunk))
            f.seek(size - chunk)
            h.update(f.read(chunk))
    return h.hexdigest()[:32]


def hash_inputs(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:32]
