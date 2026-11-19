// FR-8 Guided adjustments (no AI): each change is checked by the engine validator before it applies; its
// plain-language issues are shown next to the control (AC-12). Applied changes appear as "Manual" versions.
import { useState, type ReactNode } from "react";
import { useApi } from "../../api/context";
import { ApiError, friendlyError } from "../../api/errors";
import type { AdjustKind, Libraries, TimelineView, ValidatorIssue } from "../../api/types";
import { Icon } from "../../components/icons";
import { Button, cx, Loading, Notice, Panel, Select, TextInput, Toggle } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";
import { LOOKS, validateAdjust } from "../../lib/adjust";
import { prettyId } from "../../lib/format";
import { NotYet, useProject } from "./ProjectLayout";

export function IssueList({ issues }: { issues: ValidatorIssue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="mt-2 space-y-1.5" role="alert" aria-label="Validator issues">
      {issues.map((i, k) => (
        <li key={k} className="flex gap-2 rounded-control border-l-2 border-st-fail bg-bg-raised px-3 py-2">
          <Icon name="alert" size={16} className="mt-0.5 shrink-0 text-st-fail" />
          <div>
            <p className="text-fg-primary">{i.message}</p>
            {i.fix && <p className="text-meta text-fg-secondary">{i.fix}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}

const LOOK_SWATCH: Record<string, string> = {
  none: "linear-gradient(135deg,#6b6f7a,#c9ccd3)",
  clean: "linear-gradient(135deg,#5a6b7d,#e4ecf2)",
  warm: "linear-gradient(135deg,#8a4b2c,#ffd2a1)",
  cool: "linear-gradient(135deg,#1f4a6b,#a9d8f2)",
  punchy: "linear-gradient(135deg,#c2185b,#ffcc00)",
  film: "linear-gradient(135deg,#4a4540,#d9cbb6)",
  teal_orange: "linear-gradient(135deg,#0f5e63,#ff9a4d)",
};

const FAMILY_SAMPLE: Record<string, { text: string; cls: string; style?: React.CSSProperties }> = {
  bold_pop: { text: "THIS IS IT", cls: "font-black uppercase tracking-tight", style: { color: "#fff", textShadow: "0 0 3px #000, 0 0 3px #000" } },
  clean_phrase: { text: "Clear and simple", cls: "font-semibold rounded bg-black/70 px-1.5", style: { color: "#fff" } },
  editorial_kinetic: { text: "Ten Days Later", cls: "font-medium", style: { color: "#F2EDE6" } },
  minimal_calm: { text: "quiet moments", cls: "font-light lowercase", style: { color: "#fff" } },
  speaker_coded: { text: "you said that?", cls: "font-bold", style: { color: "#7FDBFF" } },
};

/** One adjustment row: control + Apply, with instant client checks and the engine's 422 issues. */
function Row({
  title,
  hint,
  kind,
  value,
  dirty,
  ctx,
  children,
  onApplied,
}: {
  title: string;
  hint?: string;
  kind: AdjustKind;
  value: unknown;
  dirty: boolean;
  ctx: { families: string[]; tracks: string[] };
  children: ReactNode;
  onApplied: () => void;
}) {
  const api = useApi();
  const { project: p } = useProject();
  const [server, setServer] = useState<ValidatorIssue[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const local = dirty ? validateAdjust(kind, value, ctx) : [];
  const issues = local.length ? local : server;

  async function apply() {
    setBusy(true);
    setErr(null);
    setServer([]);
    setOk(false);
    try {
      await api.adjust(p.id, kind, value);
      setOk(true);
      onApplied();
    } catch (e) {
      if (e instanceof ApiError && e.kind === "validation") setServer(e.issues.length ? e.issues : [{ code: "invalid", path: kind, message: e.message, fix: "" }]);
      else setErr(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-b border-line-subtle py-5 first:pt-0 last:border-0 last:pb-0">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-ui text-fg-primary">{title}</p>
          {hint && <p className="text-meta text-fg-muted">{hint}</p>}
        </div>
        <Button variant={dirty && !local.length ? "primary" : "secondary"} disabled={!dirty || local.length > 0} busy={busy} onClick={apply} aria-label={`Apply ${title.toLowerCase()}`}>
          Apply
        </Button>
      </div>
      <div className="min-w-0">{children}</div>
      <IssueList issues={issues} />
      {err && (
        <div className="mt-2">
          <Notice tone="error">{err}</Notice>
        </div>
      )}
      {ok && !server.length && <p className="mt-2 text-label text-st-sendable">Applied — re-rendering what changed. It’s in the version history as “Manual”.</p>}
    </div>
  );
}

function Num({ label, value, onChange, step = 0.05, min, max, suffix }: { label: string; value: string; onChange: (v: string) => void; step?: number; min: number; max: number; suffix?: string }) {
  return (
    <div className="flex items-center gap-3">
      <input type="range" aria-label={`${label} slider`} min={min} max={max} step={step} value={Number(value) || 0} onChange={(e) => onChange(e.target.value)} className="h-1 flex-1 accent-[#45D0C1]" />
      <div className="relative w-28 shrink-0">
        <TextInput aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} inputMode="decimal" className="h-8 pr-9 font-mono text-mono" />
        {suffix && <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-label text-fg-muted">{suffix}</span>}
      </div>
    </div>
  );
}

const HEX = /^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/;
/** Numbers go to the API as numbers; an empty box stays "" so the local check can say "Enter a number". */
const num = (s: string): number | "" => (s.trim() === "" ? "" : Number(s));

/** Colour tokens of a caption family (its defaults, then the plan's overrides), e.g. emph_color, speaker_a. */
function colourTokens(lib: Libraries, family: string, overrides: Record<string, string>): Record<string, string> {
  const fam = lib.caption_families.find((f) => f.id === family);
  const all = { ...(fam?.tokens ?? {}), ...overrides };
  const out = Object.fromEntries(Object.entries(all).filter(([, v]) => typeof v === "string" && HEX.test(v)));
  return Object.keys(out).length ? out : { emph_color: "#FFD400" };
}

function AdjustForm({ tl, lib }: { tl: TimelineView; lib: Libraries }) {
  const a = tl.adjust;
  const family = a.caption_family ?? tl.timeline.captions?.family ?? "";
  const tokens = colourTokens(lib, family, a.caption_tokens);
  const firstToken = "emph_color" in tokens ? "emph_color" : Object.keys(tokens)[0];
  const initial = {
    family,
    tokenKey: firstToken,
    tokenValue: tokens[firstToken],
    look: a.look,
    strength: String(a.look_strength),
    track: "",
    gain: String(a.music_gain_db),
    sfxOff: a.sfx === 0,
    punchOff: a.punch_ins === 0,
    grain: String(a.grain),
    vignette: String(a.vignette),
    pause: String(a.max_pause_ms ?? 400),
  };
  const currentTrack = a.music_track === "none" ? "No music" : lib.music.find((m) => m.id === a.music_track)?.title ?? a.music_track;
  const [v, setV] = useState(initial);
  const [base, setBase] = useState(initial);
  const set = <K extends keyof typeof initial>(k: K, x: (typeof initial)[K]) => setV((s) => ({ ...s, [k]: x }));
  const ctx = { families: lib.caption_families.map((f) => f.id), tracks: lib.music.map((m) => m.id) };
  const done = (keys: (keyof typeof initial)[]) => () => setBase((b) => ({ ...b, ...Object.fromEntries(keys.map((k) => [k, v[k]])) }));

  return (
    <div className="grid grid-cols-12 gap-x-10 gap-y-6">
      <div className="col-span-12 xl:col-span-7">
        <Panel title="Captions">
          <Row title="Caption style" hint="The family sets font, case, animation and zone." kind="caption_family" value={v.family} dirty={v.family !== base.family} ctx={ctx} onApplied={done(["family"])}>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5" role="radiogroup" aria-label="Caption style">
              {lib.caption_families.map((f) => {
                const s = FAMILY_SAMPLE[f.id] ?? { text: f.id, cls: "" };
                return (
                  <button
                    key={f.id}
                    type="button"
                    role="radio"
                    aria-checked={v.family === f.id}
                    onClick={() => set("family", f.id)}
                    className={cx("rounded-surface border p-2 text-left transition-colors duration-hover", v.family === f.id ? "border-fg-secondary bg-bg-high" : "border-line-subtle hover:border-line-control")}
                  >
                    <div className="flex h-12 items-center justify-center rounded-control bg-bg-inset">
                      <span className={cx("text-[15px]", s.cls)} style={s.style}>
                        {s.text}
                      </span>
                    </div>
                    <p className="mt-1.5 truncate text-label text-fg-primary">{prettyId(f.id)}</p>
                    <p className="truncate text-meta text-fg-muted">{f.mood}</p>
                  </button>
                );
              })}
            </div>
          </Row>
          <Row
            title="Caption colour"
            hint="Overrides one colour token of the family."
            kind="caption_token"
            value={{ key: v.tokenKey, value: v.tokenValue }}
            dirty={v.tokenKey !== base.tokenKey || v.tokenValue !== base.tokenValue}
            ctx={ctx}
            onApplied={done(["tokenKey", "tokenValue"])}
          >
            <div className="flex items-center gap-2">
              <div className="w-56 shrink-0">
                <Select aria-label="Token" value={v.tokenKey} onChange={(e) => setV((s) => ({ ...s, tokenKey: e.target.value, tokenValue: tokens[e.target.value] ?? s.tokenValue }))}>
                  {Object.keys(tokens).map((k) => (
                    <option key={k} value={k}>
                      {k === "emph_color" ? "Emphasis colour" : prettyId(k)}
                    </option>
                  ))}
                </Select>
              </div>
              <input type="color" aria-label="Pick colour" value={/^#[0-9a-fA-F]{6}$/.test(v.tokenValue) ? v.tokenValue : "#000000"} onChange={(e) => set("tokenValue", e.target.value.toUpperCase())} className="h-9 w-12 cursor-pointer rounded-control border border-line-control bg-bg-overlay p-1" />
              <TextInput aria-label="Hex colour" value={v.tokenValue} onChange={(e) => set("tokenValue", e.target.value)} className="w-28 font-mono text-mono" />
            </div>
          </Row>
        </Panel>

        <Panel title="Look">
          <Row title="Colour look" kind="look" value={v.look} dirty={v.look !== base.look} ctx={ctx} onApplied={done(["look"])}>
            <div className="grid grid-cols-4 gap-2 sm:grid-cols-7" role="radiogroup" aria-label="Colour look">
              {LOOKS.map((l) => (
                <button key={l.id} type="button" role="radio" aria-checked={v.look === l.id} title={l.note} onClick={() => set("look", l.id)} className="group text-center">
                  <span className={cx("block h-10 rounded-control border-2 transition-colors", v.look === l.id ? "border-fg-primary" : "border-transparent group-hover:border-line-control")} style={{ background: LOOK_SWATCH[l.id] }} />
                  <span className={cx("mt-1 block truncate text-meta", v.look === l.id ? "text-fg-primary" : "text-fg-muted")}>{prettyId(l.id)}</span>
                </button>
              ))}
            </div>
          </Row>
          <Row title="Look strength" hint="0.3–0.6 is typical." kind="look_strength" value={num(v.strength)} dirty={v.strength !== base.strength} ctx={ctx} onApplied={done(["strength"])}>
            <Num label="Look strength" value={v.strength} onChange={(x) => set("strength", x)} min={0} max={1} />
          </Row>
          <Row title="Grain" hint="0.15–0.3 reads as texture." kind="grain" value={num(v.grain)} dirty={v.grain !== base.grain} ctx={ctx} onApplied={done(["grain"])}>
            <Num label="Grain" value={v.grain} onChange={(x) => set("grain", x)} min={0} max={0.6} />
          </Row>
          <Row title="Vignette" kind="vignette" value={num(v.vignette)} dirty={v.vignette !== base.vignette} ctx={ctx} onApplied={done(["vignette"])}>
            <Num label="Vignette" value={v.vignette} onChange={(x) => set("vignette", x)} min={0} max={0.7} />
          </Row>
        </Panel>
      </div>

      <div className="col-span-12 xl:col-span-5">
        <Panel title="Sound">
          <Row title="Music track" hint={`Now: ${currentTrack}`} kind="music_track" value={v.track} dirty={v.track !== base.track && v.track !== ""} ctx={ctx} onApplied={done(["track"])}>
            <Select aria-label="Music track" value={v.track} onChange={(e) => set("track", e.target.value)}>
              <option value="">Keep the Editor’s pick</option>
              <option value="none">No music</option>
              {lib.music.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title} · {m.mood} · {m.bpm} bpm
                </option>
              ))}
            </Select>
          </Row>
          <Row title="Music level" hint={a.music_track === "none" ? "No music in this edit — pick a track first." : "Before ducking under speech."} kind="music_gain_db" value={num(v.gain)} dirty={v.gain !== base.gain} ctx={ctx} onApplied={done(["gain"])}>
            <Num label="Music level" value={v.gain} onChange={(x) => set("gain", x)} min={-30} max={-6} step={1} suffix="dB" />
          </Row>
          <Row title="Sound effects" hint={base.sfxOff ? "None in this edit. Ask the Editor (Revise) to add some." : `${a.sfx} in this edit.`} kind="sfx_off" value={true} dirty={v.sfxOff && !base.sfxOff} ctx={ctx} onApplied={done(["sfxOff"])}>
            <Toggle checked={v.sfxOff} onChange={(x) => !base.sfxOff && set("sfxOff", x)} label="Turn all sound effects off" />
          </Row>
        </Panel>
        <Panel title="Pacing">
          <Row title="Punch-ins" hint={base.punchOff ? "None in this edit. Ask the Editor (Revise) to add some." : `${a.punch_ins} in this edit.`} kind="punch_ins_off" value={true} dirty={v.punchOff && !base.punchOff} ctx={ctx} onApplied={done(["punchOff"])}>
            <Toggle checked={v.punchOff} onChange={(x) => !base.punchOff && set("punchOff", x)} label="Turn all punch-ins off" />
          </Row>
          <Row title="Longest pause kept" hint="Longer pauses are cut (jump cut). 0 keeps every pause." kind="max_pause_ms" value={num(v.pause)} dirty={v.pause !== base.pause} ctx={ctx} onApplied={done(["pause"])}>
            <div className="relative w-36">
              <TextInput aria-label="Longest pause kept" value={v.pause} onChange={(e) => set("pause", e.target.value)} inputMode="numeric" className="h-8 pr-10 font-mono text-mono" />
              <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-label text-fg-muted">ms</span>
            </div>
          </Row>
        </Panel>
        <p className="border-t border-line-subtle pt-4 text-meta text-fg-muted">
          Every change is checked by the engine’s validator first. For frame-level trims use the export package in Final Cut or Resolve (Deliver).
        </p>
      </div>
    </div>
  );
}

export default function Adjust() {
  const { project: p } = useProject();
  const api = useApi();
  const tl = useQuery(() => api.timeline(p.id), [api, p.id]);
  const lib = useQuery(() => api.libraries(), [api]);
  if (!p.versions.length) return <NotYet what="adjust" icon="sliders" opens="Captions, look, sound and pacing can be adjusted once the first edit has finished." />;
  if (tl.error || lib.error) return <Notice tone="error">{friendlyError(tl.error ?? lib.error)}</Notice>;
  if (!tl.data || !lib.data) return <Loading />;
  return <AdjustForm tl={tl.data} lib={lib.data} />;
}
