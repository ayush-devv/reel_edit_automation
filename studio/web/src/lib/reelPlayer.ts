// One player for the review screen: the real MP4 (<video>, Range-served by the API) or, when there is no
// media (mock mode), a canvas that draws a stand-in reel from the timeline (captions, hook title, look).
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { Timeline } from "../api/types";

export interface ReelPlayer {
  kind: "video" | "canvas";
  element: HTMLVideoElement | HTMLCanvasElement;
  duration: number;
  getTime(): number;
  seek(t: number): void;
  play(): void;
  pause(): void;
  isPlaying(): boolean;
  setMuted(m: boolean): void;
  isMuted(): boolean;
  subscribe(fn: () => void): () => void;
  dispose(): void;
}

function emitter() {
  const subs = new Set<() => void>();
  return { on: (fn: () => void) => (subs.add(fn), () => void subs.delete(fn)), fire: () => subs.forEach((f) => f()) };
}

export function createVideoPlayer(src: string): ReelPlayer {
  const v = document.createElement("video");
  v.src = src;
  v.crossOrigin = "anonymous";
  v.playsInline = true;
  v.loop = true;
  v.preload = "auto";
  v.muted = false;
  const e = emitter();
  for (const ev of ["timeupdate", "play", "pause", "loadedmetadata", "volumechange", "seeked"]) v.addEventListener(ev, e.fire);
  return {
    kind: "video",
    element: v,
    get duration() {
      return Number.isFinite(v.duration) ? v.duration : 0;
    },
    getTime: () => v.currentTime,
    seek: (t) => {
      v.currentTime = Math.max(0, t);
    },
    play: () => void v.play().catch(() => {}),
    pause: () => v.pause(),
    isPlaying: () => !v.paused,
    setMuted: (m) => {
      v.muted = m;
    },
    isMuted: () => v.muted,
    subscribe: e.on,
    dispose: () => {
      v.pause();
      v.removeAttribute("src");
      v.load();
    },
  };
}

const W = 540;
const H = 960;

function drawFrame(ctx: CanvasRenderingContext2D, tl: Timeline | null, t: number) {
  const fps = 30;
  const f = t * fps;
  // Background: warm-graded "room" with a soft key light.
  const g = ctx.createLinearGradient(0, 0, W, H);
  g.addColorStop(0, "#3a2a2f");
  g.addColorStop(0.55, "#1f1a22");
  g.addColorStop(1, "#141018");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  const key = ctx.createRadialGradient(W * 0.72, H * 0.28, 10, W * 0.72, H * 0.28, W * 0.9);
  key.addColorStop(0, "rgba(255,200,160,0.35)");
  key.addColorStop(1, "rgba(255,200,160,0)");
  ctx.fillStyle = key;
  ctx.fillRect(0, 0, W, H);
  // Window light bars
  ctx.fillStyle = "rgba(255,230,200,0.05)";
  for (let i = 0; i < 3; i++) ctx.fillRect(W * 0.62 + i * 46, 80, 30, 360);

  // Punch-in: scale the "speaker" a little on clips with scale keyframes.
  const clip = tl?.video.find((c) => c.at_f <= f && f < c.at_f + c.dur_f);
  const punch = clip && clip.scale.length ? 1 + 0.18 * Math.min(1, Math.max(0, (f - clip.at_f - 18) / 6)) : 1;
  const breathe = Math.sin(t * 1.7) * 3;
  ctx.save();
  ctx.translate(W / 2, H * 0.62);
  ctx.scale(punch, punch);
  // Shoulders
  ctx.fillStyle = "#6b4a52";
  ctx.beginPath();
  ctx.ellipse(0, 250 + breathe, 210, 170, 0, Math.PI, 0);
  ctx.fill();
  // Neck + head
  ctx.fillStyle = "#c99a86";
  ctx.fillRect(-34, -10 + breathe, 68, 90);
  ctx.beginPath();
  ctx.ellipse(0, -90 + breathe, 92, 112, 0, 0, Math.PI * 2);
  ctx.fill();
  // Hair
  ctx.fillStyle = "#2a1c1c";
  ctx.beginPath();
  ctx.ellipse(0, -130 + breathe, 104, 92, 0, Math.PI, 0);
  ctx.fill();
  ctx.fillRect(-104, -130 + breathe, 30, 150);
  ctx.fillRect(74, -130 + breathe, 30, 150);
  ctx.restore();

  // Vignette (look)
  const vg = ctx.createRadialGradient(W / 2, H / 2, H * 0.25, W / 2, H / 2, H * 0.7);
  vg.addColorStop(0, "rgba(0,0,0,0)");
  vg.addColorStop(1, "rgba(0,0,0,0.55)");
  ctx.fillStyle = vg;
  ctx.fillRect(0, 0, W, H);

  // Hook title card (upper third)
  const title = tl?.titles.find((x) => x.start_f <= f && f < x.end_f);
  if (title) {
    ctx.font = "700 34px Inter, system-ui, sans-serif";
    const tw = Math.min(W - 60, ctx.measureText(title.text).width + 40);
    ctx.fillStyle = "rgba(255,255,255,0.94)";
    roundRect(ctx, (W - tw) / 2, 150, tw, 64, 14);
    ctx.fill();
    ctx.fillStyle = "#1b1320";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(title.text, W / 2, 183, W - 80);
  }

  // Keyword / CTA graphics
  const gfx = tl?.graphics.find((x) => x.start_f <= f && f < x.end_f);
  if (gfx) {
    ctx.font = "800 30px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const label = gfx.text.toUpperCase();
    const w = ctx.measureText(label).width + 44;
    ctx.fillStyle = "#FF5FA2";
    roundRect(ctx, (W - w) / 2, gfx.kind === "cta_card" ? H - 140 : 270, w, 56, 28);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.fillText(label, W / 2, gfx.kind === "cta_card" ? H - 112 : 298);
  }

  // Captions (editorial: beside the face, emphasis in brand pink)
  const page = tl?.captions?.pages.find((p) => p.start_f <= f && f < p.end_f);
  if (page) {
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const words = page.words;
    ctx.font = "700 40px Inter, system-ui, sans-serif";
    const widths = words.map((w) => ctx.measureText(w.text + " ").width);
    const total = widths.reduce((a, b) => a + b, 0);
    let x = W / 2 - total / 2;
    const y = H * 0.74;
    words.forEach((w, i) => {
      ctx.lineWidth = 6;
      ctx.strokeStyle = "rgba(0,0,0,0.55)";
      ctx.textAlign = "left";
      ctx.strokeText(w.text, x, y);
      ctx.fillStyle = w.emph ? "#FF5FA2" : "#FFFFFF";
      ctx.fillText(w.text, x, y);
      x += widths[i];
    });
  }

  // Film grain-ish noise
  ctx.fillStyle = "rgba(255,255,255,0.025)";
  for (let i = 0; i < 160; i++) ctx.fillRect(Math.random() * W, Math.random() * H, 1.5, 1.5);
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function createCanvasPlayer(tl: Timeline | null, fallbackDuration = 34): ReelPlayer {
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const ctx = c.getContext("2d");
  const duration = tl ? tl.duration_f / 30 : fallbackDuration;
  const e = emitter();
  let t = 0;
  let playing = false;
  let muted = true;
  let raf = 0;
  let last = 0;
  let lastEmit = 0;
  const draw = () => ctx && drawFrame(ctx, tl, t);
  const loop = (now: number) => {
    if (!playing) return;
    if (last) t = (t + (now - last) / 1000) % duration;
    last = now;
    draw();
    if (now - lastEmit > 100) (lastEmit = now), e.fire();
    raf = requestAnimationFrame(loop);
  };
  draw();
  return {
    kind: "canvas",
    element: c,
    duration,
    getTime: () => t,
    seek: (x) => {
      t = Math.max(0, Math.min(duration - 0.01, x));
      draw();
      e.fire();
    },
    play: () => {
      if (playing) return;
      playing = true;
      last = 0;
      raf = requestAnimationFrame(loop);
      e.fire();
    },
    pause: () => {
      playing = false;
      cancelAnimationFrame(raf);
      e.fire();
    },
    isPlaying: () => playing,
    setMuted: (m) => {
      muted = m;
      e.fire();
    },
    isMuted: () => muted,
    subscribe: e.on,
    dispose: () => {
      playing = false;
      cancelAnimationFrame(raf);
    },
  };
}

/** Create (and dispose) the player for a project; re-renders on time/play/mute changes. */
export function useReelPlayer(src: string | null, tl: Timeline | null): ReelPlayer {
  const player = useMemo(() => (src ? createVideoPlayer(src) : createCanvasPlayer(tl)), [src, tl]);
  useEffect(() => () => player.dispose(), [player]);
  const versionRef = useRef(0);
  useSyncExternalStore(
    (fn) =>
      player.subscribe(() => {
        versionRef.current++;
        fn();
      }),
    () => versionRef.current,
  );
  return player;
}

/** Re-render ~10×/s while playing (for scrubbers). */
export function usePlayerTime(p: ReelPlayer): number {
  const [t, setT] = useState(p.getTime());
  useEffect(() => p.subscribe(() => setT(p.getTime())), [p]);
  return t;
}
