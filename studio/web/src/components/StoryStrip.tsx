// The persistent story strip (Cutting Room): the reel's beats in order, width = duration, docked at the bottom of
// every project screen like an NLE timeline. Built only from the real timeline; renders nothing until one exists.
import { useMemo } from "react";
import { useApi } from "../api/context";
import type { TimelineView } from "../api/types";
import { useQuery } from "../hooks/useQuery";
import { beatLabel } from "../lib/format";
import { buildLayers, storyBlocks } from "../lib/layers";
import { color } from "../theme/tokens";

const fmt = (t: number) => {
  const m = Math.floor(t / 60);
  return `${String(m).padStart(2, "0")}:${(t - m * 60).toFixed(1).padStart(4, "0")}`;
};

const BEAT_COLOR: Record<string, string> = { hook: color.layer.titles, payoff: color.layer.captions, "call to action": color.layer.captions };
const ROTATE = [color.layer.video, color.layer.broll, color.layer.colour, color.layer.punch];

/** Consecutive kept lines with the same beat merge into one segment; lines without a beat stay on their own. */
export function beatsOf(view: TimelineView): { label: string; start: number; end: number; lines: number; text: string }[] {
  const out: { label: string; start: number; end: number; lines: number; text: string }[] = [];
  for (const b of storyBlocks(view)) {
    const beat = view.story?.[b.id]?.beat?.trim();
    const label = beat ? beatLabel(beat) : b.id;
    const text = view.story?.[b.id]?.text ?? "";
    const last = out.at(-1);
    if (beat && last && last.label === label && Math.abs(last.end - b.start) < 0.05) {
      last.end = b.end;
      last.lines += 1;
      last.text = `${last.text} ${text}`.trim();
    } else out.push({ label, start: b.start, end: b.end, lines: 1, text });
  }
  return out;
}

export function StoryStrip({ projectId, versionKey }: { projectId: string; versionKey: number }) {
  const api = useApi();
  const tl = useQuery(() => api.timeline(projectId), [api, projectId, versionKey]);
  const beats = useMemo(() => (tl.data ? beatsOf(tl.data) : []), [tl.data]);
  if (!tl.data || beats.length === 0) return null;
  const total = buildLayers(tl.data).duration;
  const span = Math.max(0.001, beats.at(-1)!.end - beats[0].start);
  let rot = 0;
  return (
    <section aria-label="Story strip" className="sticky bottom-0 z-10 flex h-[72px] shrink-0 items-center gap-8 border-t border-line-subtle bg-bg-raised/80 px-8 backdrop-blur-md">
      <p className="shrink-0">
        <span className="font-mono text-timecode-lg tabular text-fg-primary">{fmt(Number.isFinite(total) && total > 0 ? total : span)}</span>
        <span className="ml-3 text-meta text-fg-muted">
          {beats.length} beat{beats.length === 1 ? "" : "s"}
        </span>
      </p>
      <ol className="flex h-9 min-w-0 flex-1 gap-0.5" aria-label="Beats in order, width is duration">
        {beats.map((b, i) => {
          const key = b.label.toLowerCase();
          const c = BEAT_COLOR[key] ?? ROTATE[rot++ % ROTATE.length];
          const secs = b.end - b.start;
          return (
            <li
              key={`${b.label}-${i}`}
              className="flex min-w-0 items-center overflow-hidden rounded-control px-2"
              style={{ flexGrow: secs / span, flexBasis: 0, background: `${c}80` }}
              title={`${b.label} · ${secs.toFixed(1)} s · ${b.lines} line${b.lines === 1 ? "" : "s"}${b.text ? `\n“${b.text.slice(0, 220)}${b.text.length > 220 ? "…" : ""}”` : ""}`}
            >
              <span className="truncate text-meta text-fg-primary">{b.label}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
