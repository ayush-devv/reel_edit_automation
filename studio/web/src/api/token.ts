// Per-install secret (NFR-4). `reel studio` prints http://127.0.0.1:8765/?token=<token>; we remove it from the
// address bar so it doesn't end up in history or screenshots. The token is remembered in this browser's
// localStorage (scoped to the 127.0.0.1:8765 origin only), so new tabs and restarts stay signed in. A new token
// (a fresh install) simply replaces it. Mock mode stays per tab.
const KEY = "reel.token";
const MOCK_KEY = "reel.mock";

function store(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function keep(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return store();
  }
}

/** Read ?token= and ?mock= once on load, persist them for the session, strip them from the URL. */
export function captureUrlParams(loc: Location = window.location, hist: History = window.history): void {
  const url = new URL(loc.href);
  const token = url.searchParams.get("token");
  const mock = url.searchParams.get("mock");
  const s = store();
  if (token !== null) {
    keep()?.setItem(KEY, token);
    url.searchParams.delete("token");
  }
  if (mock !== null) {
    if (mock === "0") s?.removeItem(MOCK_KEY);
    else s?.setItem(MOCK_KEY, mock || "1");
    url.searchParams.delete("mock");
  }
  if (token !== null || mock !== null) hist.replaceState(hist.state, "", url.pathname + url.search + url.hash);
}

export function getToken(): string {
  // Older builds kept it per tab; still accept that copy.
  return keep()?.getItem(KEY) ?? store()?.getItem(KEY) ?? "";
}

/** "1" = mock data, "down" = mock with the engine stopped (AC-2), "" = real API. */
export function getMockMode(): string {
  const fromSession = store()?.getItem(MOCK_KEY) ?? "";
  if (fromSession) return fromSession;
  return import.meta.env.MODE === "mock" || import.meta.env.VITE_MOCK === "1" ? "1" : "";
}
