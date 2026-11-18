import { useEffect, useRef, useState } from "react";
import { useApi } from "../api/context";
import { applyEvent } from "../api/sse";
import type { Project, SseEvent } from "../api/types";

export interface LiveProject {
  project: Project | null;
  error: unknown;
  logs: string[];
  jobs: Record<string, { kind: string; status: string }>;
  lastRevision: { reply: string; version: number } | null;
  connected: boolean;
  reload: () => void;
}

/** A project kept live over SSE (snapshot first, then stage/decision/job/revision/done events). */
export function useLiveProject(id: string): LiveProject {
  const api = useApi();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [jobs, setJobs] = useState<LiveProject["jobs"]>({});
  const [lastRevision, setLastRevision] = useState<LiveProject["lastRevision"]>(null);
  const [connected, setConnected] = useState(false);
  const [nonce, setNonce] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    setError(null);
    setProject((prev) => (prev && prev.id === id ? prev : null));
    api
      .project(id)
      .then((p) => mounted.current && setProject(p))
      .catch((e) => mounted.current && setError(e));
    const onEvent = (ev: SseEvent) => {
      if (!mounted.current) return;
      setConnected(true);
      if (ev.type === "log") setLogs((l) => [...l.slice(-399), ev.data.line]);
      else if (ev.type === "job") setJobs((j) => ({ ...j, [ev.data.id]: { kind: ev.data.kind, status: ev.data.status } }));
      else if (ev.type === "revision") setLastRevision(ev.data);
      setProject((p) => applyEvent(p, ev));
    };
    const off = api.subscribe(id, onEvent, () => mounted.current && setConnected(false));
    return () => {
      mounted.current = false;
      off();
    };
  }, [api, id, nonce]);

  return { project, error, logs, jobs, lastRevision, connected, reload: () => setNonce((n) => n + 1) };
}
