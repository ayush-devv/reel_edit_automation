// FR-1 Projects home: a 3D wall of your reels, "Needs you" first, filters, search, drop files to start an edit.
// Cinematic studio: each reel glows in its own colour (from its thumbnail); the wall is the hero, the list below
// stays the accessible path.
import { lazy, Suspense, useMemo, useState, type CSSProperties, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApi } from "../api/context";
import { friendlyError } from "../api/errors";
import type { ProjectSummary } from "../api/types";
import { Icon } from "../components/icons";
import { PageHeader } from "../components/Shell";
import { Thumb } from "../components/Thumb";
import { Button, Loading, Notice, ProgressBar, Segmented, Select, StatusBadge, TextInput } from "../components/ui";
import { useQuery } from "../hooks/useQuery";
import { ago, duration } from "../lib/format";
import { setPendingFiles } from "../lib/pendingFiles";
import { badgeOf, sortByAttention, STAGE_LABEL, type Badge } from "../lib/status";
import { useImageTint, useImageTints } from "../lib/tint";
import { useStatus } from "../hooks/status";
import { use3D } from "../hooks/useMedia";
import { color } from "../theme/tokens";
import type { WallItem } from "../three/ReelWall";

const ReelWall = lazy(() => import("../three/ReelWall"));

const BADGE_WORD: Record<Badge, string> = { hold: "Hold", failed: "Failed", sendable: "Sendable", editing: "Editing", queued: "Queued", delivered: "Delivered", draft: "Draft" };
const BADGE_COLOR: Record<Badge, string> = {
  hold: color.status.hold,
  failed: color.status.fail,
  sendable: color.status.sendable,
  editing: color.accent.ai,
  queued: color.text.muted,
  delivered: color.text.secondary,
  draft: color.text.muted,
};

/** Hero: the 3D wall of recent reels (flat row of glowing posters under reduced motion / no WebGL). */
function Hero({ list }: { list: ProjectSummary[] }) {
  const api = useApi();
  const nav = useNavigate();
  const { busy } = useStatus();
  const can3D = use3D();
  const recent = list.slice(0, 9);
  const thumbs = recent.map((p) => (p.thumb ? api.mediaUrl(p.id, p.thumb, p.updated) : null));
  const tints = useImageTints(thumbs);
  const items: WallItem[] = recent.map((p, i) => {
    const b = badgeOf(p);
    return { id: p.id, name: p.name, status: BADGE_WORD[b], statusColor: BADGE_COLOR[b], thumb: thumbs[i], tint: tints[i] };
  });
  if (!items.length) return null;
  return (
    <section aria-label="Recent reels" className="relative -mx-8 -mt-8 mb-10 h-[380px] overflow-hidden border-b border-line-subtle">
      {can3D ? (
        <Suspense fallback={null}>
          <ReelWall items={items} busy={busy} onOpen={(id) => nav(projectHref(list.find((p) => p.id === id)!))} />
        </Suspense>
      ) : (
        <ul className="flex h-full items-center justify-center gap-6 px-8" aria-hidden="true">
          {items.slice(0, 6).map((it) => (
            <li key={it.id} className="h-[280px] aspect-[9/16] overflow-hidden rounded-surface bg-bg-high" style={{ boxShadow: `0 0 60px 6px rgba(${it.tint}, 0.28)` }}>
              {it.thumb && <img src={it.thumb} alt="" className="h-full w-full object-cover" />}
            </li>
          ))}
        </ul>
      )}
      {/* Fade the wall into the page so it reads as light, not a box. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-bg-base to-transparent" aria-hidden="true" />
    </section>
  );
}

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

// A poster, not a card: the frame is the object; status and text sit under it.
function ProjectCard({ p }: { p: ProjectSummary }) {
  const api = useApi();
  const b = badgeOf(p);
  const holdCount = p.needs_attention.length || undefined;
  const src = p.thumb ? api.mediaUrl(p.id, p.thumb, p.updated) : null;
  const tint = useImageTint(src);
  return (
    <li style={{ "--tint": tint } as CSSProperties}>
      <Link to={projectHref(p)} className="group block rounded-surface focus-visible:outline-offset-4">
        {/* The reel glows in its own colour; brighter and lifted on hover. */}
        <div className="overflow-hidden rounded-surface ring-1 ring-line-subtle transition-[box-shadow,transform] duration-panel ease-std [box-shadow:0_8px_40px_-12px_rgba(var(--tint),0.45)] group-hover:-translate-y-1 group-hover:ring-line-control group-hover:[box-shadow:0_16px_60px_-10px_rgba(var(--tint),0.7)]">
          <Thumb id={p.id} src={src} label={p.name}>
            {p.duration_s !== null && (
              <span className="absolute bottom-2 right-2 rounded-control bg-black/70 px-1.5 py-0.5 font-mono text-meta text-white">{duration(p.duration_s)}</span>
            )}
            {b === "editing" && (
              <div className="absolute inset-x-2 bottom-2">
                <ProgressBar value={p.progress} label={`${p.name} progress`} />
              </div>
            )}
          </Thumb>
        </div>
        <div className="space-y-0.5 pt-3">
          <StatusBadge badge={b} stage={p.stage} count={b === "hold" ? holdCount : undefined} />
          <h3 className="truncate text-ui text-fg-primary" title={p.name}>
            {p.name}
          </h3>
          <p className="truncate text-meta text-fg-secondary">
            {p.client ?? "No client"} · {p.delivered_at ? `delivered ${ago(p.delivered_at)}` : `updated ${ago(p.updated)}`}
          </p>
        </div>
      </Link>
    </li>
  );
}

/** "Needs you": hairline rows, each with its reason and one way in. Graphite buttons: the header owns the amber. */
function AttentionStrip({ list }: { list: ProjectSummary[] }) {
  const need = list.filter((p) => ["hold", "failed"].includes(badgeOf(p)));
  if (!need.length) return null;
  return (
    <section aria-label="Needs you" className="mb-10">
      <h2 className="flex items-baseline gap-3 text-section">
        Needs you <span className="font-mono text-mono text-fg-muted">{need.length}</span>
      </h2>
      <ul className="mt-3 divide-y divide-line-subtle border-y border-line-subtle">
        {need.map((p) => (
          <li key={p.id} className="flex items-center gap-6 py-3">
            <span className="w-24 shrink-0">
              <StatusBadge badge={badgeOf(p)} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-ui text-fg-primary">{p.name}</span>
              <span className="block truncate text-meta text-fg-secondary">{p.needs_attention.join(" · ") || (p.stage ? `Stopped at ${STAGE_LABEL[p.stage]}` : "")}</span>
            </span>
            <span className="hidden shrink-0 text-meta text-fg-muted md:block">{p.client ?? ""}</span>
            <Link to={projectHref(p)} className="inline-flex h-9 shrink-0 items-center rounded-control border border-line-strong bg-bg-overlay px-4 text-ui text-fg-primary hover:bg-bg-high">
              {badgeOf(p) === "failed" ? "See what failed" : "Review"}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** First run (11 · States → Home empty): one amber action, three steps that explain the product. */
function FirstRun({ onStart }: { onStart: () => void }) {
  return (
    <div className="mx-auto max-w-[480px] py-24">
      <Icon name="film" size={24} className="text-fg-muted" />
      <h2 className="mt-5 text-title">No edits yet</h2>
      <p className="mt-2 text-fg-secondary">Drop raw footage and a short brief. The Editor cuts a vertical reel, checks it, and tells you what needs you before it goes to the client.</p>
      <div className="mt-8">
        <Button variant="primary" icon="plus" onClick={onStart}>
          Start your first edit
        </Button>
      </div>
      <ol className="mt-10 space-y-4 border-t border-line-subtle pt-6">
        {[
          ["Drop clips", "Video files of up to 4 GB each, anywhere on this page"],
          ["Watch it edit", "Every decision with its reason and cost"],
          ["Review and deliver", "Confirm flagged words, then send"],
        ].map(([a, b], i) => (
          <li key={a} className="flex gap-5">
            <span className="font-mono text-mono text-fg-muted">{i + 1}</span>
            <span>
              <span className="block text-ui text-fg-primary">{a}</span>
              <span className="block text-meta text-fg-muted">{b}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function Home() {
  const api = useApi();
  const nav = useNavigate();
  const q =useQuery(() => api.projects(), [api], { intervalMs: 4000 });
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
      <div className="relative w-full px-8 py-8">
        <PageHeader
          title="Projects"
          subtitle="Reels that need you come first."
          actions={
            // On first run the empty state owns the one amber action.
            q.data && q.data.length === 0 ? undefined : (
              <Button variant="primary" icon="plus" onClick={() => nav("/new")}>
                New edit
              </Button>
            )
          }
        />
        {q.data && q.data.length > 0 && <Hero list={sorted} />}

        {q.error && !q.data ? <Notice tone="error" title="Couldn’t load projects">{friendlyError(q.error)}</Notice> : null}
        {q.loading && !q.data ? <Loading label="Loading projects…" /> : null}

        {q.data && q.data.length === 0 && <FirstRun onStart={() => nav("/new")} />}

        {q.data && q.data.length > 0 && (
          <>
            <AttentionStrip list={sorted} />
            <h2 className="mb-3 text-section">All projects</h2>
            <div className="mb-6 flex flex-wrap items-center gap-3">
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
              <span className="ml-auto text-meta text-fg-muted">Tip: drop video files anywhere here to start an edit.</span>
            </div>
            {shown.length === 0 ? (
              <p className="py-10 text-fg-secondary">No projects match these filters.</p>
            ) : (
              <ul className="grid grid-cols-[repeat(auto-fill,minmax(176px,1fr))] gap-x-6 gap-y-8" aria-label="Projects, needs-you first">
                {shown.map((p) => (
                  <ProjectCard key={p.id} p={p} />
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-bg-base/90">
          <div className="rounded-surface border-2 border-dashed border-signal px-16 py-12 text-center">
            <Icon name="upload" size={32} className="mx-auto mb-3 text-fg-primary" />
            <p className="text-title">Drop to start a new edit</p>
            <p className="mt-1 text-fg-secondary">mp4, mov, m4v, mkv or webm · up to 4 GB each</p>
          </div>
        </div>
      )}
    </div>
  );
}
