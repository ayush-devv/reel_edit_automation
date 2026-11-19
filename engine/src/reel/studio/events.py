"""Server-sent events for one project: snapshot first, then stage / decision / log / job / revision / done.

Polls the workspace every `poll_s` (250 ms). The Project is rebuilt only when a watched file or the
project's job changes, so an idle stream costs a few stat() calls per tick.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from pathlib import Path

from reel.studio import projects

WATCHED = ("state.json", "run.lock", "plan/story.json", "plan/finish.json", "plan/history", "qa/verdict.json", "qa/review.json",
           "versions")


def _sig(ws: Path, job) -> tuple:
    out = []
    for rel in WATCHED:
        p = ws / rel
        try:
            out.append(p.stat().st_mtime_ns)
        except OSError:
            out.append(0)
    return (*out, job.id if job else None, job.status if job else None)


def _fmt(event: str, data, eid: int) -> str:
    return f"id: {eid}\nevent: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


async def stream(request, ws: Path, pid: str, mgr, settings, build_project):
    eid = 0

    def ev(event: str, data) -> str:
        nonlocal eid
        eid += 1
        return _fmt(event, data, eid)

    snap = await asyncio.to_thread(build_project)
    yield ev("snapshot", snap)
    last_stage = {s["name"]: (s["status"], s["finished"], s.get("error")) for s in snap["stages"]}
    seen = {projects.decision_key(d) for d in snap["decisions"]}
    job = mgr.latest(pid)
    last_job = (job.id, job.status) if job else None
    sig = _sig(ws, job)
    log = Path(job.log) if job else ws / "log" / "studio_job.log"
    offset = log.stat().st_size if log.exists() else 0
    pending: deque[str] = deque(maxlen=500)
    window_start, sent_in_window = time.monotonic(), 0
    start = last_sent = time.monotonic()

    while True:
        await asyncio.sleep(settings.poll_s)
        now = time.monotonic()
        if await request.is_disconnected() or (settings.sse_max_s is not None and now - start >= settings.sse_max_s):
            break
        out: list[str] = []
        job = mgr.latest(pid)
        new_sig = _sig(ws, job)
        if new_sig != sig:
            sig = new_sig
            state = mgr.project_state(pid)
            for st in await asyncio.to_thread(projects.stages, ws, state):
                key = (st["status"], st["finished"], st.get("error"))
                if last_stage.get(st["name"]) != key:
                    last_stage[st["name"]] = key
                    out.append(ev("stage", st))
            for d in await asyncio.to_thread(projects.decisions, ws):
                k = projects.decision_key(d)
                if k not in seen:
                    seen.add(k)
                    out.append(ev("decision", d))
        if job and (job.id, job.status) != last_job:
            if last_job is None or last_job[0] != job.id:  # a new job: follow its log from the start
                log, offset = Path(job.log), (Path(job.log).stat().st_size if Path(job.log).exists() else 0)
            last_job = (job.id, job.status)
            out.append(ev("job", {"id": job.id, "kind": job.kind, "status": job.status, "label": job.label}))
            if job.status in ("done", "failed", "cancelled", "lost"):
                if job.status == "done" and job.kind in ("revise", "notes"):
                    rev = projects.last_revision(ws) or {}
                    out.append(ev("revision", {"reply": rev.get("reply", ""), "request": rev.get("request", ""), "version": job.after.get("version")}))
                summary = await asyncio.to_thread(projects.summary, ws, mgr.project_state(pid))
                out.append(ev("done", {"status": summary["status"], "job": job.status, "kind": job.kind}))
        # technical log, at most `log_lines_per_s` lines a second (the rest waits; a flood keeps only the newest 500)
        if log.exists() and log.stat().st_size > offset:
            with open(log, "rb") as f:
                f.seek(offset)
                chunk = f.read(1 << 20)
            cut = chunk.rfind(b"\n") + 1
            offset += cut
            pending.extend(line for line in chunk[:cut].decode("utf-8", "replace").splitlines() if line.strip())
        if now - window_start >= 1.0:
            window_start, sent_in_window = now, 0
        while pending and sent_in_window < settings.log_lines_per_s:
            out.append(ev("log", {"line": pending.popleft()}))
            sent_in_window += 1
        if out:
            last_sent = now
            yield "".join(out)
        elif now - last_sent >= settings.keepalive_s:
            last_sent = now
            yield ": keepalive\n\n"
