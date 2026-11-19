// FR-11 Quality lab: gold set (held-out pairs locked, AC-15), score history, calibration, self-improvement.
import { useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { EvalRun, GoldPair, ImproveEntry, Lab } from "../../api/types";
import { Icon } from "../../components/icons";
import { PageHeader } from "../../components/Shell";
import { Table } from "../../components/Table";
import { Button, cx, Field, Loading, Mono, Notice, Panel, TextInput } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";
import { color } from "../../theme/tokens";

const pct = (x: number | null | undefined) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "—");
const gateName = (id: string) => (id ? id[0].toUpperCase() + id.slice(1).replace(/_/g, " ") : id);

const OUTCOME: Record<ImproveEntry["outcome"], { icon: "check" | "x" | "clock"; tone: string; text: (h: ImproveEntry) => string }> = {
  accepted: { icon: "check", tone: "bg-st-sendable/[0.16] text-st-sendable", text: (h) => `Accepted · +${((h.gain ?? 0) * 100).toFixed(1)} points` },
  rejected: { icon: "x", tone: "bg-st-fail/[0.16] text-st-fail", text: (h) => `Rejected${h.reason ? ` · ${h.reason}` : ""}` },
  invalid: { icon: "x", tone: "bg-st-fail/[0.16] text-st-fail", text: (h) => `Proposal refused by the checks${h.reason ? ` · ${h.reason}` : ""}` },
  dry_run: { icon: "clock", tone: "bg-bg-raised text-fg-muted", text: () => "Dry run — proposed only, nothing evaluated" },
};

function ScoreChart({ runs, selected, onSelect }: { runs: EvalRun[]; selected: string | null; onSelect: (id: string) => void }) {
  const W = 640;
  const H = 220;
  const P = { l: 44, r: 16, t: 16, b: 32 };
  runs = runs.filter((r) => r.at && Number.isFinite(Date.parse(r.at)));
  if (!runs.length) return <p className="py-8 text-fg-secondary">No evaluation runs yet. “Evaluate tuning set” scores the editor against the gold set.</p>;
  const xs = runs.map((r) => Date.parse(r.at!));
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs) || x0 + 1;
  const lo = 0.4;
  const hi = 1;
  const X = (t: number) => P.l + ((t - x0) / Math.max(1, x1 - x0)) * (W - P.l - P.r);
  const Y = (v: number) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
  const tuning = runs.filter((r) => r.split === "tuning");
  const path = tuning.map((r, i) => `${i ? "L" : "M"}${X(Date.parse(r.at!)).toFixed(1)},${Y(r.primary).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Average primary score per run: ${runs.map((r) => `${r.id} ${pct(r.primary)}`).join(", ")}`}>
      {[0.4, 0.6, 0.8, 1].map((v) => (
        <g key={v}>
          <line x1={P.l} x2={W - P.r} y1={Y(v)} y2={Y(v)} stroke={color.line.subtle} />
          <text x={P.l - 8} y={Y(v) + 4} textAnchor="end" fontSize="11" fill={color.text.muted} fontFamily="JetBrains Mono">
            {pct(v)}
          </text>
        </g>
      ))}
      <path d={path} fill="none" stroke={color.accent.glow} strokeWidth="2" />
      {runs.map((r) => {
        const cx_ = X(Date.parse(r.at!));
        const cy = Y(r.primary);
        const hold = r.split === "holdout";
        return (
          <g key={r.id} className="cursor-pointer" onClick={() => onSelect(r.id)} tabIndex={0} role="button" aria-label={`Run ${r.id}, ${r.split}, ${pct(r.primary)}`} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(r.id)}>
            <circle cx={cx_} cy={cy} r={selected === r.id ? 7 : 5} fill={hold ? color.accent.cyan : color.accent.glow} stroke={color.bg.raised} strokeWidth="2" />
            <text x={cx_} y={H - 10} textAnchor="middle" fontSize="11" fill={color.text.muted}>
              {new Date(r.at!).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Families({ run }: { run: EvalRun }) {
  return (
    <ul className="space-y-2.5">
      {Object.entries(run.families).map(([k, v]) => (
        <li key={k} className="grid grid-cols-[90px_1fr_44px] items-center gap-3">
          <span className="capitalize text-fg-secondary">{k}</span>
          <span className="h-2 overflow-hidden rounded-full bg-bg-overlay">
            <span className="block h-full rounded-full bg-ai-glow" style={{ width: pct(v) }} />
          </span>
          <Mono className="text-right text-fg-primary">{pct(v)}</Mono>
        </li>
      ))}
    </ul>
  );
}

function Actions({ lab, onStarted }: { lab: Lab; onStarted: () => void }) {
  const api = useApi();
  const [budget, setBudget] = useState("30");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const run = async (key: string, action: "eval" | "calibrate" | "improve", body?: Record<string, unknown>) => {
    setBusy(key);
    setMsg(null);
    try {
      await api.labAction(action, body);
      setMsg({ tone: "ok", text: "Started — it runs in the background and shows up in Jobs." });
      onStarted();
    } catch (e) {
      setMsg({ tone: "error", text: friendlyError(e) });
    } finally {
      setBusy(null);
    }
  };
  return (
    <Panel title="Run">
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon="play" busy={busy === "eval"} onClick={() => run("eval", "eval")}>
            Evaluate tuning set
          </Button>
          <Button icon="retry" busy={busy === "cal"} onClick={() => run("cal", "calibrate")}>
            Recalibrate
          </Button>
        </div>
        <div className="rounded-card border border-line-subtle bg-bg-overlay/50 p-4">
          <p className="font-medium text-fg-primary">Self-improvement</p>
          <p className="mt-1 text-fg-secondary">Proposes knowledge changes overnight and keeps only the ones that score better on the tuning set. The budget is the number of reel edits it may run (each costs AI time).</p>
          <div className="mt-3 flex items-end gap-2">
            <Field label="Budget (reel runs)" htmlFor="budget">
              <TextInput id="budget" value={budget} onChange={(e) => setBudget(e.target.value)} inputMode="numeric" className="w-28 font-mono text-[13px]" />
            </Field>
            <Button icon="sparkle" busy={busy === "imp"} disabled={!(Number.isInteger(Number(budget)) && Number(budget) > 0)} onClick={() => run("imp", "improve", { budget: Number(budget) })}>
              Run improvement
            </Button>
          </div>
        </div>
        <div className={cx("rounded-card border p-4", lab.release_locked ? "border-line-strong bg-bg-inset" : "border-line-subtle")}>
          <p className="flex items-center gap-2 font-medium text-fg-primary">
            {lab.release_locked && <Icon name="lock" size={16} className="text-st-hold" />} Release check
          </p>
          <p className="mt-1 text-fg-secondary">Scores the held-out set once against the pass mark: 5 of 6 sendable, no wrongly sendable reel.</p>
          {lab.release_locked && <p className="mt-2 text-label font-normal text-st-hold">Locked: {lab.lock_reason ?? "not allowed right now."}</p>}
          <Button className="mt-3" icon="lock" disabled={lab.release_locked} busy={busy === "rel"} onClick={() => run("rel", "eval", { release: true })}>
            Run release check
          </Button>
        </div>
        {msg && <Notice tone={msg.tone === "ok" ? "ok" : "error"}>{msg.text}</Notice>}
      </div>
    </Panel>
  );
}

export default function Quality() {
  const api = useApi();
  const q = useQuery(() => api.lab(), [api]);
  const [sel, setSel] = useState<string | null>(null);
  const lab = q.data;
  const runs = lab?.runs ?? [];
  const run = runs.find((r) => r.id === sel) ?? runs.at(-1);
  const cal = lab?.calibration;

  return (
    <div className="mx-auto w-full max-w-[1440px] px-8 py-8">
      <PageHeader eyebrow="Studio" title="Quality lab" subtitle="How good the editor is getting — and when it’s safe to send without checking every reel." />
      {q.error ? <Notice tone="error">{friendlyError(q.error)}</Notice> : null}
      {!lab ? (
        <Loading />
      ) : (
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-12 space-y-4 xl:col-span-8">
            <Panel title="Scores" actions={<span className="flex items-center gap-4 text-label font-normal text-fg-muted"><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-ai-glow" />Tuning</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-cyan" />Release (held-out)</span></span>}>
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_260px]">
                <ScoreChart runs={runs} selected={run?.id ?? null} onSelect={setSel} />
                {run && (
                  <div>
                    <p className="text-label text-fg-muted">
                      Run <Mono className="text-fg-secondary">{run.id}</Mono> · {run.split}
                    </p>
                    <p className="mb-4 mt-1 text-[28px] font-bold leading-8 tabular">{pct(run.primary)}</p>
                    <Families run={run} />
                  </div>
                )}
              </div>
            </Panel>
            <Panel title="Gold set" actions={<span className="text-label font-normal text-fg-muted">{lab.gold.pairs} pairs · {lab.gold.tuning} tuning · {lab.gold.holdout} held out · {lab.gold.hinglish} Hinglish</span>}>
              <Table<GoldPair>
                caption="Gold set reference pairs"
                rows={lab.gold_pairs}
                rowKey={(r) => r.id}
                empty="No gold pairs yet (eval/manifest.yaml)."
                columns={[
                  { key: "id", label: "Pair", render: (r) => <Mono className="text-fg-primary">{r.id}</Mono> },
                  {
                    key: "s",
                    label: "Split",
                    render: (r) =>
                      r.split === "holdout" ? (
                        <span className="inline-flex items-center gap-1.5 text-st-hold" title="Held-out pairs are scored only by Release check">
                          <Icon name="lock" size={14} /> Held out · locked
                        </span>
                      ) : (
                        <span className="text-fg-secondary">Tuning</span>
                      ),
                  },
                  { key: "l", label: "Language", render: (r) => <span className="text-fg-secondary">{r.language}</span> },
                  { key: "src", label: "Source", render: (r) => <span className="text-fg-secondary">{r.source || "—"}</span> },
                ]}
              />
            </Panel>
            <Panel title="Self-improvement history">
              {lab.improve_history.length === 0 && <p className="text-fg-secondary">No self-improvement runs yet.</p>}
              <ul className="space-y-2">
                {lab.improve_history.map((h, i) => {
                  const o = OUTCOME[h.outcome] ?? OUTCOME.rejected;
                  return (
                    <li key={i} className="flex gap-3 rounded-card border border-line-subtle bg-bg-overlay/50 p-3">
                      <span className={cx("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full", o.tone)}>
                        <Icon name={o.icon} size={12} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-[13px] text-fg-primary">{h.change || "(no change proposed)"}</p>
                        <p className="mt-0.5 text-fg-secondary">{o.text(h)}</p>
                      </div>
                      <span className="shrink-0 text-label font-normal text-fg-muted">{h.at ? new Date(h.at).toLocaleDateString() : h.round !== null ? `round ${h.round + 1}` : ""}</span>
                    </li>
                  );
                })}
              </ul>
            </Panel>
          </div>
          <div className="col-span-12 space-y-4 xl:col-span-4">
            <Panel title="Calibration">
              {cal ? (
                <>
                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-label text-fg-muted">Reviewer agrees with you</p>
                      <p className="text-[28px] font-bold leading-8 tabular">{pct(cal.agreement)}</p>
                      <p className="text-label font-normal text-fg-muted">{cal.n_labels ? `over ${cal.n_labels} labels` : "no labels yet"}</p>
                    </div>
                    <span className={cx("rounded-full px-3 py-1 text-label", cal.trusted ? "bg-st-sendable/[0.14] text-st-sendable" : "bg-bg-overlay text-fg-secondary")}>{cal.trusted ? "Trusted" : "Not trusted yet"}</span>
                  </div>
                  {!cal.trusted && <p className="mt-2 text-label font-normal text-fg-muted">Keep answering “Would you post this?” on reviews. Trust turns on when agreement is high enough.</p>}
                  <h3 className="mb-2 mt-5 text-label text-fg-muted">False alarms per check</h3>
                  {cal.rule && <p className="mb-2 text-label font-normal text-fg-muted">Promotion rule: {cal.rule}</p>}
                  <ul className="space-y-2">
                    {cal.gates.map((g) => (
                      <li key={g.name} className="flex items-center gap-3" title={g.catch_rate !== null ? `Catches ${pct(g.catch_rate)} of its injected defects${g.promote_to_block ? " · ready to block" : ""}` : undefined}>
                        <span className="min-w-0 flex-1 truncate text-fg-primary">{gateName(g.name)}</span>
                        <Mono className={cx((g.false_alarm_rate ?? 0) > 0.2 ? "text-st-hold" : "text-fg-secondary")}>{pct(g.false_alarm_rate)}</Mono>
                        <span className={cx("w-14 rounded px-1.5 py-0.5 text-center text-label", g.mode === "block" ? "bg-st-fail/[0.14] text-st-fail" : "bg-st-hold/[0.12] text-st-hold")}>{g.mode}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-fg-secondary">No labels yet. Answer “Would you post this?” on a few reviews to start calibration.</p>
              )}
            </Panel>
            <Actions lab={lab} onStarted={q.reload} />
          </div>
        </div>
      )}
    </div>
  );
}
