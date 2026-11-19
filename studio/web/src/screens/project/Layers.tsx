// FR-5 Layers: exploded 3D timeline (flat stacked tracks under reduced motion, AC-9), click any block for
// the Editor's reason (AC-8), story strip of the kept lines.
import { lazy, Suspense, useMemo, useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import { Button, cx, Loading, Mono, Notice, Panel, Segmented } from "../../components/ui";
import { useStatus } from "../../hooks/status";
import { use3D } from "../../hooks/useMedia";
import { useQuery } from "../../hooks/useQuery";
import { buildLayers, storyBlocks, type Layer, type LayerBlock } from "../../lib/layers";
import { color } from "../../theme/tokens";
import { NotYet, useProject } from "./ProjectLayout";

const LayersScene = lazy(() => import("../../three/LayersScene"));

const BEAT_COLORS = [color.layer.video, color.layer.colour, color.layer.punch, color.layer.broll, color.layer.captions, color.layer.titles];
const fmt = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;

/** Flat stacked tracks: every block is a button, so the whole view works by keyboard. */
function FlatLayers({ layers, duration, time, selected, onSelect }: { layers: Layer[]; duration: number; time: number; selected: string | null; onSelect: (l: Layer, b: LayerBlock) => void }) {
  return (
    <div className="space-y-2 p-6" data-gl="off">
      {layers.map((l) => (
        <div key={l.id} className="grid grid-cols-[140px_1fr] items-center gap-3">
          <span className="truncate text-label" style={{ color: l.color }}>
            {l.label}
          </span>
          <div className={cx("relative rounded-control bg-bg-raised", l.kind === "audio" ? "h-6" : "h-9")}>
            {l.blocks.map((b, i) => {
              const key = `${l.id}:${b.id}:${b.start}`;
              return (
                <button
                  key={`${b.id}-${i}`}
                  type="button"
                  onClick={() => onSelect(l, b)}
                  aria-pressed={selected === key}
                  aria-label={`${l.label}: ${b.label}, ${fmt(b.start)}–${fmt(b.end)}`}
                  title={b.label}
                  className={cx("absolute inset-y-1 overflow-hidden rounded-control px-1.5 text-left text-meta font-medium text-black/85 transition-[filter] duration-hover hover:brightness-110", selected === key && "ring-2 ring-fg-primary")}
                  style={{ left: `${(b.start / duration) * 100}%`, width: `calc(${((b.end - b.start) / duration) * 100}% - 2px)`, background: l.color }}
                >
                  <span className="block truncate leading-[inherit]">{l.kind === "audio" ? "" : b.label}</span>
                </button>
              );
            })}
            <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-signal" style={{ left: `${(time / duration) * 100}%` }} aria-hidden="true" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Layers() {
  const { project: p } = useProject();
  const api = useApi();
  const { busy } = useStatus();
  const can3D = use3D();
  const tl = useQuery(() => api.timeline(p.id), [api, p.id]);
  const model = useMemo(() => (tl.data ? buildLayers(tl.data) : null), [tl.data]);
  const story = useMemo(() => (tl.data ? storyBlocks(tl.data) : []), [tl.data]);
  const [mode, setMode] = useState<"3d" | "flat">("3d");
  const [exploded, setExploded] = useState(true);
  const [time, setTime] = useState(0);
  const [sel, setSel] = useState<{ layer: Layer; block: LayerBlock } | null>(null);

  if (!p.versions.length) return <NotYet what="show" icon="layers" opens="Every layer of the reel, and the Editor’s reason for each piece, appears here once the first edit has finished." />;
  if (tl.error) return <Notice tone="error" title="Couldn’t load the timeline">{friendlyError(tl.error)}</Notice>;
  if (!model || !tl.data) return <Loading label="Loading layers…" />;
  const show3D = can3D && mode === "3d";
  const selKey = sel ? `${sel.layer.id}:${sel.block.id}:${sel.block.start}` : null;
  const reason = sel ? tl.data.reasons[sel.block.id] ?? tl.data.reasons[sel.layer.id] : null;
  const select = (layer: Layer, block: LayerBlock) => {
    setSel({ layer, block });
    setTime(block.start);
  };

  return (
    <div className="grid grid-cols-12 gap-x-10 gap-y-6">
      <div className="col-span-12 xl:col-span-8">
        <section className="mb-6 overflow-hidden rounded-surface bg-bg-inset" aria-label="Layers">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-subtle px-4 py-3">
            <div className="flex items-center gap-2">
              {can3D && (
                <Segmented
                  label="View"
                  value={mode}
                  onChange={setMode}
                  options={[
                    { value: "3d", label: "3D" },
                    { value: "flat", label: "Flat" },
                  ]}
                />
              )}
              {show3D && (
                <Button icon="layers" onClick={() => setExploded((e) => !e)} aria-pressed={!exploded}>
                  {exploded ? "Collapse stack" : "Explode stack"}
                </Button>
              )}
            </div>
            <div className="flex min-w-[260px] flex-1 items-center gap-3 sm:max-w-md">
              <Mono className="w-12 text-fg-secondary">{fmt(time)}</Mono>
              <input type="range" min={0} max={model.duration} step={0.05} value={time} onChange={(e) => setTime(Number(e.target.value))} aria-label="Playhead" className="h-1 flex-1 accent-[#E8A33D]" />
              <Mono className="w-12 text-right text-fg-muted">{fmt(model.duration)}</Mono>
            </div>
          </div>
          {show3D ? (
            <div className="h-[480px]">
              <Suspense fallback={null}>
                <LayersScene layers={model.layers} duration={model.duration} time={time} exploded={exploded} selected={selKey} onSelect={select} busy={busy} />
              </Suspense>
            </div>
          ) : (
            <FlatLayers layers={model.layers} duration={model.duration} time={time} selected={selKey} onSelect={select} />
          )}
        </section>

        <Panel title="Story strip" actions={<span className="text-meta text-fg-muted">Kept lines in order · width = duration</span>}>
          <ol className="flex h-14 gap-1" aria-label="Kept lines">
            {story.map((b, i) => (
              <li key={b.id} style={{ flexGrow: b.end - b.start, flexBasis: 0 }} className="min-w-0">
                <button
                  type="button"
                  onClick={() => select(model.layers[0], b)}
                  title={b.text}
                  aria-label={`Line ${i + 1}: ${b.text}`}
                  className={cx("group flex h-full w-full flex-col justify-center overflow-hidden rounded-control px-2 text-left text-black/85 transition-[filter] hover:brightness-110", selKey?.includes(`:${b.id}:`) && "ring-2 ring-fg-primary")}
                  style={{ background: BEAT_COLORS[i % BEAT_COLORS.length] }}
                >
                  <span className="font-mono text-meta font-medium">{b.id}</span>
                  <span className="truncate text-meta">{b.text}</span>
                </button>
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      <aside className="col-span-12 xl:col-span-4">
        <Panel title="Why it’s there" className="xl:sticky xl:top-4 xl:border-t-0">
          {sel ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ background: sel.layer.color }} aria-hidden="true" />
                <span className="text-label" style={{ color: sel.layer.color }}>
                  {sel.layer.label}
                </span>
                <Mono className="ml-auto text-fg-muted">
                  {fmt(sel.block.start)}–{fmt(sel.block.end)}
                </Mono>
              </div>
              <p className="text-section text-fg-primary">{sel.block.label}</p>
              <p className="text-fg-secondary">{reason ?? "No reason was recorded for this piece."}</p>
              <Mono className="block text-fg-muted">id {sel.block.id}</Mono>
            </div>
          ) : (
            <p className="text-fg-secondary">Click any block — a kept line, a punch-in, a caption page, a sound effect or the colour look — to read the Editor’s reason for it.</p>
          )}
        </Panel>
      </aside>
    </div>
  );
}
