// Timeline → layer model shared by the exploded 3D view and its flat equivalent (FR-5).
import type { TimelineView } from "../api/types";
import { color } from "../theme/tokens";

export interface LayerBlock {
  id: string; // reason key (plan item / finish id)
  start: number; // seconds
  end: number;
  label: string;
}
export interface Layer {
  id: string;
  label: string;
  color: string;
  kind: "picture" | "audio";
  blocks: LayerBlock[];
}

export function buildLayers(view: TimelineView): { layers: Layer[]; duration: number; fps: number } {
  const tl = view.timeline;
  const [num, den] = tl.fps.split("/").map(Number);
  const fps = num / (den || 1);
  const s = (f: number) => f / fps;
  const duration = s(tl.duration_f);
  const reasons = view.reasons;
  const short = (t: string, n = 28) => (t.length > n ? t.slice(0, n - 1) + "…" : t);

  const layers: Layer[] = [
    {
      id: "video",
      label: "Source video",
      color: color.layer.video,
      kind: "picture",
      blocks: tl.video.map((c) => ({ id: c.src.item, start: s(c.at_f), end: s(c.at_f + c.dur_f), label: c.src.item })),
    },
    {
      id: "colour",
      label: "Colour & effects",
      color: color.layer.colour,
      kind: "picture",
      blocks: [
        { id: "grade", start: 0, end: duration, label: `${tl.grade.look} ${tl.grade.strength.toFixed(2)}` },
        ...tl.effects.map((e) => ({ id: e.id, start: s(e.start_f), end: s(e.end_f), label: e.type.replace(/_/g, " ") })),
      ],
    },
    {
      id: "punch",
      label: "Punch-ins",
      color: color.layer.punch,
      kind: "picture",
      blocks: tl.video.filter((c) => c.scale.length > 0).map((c) => ({ id: c.id, start: s(c.at_f + (c.scale[0]?.f ?? 0)), end: s(c.at_f + c.dur_f), label: `${Math.max(...c.scale.map((k) => k.v)).toFixed(2)}×` })),
    },
    {
      id: "broll",
      label: "B-roll",
      color: color.layer.broll,
      kind: "picture",
      blocks: tl.pips.map((b) => ({ id: b.id, start: s(b.start_f), end: s(b.end_f), label: b.id })),
    },
    {
      id: "captions",
      label: "Captions",
      color: color.layer.captions,
      kind: "picture",
      blocks: (tl.captions?.pages ?? []).map((pg, i) => ({ id: reasons[`page${i}`] ? `page${i}` : "captions", start: s(pg.start_f), end: s(pg.end_f), label: short(pg.words.map((w) => w.text).join(" "), 22) })),
    },
    {
      id: "titles",
      label: "Titles & graphics",
      color: color.layer.titles,
      kind: "picture",
      blocks: [
        ...tl.titles.map((t) => ({ id: t.id, start: s(t.start_f), end: s(t.end_f), label: short(t.text) })),
        ...tl.graphics.map((g) => ({ id: g.id, start: s(g.start_f), end: s(g.end_f), label: short(g.text || g.kind.replace(/_/g, " ")) })),
      ],
    },
  ];
  const audio = (role: string, label: string, col: string): Layer => ({
    id: role,
    label,
    color: col,
    kind: "audio",
    blocks: tl.audio.filter((a) => a.role === role).map((a) => ({ id: a.id, start: s(a.at_f), end: s(a.at_f + a.dur_f), label: `${a.gain_db} dB` })),
  });
  layers.push(audio("voice", "Dialogue", color.text.secondary), audio("music", "Music", color.accent.glow), audio("sfx", "Sound effects", color.status.hold));
  return { layers, duration, fps };
}

/** Kept lines in order (story strip): one block per clip, with the caption words spoken in it. */
export function storyBlocks(view: TimelineView): (LayerBlock & { text: string })[] {
  const { layers, fps } = buildLayers(view);
  const pages = view.timeline.captions?.pages ?? [];
  return layers[0].blocks.map((b) => ({
    ...b,
    text: pages
      .filter((p) => p.start_f / fps >= b.start - 0.01 && p.start_f / fps < b.end)
      .flatMap((p) => p.words.map((w) => w.text))
      .join(" "),
  }));
}
