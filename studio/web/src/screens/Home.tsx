// FR-1 Projects home: attention first, filters, search, ambient 3D backdrop, drop files to start an edit.
import { lazy, Suspense, useMemo, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApi } from "../api/context";
import { friendlyError } from "../api/errors";
import type { ProjectSummary } from "../api/types";
import { Icon } from "../components/icons";
import { PageHeader } from "../components/Shell";
import { Thumb } from "../components/Thumb";
import { Button, cx, Empty, Loading, Notice, ProgressBar, Segmented, Select, StatusBadge, TextInput } from "../components/ui";
import { useStatus } from "../hooks/status";
import { use3D } from "../hooks/useMedia";
import { useQuery } from "../hooks/useQuery";
import { ago, duration } from "../lib/format";
import { setPendingFiles } from "../lib/pendingFiles";
import { badgeOf, sortByAttention, STAGE_LABEL, type Badge } from "../lib/status";

const AmbientScene = lazy(() => import("../three/AmbientScene"));

type Filter = "all" | "attention" | "editing" | "sendable" | "delivered";
const FILTER_MATCH: Record<Filter, (b: Badge) => boolean> = {
  all: () => true,
  attention: (b) => b === "hold" || b === "failed",
  editing: (b) => b === "editing" || b === "queued",
  sendable: (b) => b === "sendable",
  delivered: (b) => b === "delivered",
};

export function projectHref(p: Pick<ProjectSummary, "id" | "status">): string {
  return p.status === "running" || p.status === "queued" || p.status === "failed" || p.status === "draft" ? `/p/${p.id}/live` : `/p/${p.id}/review`;
}

function ProjectCard({ p }: { p: ProjectSummary }) {
  const api = useApi();
  const b = badgeOf(p);
  const holdCount = p.needs_attention.length || undefined;
  return (
    <li>
      <Link
        to={projectHref(p)}
        className="group block overflow-hidden rounded-card border border-line-subtle bg-bg-raised transition-[transform,border-color] duration-hover ease-std hover:-translate-y-0.5 hover:border-ai focus-visible:border-ai"
      >
        <Thumb id={p.id} src={p.thumb ? api.mediaUrl(p.id, p.thumb) : null} label={p.name}>
          <div className="absolute left-2 top-2">
            <StatusBadge badge={b} stage={p.stage} count={b === "hold" ? holdCount : undefined} />
          </div>
          {p.duration_s !== null && (
            <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 font-mono text-mono text-white">{duration(p.duration_s)}</span>
          )}
          {b === "editing" && (
            <div className="absolute inset-x-2 bottom-2">
              <ProgressBar value={p.progress} label={`${p.name} progress`} />
            </div>
          )}
        </Thumb>
        <div className="space-y-1 p-3">
          <h3 className="truncate font-semibold text-fg-primary" title={p.name}>
            {p.name}
          </h3>
          <p className="truncate text-fg-secondary">{p.client ?? "No client"}</p>
          <p className="flex items-center justify-between gap-2 text-label font-normal text-fg-muted">
            <span>{p.delivered_at ? `Delivered ${ago(p.delivered_at)}` : `Updated ${ago(p.updated)}`}</span>
          </p>
          {p.needs_attention.length > 0 && (
            <p className={cx("truncate text-label", b === "failed" ? "text-st-fail" : "text-st-hold")}>{p.needs_attention.join(" · ")}</p>
          )}
        </div>
      </Link>
    </li>
  );
}

function AttentionStrip({ list }: { list: ProjectSummary[] }) {
  const need = list.filter((p) => ["hold", "failed"].includes(badgeOf(p)));
  if (!need.length) return null;
  return (
    <section aria-label="Needs you" className="mb-6 rounded-panel border border-st-hold/30 bg-st-hold/[0.05] px-5 py-4">
      <h2 className="mb-2 flex items-center gap-2 text-label text-st-hold">
        <Icon name="alert" size={14} /> {need.length} {need.length === 1 ? "reel needs" : "reels need"} you
      </h2>
      <ul className="flex flex-wrap gap-2">
        {need.map((p) => (
          <li key={p.id}>
            <Link to={projectHref(p)} className="flex items-center gap-2 rounded-input border border-line-subtle bg-bg-raised px-3 py-1.5 hover:border-line-strong">
              <StatusBadge badge={badgeOf(p)} />
              <span className="text-fg-primary">{p.name}</span>
              <span className="text-fg-muted">— {p.needs_attention.join(", ") || (p.stage ? `stopped at ${STAGE_LABEL[p.stage]}` : "")}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function Home() {
  const api = useApi();
  const nav = useNavigate();
  const { busy } = useStatus();
  const can3D = use3D();
  const q = useQuery(() => api.projects(), [api], { intervalMs: 4000 });
  const [filter, setFilter] = useState<Filter>("all");
  const [client, setClient] = useState("");
  const [search, setSearch] = useState("");
  const [dragging, setDragging] = useState(false);

  const sorted = useMemo(() => sortByAttention(q.data ?? []), [q.data]);
  const clients = useMemo(() => [...new Set(sorted.map((p) => p.client).filter((c): c is string => !!c))].sort(), [sorted]);
  const shown = sorted.filter(
    (p) => FILTER_MATCH[filter](badgeOf(p)) && (!client || p.client === client) && (!search || `${p.name} ${p.client ?? ""}`.toLowerCase().includes(search.toLowerCase())),
  );

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = [...e.dataTransfer.files];
    if (!files.length) return;
    setPendingFiles(files);
    nav("/new");
  };

  return (
    <div
      className="relative flex-1"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        {can3D ? (
          <Suspense fallback={null}>
            <AmbientScene busy={busy} />
          </Suspense>
        ) : (
          <StaticBackdrop />
        )}
        <div className="absolute inset-0 bg-gradient-to-b from-bg-base/40 via-bg-base/70 to-bg-base" />
      </div>

      <div className="relative mx-auto w-full max-w-[1440px] px-8 py-8">
        <PageHeader
          title="Projects"
          subtitle="Reels that need you come first."
          actions={
            <Button variant="primary" size={40} icon="plus" onClick={() => nav("/new")}>
              New edit
            </Button>
          }
        />

        {q.error && !q.data ? <Notice tone="error" title="Couldn't load projects">{friendlyError(q.error)}</Notice> : null}
        {q.loading && !q.data ? <Loading label="Loading projects…" /> : null}

        {q.data && q.data.length === 0 && (
          <div className="rounded-panel border border-line-subtle bg-bg-raised/80">
            <Empty
              icon="film"
              title="Welcome to Reel Studio"
              action={
                <Button variant="primary" size={40} icon="plus" onClick={() => nav("/new")}>
                  New edit
                </Button>
              }
            >
              Drop a client’s raw footage anywhere on this page, or start a new edit. The Editor cuts it, checks it and tells you if it’s safe to send.
            </Empty>
          </div>
        )}

        {q.data && q.data.length > 0 && (
          <>
            <AttentionStrip list={sorted} />
            <div className="mb-5 flex flex-wrap items-center gap-3">
              <Segmented
                label="Filter by status"
                value={filter}
                onChange={setFilter}
                options={[
                  { value: "all", label: `All ${sorted.length}` },
                  { value: "attention", label: "Needs me" },
                  { value: "editing", label: "Editing" },
                  { value: "sendable", label: "Sendable" },
                  { value: "delivered", label: "Delivered" },
                ]}
              />
              <div className="w-52">
                <Select aria-label="Filter by client" value={client} onChange={(e) => setClient(e.target.value)}>
                  <option value="">All clients</option>
                  {clients.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </Select>
              </div>
              <div className="relative w-64">
                <Icon name="search" size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-muted" />
                <TextInput aria-label="Search projects" placeholder="Search by name" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
              </div>
              <span className="ml-auto text-label font-normal text-fg-muted">Tip: drop video files anywhere here to start an edit.</span>
            </div>
            {shown.length === 0 ? (
              <p className="py-10 text-center text-fg-secondary">No projects match these filters.</p>
            ) : (
              <ul className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4" aria-label="Projects, needs-you first">
                {shown.map((p) => (
                  <ProjectCard key={p.id} p={p} />
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-bg-base/80 backdrop-blur-sm">
          <div className="rounded-panel border-2 border-dashed border-ai-glow px-16 py-12 text-center">
            <Icon name="upload" size={32} className="mx-auto mb-3 text-ai-glow" />
            <p className="text-title">Drop to start a new edit</p>
            <p className="mt-1 text-fg-secondary">mp4, mov, m4v, mkv or webm · up to 4 GB each</p>
          </div>
        </div>
      )}
    </div>
  );
}

/** Static stand-in for the ambient scene (reduced motion / no WebGL). */
function StaticBackdrop() {
  return (
    <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid slice" viewBox="0 0 1440 900">
      <defs>
        <radialGradient id="amb" cx="70%" cy="10%" r="70%">
          <stop offset="0" stopColor="#6A4BF0" stopOpacity="0.16" />
          <stop offset="1" stopColor="#0B0D12" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="1440" height="900" fill="url(#amb)" />
      {[
        [1080, 120, -8, "#9D85FF"],
        [1250, 260, 6, "#36D6E7"],
        [960, 330, 12, "#8a90a6"],
        [180, 520, -5, "#8a90a6"],
        [1320, 560, -12, "#9D85FF"],
        [640, 90, 4, "#8a90a6"],
      ].map(([x, y, r, c], i) => (
        <rect key={i} x={x as number} y={y as number} width="90" height="160" rx="12" fill="none" stroke={c as string} strokeOpacity="0.22" strokeWidth="3" transform={`rotate(${r} ${x} ${y})`} />
      ))}
    </svg>
  );
}
