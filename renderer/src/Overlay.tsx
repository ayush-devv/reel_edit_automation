import React, { useEffect, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, interpolate, spring, useCurrentFrame } from "remotion";
import { Box, CaptionPage, CaptionTrack, CaptionWord, FaceSpan, Flash, OverlayProps, Title } from "./types";

// ------------------------------------------------------------------ tokens

const BUNDLED = ["Inter", "Plus Jakarta Sans"];

export function fontFamily(token: string | undefined): string {
  const name = (token || "Inter").replace(/ (Black|ExtraBold|SemiBold|Bold|Medium|Regular|Light|Thin)$/i, "").trim();
  return BUNDLED.includes(name) ? name : "Inter";
}

const truthy = (v: string | undefined) => v === "true" || v === "1";
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
  return Math.round(Math.max(base * 0.62, Math.min(base, fit)));
}

/** Move a horizontal band [top, top+h] (px) off any text box; prefer moving `dir` (-1 up, +1 down). */
export function clearOf(top: number, h: number, boxes: Box[], H: number, dir: number, minTop: number, maxBottom: number): number {
  let t = top;
  for (let pass = 0; pass < 4; pass++) {
    const hit = boxes.find((b) => t < (b.y + b.h) * H && b.y * H < t + h);
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
  const t = track.tokens;
  const sentence = t.case === "sentence";
  const words = displayWords(page.words, sentence);
  const heavy = num(t.weight, 700) >= 800;
  const upperHeavy = heavy || t.case === "upper";
  const boxed0 = truthy(t.box);
  const maxW = p.width - p.safe.left - p.safe.right - (boxed0 ? 52 : 0) - 20;
  const chars = words.reduce((n, w) => n + w.text.length + 1, -1);
  const size = fitSize(upperHeavy ? 88 : 66, chars, maxW, upperHeavy);
  const animF = Math.max(1, Math.round((num(t.anim_ms, 150) / 1000) * p.fps));
  const local = frame - page.start_f;
  const pageIn = interpolate(local, [0, animF], [0, 1], { extrapolateRight: "clamp" });
  const pageOut = interpolate(frame, [page.end_f - 3, page.end_f], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const base = t.base_color || t.speaker_a || "#FFFFFF";
  const emph = t.emph_color || base;
  const stroke = truthy(t.stroke);
  const boxed = truthy(t.box);
  const blockH = size * 1.15 + (boxed ? 28 : 0) + 16;
  const y0 = zoneCentreY(t.zone, face, p.height, p.safe.bottom) - blockH / 2;
  const top = clearOf(y0, blockH, span?.text ?? [], p.height, -1, 0.45 * p.height, p.height - p.safe.bottom);

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
          WebkitTextStroke: stroke ? `${Math.round(size * 0.11)}px #000` : undefined,
          paintOrder: "stroke fill",
          textShadow: stroke || boxed ? undefined : "0 4px 16px rgba(0,0,0,0.55)",
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
            whiteSpace: "nowrap",
            padding: boxed ? "14px 26px" : 0,
            borderRadius: boxed ? 18 : 0,
            background: boxed ? t.box_color || "#000000B3" : "transparent",
          }}
        >
          {wordEls}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ hook title

const Titles: React.FC<{ titles: Title[]; tokens: Record<string, string>; p: OverlayProps }> = ({ titles, tokens, p }) => {
  const frame = useCurrentFrame();
  const title = titles.find((x) => frame >= x.start_f && frame < x.end_f);
  if (!title) return null;
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

// ------------------------------------------------------------------ root

function useFonts(tokens: Record<string, string>) {
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    const fam = fontFamily(tokens.font);
    const specs = [`${num(tokens.weight, 700)} 80px "${fam}"`, `800 80px "${fam}"`];
    Promise.all(specs.map((s) => document.fonts.load(s)))
      .then(() => document.fonts.ready)
      .then(() => continueRender(handle))
      .catch(() => continueRender(handle));
  }, [handle, tokens.font, tokens.weight]);
}

export const Overlay: React.FC<OverlayProps> = (p) => {
  const tokens = p.captions?.tokens ?? {};
  useFonts(tokens);
  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      {p.captions ? <Captions track={p.captions} p={p} /> : null}
      <Titles titles={p.titles} tokens={tokens} p={p} />
      <Flashes flashes={p.flashes} />
    </AbsoluteFill>
  );
};
