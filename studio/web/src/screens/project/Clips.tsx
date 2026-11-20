import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { ClipCandidate } from "../../api/types";
import { Button, cx, Empty, Loading, Mono, Notice, Panel } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";
import { usd } from "../../lib/format";
import { useProject } from "./ProjectLayout";

const FAMILY: Record<ClipCandidate["family"], string> = {
  hook: "Hook", story: "Story", tip: "Tip", hot_take: "Hot take", proof: "Proof", myth: "Myth",
};
const MARKS: (keyof ClipCandidate["scores"])[] = ["hook", "standalone", "payoff", "shareability", "energy"];

function minutes(s: number): string {
  return `${Math.round(s / 60)} min`;
}

/** G2.2 Clip Factory: the ranked candidates of a long recording; tick some and make them into reels. */
export default function Clips() {
  const api = useApi();
  const { project: p, reload } = useProject();
  const board = useQuery(() => api.clips(p.id), [api, p.id, p.status], { intervalMs: 5000 });
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [made, setMade] = useState<string[]>([]);

  if (p.kind !== "source") {
    return (
      <Empty icon="film" title="Not a long recording">
        Clip Factory boards belong to long recordings. Start one from New edit → “Long recording → several reels”.
      </Empty>
    );
  }
  if (board.loading && !board.data) return <Loading label="Opening the board…" />;
  if (!board.data) {
    return (
      <Empty icon="sparkle" title="Still reading the recording">
        The recording is analysed once, then the Clip Miner reads all of it. The board appears here when it’s done.
      </Empty>
    );
  }
  const b = board.data;
  const sel = picked ?? new Set(b.candidates.filter((c) => c.status === "selected" && !c.project).map((c) => c.id));
  const toggle = (id: string) => {
    const next = new Set(sel);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setPicked(next);
  };
  const est = b.estimate_per_reel;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-section text-fg-primary">Reels found in this recording</p>
          <p className="text-meta text-fg-muted">
            {minutes(b.source_s)} of source · {b.target_s[0]}–{b.target_s[1]} s of speech per reel · up to {b.yield_cap} reels. Score = the{" "}
            {b.score_label.toLowerCase()} from its 1–5 marks, not a prediction of views.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-meta text-fg-secondary">
            {sel.size} picked
            {est ? (
              <> · about <Mono>{usd(est.low_usd * sel.size)}</Mono>–<Mono>{usd(est.high_usd * sel.size)}</Mono> AI cost</>
            ) : (
              <> · cost estimate after 3 edits</>
            )}
          </span>
          <Button
            variant="primary"
            busy={busy}
            disabled={sel.size === 0}
            onClick={async () => {
              setBusy(true);
              setErr(null);
              try {
                const r = await api.makeClips(p.id, [...sel], true);
                setMade(r.made);
                setPicked(new Set());
                board.reload();
                reload();
              } catch (e) {
                setErr(friendlyError(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            Make {sel.size || ""} reel{sel.size === 1 ? "" : "s"}
          </Button>
        </div>
      </div>
      {err && <Notice tone="error">{err}</Notice>}
      {made.length > 0 && (
        <Notice tone="ok" title={`${made.length} reel project${made.length === 1 ? "" : "s"} queued`}>
          Each one edits like any reel: story, finish, quality checks, then Sendable or Hold.
        </Notice>
      )}
      <ol className="flex flex-col gap-3" aria-label="Candidate reels">
        {b.candidates.map((c) => (
          <li key={c.id}>
            <Panel bodyClass="p-4">
              <div className="flex flex-wrap items-start gap-4">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-signal"
                  aria-label={`Pick ${c.title}`}
                  checked={sel.has(c.id)}
                  disabled={!!c.project}
                  onChange={() => toggle(c.id)}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-ui font-medium text-fg-primary">
                    <span className="mr-2 text-fg-muted">{c.rank}.</span>
                    {c.title}
                  </p>
                  <p className="mt-1 text-meta text-fg-secondary">“{c.hook_text}”</p>
                  <p className="mt-2 line-clamp-3 text-meta text-fg-muted">{c.excerpt}</p>
                  <p className="mt-2 text-meta text-fg-secondary">{c.reason}</p>
                  {c.standalone_risks.length > 0 && (
                    <p className="mt-1 text-meta text-st-hold">Cold viewers might miss: {c.standalone_risks.join("; ")}</p>
                  )}
                  {c.warnings.map((w) => (
                    <p key={w} className="mt-1 text-meta text-st-hold">{w}</p>
                  ))}
                </div>
                <div className="flex w-56 shrink-0 flex-col items-end gap-1 text-right">
                  <span className="text-meta text-fg-secondary">
                    {FAMILY[c.family]} · {Math.round(c.duration_s)} s · score <Mono>{c.score.toFixed(2)}</Mono>
                  </span>
                  <span className="text-label text-fg-muted">{MARKS.map((m) => `${m} ${c.scores[m]}`).join(" · ")}</span>
                  {c.project ? (
                    <Link to={`/p/${c.project.id}/live`} className="text-meta text-info underline">
                      Open the reel ({c.project.status})
                    </Link>
                  ) : (
                    <span className={cx("text-label", c.status === "selected" ? "text-st-sendable" : "text-fg-muted")}>
                      {c.status === "selected" ? "Suggested" : `Not suggested: ${c.why}`}
                    </span>
                  )}
                </div>
              </div>
            </Panel>
          </li>
        ))}
      </ol>
    </div>
  );
}
