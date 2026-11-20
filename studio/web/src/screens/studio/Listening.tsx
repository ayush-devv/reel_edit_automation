// G2.5 listening test: blind A/B of generated SFX, music and voice against today's fallback. The page never names
// the models; the engine keeps the key. Group 3 adopts a free model only if it is usable and beats the fallback.
import { useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { ListenSet } from "../../api/types";
import { PageHeader } from "../../components/Shell";
import { Button, Loading, Mono, Notice, Panel, Segmented } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";

const SETS: { value: ListenSet; label: string }[] = [
  { value: "sfx", label: "Sound effects" },
  { value: "music", label: "Music" },
  { value: "voice", label: "Voice" },
];
const pct = (x: number) => `${Math.round(x * 100)}%`;

export default function Listening() {
  const api = useApi();
  const [set, setSet] = useState<ListenSet>("sfx");
  const q = useQuery(() => api.listening(set), [api, set]);
  const [usable, setUsable] = useState({ a: false, b: false });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const data = q.data;
  const next = data?.pairs.find((p) => !p.done);
  const done = data?.pairs.filter((p) => p.done).length ?? 0;

  async function vote(choice: "A" | "B" | "tie") {
    if (!next) return;
    setBusy(true);
    setErr(null);
    try {
      await api.voteListening(set, { pair: next.id, choice, usable_a: usable.a, usable_b: usable.b });
      setUsable({ a: false, b: false });
      q.reload();
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full px-8 py-8">
      <PageHeader title="Listening test" subtitle="Blind A/B: is a free model better than what we have, and good enough for a client reel?" />
      <div className="mb-6">
        <Segmented label="Set" value={set} options={SETS} onChange={(v) => setSet(v)} />
      </div>
      {q.error ? (
        <Notice tone="error">{friendlyError(q.error)}</Notice>
      ) : !data ? (
        <Loading />
      ) : data.pairs.length === 0 ? (
        <Panel title="Nothing rendered yet">
          <p className="text-fg-secondary">
            Install a model, read its licence, add its licence row to the registry and declare it in <Mono>~/.config/reel/generators.json</Mono>. Then
            render the {data.prompts} prompts. Without any model, only today’s fallback is rendered.
          </p>
          <Button className="mt-3" variant="primary" icon="play" busy={busy} onClick={async () => {
            setBusy(true);
            try {
              await api.prepareListening(set);
              q.reload();
            } catch (e) {
              setErr(friendlyError(e));
            } finally {
              setBusy(false);
            }
          }}>
            Render the {set} set
          </Button>
        </Panel>
      ) : (
        <div className="grid grid-cols-12 gap-x-10 gap-y-6">
          <div className="col-span-12 xl:col-span-7">
            <Panel title={next ? `Pair ${done + 1} of ${data.pairs.length}` : "All pairs heard"}>
              {next ? (
                <>
                  <p className="mb-4 text-ui text-fg-primary">“{next.prompt}”</p>
                  <div className="grid grid-cols-2 gap-4">
                    {(["A", "B"] as const).map((side) => (
                      <figure key={side}>
                        <figcaption className="mb-2 text-section text-fg-primary">{side}</figcaption>
                        <audio controls src={api.listeningMediaUrl(set, next[side])} className="w-full" aria-label={`Sound ${side}`} />
                        <label className="mt-2 flex items-center gap-2 text-meta text-fg-secondary">
                          <input type="checkbox" className="accent-signal" checked={side === "A" ? usable.a : usable.b}
                                 onChange={(e) => setUsable((u) => (side === "A" ? { ...u, a: e.target.checked } : { ...u, b: e.target.checked }))} />
                          I’d use {side} in a client reel
                        </label>
                      </figure>
                    ))}
                  </div>
                  <div className="mt-5 flex gap-2">
                    <Button variant="primary" busy={busy} onClick={() => vote("A")}>A is better</Button>
                    <Button busy={busy} onClick={() => vote("tie")}>Same</Button>
                    <Button variant="primary" busy={busy} onClick={() => vote("B")}>B is better</Button>
                  </div>
                </>
              ) : (
                <p className="text-fg-secondary">Every pair has a vote. The result is on the right; you can render the set again after adding a model.</p>
              )}
              {err && <div className="mt-3"><Notice tone="error">{err}</Notice></div>}
            </Panel>
          </div>
          <div className="col-span-12 xl:col-span-5">
            <Panel title="Result so far">
              {data.summary && Object.keys(data.summary.models).length ? (
                <>
                  <table className="w-full text-meta">
                    <thead>
                      <tr className="text-fg-muted">
                        <th className="text-left font-normal">Model</th>
                        <th className="text-right font-normal">Wins</th>
                        <th className="text-right font-normal">Usable</th>
                        <th className="text-right font-normal">Decision</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(data.summary.models).map(([m, r]) => (
                        <tr key={m}>
                          <td className="text-fg-primary">{m}</td>
                          <td className="text-right font-mono">{pct(r.win_rate)}</td>
                          <td className="text-right font-mono">{pct(r.usable_rate)}</td>
                          <td className="text-right">{r.decision}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-2 text-label text-fg-muted">{data.summary.rule}. Model names show only here, after you vote.</p>
                </>
              ) : (
                <p className="text-fg-secondary">No votes yet.</p>
              )}
              {data.summary &&
                Object.entries(data.summary.generators)
                  .filter(([, g]) => g.status !== "ok")
                  .map(([gid, g]) => (
                    <p key={gid} className="mt-2 text-meta text-st-hold">{gid}: {g.why}</p>
                  ))}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
