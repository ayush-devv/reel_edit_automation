import React, { useEffect, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, interpolate, OffthreadVideo, Sequence, spring, staticFile, useCurrentFrame } from "remotion";
import { Graphics } from "./Graphics";
import { Box, CaptionPage, CaptionTrack, CaptionWord, FaceSpan, Flash, OverlayProps, Pip, Title } from "./types";

// ------------------------------------------------------------------ tokens

const BUNDLED = ["Inter", "Plus Jakarta Sans"];

export function fontFamily(token: string | undefined): string {
  const name = (token || "Inter").replace(/ (Black|ExtraBold|SemiBold|Bold|Medium|Regular|Light|Thin)$/i, "").trim();
  return BUNDLED.includes(name) ? name : "Inter";
}

const truthy = (v: string | undefined) => v === "true" || v === "1" || isColour(v);
const isColour = (v: string | undefined) => !!v && /^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(v);
// stroke / box tokens: "true" (default colour) or a hex colour
const colourOf = (v: string | undefined, d: string) => (isColour(v) ? (v as string) : d);
const num = (v: string | undefined, d: number) => (v !== undefined && !isNaN(Number(v)) ? Number(v) : d);

function textTransform(c: string | undefined): React.CSSProperties["textTransform"] {
  return c === "upper" ? "uppercase" : c === "lower" ? "lowercase" : c === "title" ? "capitalize" : "none";
}

// Punctuation-only tokens ("%", "—") attach to the previous word; trailing . , ; : are dropped
// unless the family is sentence case (then the page reads as a sentence).
export function displayWords(words: CaptionWord[], keepPunct: boolean): CaptionWord[] {
  const out: CaptionWord[] = [];
  for (const w of words) {
    if (/^[^\p{L}\p{N}]+$/u.test(w.text) && out.length) {
      const prev = out[out.length - 1];
      out[out.length - 1] = { ...prev, text: prev.text + w.text, end_f: w.end_f, emph: prev.emph || w.emph };
      continue;
    }
    out.push({ ...w });
  }
  return keepPunct ? out : out.map((w) => ({ ...w, text: w.text.replace(/[.,;:]+$/u, "") }));
}

// ------------------------------------------------------------------ layout

// Approximate advance width per character in em (layout must be deterministic, so no DOM measuring).
const CHAR_EM = (upperHeavy: boolean) => (upperHeavy ? 0.68 : 0.54);

/** Largest font size (≤ base, ≥ 62 % of base) that keeps `chars` on one line of `maxW` px. */
export function fitSize(base: number, chars: number, maxW: number, upperHeavy: boolean): number {
  const fit = maxW / Math.max(1, chars * CHAR_EM(upperHeavy));
  return Math.round(Math.max(base * 0.85, Math.min(base, fit))); // near-constant size: long lines are re-paged upstream, not shrunk
}

/** Move a block [top, top+h] × [x0, x1] (px) off any text box it actually overlaps; prefer moving `dir` (-1 up, +1 down). */
export function clearOf(top: number, h: number, boxes: Box[], H: number, dir: number, minTop: number, maxBottom: number,
                        x0 = -Infinity, x1 = Infinity, W = 1): number {
  let t = top;
  for (let pass = 0; pass < 4; pass++) {
    const hit = boxes.find((b) => t < (b.y + b.h) * H && b.y * H < t + h && x0 < (b.x + b.w) * W && b.x * W < x1);
    if (!hit) break;
    t = dir > 0 ? (hit.y + hit.h) * H + 24 : hit.y * H - h - 24;
  }
  return Math.min(Math.max(t, minTop), maxBottom - h);
}

function zoneCentreY(zone: string | undefined, face: Box | null, H: number, safeBottom: number): number {
  const maxY = H - safeBottom - 120;
  if (zone === "beside_face" && face) return Math.min(Math.max((face.y + face.h) * H + 150, 0.5 * H), maxY);
  if (zone === "lower_third") return Math.min(0.72 * H, maxY);
  return Math.min(0.64 * H, maxY); // lower_middle
}

// ------------------------------------------------------------------ captions

function spanAt(faces: FaceSpan[], f: number): FaceSpan | undefined {
  return faces.find((s) => f >= s.start_f && f < s.end_f);
}

const Captions: React.FC<{ track: CaptionTrack; p: OverlayProps }> = ({ track, p }) => {
  const frame = useCurrentFrame();
  const page: CaptionPage | undefined = track.pages.find((pg) => frame >= pg.start_f && frame < pg.end_f);
  if (!page) return null;
  const span = spanAt(p.faces, page.start_f);
  const face = span?.box ?? null;
  const phrase = track.timing === "phrase";
  // phrase fallback: no per-word highlight / pop / reveal — the page fades in as a unit
  const t = phrase ? { ...track.tokens, highlight: "none", anim: "fade" } : track.tokens;
  const sentence = t.case === "sentence";
  const words = displayWords(page.words, sentence);
  const heavy = num(t.weight, 700) >= 800;
  const upperHeavy = heavy || t.case === "upper";
  const boxed0 = truthy(t.box);
  const maxW = p.width - p.safe.left - p.safe.right - (boxed0 ? 52 : 0) - 20;
  const chars = words.reduce((n, w) => n + w.text.length + 1, -1);
  // mirrors compile.page_char_budget: pages longer than one line's budget are laid out on two lines
  const lineBudget = t.case === "upper" ? 14 : heavy ? 16 : 20;
  const lines = chars > lineBudget ? 2 : 1;
  const size = fitSize(upperHeavy ? 88 : 66, Math.ceil(chars / lines), maxW, upperHeavy);
  const animF = Math.max(1, Math.round((num(t.anim_ms, 150) / 1000) * p.fps));
  const local = frame - page.start_f;
  const pageIn = interpolate(local, [0, animF], [0, 1], { extrapolateRight: "clamp" });
  // fade out only at a real gap or the end — back-to-back pages must not dim into a grey "ghost"
  const next = track.pages.find((pg) => pg.start_f >= page.end_f);
  const backToBack = !!next && next.start_f - page.end_f <= 1;
  const pageOut = backToBack ? 1 : interpolate(frame, [page.end_f - 3, page.end_f], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const base = t.base_color || t.speaker_a || "#FFFFFF";
  const emph = t.emph_color || base;
  const stroke = truthy(t.stroke);
  const boxed = truthy(t.box);
  const blockH = size * 1.15 * lines + (boxed ? 28 : 0) + 16;
  // one caption line for the whole reel, below the speakers' chins (robust: 75th percentile, so one odd detection can't move it)
  const chins = p.faces.filter((f) => f.box).map((f) => (f.box!.y + f.box!.h) * p.height).sort((a, b) => a - b);
  const chin = chins.length ? chins[Math.min(chins.length - 1, Math.floor(chins.length * 0.75))] : 0;
  // pro reference (official DOAC Short of the same footage): ONE fixed line at ~66 % for the whole reel,
  // never moved per shot; pushed lower only for low chins, and never below 70 % (platform UI zone)
  const lineCentre = Math.min(Math.max(zoneCentreY(t.zone, null, p.height, p.safe.bottom), chin + blockH / 2 + 30), 0.70 * p.height);
  const y0 = Math.min(lineCentre, p.height - p.safe.bottom - blockH / 2) - blockH / 2;
  const textW = Math.min(p.width - p.safe.left - p.safe.right, chars * size * CHAR_EM(upperHeavy) + size * 0.6);
  const top = clearOf(y0, blockH, span?.text ?? [], p.height, +1, 0.45 * p.height, p.height - p.safe.bottom,
                    (p.width - textW) / 2, (p.width + textW) / 2, p.width);
  const wordEls = words.map((w) => {
    const active = frame >= w.start_f && frame < w.end_f;
    const since = frame - w.start_f;
    let scale = 1;
    let opacity = 1;
    let dy = 0;
    let color = w.emph ? emph : base;
    if (t.anim === "pop") {
      if (active) scale = 0.85 + 0.2 * spring({ frame: since, fps: p.fps, config: { damping: 12, stiffness: 220 } });
    } else if (t.anim === "slide_fade") {
      const k = interpolate(since, [0, animF], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
      opacity = k;
      dy = (1 - k) * 24;
    }
    if (t.highlight === "word") {
      color = active ? emph : w.emph ? emph : base;
      if (!active && frame < w.start_f) opacity *= 0.9;
    }
    const emphScale = (t.highlight === "scale" || t.highlight === "word") && w.emph ? (t.highlight === "scale" ? num(t.emph_scale, 1.4) : 1.08) : 1;
    scale *= emphScale;
    // transforms do not take layout space: widen the gap by the emphasised growth
    const extra = (size * (emphScale - 1) * Math.max(3, w.text.length) * CHAR_EM(upperHeavy)) / 2;
    return (
      <span
        key={w.i}
        style={{
          display: "inline-block",
          margin: `0 ${size * 0.16 + extra}px`,
          color,
          opacity,
          transform: `translateY(${dy}px) scale(${scale})`,
          WebkitTextStroke: stroke ? `${Math.round(size * 0.11)}px ${colourOf(t.stroke, "#000000")}` : undefined,
          paintOrder: "stroke fill",
          textShadow: stroke || boxed ? undefined : "0 0 3px rgba(0,0,0,0.95), 0 2px 4px rgba(0,0,0,0.9), 0 6px 18px rgba(0,0,0,0.6)",
        }}
      >
        {w.text}
      </span>
    );
  });

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: p.safe.left,
          right: p.safe.right,
          top,
          height: blockH,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          opacity: (t.anim === "fade" || t.anim === "slide_fade" ? pageIn : 1) * pageOut,
        }}
      >
        <div
          style={{
            fontFamily: fontFamily(t.font),
            fontWeight: num(t.weight, 700),
            fontSize: size,
            lineHeight: 1.15,
            textTransform: textTransform(t.case),
            textAlign: "center",
            whiteSpace: lines > 1 ? "normal" : "nowrap",
            textWrap: "balance",
            maxWidth: maxW,
            padding: boxed ? "14px 26px" : 0,
            borderRadius: boxed ? 18 : 0,
            background: boxed ? t.box_color || colourOf(t.box, "#000000B3") : "transparent",
          }}
        >
          {wordEls}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ hook title

const BehindTitle: React.FC<{ title: Title; tokens: Record<string, string>; p: OverlayProps }> = ({ title, tokens, p }) => {
  const frame = useCurrentFrame();
  const k = spring({ frame: frame - title.start_f, fps: p.fps, config: { damping: 18, stiffness: 120 } });
  const out = interpolate(frame, [title.end_f - 8, title.end_f], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const face = spanAt(p.faces, title.start_f)?.box;
  const maxW = p.width - p.safe.left - p.safe.right;
  const size = fitSize(220, title.text.length, maxW, true);
  // the head should overlap the lower part of the text: centre the text a little above the face top
  const centre = face ? Math.max(p.safe.top + size, (face.y + face.h * 0.15) * p.height) : p.height * 0.32;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: p.safe.left, right: p.safe.right, top: centre - size * 0.6, display: "flex", justifyContent: "center",
                    opacity: k * out, transform: `translateY(${(1 - k) * 40}px)` }}>
        <div style={{ fontFamily: fontFamily(tokens.font), fontWeight: 900, fontSize: size, lineHeight: 0.95, textTransform: "uppercase",
                      textAlign: "center", color: tokens.emph_color || tokens.base_color || "#FFFFFF", letterSpacing: -2, whiteSpace: "nowrap" }}>
          {title.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Titles: React.FC<{ titles: Title[]; tokens: Record<string, string>; p: OverlayProps }> = ({ titles, tokens, p }) => {
  const frame = useCurrentFrame();
  const title = titles.find((x) => frame >= x.start_f && frame < x.end_f);
  if (!title) return null;
  if (title.layer === "behind") return <BehindTitle title={title} tokens={tokens} p={p} />;
  const k = spring({ frame: frame - title.start_f, fps: p.fps, config: { damping: 14, stiffness: 200 } });
  const size = 70;
  const maxW = p.width - p.safe.left - p.safe.right;
  const lines = Math.ceil((title.text.length * size * CHAR_EM(false)) / (maxW - 60));
  const h = lines * size * 1.12 + 36;
  const top = clearOf(p.safe.top + 70, h, spanAt(p.faces, title.start_f)?.text ?? [], p.height, +1, p.safe.top, 0.5 * p.height);
  const out = interpolate(frame, [title.end_f - 6, title.end_f], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", top, left: p.safe.left, right: p.safe.right, display: "flex", justifyContent: "center" }}>
        <div
          style={{
            fontFamily: fontFamily(tokens.font),
            fontWeight: 800,
            fontSize: size,
            textWrap: "balance",
            lineHeight: 1.12,
            textAlign: "center",
            color: tokens.base_color || "#FFFFFF",
            background: "rgba(0,0,0,0.6)",
            padding: "18px 30px",
            borderRadius: 22,
            maxWidth: maxW,
            opacity: k * out,
            transform: `scale(${0.9 + 0.1 * k})`,
          }}
        >
          {title.text}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ flashes

const Flashes: React.FC<{ flashes: Flash[] }> = ({ flashes }) => {
  const frame = useCurrentFrame();
  const f = flashes.find((x) => Math.abs(frame - x.at_f) <= x.frames / 2);
  if (!f) return null;
  const opacity = Math.max(0, 1 - Math.abs(frame - f.at_f) / Math.max(1, f.frames / 2));
  return <AbsoluteFill style={{ backgroundColor: "#FFFFFF", opacity }} />;
};

// ------------------------------------------------------------------ picture-in-picture b-roll

const PipCard: React.FC<{ pip: Pip; p: OverlayProps }> = ({ pip, p }) => {
  const frame = useCurrentFrame(); // local to the Sequence
  const dur = pip.end_f - pip.start_f;
  const k = spring({ frame, fps: p.fps, config: { damping: 15, stiffness: 180 } });
  const out = interpolate(frame, [dur - 6, dur], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const w = Math.round(p.width * 0.42);
  const h = Math.round(w * 4 / 3);
  const left = pip.corner.endsWith("left") ? p.safe.left + 20 : p.width - p.safe.right - w - 20;
  const top = pip.corner.startsWith("bottom") ? p.height - p.safe.bottom - h - 20 : p.safe.top + 40;
  return (
    <div style={{ position: "absolute", left, top, width: w, height: h, borderRadius: 28, overflow: "hidden",
                  boxShadow: "0 18px 50px rgba(0,0,0,0.45)", border: "5px solid rgba(255,255,255,0.92)",
                  opacity: k * out, transform: `scale(${0.85 + 0.15 * k})` }}>
      <OffthreadVideo src={staticFile(pip.uri)} startFrom={Math.round((pip.src_in_us / 1e6) * p.fps)} muted
                      style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </div>
  );
};

// ------------------------------------------------------------------ root

function useFonts(tokens: Record<string, string>) {
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    const fam = fontFamily(tokens.font);
    const specs = [`${num(tokens.weight, 700)} 80px "${fam}"`, `800 80px "${fam}"`, `900 80px "Inter"`, `500 80px "Inter"`];
    Promise.all(specs.map((s) => document.fonts.load(s)))
      .then(() => document.fonts.ready)
      .then(() => continueRender(handle))
      .catch(() => continueRender(handle));
  }, [handle, tokens.font, tokens.weight]);
}

export const Overlay: React.FC<OverlayProps> = (p) => {
  const tokens = p.captions?.tokens ?? {};
  const graphics = p.graphics ?? [];
  useFonts(tokens);
  const behind = p.layer === "behind";
  const titles = p.titles.filter((t) => (t.layer === "behind") === behind);
  if (behind) {
    return (
      <AbsoluteFill style={{ backgroundColor: "transparent" }}>
        <Titles titles={titles} tokens={tokens} p={p} />
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      <Graphics graphics={graphics} p={p} layer="under" />
      {p.captions ? <Captions track={p.captions} p={p} /> : null}
      <Titles titles={titles} tokens={tokens} p={p} />
      <Graphics graphics={graphics} p={p} layer="over" />
      {(p.pips ?? []).map((pip) => (
        <Sequence key={pip.id} from={pip.start_f} durationInFrames={pip.end_f - pip.start_f}>
          <PipCard pip={pip} p={p} />
        </Sequence>
      ))}
      <Flashes flashes={p.flashes} />
    </AbsoluteFill>
  );
};
