import { NavLink, Outlet, useOutletContext, useParams, Link } from "react-router-dom";
import { friendlyError } from "../../api/errors";
import { useApi } from "../../api/context";
import { Icon, type IconName } from "../../components/icons";
import { cx, Loading, Mono, Notice, StatusBadge } from "../../components/ui";
import { useLiveProject, type LiveProject } from "../../hooks/useLiveProject";
import { useStatus } from "../../hooks/status";
import { useQuery } from "../../hooks/useQuery";
import { usd } from "../../lib/format";
import { badgeOf, STAGE_LABEL } from "../../lib/status";
import type { Project } from "../../api/types";

export type ProjectCtx = LiveProject & { project: Project };
export const useProject = () => useOutletContext<ProjectCtx>();

const TABS: { to: string; label: string; icon: IconName }[] = [
  { to: "live", label: "Live", icon: "sparkle" },
  { to: "review", label: "Review", icon: "phone" },
  { to: "layers", label: "Layers", icon: "layers" },
  { to: "revise", label: "Revise", icon: "chat" },
  { to: "adjust", label: "Adjust", icon: "sliders" },
  { to: "deliver", label: "Deliver", icon: "download" },
];

/** FR-3: compact strip of every running edit; click to switch the view. */
function RunningStrip({ current }: { current: string }) {
  const api = useApi();
  const { jobs } = useStatus();
  const list = useQuery(() => api.projects(), [api, jobs?.running.length, jobs?.queued.length], { intervalMs: 3000 });
  const running = (list.data ?? []).filter((p) => p.status === "running" || p.status === "queued");
  if (running.length < 1) return null;
  return (
    <nav aria-label="Running edits" className="flex items-center gap-2 overflow-x-auto border-b border-line-subtle bg-bg-base px-8 py-2">
      <span className="shrink-0 text-label text-fg-muted">Running edits</span>
      {running.map((p) => (
        <Link
          key={p.id}
          to={`/p/${p.id}/live`}
          aria-current={p.id === current ? "page" : undefined}
          className={cx(
            "flex h-7 shrink-0 items-center gap-2 rounded-full border px-3 text-[13px] transition-colors duration-hover",
            p.id === current ? "border-ai bg-ai/[0.14] text-fg-primary" : "border-line-subtle bg-bg-raised text-fg-secondary hover:border-line-strong hover:text-fg-primary",
          )}
        >
          <span className={cx("h-1.5 w-1.5 rounded-full", p.status === "running" ? "bg-ai-glow pulse-dot" : "bg-st-queued")} aria-hidden="true" />
          <span className="max-w-[180px] truncate">{p.name}</span>
          <span className="text-fg-muted">{p.status === "queued" ? "Queued" : STAGE_LABEL[p.stage ?? ""] ?? ""}</span>
        </Link>
      ))}
    </nav>
  );
}

export default function ProjectLayout() {
  const { id = "" } = useParams();
  const live = useLiveProject(id);
  const p = live.project;

  return (
    <div className="flex flex-1 flex-col">
      <RunningStrip current={id} />
      <div className="mx-auto w-full max-w-[1440px] px-8 pt-6">
        {live.error && !p ? (
          <Notice tone="error" title="Couldn't open this project">
            {friendlyError(live.error)} <Link to="/" className="text-ai-glow underline">Back to projects</Link>
          </Notice>
        ) : !p ? (
          <Loading label="Opening project…" />
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0">
                <Link to="/" className="mb-1 inline-flex items-center gap-1 text-label text-fg-muted hover:text-fg-secondary">
                  <Icon name="chevron" size={12} className="rotate-180" /> Projects
                </Link>
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="truncate text-display tracking-tight">{p.name}</h1>
                  <StatusBadge badge={badgeOf(p)} stage={p.stage} count={p.needs_attention.length || undefined} size="lg" />
                </div>
                <p className="mt-1 text-fg-secondary">
                  {p.client ?? "No client"} · AI cost <Mono className="text-fg-primary">{usd(p.cost_usd)}</Mono>
                  {p.versions.length > 0 && <> · version {p.versions.at(-1)!.n}</>}
                </p>
              </div>
            </div>
            <nav aria-label="Project" className="mt-5 flex gap-1 border-b border-line-subtle">
              {TABS.map((t) => (
                <NavLink
                  key={t.to}
                  to={t.to}
                  className={({ isActive }) =>
                    cx(
                      "-mb-px flex h-10 items-center gap-2 border-b-2 px-3 text-body font-medium transition-colors duration-hover",
                      isActive ? "border-ai-glow text-fg-primary" : "border-transparent text-fg-secondary hover:text-fg-primary",
                    )
                  }
                >
                  <Icon name={t.icon} size={16} />
                  {t.label}
                </NavLink>
              ))}
            </nav>
          </>
        )}
      </div>
      {p && (
        <div className="mx-auto w-full max-w-[1440px] flex-1 px-8 py-6">
          <Outlet context={{ ...live, project: p } satisfies ProjectCtx} />
        </div>
      )}
    </div>
  );
}
