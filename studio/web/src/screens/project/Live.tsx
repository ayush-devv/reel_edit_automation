// FR-3 Watch the edit live: 3D pipeline stage (flat under reduced motion), running-stage detail with time
// left, the Editor's decisions as they stream in, cancel, and retry from a failed stage (AC-5).
import { lazy, Suspense, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { Decision, Stage } from "../../api/types";
import { Icon, type IconName } from "../../components/icons";
import { Button, cx, Mono, Notice, Panel, ProgressBar } from "../../components/ui";
import { useStatus } from "../../hooks/status";
import { use3D } from "../../hooks/useMedia";
import { elapsed, usd } from "../../lib/format";
import { estimateLeft, STAGE_GROUPS, STAGE_LABEL, STAGE_PLAIN } from "../../lib/status";
import { useProject } from "./ProjectLayout";

const PipelineScene = lazy(() => import("../../three/PipelineScene"));

function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

// Done is graphite, running is violet (the AI is working), failed is red, waiting is a hairline. No glow.
const NODE_STYLE: Record<string, string> = {
  done: "border-line-strong bg-bg-overlay text-fg-secondary",
  running: "border-ai bg-ai/[0.12] text-fg-primary",
  failed: "border-st-fail bg-transparent text-st-fail",
  skipped: "border-line-subtle bg-transparent text-fg-muted line-through decoration-fg-muted/50",
  pending: "border-line-subtle bg-transparent text-fg-muted",
  queued: "border-line-subtle bg-transparent text-fg-muted",
};

const STATUS_WORD: Record<string, string> = { done: "done", running: "running", failed: "failed", skipped: "skipped", pending: "waiting", queued: "queued" };

/** Flat pipeline: the reduced-motion equivalent of the 3D stage, and its keyboard-reachable list. */
export function FlatPipeline({ stages, selected, onSelect, large }: { stages: Stage[]; selected: string | null; onSelect: (n: string) => void; large?: boolean }) {
  return (
    <ol aria-label="Pipeline stages" className={cx("flex flex-wrap gap-x-4 gap-y-3", large && "py-2")}>
      {STAGE_GROUPS.map((g) => (
        <li key={g.name} className="flex flex-col gap-1.5">
          <span className="text-meta text-fg-muted">{g.name}</span>
          <ol className="flex gap-1.5">
            {g.stages.map((name) => {
              const s = stages.find((x) => x.name === name);
              if (!s) return null;
              return (
                <li key={name}>
                  <button
                    type="button"
                    onClick={() => onSelect(name)}
                    aria-pressed={selected === name}
                    aria-label={`${STAGE_LABEL[name]}: ${STATUS_WORD[s.status] ?? s.status}`}
                    className={cx(
                      "flex items-center gap-1.5 rounded-control border px-2.5 transition-colors duration-hover",
                      large ? "h-8 text-ui" : "h-7 text-label",
                      NODE_STYLE[s.status] ?? NODE_STYLE.pending,
                      selected === name && "ring-2 ring-signal ring-offset-2 ring-offset-bg-base",
                    )}
                  >
                    {s.status === "done" && <Icon name="check" size={12} />}
                    {s.status === "failed" && <Icon name="alert" size={12} />}
                    {s.status === "running" && <span className="h-1.5 w-1.5 rounded-full bg-ai pulse-dot" aria-hidden="true" />}
                    {STAGE_LABEL[name]}
                  </button>
                </li>
              );
            })}
          </ol>
        </li>
      ))}
    </ol>
  );
}

function decisionIcon(d: Decision): IconName {
  const t = d.title.toLowerCase();
  if (t.startsWith("hook")) return "sparkle";
  if (t.includes("kept") || t.includes("line")) return "film";
  if (t.startsWith("caption")) return "edit";
  if (t.startsWith("look")) return "brand";
  if (t.includes("punch") || t.includes("music") || t.includes("sfx")) return "volume";
  if (d.kind === "qa") return "check";
  if (d.kind === "review") return "eye";
  if (d.kind === "revision") return "chat";
  return "info";
}

function DecisionFeed({ decisions, cost }: { decisions: Decision[]; cost: number }) {
  const list = [...decisions].sort((a, b) => b.at - a.at);
  return (
    <Panel
      title="The Editor’s decisions"
      actions={
        <span className="text-meta text-fg-muted">
          AI cost so far <Mono className="text-fg-secondary">{usd(cost)}</Mono>
        </span>
      }
      bodyClass="max-h-[560px] overflow-y-auto"
    >
      {list.length === 0 ? (
        <p className="py-6 text-fg-secondary">Decisions appear here as soon as the Editor makes them — the hook, the kept lines, captions, look and punch-ins, each with its reason.</p>
      ) : (
        <ol className="divide-y divide-line-subtle" aria-live="polite" aria-label="Decisions, newest first">
          {list.map((d) => (
            // Each decision is the Editor's (AI) output: a 2 px violet rule, then what and why.
            <li key={`${d.at}-${d.title}`} className="fade-in flex gap-4 py-4">
              <span className="w-0.5 shrink-0 rounded-full bg-ai" aria-hidden="true" />
              <Icon name={decisionIcon(d)} size={16} className="mt-0.5 shrink-0 text-fg-muted" />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-ui text-fg-primary">{d.title}</p>
                  <span className="shrink-0 text-meta text-fg-muted">
                    {d.kind}
                    {typeof d.cost_usd === "number" && <> · <Mono className="text-meta">{usd(d.cost_usd)}</Mono></>}
                  </span>
                </div>
                <p className="mt-1 text-meta text-fg-secondary">{d.detail}</p>
                {d.knowledge.length > 0 && <p className="mt-2 font-mono text-meta text-fg-muted">{d.knowledge.join(" · ")}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

export default function Live() {
  const { project: p, logs, connected } = useProject();
  const api = useApi();
  const { busy, health } = useStatus();
  const can3D = use3D();
  const now = useNow();
  const [selected, setSelected] = useState<string | null>(null);
  const [acting, setActing] = useState<"retry" | "cancel" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const running = p.stages.find((s) => s.status === "running");
  const failed = p.stages.find((s) => s.status === "failed");
  const sel = p.stages.find((s) => s.name === (selected ?? running?.name ?? failed?.name)) ?? null;
  const left = estimateLeft(p.stages, now, (p as { eta_s?: number | null }).eta_s);
  const finished = p.status === "sendable" || p.status === "hold";

  async function act(kind: "retry" | "cancel") {
    setActing(kind);
    setErr(null);
    try {
      if (kind === "retry") await api.retry(p.id, failed?.name);
      else if (window.confirm("Stop this edit? You can resume it from the last finished stage.")) await api.cancel(p.id);
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setActing(null);
    }
  }

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-surface bg-bg-inset" aria-label="Pipeline">
        {can3D ? (
          <div className="h-[340px]">
            <Suspense fallback={<div className="h-full" />}>
              <PipelineScene stages={p.stages} selected={sel?.name ?? null} onSelect={setSelected} busy={busy} />
            </Suspense>
          </div>
        ) : null}
        <div className={cx("border-line-subtle px-6", can3D ? "border-t py-4" : "py-6")}>
          <FlatPipeline stages={p.stages} selected={sel?.name ?? null} onSelect={setSelected} large={!can3D} />
        </div>
      </section>

      {p.status === "queued" && (
        <Notice tone="info" title="Queued — starts when a slot frees up">
          At most {health?.jobs.limit ?? 3} edits run at once so the Mac stays responsive. This one starts automatically.
        </Notice>
      )}

      <div className="grid grid-cols-12 gap-x-10 gap-y-6">
        <div className="col-span-12 lg:col-span-5">
          {failed ? (
            <Panel title={<span className="text-st-fail">Stopped at {STAGE_LABEL[failed.name]}</span>}>
              <pre className="whitespace-pre-wrap rounded-control bg-bg-inset px-4 py-3 font-mono text-mono text-fg-secondary">{failed.error ?? "This stage failed."}</pre>
              <p className="mt-3 text-meta text-fg-muted">Earlier stages stay done, so nothing is lost. Retry runs again from {STAGE_LABEL[failed.name]}.</p>
              <div className="mt-4 flex gap-2">
                <Button variant="primary" icon="retry" busy={acting === "retry"} onClick={() => act("retry")}>
                  Retry from {STAGE_LABEL[failed.name]}
                </Button>
              </div>
            </Panel>
          ) : running ? (
            <Panel title="Now">
              <p className="text-title text-fg-primary">{STAGE_PLAIN[running.name] ?? running.name}</p>
              <dl className="mt-4 grid grid-cols-3 gap-4">
                <div>
                  <dt className="text-meta text-fg-muted">Progress</dt>
                  <dd className="mt-1 font-mono text-timecode-lg tabular text-fg-primary">{Math.round(p.progress * 100)}%</dd>
                </div>
                <div>
                  <dt className="text-meta text-fg-muted">In this stage</dt>
                  <dd className="mt-1 font-mono text-timecode-lg tabular text-fg-primary">{running.started ? elapsed(now - running.started) : "—"}</dd>
                </div>
                <div>
                  <dt className="text-meta text-fg-muted">Time left</dt>
                  <dd className="mt-1 font-mono text-timecode-lg tabular text-fg-primary">{left !== null ? `≈ ${elapsed(left)}` : "—"}</dd>
                </div>
              </dl>
              <div className="mt-4">
                <ProgressBar value={p.progress} label="Edit progress" />
              </div>
              <div className="mt-4 flex items-center justify-between">
                <span className="flex items-center gap-2 text-meta text-fg-muted">
                  <span className={cx("h-2 w-2 rounded-full", connected ? "bg-st-sendable" : "bg-st-hold")} aria-hidden="true" />
                  {connected ? "Live" : "Reconnecting…"} · closing this tab doesn’t stop the edit
                </span>
                <Button variant="danger" icon="stop" busy={acting === "cancel"} onClick={() => act("cancel")}>
                  Cancel edit
                </Button>
              </div>
            </Panel>
          ) : finished ? (
            <Panel title="Edit finished">
              <p className="text-fg-secondary">The reel is rendered and checked. The verdict is ready.</p>
              <Link to="../review" relative="path" className="mt-4 inline-flex h-9 items-center gap-2 rounded-control bg-signal px-4 text-ui text-signal-on hover:bg-signal-hover">
                <Icon name="phone" size={16} /> Review the reel
              </Link>
            </Panel>
          ) : (
            <Panel title="Waiting">
              <p className="text-fg-secondary">The edit hasn’t started yet.</p>
            </Panel>
          )}
          {err && <Notice tone="error">{err}</Notice>}
          {sel && sel.name !== running?.name && sel.name !== failed?.name && (
            <Panel title={STAGE_LABEL[sel.name]}>
              <p className="text-fg-secondary">{STAGE_PLAIN[sel.name]}</p>
              <p className="mt-2 text-meta text-fg-muted">
                Status: {STATUS_WORD[sel.status] ?? sel.status}
                {sel.started && sel.finished ? ` · took ${elapsed(sel.finished - sel.started)}` : ""}
              </p>
            </Panel>
          )}
          <details className="group border-t border-line-subtle">
            <summary className="flex cursor-pointer list-none items-center justify-between py-5 text-fg-secondary hover:text-fg-primary">
              <span className="text-section">Technical log</span>
              <Icon name="chevronDown" size={16} className="transition-transform group-open:rotate-180" />
            </summary>
            <pre className="mb-6 max-h-64 overflow-auto rounded-control bg-bg-inset px-4 py-3 font-mono text-meta leading-5 text-fg-secondary">
              {logs.length ? logs.join("\n") : "No log lines yet."}
            </pre>
          </details>
        </div>
        <div className="col-span-12 lg:col-span-7">
          <DecisionFeed decisions={p.decisions} cost={p.cost_usd} />
        </div>
      </div>
    </div>
  );
}
