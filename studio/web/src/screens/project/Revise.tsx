// FR-6 revision chat with version history and compare; FR-7 client notes with anchored preview (AC-11).
import { useEffect, useRef, useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { Project, Version } from "../../api/types";
import { Icon } from "../../components/icons";
import { Button, cx, IconButton, Mono, Notice, Panel, TextArea, TextInput } from "../../components/ui";
import { ago, usd } from "../../lib/format";
import { parseNotes } from "../../lib/notes";
import { isJobTerminal } from "../../lib/status";
import { NotYet, useProject } from "./ProjectLayout";

interface Msg {
  who: "owner" | "editor";
  text: string;
  version?: Version;
  pending?: boolean;
}

function chatFrom(p: Project, pending: string | null): Msg[] {
  const out: Msg[] = [];
  for (const v of p.versions) {
    if (v.n === 1) continue;
    const m = /^Revision: “(.*)”$/.exec(v.label);
    out.push({ who: "owner", text: m ? m[1] : v.label });
    out.push({ who: "editor", text: v.reply || "Done.", version: v });
  }
  if (pending) out.push({ who: "owner", text: pending }, { who: "editor", text: "Working on it…", pending: true });
  return out;
}

function CompareDialog({ p, v, onClose }: { p: Project; v: Version; onClose: () => void }) {
  const api = useApi();
  const prev = p.versions.filter((x) => x.n < v.n).at(-1);
  const ref = useRef<HTMLDialogElement>(null);
  const [which, setWhich] = useState<"old" | "new">("old");
  useEffect(() => {
    ref.current?.showModal?.();
  }, []);
  const src = which === "old" ? prev?.final : v.final;
  return (
    <dialog ref={ref} onClose={onClose} className="m-auto w-[min(92vw,520px)] rounded-surface border border-line-strong bg-bg-raised p-6 text-fg-primary shadow-menu backdrop:bg-black/80" aria-label="Compare versions">
      <h2 className="text-title">
        Compare v{prev?.n ?? "?"} → v{v.n}
      </h2>
      <p className="mt-1 text-fg-secondary">Plays the old version, then the new one.</p>
      <div className="mt-4 flex items-center gap-2">
        <span className={cx("rounded-control px-2 py-1 text-label", which === "old" ? "bg-bg-high text-fg-primary" : "text-fg-muted")}>Old · v{prev?.n}</span>
        <Icon name="chevron" size={14} className="text-fg-muted" />
        <span className={cx("rounded-control px-2 py-1 text-label", which === "new" ? "bg-bg-high text-fg-primary" : "text-fg-muted")}>New · v{v.n}</span>
      </div>
      <div className="mt-4 flex justify-center rounded-surface bg-bg-inset p-3">
        {src ? (
          <video key={src} src={api.mediaUrl(p.id, src, which === "old" ? prev?.n : v.n)} autoPlay controls className="max-h-[60vh] rounded-control" onEnded={() => setWhich((w) => (w === "old" ? "new" : w))} />
        ) : (
          <p className="px-4 py-10 text-center text-fg-secondary">The rendered files for these versions aren’t available here{api.mode === "mock" ? " (sample data)" : ""}.</p>
        )}
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={() => ref.current?.close()}>Close</Button>
      </div>
    </dialog>
  );
}

function Chat({ p }: { p: Project }) {
  const api = useApi();
  const { lastRevision, jobs } = useProject();
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [compare, setCompare] = useState<Version | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const jobStatus = jobId ? jobs[jobId]?.status : undefined;

  useEffect(() => {
    if (lastRevision) {
      setPending(null);
      setJobId(null);
    }
  }, [lastRevision]);
  // FR-6: if the Editor's change fails the validator (twice), the job ends without a revision event.
  useEffect(() => {
    if (!jobId || !isJobTerminal(jobStatus)) return;
    if (jobStatus !== "done") {
      setErr("The Editor couldn’t make that change safely — nothing changed.");
      setText((t) => t || pending || "");
    }
    setPending(null);
    setJobId(null);
  }, [jobId, jobStatus, pending]);
  const msgs = chatFrom(p, pending);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [msgs.length]);

  async function send() {
    const req = text.trim();
    if (!req) return;
    setErr(null);
    setPending(req);
    setText("");
    try {
      const r = await api.revise(p.id, req);
      setJobId(r.job.id);
    } catch (e) {
      setPending(null);
      setText(req);
      setErr(friendlyError(e));
    }
  }

  return (
    <Panel title="Ask for changes" bodyClass="flex flex-col gap-4">
      <div className="max-h-[520px] min-h-[200px] divide-y divide-line-subtle overflow-y-auto pr-1" aria-live="polite">
        {msgs.length === 0 && <p className="text-fg-secondary">Type what you want changed, like “make the hook faster” or “warmer look”. The Editor replies in one line, then the reel re-renders only what changed.</p>}
        {msgs.map((m, i) => (
          // A transcript, not bubbles: who, then what. The Editor is the AI, so its name carries the violet dot.
          <div key={i} className="py-4">
            <div>
              {m.who === "editor" ? (
                <p className="mb-1 flex items-center gap-2 text-label text-ai">
                  <span className={cx("h-2 w-2 rounded-full bg-ai", m.pending && "pulse-dot")} aria-hidden="true" />
                  Editor
                </p>
              ) : (
                <p className="mb-1 text-label text-fg-secondary">You</p>
              )}
              <p className={cx("text-body", m.pending && "text-fg-secondary")}>{m.text}</p>
              {m.version && (
                <div className="mt-2 flex items-center gap-3">
                  <span className="text-meta text-fg-muted">changed: v{m.version.n}</span>
                  {typeof m.version.cost_usd === "number" && <Mono className="text-fg-muted">{usd(m.version.cost_usd)}</Mono>}
                  <Button variant="ghost" icon="play" className="ml-auto h-7" onClick={() => setCompare(m.version!)}>
                    Compare
                  </Button>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {err && <Notice tone="error">{err}</Notice>}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <TextInput aria-label="Your request" placeholder="e.g. make the hook shorter" value={text} onChange={(e) => setText(e.target.value)} disabled={!!pending} />
        <Button type="submit" variant="primary" icon="send" busy={!!pending} disabled={!text.trim()}>
          Send
        </Button>
      </form>
      {compare && <CompareDialog p={p} v={compare} onClose={() => setCompare(null)} />}
    </Panel>
  );
}

function History({ p }: { p: Project }) {
  const api = useApi();
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const current = p.versions.at(-1)?.n;
  return (
    <Panel title="Version history">
      {err && (
        <div className="mb-3">
          <Notice tone="error">{err}</Notice>
        </div>
      )}
      <ol className="space-y-1">
        {[...p.versions].reverse().map((v) => (
          <li key={v.n} className={cx("flex items-center gap-3 rounded-control px-3 py-2.5", v.n === current && "bg-bg-overlay")} aria-current={v.n === current ? "true" : undefined}>
            <Mono className={cx("w-7", v.n === current ? "text-fg-primary" : "text-fg-secondary")}>v{v.n}</Mono>
            <div className="min-w-0 flex-1">
              <p className="truncate text-fg-primary">
                {v.label === "Manual" ? <span className="mr-1.5 text-label text-info">Manual ·</span> : null}
                {v.label === "Manual" ? v.reply : v.label}
              </p>
              <p className="text-meta text-fg-muted">
                {ago(v.created)}
                {typeof v.cost_usd === "number" && <> · {usd(v.cost_usd)}</>}
              </p>
            </div>
            {v.n === current ? (
              <span className="text-label text-fg-muted">Current</span>
            ) : (
              <Button
                icon="retry"
                busy={busy === v.n}
                onClick={async () => {
                  setBusy(v.n);
                  setErr(null);
                  try {
                    await api.restore(p.id, v.n);
                  } catch (e) {
                    setErr(friendlyError(e));
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                Restore
              </Button>
            )}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

export function ClientNotes({ p }: { p: Project }) {
  const api = useApi();
  const [text, setText] = useState("");
  const [notes, setNotes] = useState<{ line: string; anchor: string }[] | null>(null);
  const [unreadable, setUnreadable] = useState<string[]>([]);
  const [busy, setBusy] = useState<"preview" | "apply" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function preview(src: string) {
    setBusy("preview");
    setErr(null);
    setDone(false);
    try {
      const local = parseNotes(src);
      const r = await api.notesPreview(p.id, local.notes.map((n) => n.line).join("\n"));
      setNotes(local.notes.map((n, i) => ({ line: n.line, anchor: r.anchored[i] ?? "" })));
      setUnreadable([...local.unreadable, ...(r.unreadable ?? [])]);
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  async function apply() {
    if (!notes?.length) return;
    setBusy("apply");
    setErr(null);
    try {
      await api.notesApply(p.id, notes.map((n) => n.line).join("\n"));
      setDone(true);
      setNotes(null);
      setUnreadable([]);
      setText("");
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel title="Client notes">
      {!notes ? (
        <div className="space-y-3">
          <TextArea
            aria-label="Paste the client's notes"
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"Paste the client’s notes, one per line:\n0:12 make this faster\n[0:04] cut this\nlove the colours"}
            className="font-mono text-mono"
          />
          <div className="flex items-center gap-3">
            <Button icon="eye" busy={busy === "preview"} disabled={!text.trim()} onClick={() => preview(text)}>
              Preview notes
            </Button>
            {done && <span className="text-label text-st-sendable">Sent as one revision — see the chat.</span>}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-fg-secondary">Each note shows the line and caption on screen at its time. Edit or remove any note before sending.</p>
          <ul className="divide-y divide-line-subtle border-y border-line-subtle" aria-label="Notes to send">
            {notes.map((n, i) => (
              <li key={i} className="py-3">
                <div className="flex items-center gap-2">
                  <TextInput
                    aria-label={`Note ${i + 1}`}
                    value={n.line}
                    onChange={(e) => setNotes((list) => list!.map((x, j) => (j === i ? { ...x, line: e.target.value, anchor: "" } : x)))}
                    className="h-8 font-mono text-mono"
                  />
                  <IconButton icon="trash" label={`Remove note ${i + 1}`} onClick={() => setNotes((list) => list!.filter((_, j) => j !== i))} />
                </div>
                <p className="mt-1.5 text-meta text-fg-secondary">{n.anchor || "Edited — refresh the preview to re-anchor."}</p>
              </li>
            ))}
          </ul>
          {unreadable.length > 0 && (
            <div className="rounded-control border-l-2 border-st-hold bg-bg-raised px-4 py-3">
              <p className="text-label text-st-hold">Couldn’t read — not sent</p>
              <ul className="mt-1 space-y-0.5">
                {unreadable.map((u) => (
                  <li key={u} className="font-mono text-mono text-fg-secondary">
                    {u}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {err && <Notice tone="error">{err}</Notice>}
          <div className="flex flex-wrap gap-2">
            <Button icon="send" busy={busy === "apply"} disabled={!notes.length} onClick={apply}>
              Apply {notes.length} note{notes.length === 1 ? "" : "s"}
            </Button>
            <Button icon="retry" busy={busy === "preview"} onClick={() => preview(notes.map((n) => n.line).join("\n"))}>
              Refresh preview
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setNotes(null);
                setUnreadable([]);
              }}
            >
              Back
            </Button>
          </div>
        </div>
      )}
      {err && !notes && (
        <div className="mt-3">
          <Notice tone="error">{err}</Notice>
        </div>
      )}
    </Panel>
  );
}

export default function Revise() {
  const { project: p } = useProject();
  if (!p.versions.length) {
    return <NotYet what="revise" icon="chat" opens="Ask the Editor for changes or paste client notes once the first edit has finished." />;
  }
  return (
    <div className="grid grid-cols-12 gap-x-10 gap-y-6">
      <div className="col-span-12 lg:col-span-7">
        <Chat p={p} />
      </div>
      <div className="col-span-12 lg:col-span-5">
        <ClientNotes p={p} />
        <History p={p} />
      </div>
    </div>
  );
}
