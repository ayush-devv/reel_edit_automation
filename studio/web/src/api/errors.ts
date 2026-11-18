import type { ValidatorIssue } from "./types";

export type ErrorKind = "offline" | "auth" | "toolchain" | "validation" | "conflict" | "notfound" | "bad";

/** One error type for every API failure, so screens can pick the right plain-language message. */
export class ApiError extends Error {
  readonly status: number;
  readonly kind: ErrorKind;
  readonly issues: ValidatorIssue[];
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.kind = kindFor(status);
    this.issues = extractIssues(detail);
  }
}

function kindFor(status: number): ErrorKind {
  if (status === 0 || status === 502 || status === 504) return "offline"; // no engine behind the proxy
  if (status === 401 || status === 403) return "auth";
  if (status === 503) return "toolchain";
  if (status === 422) return "validation";
  if (status === 409) return "conflict";
  if (status === 404) return "notfound";
  return "bad";
}

function extractIssues(detail: unknown): ValidatorIssue[] {
  if (!detail || typeof detail !== "object") return [];
  const d = detail as { issues?: unknown; detail?: unknown };
  const raw = Array.isArray(d.issues) ? d.issues : d.detail && typeof d.detail === "object" ? (d.detail as { issues?: unknown }).issues : null;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => ({
      code: String(x.code ?? ""),
      path: String(x.path ?? ""),
      message: String(x.message ?? ""),
      fix: String(x.fix ?? ""),
    }));
}

export function friendlyError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.kind) {
      case "offline":
        return "Engine is not running.";
      case "auth":
        return "This browser doesn't have the studio token. Reopen the link `reel studio` printed.";
      case "conflict":
        return "Another job is already running for this project. Wait for it to finish.";
      case "toolchain":
        return "A required tool is missing. See Settings → Health.";
      default:
        return e.message;
    }
  }
  return e instanceof Error ? e.message : String(e);
}
