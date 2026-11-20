// E2: a browser notification when an edit turns Sendable, Hold or Failed, waits for a pick, or a long recording's
// reels are ready to choose. Opt-in in Settings; the choice is a per-browser convenience (localStorage).
import { useEffect, useRef } from "react";
import { useApi } from "../api/context";
import type { ProjectStatus, ProjectSummary } from "../api/types";

const KEY = "reel.notify";
const POLL_MS = 10_000;
const NOTIFY: Partial<Record<ProjectStatus, string>> = {
  sendable: "is Sendable",
  hold: "is on Hold: it needs you",
  failed: "stopped: it failed",
  awaiting_choice: "is waiting for the A/B pick",
  source: "has reels ready to pick",
};

export function notificationsOn(): boolean {
  try {
    return localStorage.getItem(KEY) === "1" && typeof Notification !== "undefined" && Notification.permission === "granted";
  } catch {
    return false;
  }
}

export async function setNotifications(on: boolean): Promise<boolean> {
  try {
    if (!on) {
      localStorage.removeItem(KEY);
      return false;
    }
    if (typeof Notification === "undefined") return false;
    const perm = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    if (perm !== "granted") return false;
    localStorage.setItem(KEY, "1");
    return true;
  } catch {
    return false;
  }
}

/** Which projects changed into a status worth a notification (pure, for tests). */
export function changes(prev: Map<string, ProjectStatus>, now: ProjectSummary[]): { p: ProjectSummary; text: string }[] {
  const out: { p: ProjectSummary; text: string }[] = [];
  for (const p of now) {
    const before = prev.get(p.id);
    const text = NOTIFY[p.status];
    if (before !== undefined && before !== p.status && text) out.push({ p, text });
  }
  return out;
}

export function useStatusNotifications(): void {
  const api = useApi();
  const prev = useRef<Map<string, ProjectStatus> | null>(null);
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      if (!notificationsOn()) {
        prev.current = null;
        return;
      }
      try {
        const list = await api.projects();
        if (stop) return;
        if (prev.current) {
          for (const { p, text } of changes(prev.current, list)) {
            const n = new Notification(`${p.name} ${text}`, { body: p.client ?? undefined, tag: `reel-${p.id}` });
            n.onclick = () => window.focus();
          }
        }
        prev.current = new Map(list.map((p) => [p.id, p.status]));
      } catch {
        /* engine down: try again next tick */
      }
    };
    void tick();
    const t = setInterval(tick, POLL_MS);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [api]);
}
