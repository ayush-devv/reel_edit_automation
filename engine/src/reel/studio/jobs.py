"""Job queue (NFR-2): each edit action is a `python -m reel.cli …` subprocess.

- At most `max_jobs` run at once; the rest wait in FIFO order.
- Memory guard: a job starts only while the estimated memory of running jobs plus its own stays under
  the budget (12 GB). The estimate comes from the footage length, not from macOS "used" memory (a browser
  alone would block every edit). A job always starts when nothing else runs, so the queue cannot deadlock.
- One job per project (or per global slot: `_lab`, `_library`) at a time: a second one is a conflict (409).
- Queued and running jobs are persisted to projects/.studio_queue.json and picked up again after a restart.
- The launcher is injectable: tests never spawn processes.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from reel.workspace import _pid_alive, atomic_write_json

KILL_AFTER_S = 10.0


class JobConflict(RuntimeError):
    def __init__(self, job: "Job"):
        super().__init__(f"{job.kind} job {job.id} is already {job.status} for {job.project}")
        self.job = job


@dataclass
class Job:
    id: str
    project: str  # project id, or a global slot ("_lab", "_library")
    kind: str
    argv: list[str]
    cwd: str
    log: str
    est_gb: float
    label: str = ""
    status: str = "queued"  # queued | running | done | failed | cancelled | lost
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    returncode: int | None = None
    pid: int | None = None
    after: dict = field(default_factory=dict)  # what to do when it succeeds (snapshot a version, …)
    cancel_requested: bool = False

    def public(self) -> dict:
        return {"id": self.id, "project": self.project, "kind": self.kind, "status": self.status, "label": self.label,
                "created": self.created, "started": self.started, "finished": self.finished, "est_gb": self.est_gb,
                "returncode": self.returncode}


# ------------------------------------------------------------------ memory estimates (GB)


def estimate_run_gb(footage_s: float | None) -> float:
    """Full edit: ASR + vision models, ProRes mezzanine, ffmpeg render, Remotion (Chrome) overlay."""
    return round(min(8.0, 3.0 + 0.5 * (footage_s or 120.0) / 60.0), 2)


def estimate_render_gb(reel_s: float | None) -> float:
    """Re-render from compile (ffmpeg + Remotion), or a revision (one Editor call + re-render)."""
    return round(min(6.0, 2.5 + 0.25 * (reel_s or 60.0) / 60.0), 2)


ESTIMATE_GB = {"library": 1.0, "calibrate": 0.3, "eval": 6.0, "improve": 6.0}


def system_memory() -> dict:
    """Total / available physical memory in GB from sysctl + vm_stat (macOS); {} elsewhere."""
    try:
        total = int(subprocess.run(["/usr/sbin/sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout.strip())
        vm = subprocess.run(["/usr/bin/vm_stat"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}
    page = int(m.group(1)) if (m := re.search(r"page size of (\d+) bytes", vm)) else 16384
    pages = {k.strip().lower(): int(v.strip().rstrip(".")) for k, v in re.findall(r"^([^:\n]+):\s+(\d+)\.?$", vm, re.M)}
    free = sum(pages.get(k, 0) for k in ("pages free", "pages inactive", "pages speculative", "pages purgeable"))
    return {"total": round(total / 2**30, 2), "available": round(free * page / 2**30, 2)}


# ------------------------------------------------------------------ launcher


def popen_launcher(job: Job, logf):
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}  # log lines reach studio_job.log (and SSE) as they happen
    return subprocess.Popen(job.argv, cwd=job.cwd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            start_new_session=True, env=env)


def _signal(proc, pid: int | None, sig: int) -> None:
    if pid:
        try:
            os.killpg(pid, sig)  # the whole group: ffmpeg, node and claude children too
            return
        except (ProcessLookupError, PermissionError):
            return
        except OSError:
            pass
    if proc is not None:
        (proc.kill if sig == signal.SIGKILL else proc.terminate)()


class JobManager:
    def __init__(self, settings, launcher: Callable | None = None, on_finish: Callable[[Job], None] | None = None):
        self.s = settings
        self.launcher = launcher or popen_launcher
        self.on_finish = on_finish
        self.lock = threading.RLock()
        self.jobs: dict[str, Job] = {}
        self.queue: list[str] = []
        self.procs: dict[str, object] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.load()

    # -------------------------------------------------------------- persistence

    def load(self) -> None:
        data = {}
        if self.s.queue_file.exists():
            try:
                data = json.loads(self.s.queue_file.read_text())
            except ValueError:
                data = {}
        for d in data.get("jobs", []):
            job = Job(**{k: v for k, v in d.items() if k in Job.__dataclass_fields__})
            if job.status == "running":
                if job.pid and _pid_alive(job.pid):
                    self.jobs[job.id] = job  # survived the restart: watched by pid
                    threading.Thread(target=self._watch_orphan, args=(job,), daemon=True).start()
                else:
                    job.status, job.finished = "lost", time.time()
                    self.jobs[job.id] = job
            elif job.status == "queued":
                self.jobs[job.id] = job
                self.queue.append(job.id)
        self.save()

    def save(self) -> None:
        with self.lock:  # one writer at a time: saves come from request threads and job-waiter threads
            active = [asdict(j) for j in self.jobs.values() if j.status in ("queued", "running")]
            active.sort(key=lambda d: (d["status"] != "running", self.queue.index(d["id"]) if d["id"] in self.queue else 0))
            self.s.projects_root.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.s.queue_file, {"jobs": active})

    # -------------------------------------------------------------- queries

    def active(self, project: str) -> Job | None:
        with self.lock:
            return next((j for j in self.jobs.values() if j.project == project and j.status in ("queued", "running")), None)

    def latest(self, project: str) -> Job | None:
        with self.lock:
            js = [j for j in self.jobs.values() if j.project == project]
            return max(js, key=lambda j: j.created) if js else None

    def project_state(self, project: str) -> str | None:
        j = self.active(project)
        return j.status if j else None

    def running(self) -> list[Job]:
        with self.lock:
            return sorted((j for j in self.jobs.values() if j.status == "running"), key=lambda j: j.started or 0)

    def queued(self) -> list[Job]:
        with self.lock:
            return [self.jobs[i] for i in self.queue]

    def used_gb(self) -> float:
        return round(sum(j.est_gb for j in self.running()), 2)

    # -------------------------------------------------------------- submit / schedule / cancel

    def submit(self, project: str, kind: str, argv: list[str], *, cwd: Path, log: Path, est_gb: float, label: str = "",
               after: dict | None = None) -> Job:
        with self.lock:
            if (other := self.active(project)) is not None:
                raise JobConflict(other)
            job = Job(id=f"j{int(time.time() * 1000):x}{secrets.token_hex(2)}", project=project, kind=kind, argv=[str(a) for a in argv],
                      cwd=str(cwd), log=str(log), est_gb=est_gb, label=label, after=after or {})
            self.jobs[job.id] = job
            self.queue.append(job.id)
        self.save()
        self.tick()
        return job

    def tick(self) -> None:
        """Start queued jobs in FIFO order while a slot is free and the memory guard allows."""
        started = False
        with self.lock:
            while self.queue:
                head = self.jobs[self.queue[0]]
                running = self.running()
                if len(running) >= self.s.max_jobs:
                    break
                if running and self.used_gb() + head.est_gb > self.s.memory_budget_gb:
                    break  # strict FIFO: later jobs wait behind the head
                self.queue.pop(0)
                self._start(head)
                started = True
        if started:
            self.save()

    def _start(self, job: Job) -> None:
        Path(job.log).parent.mkdir(parents=True, exist_ok=True)
        logf = open(job.log, "a", buffering=1)
        logf.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} job {job.id} {job.kind}: {' '.join(job.argv[3:])}\n")
        logf.flush()
        job.status, job.started = "running", time.time()
        try:
            proc = self.launcher(job, logf)
        except Exception as exc:  # noqa: BLE001 — a launch failure is a failed job, not a crashed API
            logf.write(f"could not start: {exc}\n")
            logf.close()
            self._finish(job, -1)
            return
        job.pid = getattr(proc, "pid", None)
        self.procs[job.id] = proc
        threading.Thread(target=self._wait, args=(job, proc, logf), daemon=True).start()

    def _wait(self, job: Job, proc, logf) -> None:
        rc = proc.wait()
        try:
            logf.write(f"=== job {job.id} exited with {rc}\n")
            logf.close()
        except OSError:
            pass
        self._finish(job, rc)

    def _watch_orphan(self, job: Job) -> None:
        while _pid_alive(job.pid or 0) and not self._stop.is_set():
            time.sleep(1.0)
        if not self._stop.is_set():
            self._finish(job, None)

    def _finish(self, job: Job, rc: int | None) -> None:
        if job.cancel_requested or job.status == "cancelled":
            status = "cancelled"
        else:
            status = "done" if rc == 0 else ("lost" if rc is None else "failed")
        if status == "done" and self.on_finish:
            try:  # before the status flips, so whoever sees "done" also sees its version snapshot
                self.on_finish(job)
            except Exception as exc:  # noqa: BLE001 — a post-step must not kill the scheduler
                job.after["post_error"] = f"{type(exc).__name__}: {exc}"
        with self.lock:
            self.procs.pop(job.id, None)
            job.returncode, job.finished, job.status = rc, time.time(), status
        self.save()
        self.tick()

    def cancel(self, project: str) -> Job | None:
        with self.lock:
            job = self.active(project)
            if job is None:
                return None
            if job.status == "queued":
                self.queue.remove(job.id)
                job.status, job.finished = "cancelled", time.time()
                proc = None
            else:  # stays "running" (holds its slot and the project) until the process group has exited
                job.cancel_requested = True
                proc = self.procs.get(job.id)
        self.save()
        if proc is not None or job.pid:
            _signal(proc, job.pid, signal.SIGTERM)
            t = threading.Timer(KILL_AFTER_S, lambda: job.finished is None and _signal(proc, job.pid, signal.SIGKILL))
            t.daemon = True
            t.start()
        return job

    # -------------------------------------------------------------- scheduler thread

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="studio-jobs")
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self.s.poll_s):
            self.tick()

    def stop(self) -> None:
        self._stop.set()
