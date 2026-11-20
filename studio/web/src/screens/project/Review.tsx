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
import { NotYet, useProject } from "./ProjectLayout";

function VerdictCard({ p, onSeek }: { p: Project; onSeek: (t: number) => void }) {
  const v = p.verdict_detail;
  const plain = v?.plain ?? [];
  const sendable = (v?.verdict ?? p.verdict) === "sendable";
  const fixable = p.proof.length > 0;
  return (
    // The verdict is the hero: big status word + one sentence + (when sendable) the one amber action. No card.
    <section aria-label="Verdict" className="pb-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className={cx("text-display [text-shadow:0_0_28px_currentColor]", sendable ? "text-st-sendable" : "text-st-hold")}>{sendable ? "Sendable" : "Hold"}</p>
          <p className="mt-1 text-body text-fg-secondary">{sendable ? "Safe to send to the client." : fixable ? "Fix the items below, then it re-checks." : "Needs you — see the reasons."}</p>
        </div>
        {sendable && (
          <Link to="../deliver" relative="path" className="inline-flex h-9 items-center gap-2 rounded-control bg-signal px-4 text-ui text-signal-on hover:bg-signal-hover">
            <Icon name="download" size={16} /> Deliver
          </Link>
        )}
      </div>
      {plain.length > 0 && (
        <ul className="mt-4 space-y-3" aria-label="What the checks found">
          {plain.map((c) => (
            <li key={c.gate} className="flex gap-3">
              <span className={cx("mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full", c.status === "fail" ? "bg-st-hold" : "bg-fg-muted")} aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-fg-primary">
                  <span className="font-medium">{c.title}.</span> {c.sentence}
                  {c.status === "warn" && <span className="ml-2 text-meta text-fg-muted">(warning)</span>}
                </p>
                {c.at.length > 0 && (
                  <p className="mt-1 flex flex-wrap gap-x-3 font-mono text-mono">
                    {c.at.map((t) => (
                      <button key={t} type="button" className="text-info hover:underline" onClick={() => onSeek(tcToSeconds(t))} aria-label={`Jump to ${t}`}>
                        {t}
                      </button>
                    ))}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {v && v.reasons.some((r) => r.startsWith("reviewer")) && (
        <ul className="mt-4 space-y-2" aria-label="Reviewer">
          {v.reasons
            .filter((r) => r.startsWith("reviewer"))
            .map((r) => (
              <li key={r} className="flex gap-3 text-fg-primary">
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-st-hold" aria-hidden="true" />
                {r.replace(/^reviewer[^:]*:\s*/, "The Reviewer: ")}
              </li>
            ))}
        </ul>
      )}
      {v && (v.reasons.length > 0 || v.warnings.length > 0) && (
        <details className="mt-4 text-meta text-fg-muted">
          <summary className="cursor-pointer select-none">Details (the engine’s wording)</summary>
          <ul className="mt-2 space-y-1">
            {[...v.reasons, ...v.warnings.map((w) => `Warning · ${w}`)].map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function ProofItem({ w, onSeek, onSubmit, busy, first }: { w: ProofWord; onSeek: () => void; onSubmit: (text: string) => void; busy: boolean; first: boolean }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(w.suggestion ?? w.text);
  return (
    <li className="rounded-surface bg-bg-raised px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={onSeek} className="group flex min-w-0 items-center gap-4 text-left" aria-label={`Jump to “${w.text}” at ${w.at}`}>
          <Mono className="text-info group-hover:underline">{w.at.replace(/^00:/, "")}</Mono>
          <span className="truncate text-section text-fg-primary">“{w.text}”</span>
          {w.suggestion && <span className="truncate text-fg-secondary">→ {w.suggestion}?</span>}
        </button>
        {!editing && (
          <div className="flex shrink-0 gap-2">
            {/* The first open word is the owner's next move: the screen's one amber action. */}
            <Button variant={first ? "primary" : "secondary"} icon="check" onClick={() => onSubmit(w.text)} disabled={busy} title="The word is right as it is">
              Correct
            </Button>
            <Button icon="edit" onClick={() => setEditing(true)} disabled={busy}>
              Change
            </Button>
          </div>
        )}
      </div>
      <p className="mt-1 text-meta text-fg-muted">{w.why}</p>
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

// Severity is a 2 px rule on the left plus a word (never colour alone).
const SEV: Record<string, string> = { blocker: "bg-st-fail", major: "bg-st-hold", minor: "bg-line-control" };
const SEV_TEXT: Record<string, string> = { blocker: "text-st-fail", major: "text-st-hold", minor: "text-fg-secondary" };
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function ReviewerNotes({ issues, summary, onSeek }: { issues: ReviewIssue[]; summary: string; onSeek: (t: number) => void }) {
  return (
    <Panel title={issues.length ? <span className="flex items-baseline gap-3">Reviewer notes <Mono className="text-fg-muted">{issues.length}</Mono></span> : "Reviewer notes"}>
      <p className="text-fg-secondary">{summary}</p>
      {issues.length > 0 && (
        <ul className="mt-2 divide-y divide-line-subtle">
          {issues.map((i, k) => (
            <li key={k} className="flex gap-4 py-4">
              <span className={cx("w-0.5 shrink-0 rounded-full", SEV[i.severity ?? "minor"])} aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-label">
                  <span className={SEV_TEXT[i.severity ?? "minor"]}>{cap(i.severity ?? "note")}</span>
                  <span className="text-fg-muted">·</span>
                  <span className="text-fg-secondary">{i.category}</span>
                  {i.at ? (
                    <button type="button" onClick={() => onSeek(tcToSeconds(i.at))} className="ml-auto max-w-[50%] truncate font-mono text-mono text-info hover:underline" title={i.at} aria-label={`Jump to ${i.at}`}>
                      {i.at.replace(/^00:/, "")}
                    </button>
                  ) : (
                    <span className="ml-auto text-meta text-fg-muted">whole reel</span>
                  )}
                </div>
                <p className="mt-1 text-fg-primary">{i.text}</p>
                {i.fix && <p className="mt-1 text-meta text-fg-secondary">Suggested fix: {i.fix}</p>}
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
    <details className="group border-t border-line-subtle" open={fails > 0}>
      <summary className="flex cursor-pointer list-none items-center justify-between py-5">
        <span className="text-section">Quality checks</span>
        <span className="flex items-center gap-3 text-label">
          <span className="text-st-sendable">{gates.length - fails - warns} pass</span>
          {warns > 0 && <span className="text-st-hold">{warns} warn</span>}
          {fails > 0 && <span className="text-st-fail">{fails} fail</span>}
          <Icon name="chevronDown" size={16} className="text-fg-muted transition-transform group-open:rotate-180" />
        </span>
      </summary>
      <ul className="grid grid-cols-1 gap-x-8 pb-6 xl:grid-cols-2">
        {gates.map((g) => (
          <li key={g.name} className="flex items-start gap-3 py-2">
            {/* Dot + word: status is never colour alone. */}
            <span
              className={cx("flex w-14 shrink-0 items-center gap-2 text-label", g.status === "pass" ? "text-st-sendable" : g.status === "warn" ? "text-st-hold" : "text-st-fail")}
            >
              <span className={cx("h-2 w-2 rounded-full", g.status === "pass" ? "bg-st-sendable" : g.status === "warn" ? "bg-st-hold" : "bg-st-fail")} aria-hidden="true" />
              {cap(g.status)}
            </span>
            <div className="min-w-0">
              <p className="text-ui text-fg-primary">{gateLabel(g.name)}</p>
              <p className="font-mono text-meta text-fg-muted">{g.detail}</p>
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
        {/* A chosen answer is selection, not an action: graphite with a stronger edge, not amber. */}
        <Button icon="check" onClick={() => save(true)} aria-pressed={answer === true} className={answer === true ? "border-fg-secondary bg-bg-high" : undefined}>
          Yes
        </Button>
        <Button icon="x" onClick={() => save(false)} aria-pressed={answer === false} className={answer === false ? "border-fg-secondary bg-bg-high" : undefined}>
          No
        </Button>
        {saved && <span className="text-label text-st-sendable">Saved</span>}
        {err && <span className="text-meta text-st-fail">{err}</span>}
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
    return <NotYet what="review" icon="phone" opens="The verdict and the reel appear here once the edit has rendered and checked itself." />;
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
    <div className="grid grid-cols-12 gap-x-10 gap-y-6">
      <div className="col-span-12 lg:col-span-5">{player ? <PhonePreview player={player} client={p.client ?? "client"} /> : <Loading label="Loading the reel…" />}</div>
      <div className="col-span-12 lg:col-span-7">
        <VerdictCard p={p} onSeek={seek} />
        {(p.proof.length > 0 || proofBusy) && (
          <Panel title="Proof words" actions={<span className="text-meta text-fg-muted">Click a word to jump to it</span>}>
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
              {p.proof.map((w, k) => (
                <ProofItem key={w.i} w={w} first={k === 0} busy={proofBusy} onSeek={() => seek(tcToSeconds(w.at))} onSubmit={(t) => fix(w, t)} />
              ))}
            </ul>
          </Panel>
        )}
        {p.review && <ReviewerNotes issues={p.review.issues} summary={p.review.summary} onSeek={seek} />}
        {p.review?.rubric && p.review.rubric.length > 0 && (
          <Panel title="Brief checklist (fixed before the edit)">
            <ul className="space-y-1.5" aria-label="Brief checklist">
              {p.review.rubric.map((r) => (
                <li key={r.id} className="flex gap-2 text-meta">
                  <span className={r.met ? "text-st-sendable" : "text-st-hold"} aria-label={r.met ? "met" : "not met"}>{r.met ? "✓" : "✗"}</span>
                  <span className="text-fg-primary">{r.id.replace(/_/g, " ")}</span>
                  {r.evidence && <span className="text-fg-muted">· {r.evidence}</span>}
                </li>
              ))}
            </ul>
          </Panel>
        )}
        <Gates p={p} />
        <div className="grid grid-cols-1 gap-x-10 xl:grid-cols-2">
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
