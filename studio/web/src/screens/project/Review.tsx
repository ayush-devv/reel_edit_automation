// FR-4 Review: 3D phone preview, verdict, proof list with inline fix (AC-6), Reviewer notes, quality
// checks, the owner's "Would you post this?" label, cover image.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { Project, ProofWord, ReviewIssue } from "../../api/types";
import { Icon } from "../../components/icons";
import { PhonePreview } from "../../components/Player";
import { Button, cx, Loading, Mono, Notice, Panel, TextInput } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";
import { gateLabel, tcToSeconds } from "../../lib/format";
import { isJobTerminal } from "../../lib/status";
import { useReelPlayer, type ReelPlayer } from "../../lib/reelPlayer";
import { useProject } from "./ProjectLayout";

function VerdictCard({ p }: { p: Project }) {
  const v = p.verdict_detail;
  const sendable = (v?.verdict ?? p.verdict) === "sendable";
  const fixable = p.proof.length > 0;
  return (
    <section
      aria-label="Verdict"
      className={cx("rounded-panel border p-6", sendable ? "border-st-sendable/40 bg-st-sendable/[0.06]" : "border-st-hold/40 bg-st-hold/[0.06]")}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className={cx("flex h-11 w-11 items-center justify-center rounded-card", sendable ? "bg-st-sendable/[0.16] text-st-sendable" : "bg-st-hold/[0.16] text-st-hold")}>
            <Icon name={sendable ? "check" : "alert"} size={24} />
          </div>
          <div>
            <p className={cx("text-[28px] font-bold leading-8 tracking-tight", sendable ? "text-st-sendable" : "text-st-hold")}>{sendable ? "Sendable" : "Hold"}</p>
            <p className="text-fg-secondary">{sendable ? "Safe to send to the client." : fixable ? "Fix the items below, then it re-checks." : "Needs you — see the reasons."}</p>
          </div>
        </div>
        {sendable && (
          <Link to="../deliver" relative="path" className="inline-flex h-10 items-center gap-2 rounded-input bg-ai px-4 font-medium text-white hover:brightness-110">
            <Icon name="download" size={18} /> Deliver
          </Link>
        )}
      </div>
      {v && v.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-label font-normal text-fg-secondary" aria-label="Warnings">
          {v.warnings.map((w) => (
            <li key={w}>Warning · {w}</li>
          ))}
        </ul>
      )}
      {v && v.reasons.length > 0 && (
        <ul className="mt-4 space-y-2 border-t border-line-subtle pt-4">
          {v.reasons.map((r) => (
            <li key={r} className="flex gap-2 text-fg-primary">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-st-hold" aria-hidden="true" />
              {r}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ProofItem({ w, onSeek, onSubmit, busy }: { w: ProofWord; onSeek: () => void; onSubmit: (text: string) => void; busy: boolean }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(w.suggestion ?? w.text);
  return (
    <li className="rounded-card border border-line-subtle bg-bg-overlay/60 p-3">
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={onSeek} className="group flex min-w-0 items-center gap-3 text-left" aria-label={`Jump to “${w.text}” at ${w.at}`}>
          <Mono className="rounded bg-bg-raised px-1.5 py-0.5 text-cyan group-hover:underline">{w.at.replace(/^00:/, "")}</Mono>
          <span className="truncate text-[15px] font-semibold text-fg-primary">“{w.text}”</span>
          {w.suggestion && (
            <span className="truncate text-fg-secondary">
              → <span className="text-ai-glow">{w.suggestion}</span>?
            </span>
          )}
        </button>
        {!editing && (
          <div className="flex shrink-0 gap-1">
            <Button icon="check" onClick={() => onSubmit(w.text)} disabled={busy} title="The word is right as it is">
              Correct
            </Button>
            <Button icon="edit" onClick={() => setEditing(true)} disabled={busy}>
              Change
            </Button>
          </div>
        )}
      </div>
      <p className="mt-1.5 text-label font-normal text-fg-muted">{w.why}</p>
      {editing && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) onSubmit(text.trim());
          }}
        >
          <TextInput aria-label={`Correct spelling for “${w.text}”`} value={text} onChange={(e) => setText(e.target.value)} autoFocus className="h-8" />
          <Button type="submit" variant="primary" busy={busy}>
            Fix
          </Button>
          <Button variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </form>
      )}
    </li>
  );
}

const SEV: Record<string, string> = { blocker: "bg-st-fail", major: "bg-st-hold", minor: "bg-fg-muted" };

function ReviewerNotes({ issues, summary, onSeek }: { issues: ReviewIssue[]; summary: string; onSeek: (t: number) => void }) {
  return (
    <Panel title="Reviewer notes">
      <p className="text-fg-secondary">{summary}</p>
      {issues.length > 0 && (
        <ul className="mt-4 space-y-2">
          {issues.map((i, k) => (
            <li key={k} className="flex overflow-hidden rounded-card border border-line-subtle bg-bg-overlay/60">
              <span className={cx("w-1 shrink-0", SEV[i.severity ?? "minor"])} aria-hidden="true" />
              <div className="min-w-0 flex-1 p-3">
                <div className="flex flex-wrap items-center gap-2 text-label">
                  <span className={cx("uppercase tracking-[0.06em]", i.severity === "blocker" ? "text-st-fail" : i.severity === "major" ? "text-st-hold" : "text-fg-secondary")}>{i.severity ?? "note"}</span>
                  <span className="text-fg-muted">·</span>
                  <span className="text-fg-secondary">{i.category}</span>
                  {i.at ? (
                    <button type="button" onClick={() => onSeek(tcToSeconds(i.at))} className="ml-auto max-w-[50%] truncate font-mono text-mono text-cyan hover:underline" title={i.at} aria-label={`Jump to ${i.at}`}>
                      {i.at.replace(/^00:/, "")}
                    </button>
                  ) : (
                    <span className="ml-auto text-fg-muted">whole reel</span>
                  )}
                </div>
                <p className="mt-1 text-fg-primary">{i.text}</p>
                {i.fix && <p className="mt-1 text-fg-secondary">Suggested fix: {i.fix}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Gates({ p }: { p: Project }) {
  const gates = p.verdict_detail?.gates ?? [];
  const fails = gates.filter((g) => g.status === "fail").length;
  const warns = gates.filter((g) => g.status === "warn").length;
  return (
    <details className="group rounded-panel border border-line-subtle bg-bg-raised" open={fails > 0}>
      <summary className="flex cursor-pointer list-none items-center justify-between px-6 py-4">
        <span className="text-title">Quality checks</span>
        <span className="flex items-center gap-3 text-label">
          <span className="text-st-sendable">{gates.length - fails - warns} pass</span>
          {warns > 0 && <span className="text-st-hold">{warns} warn</span>}
          {fails > 0 && <span className="text-st-fail">{fails} fail</span>}
          <Icon name="chevronDown" size={16} className="text-fg-muted transition-transform group-open:rotate-180" />
        </span>
      </summary>
      <ul className="border-t border-line-subtle px-6 py-3">
        {gates.map((g) => (
          <li key={g.name} className="flex items-start gap-3 py-2">
            <span
              className={cx(
                "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                g.status === "pass" ? "bg-st-sendable/[0.16] text-st-sendable" : g.status === "warn" ? "bg-st-hold/[0.16] text-st-hold" : "bg-st-fail/[0.16] text-st-fail",
              )}
              aria-label={g.status}
            >
              <Icon name={g.status === "pass" ? "check" : g.status === "warn" ? "alert" : "x"} size={12} />
            </span>
            <div className="min-w-0">
              <p className="text-fg-primary">{gateLabel(g.name)}</p>
              <p className="font-mono text-mono text-fg-muted">{g.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}

function LabelControl({ p }: { p: Project }) {
  const api = useApi();
  const [answer, setAnswer] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function save(v: boolean) {
    setAnswer(v);
    setErr(null);
    try {
      await api.label(p.id, v, reason);
      setSaved(true);
    } catch (e) {
      setErr(friendlyError(e));
    }
  }
  return (
    <Panel title="Would you post this?">
      <p className="mb-3 text-fg-secondary">Your answer trains the Reviewer’s calibration (Quality lab).</p>
      <TextInput aria-label="Why (optional)" placeholder="Why? (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="mt-3 flex items-center gap-2">
        <Button variant={answer === true ? "primary" : "secondary"} icon="check" onClick={() => save(true)} aria-pressed={answer === true}>
          Yes
        </Button>
        <Button variant={answer === false ? "primary" : "secondary"} icon="x" onClick={() => save(false)} aria-pressed={answer === false}>
          No
        </Button>
        {saved && <span className="text-label text-st-sendable">Saved</span>}
        {err && <span className="text-label text-st-fail">{err}</span>}
      </div>
    </Panel>
  );
}

function useReviewPlayer(p: Project): ReelPlayer | null {
  const api = useApi();
  const src = p.media.final ? api.mediaUrl(p.id, p.media.final, p.versions.at(-1)?.n ?? p.updated) : null;
  const tl = useQuery(() => (src ? Promise.resolve(null) : api.timeline(p.id).then((t) => t.timeline)), [api, p.id, src]);
  const timeline = useMemo(() => tl.data ?? null, [tl.data]);
  const player = useReelPlayer(src || null, timeline);
  return src || !tl.loading ? player : null;
}

export default function Review() {
  const { project: p, jobs } = useProject();
  const api = useApi();
  const player = useReviewPlayer(p);
  const [proofErr, setProofErr] = useState<string | null>(null);
  // The fix job: busy until its SSE `job` event turns terminal, or a snapshot no longer lists the word.
  const [proofJob, setProofJob] = useState<{ id: string; word: number } | null>(null);
  const jobState = proofJob ? jobs[proofJob.id]?.status : undefined;
  const wordGone = !!proofJob && !p.proof.some((w) => w.i === proofJob.word);
  const proofBusy = !!proofJob && !isJobTerminal(jobState) && !wordGone;
  useEffect(() => {
    if (proofJob && jobState && isJobTerminal(jobState) && jobState !== "done" && !wordGone) setProofErr("The caption fix didn’t finish. Nothing changed — try again.");
  }, [proofJob, jobState, wordGone]);

  if (p.status !== "sendable" && p.status !== "hold") {
    return (
      <Notice tone="info" title="Nothing to review yet">
        The edit is {p.status === "failed" ? "stopped" : "still running"}. <Link to="../live" relative="path" className="text-ai-glow underline">Watch it live</Link>
      </Notice>
    );
  }

  const seek = (t: number) => {
    player?.seek(t);
    player?.pause();
  };

  async function fix(w: ProofWord, text: string) {
    setProofErr(null);
    try {
      const r = await api.proof(p.id, [{ i: w.i, text }]);
      setProofJob({ id: r.job.id, word: w.i });
    } catch (e) {
      setProofErr(friendlyError(e));
    }
  }

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12 lg:col-span-5">{player ? <PhonePreview player={player} client={p.client ?? "client"} /> : <Loading label="Loading the reel…" />}</div>
      <div className="col-span-12 space-y-4 lg:col-span-7">
        <VerdictCard p={p} />
        {(p.proof.length > 0 || proofBusy) && (
          <Panel title="Proof words" actions={<span className="text-label font-normal text-fg-muted">Click a word to jump to it</span>}>
            {proofBusy && (
              <div className="mb-3">
                <Notice tone="info" title="Re-rendering captions…">
                  Only the caption layer re-renders. The verdict updates when it’s done.
                </Notice>
              </div>
            )}
            {proofErr && (
              <div className="mb-3">
                <Notice tone="error">{proofErr}</Notice>
              </div>
            )}
            <ul className="space-y-2">
              {p.proof.map((w) => (
                <ProofItem key={w.i} w={w} busy={proofBusy} onSeek={() => seek(tcToSeconds(w.at))} onSubmit={(t) => fix(w, t)} />
              ))}
            </ul>
          </Panel>
        )}
        {p.review && <ReviewerNotes issues={p.review.issues} summary={p.review.summary} onSeek={seek} />}
        <Gates p={p} />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <LabelControl p={p} />
          <Panel title="Cover image">
            {p.media.cover ? (
              <img src={api.mediaUrl(p.id, p.media.cover, p.versions.at(-1)?.n ?? p.updated)} alt="Cover image for the reel" className="mx-auto max-h-56 rounded-card" />
            ) : (
              <p className="text-fg-secondary">The cover is picked from the strongest frame at the end of the edit. None yet for this version.</p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
