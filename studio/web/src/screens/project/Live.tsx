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

const NODE_STYLE: Record<string, string> = {
  done: "border-ai-glow/60 bg-ai/[0.14] text-fg-primary",
  running: "border-ai-glow bg-ai/[0.28] text-white shadow-[0_0_18px_rgba(157,133,255,0.45)]",
  failed: "border-st-fail bg-st-fail/[0.14] text-st-fail",
  skipped: "border-line-subtle bg-transparent text-fg-muted line-through decoration-fg-muted/50",
  pending: "border-line-subtle bg-bg-overlay text-fg-muted",
  queued: "border-line-subtle bg-bg-overlay text-fg-muted",
};

const STATUS_WORD: Record<string, string> = { done: "done", running: "running", failed: "failed", skipped: "skipped", pending: "waiting", queued: "queued" };

/** Flat pipeline: the reduced-motion equivalent of the 3D stage, and its keyboard-reachable list. */
export function FlatPipeline({ stages, selected, onSelect, large }: { stages: Stage[]; selected: string | null; onSelect: (n: string) => void; large?: boolean }) {
  return (
    <ol aria-label="Pipeline stages" className={cx("flex flex-wrap gap-x-5 gap-y-3", large && "py-2")}>
      {STAGE_GROUPS.map((g) => (
        <li key={g.name} className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-fg-muted">{g.name}</span>
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
                      "flex items-center gap-1.5 rounded-full border px-2.5 font-medium transition-colors duration-hover",
                      large ? "h-8 text-[13px]" : "h-7 text-[12px]",
                      NODE_STYLE[s.status] ?? NODE_STYLE.pending,
                      selected === name && "ring-2 ring-cyan ring-offset-2 ring-offset-bg-raised",
                    )}
                  >
                    {s.status === "done" && <Icon name="check" size={12} />}
                    {s.status === "failed" && <Icon name="alert" size={12} />}
                    {s.status === "running" && <span className="h-1.5 w-1.5 rounded-full bg-white pulse-dot" aria-hidden="true" />}
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
        <span className="text-label font-normal text-fg-muted">
          AI cost so far <Mono className="text-fg-primary">{usd(cost)}</Mono>
        </span>
      }
      bodyClass="max-h-[520px] overflow-y-auto"
    >
      {list.length === 0 ? (
        <p className="py-6 text-fg-secondary">Decisions appear here as soon as the Editor makes them — the hook, the kept lines, captions, look and punch-ins, each with its reason.</p>
      ) : (
        <ol className="space-y-3" aria-live="polite" aria-label="Decisions, newest first">
          {list.map((d) => (
            <li key={`${d.at}-${d.title}`} className="fade-in flex gap-3 rounded-card border border-line-subtle bg-bg-overlay/60 p-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-input bg-ai/[0.14] text-ai-glow">
                <Icon name={decisionIcon(d)} size={16} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <p className="font-medium text-fg-primary">{d.title}</p>
                  {typeof d.cost_usd === "number" && <Mono className="shrink-0 text-fg-muted">{usd(d.cost_usd)}</Mono>}
                </div>
                <p className="mt-1 text-fg-secondary">{d.detail}</p>
                {d.knowledge.length > 0 && (
                  <p className="mt-2 flex flex-wrap gap-1.5">
                    {d.knowledge.map((k) => (
                      <span key={k} className="rounded bg-bg-raised px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
                        {k}
                      </span>
                    ))}
                  </p>
                )}
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
    <div className="space-y-4">
      <section className="overflow-hidden rounded-panel border border-line-subtle bg-bg-inset" aria-label="Pipeline">
        {can3D ? (
          <div className="h-[340px]">
            <Suspense fallback={<div className="h-full" />}>
              <PipelineScene stages={p.stages} selected={sel?.name ?? null} onSelect={setSelected} busy={busy} />
            </Suspense>
          </div>
        ) : null}
        <div className={cx("border-line-subtle bg-bg-raised px-6", can3D ? "border-t py-3" : "py-6")}>
          <FlatPipeline stages={p.stages} selected={sel?.name ?? null} onSelect={setSelected} large={!can3D} />
        </div>
      </section>

      {p.status === "queued" && (
        <Notice tone="info" title="Queued — starts when a slot frees up">
          At most {health?.jobs.limit ?? 3} edits run at once so the Mac stays responsive. This one starts automatically.
        </Notice>
      )}

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 space-y-4 lg:col-span-5">
          {failed ? (
            <Panel title={<span className="text-st-fail">Stopped at {STAGE_LABEL[failed.name]}</span>}>
              <p className="text-fg-primary">{failed.error ?? "This stage failed."}</p>
              <p className="mt-2 text-label font-normal text-fg-muted">Earlier stages stay done. Retry runs again from {STAGE_LABEL[failed.name]}.</p>
              <div className="mt-4 flex gap-2">
                <Button variant="primary" icon="retry" busy={acting === "retry"} onClick={() => act("retry")}>
                  Retry from {STAGE_LABEL[failed.name]}
                </Button>
              </div>
            </Panel>
          ) : running ? (
            <Panel title="Now">
              <p className="text-title text-fg-primary">{STAGE_PLAIN[running.name] ?? running.name}</p>
              <dl className="mt-4 grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-label text-fg-muted">Elapsed in this stage</dt>
                  <dd className="mt-1 font-mono text-[15px] tabular text-fg-primary">{running.started ? elapsed(now - running.started) : "—"}</dd>
                </div>
                <div>
                  <dt className="text-label text-fg-muted">Estimated time left</dt>
                  <dd className="mt-1 font-mono text-[15px] tabular text-fg-primary">{left !== null ? `≈ ${elapsed(left)}` : "—"}</dd>
                </div>
              </dl>
              <div className="mt-4">
                <ProgressBar value={p.progress} label="Edit progress" />
              </div>
              <div className="mt-4 flex items-center justify-between">
                <span className="flex items-center gap-2 text-label font-normal text-fg-muted">
                  <span className={cx("h-1.5 w-1.5 rounded-full", connected ? "bg-st-sendable" : "bg-st-hold")} aria-hidden="true" />
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
              <Link to="../review" relative="path" className="mt-4 inline-flex h-10 items-center gap-2 rounded-input bg-ai px-4 font-medium text-white hover:brightness-110">
                <Icon name="phone" size={18} /> Review the reel
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
              <p className="mt-2 text-label font-normal text-fg-muted">
                Status: {STATUS_WORD[sel.status] ?? sel.status}
                {sel.started && sel.finished ? ` · took ${elapsed(sel.finished - sel.started)}` : ""}
              </p>
            </Panel>
          )}
          <details className="group rounded-panel border border-line-subtle bg-bg-raised">
            <summary className="flex cursor-pointer list-none items-center justify-between px-6 py-4 text-fg-secondary hover:text-fg-primary">
              <span className="font-medium">Technical log</span>
              <Icon name="chevronDown" size={16} className="transition-transform group-open:rotate-180" />
            </summary>
            <pre className="max-h-64 overflow-auto border-t border-line-subtle bg-bg-inset px-6 py-4 font-mono text-[12px] leading-5 text-fg-secondary">
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
