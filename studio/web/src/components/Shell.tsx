import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useApi } from "../api/context";
import { useStatus } from "../hooks/status";
import { useQuery } from "../hooks/useQuery";
import { STAGE_LABEL } from "../lib/status";
import { Icon, type IconName } from "./icons";
import { Button, cx, Mono } from "./ui";

const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/", label: "Projects", icon: "home", end: true },
  { to: "/new", label: "New edit", icon: "plus" },
];
const STUDIO: { to: string; label: string; icon: IconName }[] = [
  { to: "/studio/libraries", label: "Libraries", icon: "library" },
  { to: "/studio/brands", label: "Brand kits", icon: "brand" },
  { to: "/studio/quality", label: "Quality lab", icon: "quality" },
  { to: "/studio/settings", label: "Settings", icon: "settings" },
];

function RailLink({ to, label, icon, end }: { to: string; label: string; icon: IconName; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      aria-label={label}
      className={({ isActive }) =>
        cx(
          "group relative flex h-11 w-11 items-center justify-center rounded-card transition-colors duration-hover",
          isActive ? "bg-ai/[0.18] text-ai-glow" : "text-fg-secondary hover:bg-bg-overlay hover:text-fg-primary",
        )
      }
    >
      <Icon name={icon} size={20} />
      <span
        role="tooltip"
        className="pointer-events-none absolute left-[calc(100%+12px)] top-1/2 z-50 -translate-y-1/2 whitespace-nowrap rounded-input border border-line-strong bg-bg-overlay px-2.5 py-1 text-label text-fg-primary opacity-0 transition-opacity duration-hover group-hover:opacity-100 group-focus-visible:opacity-100"
      >
        {label}
      </span>
    </NavLink>
  );
}

function NavRail() {
  return (
    <nav aria-label="Main" className="flex w-[72px] shrink-0 flex-col items-center gap-2 border-r border-line-subtle bg-bg-base py-4">
      <Link to="/" aria-label="Reel Studio home" className="mb-3 flex h-10 w-10 items-center justify-center rounded-card bg-bg-raised border border-line-subtle">
        <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
          <rect x="10" y="5" width="12" height="22" rx="3" fill="none" stroke="#9D85FF" strokeWidth="2" />
          <path d="M14 12.5v7l5.5-3.5z" fill="#9D85FF" />
        </svg>
      </Link>
      {NAV.map((n) => (
        <RailLink key={n.to} {...n} />
      ))}
      <div className="my-2 h-px w-8 bg-line-subtle" role="separator" />
      <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-fg-muted">Studio</span>
      {STUDIO.map((n) => (
        <RailLink key={n.to} {...n} />
      ))}
    </nav>
  );
}

function JobsIndicator() {
  const { jobs, health } = useStatus();
  const api = useApi();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const projects = useQuery(() => api.projects(), [api, open], {});
  const names = new Map((projects.data ?? []).map((p) => [p.id, p]));
  const running = jobs?.running ?? [];
  const queued = jobs?.queued ?? [];
  const limit = health?.jobs.limit ?? 3;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((o) => !o)}
        className="flex h-8 items-center gap-2 rounded-input border border-line-subtle bg-bg-raised px-3 text-[13px] text-fg-secondary hover:border-line-strong hover:text-fg-primary"
      >
        <span className={cx("h-2 w-2 rounded-full", running.length ? "bg-ai-glow pulse-dot" : "bg-fg-muted")} aria-hidden="true" />
        <span>
          <span className="text-fg-primary font-medium tabular">{running.length}</span>/{limit} running
          {queued.length > 0 && (
            <>
              {" · "}
              <span className="text-fg-primary font-medium tabular">{queued.length}</span> queued
            </>
          )}
        </span>
      </button>
      {open && (
        <div role="dialog" aria-label="Jobs" className="fade-in absolute right-0 top-10 z-40 w-80 rounded-card border border-line-strong bg-bg-overlay p-2 shadow-2xl">
          {running.length + queued.length === 0 && <p className="px-3 py-3 text-fg-secondary">No edits running.</p>}
          {[...running, ...queued].map((j) => {
            const p = names.get(j.project);
            const isQ = queued.includes(j);
            return (
              <Link
                key={j.id}
                to={j.project === "_lab" ? "/studio/quality" : j.project === "_library" ? "/studio/libraries" : `/p/${j.project}/live`}
                onClick={() => setOpen(false)}
                className="flex items-center justify-between gap-3 rounded-input px-3 py-2 hover:bg-bg-raised"
              >
                <span className="min-w-0">
                  <span className="block truncate text-fg-primary">{p?.name ?? (j.label || j.project)}</span>
                  <span className="block text-label font-normal text-fg-muted">{p?.client ?? j.kind}</span>
                </span>
                <span className={cx("shrink-0 text-label", isQ ? "text-fg-secondary" : "text-ai-glow")}>{isQ ? "Queued" : STAGE_LABEL[p?.stage ?? ""] ?? j.kind}</span>
              </Link>
            );
          })}
          {queued.length > 0 && <p className="px-3 pb-1 pt-2 text-label font-normal text-fg-muted">Queued edits start when a slot frees up.</p>}
        </div>
      )}
    </div>
  );
}

function HealthChip() {
  const { engine, health } = useStatus();
  const bad = health?.tools.filter((t) => !t.ok).length ?? 0;
  const tone = engine !== "ok" ? "bg-st-fail" : bad ? "bg-st-hold" : "bg-st-sendable";
  const label = engine === "checking" ? "Checking engine…" : engine !== "ok" ? "Engine offline" : bad ? `${bad} health issue${bad > 1 ? "s" : ""}` : "Engine healthy";
  return (
    <Link to="/studio/settings" className="flex h-8 items-center gap-2 rounded-input border border-line-subtle bg-bg-raised px-3 text-[13px] text-fg-secondary hover:border-line-strong hover:text-fg-primary">
      <span className={cx("h-2 w-2 rounded-full", tone)} aria-hidden="true" />
      {label}
    </Link>
  );
}

function TopBar() {
  const api = useApi();
  const { health, engine } = useStatus();
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line-subtle bg-bg-base/90 px-8 backdrop-blur">
      <div className="flex items-center gap-3">
        <span className="text-body font-semibold tracking-tight">Reel Studio</span>
        {health && <Mono className="text-fg-muted">v{health.version}</Mono>}
        {api.mode === "mock" && (
          <span className="rounded-full border border-ai/60 px-2 py-0.5 text-label text-ai-glow" title="Showing sample data. Open the link `reel studio` prints to use the engine.">
            Sample data
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {engine === "ok" && <JobsIndicator />}
        <HealthChip />
      </div>
    </header>
  );
}

export function EngineDown() {
  const { refresh } = useStatus();
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="w-full max-w-lg rounded-panel border border-line-subtle bg-bg-raised p-8">
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-card bg-st-fail/[0.12] text-st-fail">
          <Icon name="alert" size={22} />
        </div>
        <h1 className="text-title">Engine is not running</h1>
        <p className="mt-2 text-fg-secondary">Reel Studio needs the local engine. Start it in Terminal, then open the link it prints:</p>
        <pre className="mt-4 overflow-x-auto rounded-card border border-line-subtle bg-bg-inset px-4 py-3 font-mono text-mono text-fg-primary">reel studio --open</pre>
        <p className="mt-3 text-label font-normal text-fg-muted">It listens on 127.0.0.1:8765 only. This page checks again every 5 seconds.</p>
        <div className="mt-6 flex gap-2">
          <Button variant="primary" icon="retry" onClick={refresh}>
            Check again
          </Button>
        </div>
      </div>
    </div>
  );
}

function TokenMissing() {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="w-full max-w-lg rounded-panel border border-line-subtle bg-bg-raised p-8">
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-card bg-st-hold/[0.12] text-st-hold">
          <Icon name="lock" size={22} />
        </div>
        <h1 className="text-title">This browser isn't signed in to the studio</h1>
        <p className="mt-2 text-fg-secondary">
          The engine refuses requests without its private token. Open the full link that <code className="font-mono text-mono">reel studio</code> printed in Terminal
          (it ends with <code className="font-mono text-mono">?token=…</code>).
        </p>
      </div>
    </div>
  );
}

export function Shell({ children }: { children?: ReactNode }) {
  const { engine } = useStatus();
  const loc = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    mainRef.current?.scrollTo?.({ top: 0 });
  }, [loc.pathname]);
  return (
    <div className="flex h-full min-h-0">
      <a href="#main" className="skip-link rounded-input bg-ai px-3 py-2 text-white">
        Skip to content
      </a>
      <NavRail />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main id="main" ref={mainRef} tabIndex={-1} className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
          {engine === "offline" ? <EngineDown /> : engine === "auth" ? <TokenMissing /> : children ?? <Outlet />}
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 pb-6">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-label text-fg-muted">{eyebrow}</div>}
        <h1 className="text-display tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-fg-secondary">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
