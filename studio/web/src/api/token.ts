// Per-install secret (NFR-4). `reel studio` prints http://127.0.0.1:8765/?token=<token>; we keep it for the
// browser session and remove it from the address bar so it doesn't end up in history or screenshots.
const KEY = "reel.token";
const MOCK_KEY = "reel.mock";

function store(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Read ?token= and ?mock= once on load, persist them for the session, strip them from the URL. */
export function captureUrlParams(loc: Location = window.location, hist: History = window.history): void {
  const url = new URL(loc.href);
  const token = url.searchParams.get("token");
  const mock = url.searchParams.get("mock");
  const s = store();
  if (token !== null) {
    s?.setItem(KEY, token);
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
  return store()?.getItem(KEY) ?? "";
}

/** "1" = mock data, "down" = mock with the engine stopped (AC-2), "" = real API. */
export function getMockMode(): string {
  const fromSession = store()?.getItem(MOCK_KEY) ?? "";
  if (fromSession) return fromSession;
  return import.meta.env.MODE === "mock" || import.meta.env.VITE_MOCK === "1" ? "1" : "";
}
