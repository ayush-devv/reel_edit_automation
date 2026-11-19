import { NavLink, Outlet, useLocation, useOutletContext, useParams, Link } from "react-router-dom";
import { friendlyError } from "../../api/errors";
import { useApi } from "../../api/context";
import { Icon, type IconName } from "../../components/icons";
import { StoryStrip } from "../../components/StoryStrip";
import { cx, Empty, Loading, Mono, Notice, StatusBadge } from "../../components/ui";
import { useLiveProject, type LiveProject } from "../../hooks/useLiveProject";
import { useStatus } from "../../hooks/status";
import { useQuery } from "../../hooks/useQuery";
import { usd } from "../../lib/format";
import { badgeOf, STAGE_LABEL } from "../../lib/status";
import type { Project } from "../../api/types";

export type ProjectCtx = LiveProject & { project: Project };
export const useProject = () => useOutletContext<ProjectCtx>();

/** Empty state for a project tab whose content needs a finished edit (Review, Layers, Revise, Adjust, Deliver).
 *  Says why it's empty and gives the one way forward: watch the edit, or see what stopped it. */
export function NotYet({ what, icon, opens }: { what: string; icon: IconName; opens: string }) {
  const { project: p } = useProject();
  const failed = p.status === "failed";
  return (
    <Empty
      icon={icon}
      title={`Nothing to ${what} yet`}
      action={
        <Link to="../live" relative="path" className="inline-flex h-9 items-center gap-2 rounded-control border border-line-strong bg-bg-overlay px-4 text-ui text-fg-primary hover:bg-bg-high">
          {failed ? "See what stopped it" : "Watch it live"}
        </Link>
      }
    >
      {opens} {failed ? "This edit stopped before it finished." : p.status === "queued" ? "This edit is queued." : "The edit is still running."}
    </Empty>
  );
}

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
    <nav aria-label="Running edits" className="flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b border-line-subtle bg-bg-raised px-6">
      <span className="shrink-0 px-2 text-meta text-fg-muted">Running edits</span>
      {running.map((p) => (
        <Link
          key={p.id}
          to={`/p/${p.id}/live`}
          aria-current={p.id === current ? "page" : undefined}
          className={cx(
            "flex h-7 shrink-0 items-center gap-2 rounded-control px-2 text-ui transition-colors duration-hover",
            p.id === current ? "bg-bg-high text-fg-primary" : "text-fg-secondary hover:bg-bg-overlay hover:text-fg-primary",
          )}
        >
          <span className={cx("h-2 w-2 rounded-full", p.status === "running" ? "bg-ai pulse-dot" : "bg-st-queued")} aria-hidden="true" />
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
  const onLayers = useLocation().pathname.endsWith("/layers");

  return (
    <div className="flex flex-1 flex-col">
      <RunningStrip current={id} />
      {live.error && !p ? (
        <div className="px-8 pt-6">
          <Notice tone="error" title="Couldn’t open this project">
            {friendlyError(live.error)} <Link to="/" className="text-info underline">Back to projects</Link>
          </Notice>
        </div>
      ) : !p ? (
        <div className="px-8 pt-6">
          <Loading label="Opening project…" />
        </div>
      ) : (
        <>
          {/* 64 px header: breadcrumb left, status and cost right. */}
          <header className="flex min-h-16 flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-line-subtle px-8 py-3">
            <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2">
              <Link to="/" className="text-body text-fg-secondary hover:text-fg-primary">
                Projects
              </Link>
              <Icon name="chevron" size={16} className="shrink-0 text-fg-muted" />
              <h1 className="truncate text-title" aria-current="page">
                {p.name}
              </h1>
            </nav>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
              <span className="text-meta text-fg-muted">
                {p.client ?? "No client"} · AI cost <Mono className="text-fg-secondary">{usd(p.cost_usd)}</Mono>
                {p.versions.length > 0 && <> · v{p.versions.at(-1)!.n}</>}
              </span>
              <StatusBadge badge={badgeOf(p)} stage={p.stage} count={p.needs_attention.length || undefined} size="lg" />
            </div>
          </header>
          <nav aria-label="Project" className="flex h-11 shrink-0 gap-2 border-b border-line-subtle px-6">
            {TABS.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                className={({ isActive }) =>
                  cx(
                    "-mb-px flex items-center border-b-2 px-3 text-ui transition-colors duration-hover",
                    isActive ? "border-signal text-fg-primary" : "border-transparent text-fg-secondary hover:text-fg-primary",
                  )
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
          <div className="w-full flex-1 px-8 py-6">
            <Outlet context={{ ...live, project: p } satisfies ProjectCtx} />
          </div>
          {/* Layers has its own, more detailed strip; elsewhere the docked strip keeps orientation. */}
          {p.versions.length > 0 && !onLayers && <StoryStrip projectId={p.id} versionKey={p.versions.length} />}
        </>
      )}
    </div>
  );
}
