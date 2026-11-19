export const usd = (n: number) => `$${n.toFixed(n < 1 ? 3 : 2)}`;

export function duration(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60);
  const r = Math.round(s - m * 60);
  return m ? `${m}:${String(r).padStart(2, "0")}` : `${s.toFixed(1)} s`;
}

export function elapsed(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

export function ago(isoStr: string | null | undefined, now = Date.now()): string {
  if (!isoStr) return "—";
  const d = (now - Date.parse(isoStr)) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return `${Math.floor(d / 86400)} d ago`;
}

export function bytes(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} KB`;
  return `${n} B`;
}

/** "00:00:12.40" or "0:12.4" → seconds. */
export function tcToSeconds(tc: string): number {
  const parts = tc.split(":").map(Number);
  return parts.reduce((a, p) => a * 60 + p, 0);
}

export const prettyId = (id: string) => id.replace(/^[a-z]+\./, "").replace(/_/g, " ");
