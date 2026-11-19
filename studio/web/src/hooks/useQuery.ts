import { useCallback, useEffect, useRef, useState } from "react";

export interface QueryState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
  setData: (fn: (prev: T | undefined) => T | undefined) => void;
}

/** Minimal fetch-on-mount with optional polling. Keeps the last good data while refetching. */
export function useQuery<T>(fn: () => Promise<T>, deps: unknown[], opts: { intervalMs?: number } = {}): QueryState<T> {
  const [data, setDataState] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let alive = true;
    const run = () =>
      fnRef
        .current()
        .then((d) => {
          if (!alive) return;
          setDataState(d);
          setError(null);
        })
        .catch((e) => alive && setError(e))
        .finally(() => alive && setLoading(false));
    run();
    const t = opts.intervalMs ? setInterval(run, opts.intervalMs) : null;
    return () => {
      alive = false;
      if (t) clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, opts.intervalMs]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((f: (prev: T | undefined) => T | undefined) => setDataState(f), []);
  return { data, error, loading, reload, setData };
}
