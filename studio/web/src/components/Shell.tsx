import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useApi } from "../api/context";
import { useStatus } from "../hooks/status";
import { useQuery } from "../hooks/useQuery";
import { STAGE_LABEL } from "../lib/status";
import { Icon, type IconName } from "./icons";
import { Button, cx } from "./ui";

// Cutting Room shell: a 72 px rail of icon + label destinations, then each screen's own 64 px header.
// Global status (jobs, engine health, sample data) lives at the foot of the rail.
const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/", label: "Projects", icon: "home", end: true },
  { to: "/new", label: "New edit", icon: "plus" },
  { to: "/studio/libraries", label: "Library", icon: "music" },
  { to: "/studio/brands", label: "Brands", icon: "brand" },
  { to: "/studio/quality", label: "Quality", icon: "quality" },
];

const railItem = (active: boolean) =>
  cx(
    "relative flex w-16 flex-col items-center gap-1 rounded-card py-2 text-meta transition-colors duration-hover",
    active ? "bg-bg-overlay text-fg-primary" : "text-fg-secondary hover:bg-bg-overlay/60 hover:text-fg-primary",
  );

function ActiveBar() {
  return <span className="absolute -left-1 top-2 bottom-2 w-0.5 rounded-full bg-signal shadow-[0_0_12px_2px_rgba(242,169,59,0.6)]" aria-hidden="true" />;
}

function RailLink({ to, label, icon, end, dot }: { to: string; label: string; icon: IconName; end?: boolean; dot?: { tone: string; label: string } | null }) {
  // On a project page, "Projects" is the current location.
  const loc = useLocation();
  const inProject = to === "/" && loc.pathname.startsWith("/p/");
  return (
    <NavLink to={to} end={end} aria-label={dot ? `${label} (${dot.label})` : undefined} className={({ isActive }) => railItem(isActive || inProject)}>
      {({ isActive }) => (
        <>
          {(isActive || inProject) && <ActiveBar />}
          <span className="relative">
            <Icon name={icon} size={20} />
            {dot && <span className={cx("absolute -right-1 -top-0.5 h-2 w-2 rounded-full ring-2 ring-bg-raised", dot.tone)} aria-hidden="true" />}
          </span>
          <span>{label}</span>
        </>
      )}
    </NavLink>
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
        aria-label={`Jobs: ${running.length} of ${limit} running${queued.length ? `, ${queued.length} queued` : ""}`}
        onClick={() => setOpen((o) => !o)}
        className={railItem(open)}
      >
        <span className="flex items-center gap-1.5 font-mono text-mono tabular text-fg-primary">
          <span className={cx("h-2 w-2 rounded-full", running.length ? "bg-ai pulse-dot" : "bg-fg-muted")} aria-hidden="true" />
          {running.length}/{limit}
        </span>
        <span>{queued.length ? `+${queued.length} queued` : "Jobs"}</span>
      </button>
      {open && (
        <div role="dialog" aria-label="Jobs" className="fade-in absolute bottom-0 left-[calc(100%+12px)] z-40 w-80 rounded-card border border-line-strong bg-bg-overlay p-2 shadow-menu">
          {running.length + queued.length === 0 && <p className="px-3 py-3 text-fg-secondary">No edits running.</p>}
          {[...running, ...queued].map((j) => {
            const p = names.get(j.project);
            const isQ = queued.includes(j);
            return (
              <Link
                key={j.id}
                to={j.project === "_lab" ? "/studio/quality" : j.project === "_library" ? "/studio/libraries" : `/p/${j.project}/live`}
                onClick={() => setOpen(false)}
                className="flex items-center justify-between gap-3 rounded-control px-3 py-2 hover:bg-bg-high"
              >
                <span className="min-w-0">
                  <span className="block truncate text-ui text-fg-primary">{p?.name ?? (j.label || j.project)}</span>
                  <span className="block text-meta text-fg-muted">{p?.client ?? j.kind}</span>
                </span>
                <span className={cx("shrink-0 text-label", isQ ? "text-fg-secondary" : "text-ai")}>{isQ ? "Queued" : STAGE_LABEL[p?.stage ?? ""] ?? j.kind}</span>
              </Link>
            );
          })}
          {queued.length > 0 && <p className="px-3 pb-1 pt-2 text-meta text-fg-muted">Queued edits start when a slot frees up.</p>}
        </div>
      )}
    </div>
  );
}

function useHealthDot() {
  const { engine, health } = useStatus();
  const bad = health?.tools.filter((t) => !t.ok && t.required).length ?? 0;
  if (engine === "checking") return null;
  if (engine !== "ok") return { tone: "bg-st-fail", label: "engine offline" };
  if (bad) return { tone: "bg-st-hold", label: `${bad} health issue${bad > 1 ? "s" : ""}` };
  return null;
}

function NavRail() {
  const api = useApi();
  const { engine } = useStatus();
  const healthDot = useHealthDot();
  return (
    <nav aria-label="Main" className="flex w-[72px] shrink-0 flex-col items-center gap-2 border-r border-line-subtle bg-bg-raised/75 py-4 backdrop-blur-md">
      <Link to="/" aria-label="Reel Studio home" className="mb-4 flex h-9 w-9 items-center justify-center rounded-card bg-[linear-gradient(135deg,#F2A93B,#45D0C1)] text-signal-on shadow-[0_6px_20px_-6px_rgba(242,169,59,0.7)]">
        <Icon name="film" size={18} />
      </Link>
      {NAV.map((n) => (
        <RailLink key={n.to} {...n} />
      ))}
      <div className="flex-1" />
      {api.mode === "mock" && (
        <span className="px-1 text-center text-meta text-info" title="Showing sample data. Open the link `reel studio` prints to use the engine.">
          Sample data
        </span>
      )}
      {engine === "ok" && <JobsIndicator />}
      <RailLink to="/studio/settings" label="Settings" icon="settings" dot={healthDot} />
    </nav>
  );
}

/** Failed-state pattern (11 · States): left-aligned, plain words, what to try. No card. */
function StatePage({ icon, tone, title, children }: { icon: IconName; tone: string; title: string; children: ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="w-full max-w-[520px]">
        <Icon name={icon} size={24} className={tone} />
        <h1 className="mt-4 text-title">{title}</h1>
        {children}
      </div>
    </div>
  );
}

export function EngineDown() {
  const { refresh } = useStatus();
  return (
    <StatePage icon="alert" tone="text-st-fail" title="Engine is not running">
      <p className="mt-2 text-fg-secondary">Reel Studio needs the local engine. Start it in Terminal, then open the link it prints:</p>
      <pre className="mt-4 overflow-x-auto rounded-control bg-bg-inset px-4 py-3 font-mono text-mono text-fg-secondary">reel studio --open</pre>
      <p className="mt-3 text-meta text-fg-muted">It listens on 127.0.0.1:8765 only. This page checks again every 5 seconds.</p>
      <div className="mt-6 flex gap-2">
        <Button variant="primary" icon="retry" onClick={refresh}>
          Check again
        </Button>
      </div>
    </StatePage>
  );
}

function TokenMissing() {
  return (
    <StatePage icon="lock" tone="text-st-hold" title="This browser isn’t signed in to the studio">
      <p className="mt-2 text-fg-secondary">
        The engine refuses requests without its private token. Open the full link that <code className="font-mono text-mono">reel studio</code> printed in Terminal
        (it ends with <code className="font-mono text-mono">?token=…</code>).
      </p>
    </StatePage>
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
      <a href="#main" className="skip-link rounded-control bg-signal px-3 py-2 text-signal-on">
        Skip to content
      </a>
      <NavRail />
      <main id="main" ref={mainRef} tabIndex={-1} className="relative flex min-h-0 min-w-0 flex-1 scroll-pb-24 flex-col overflow-y-auto">
        {engine === "offline" ? <EngineDown /> : engine === "auth" ? <TokenMissing /> : children ?? <Outlet />}
      </main>
    </div>
  );
}

/** The screen header: a 64 px bar under a hairline. Title + short description left, actions right. */
export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="-mx-8 -mt-8 mb-8 flex min-h-16 flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-line-subtle px-8 py-3">
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-6 gap-y-1">
        <h1 className="text-title">{title}</h1>
        {subtitle && <p className="text-meta text-fg-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  );
}
