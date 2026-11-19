import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useApi } from "../api/context";
import { ApiError } from "../api/errors";
import type { Health, Jobs } from "../api/types";
import { useQuery } from "./useQuery";

export type EngineState = "checking" | "ok" | "offline" | "auth" | "error";

interface StatusValue {
  health: Health | undefined;
  jobs: Jobs | undefined;
  engine: EngineState;
  /** Any job running: 3D throttles to ≤ 15 fps or a still frame (NFR-1). */
  busy: boolean;
  refresh: () => void;
}

const StatusContext = createContext<StatusValue>({ health: undefined, jobs: undefined, engine: "checking", busy: false, refresh: () => {} });

export function StatusProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const health = useQuery(() => api.health(), [api], { intervalMs: 5000 });
  const jobs = useQuery(() => api.jobs(), [api], { intervalMs: 3000 });
  const value = useMemo<StatusValue>(() => {
    const err = health.error;
    let engine: EngineState = "checking";
    if (err instanceof ApiError && err.kind === "offline") engine = "offline";
    else if (err instanceof ApiError && err.kind === "auth") engine = "auth";
    else if (err) engine = "error";
    else if (health.data) engine = "ok";
    return {
      health: health.data,
      jobs: jobs.data,
      engine,
      busy: (jobs.data?.running.length ?? 0) > 0,
      refresh: () => {
        health.reload();
        jobs.reload();
      },
    };
  }, [health, jobs]);
  return <StatusContext.Provider value={value}>{children}</StatusContext.Provider>;
}

export const useStatus = () => useContext(StatusContext);
