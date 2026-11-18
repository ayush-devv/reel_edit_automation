// Motion graphics (finish.graphics → timeline.graphics). Normal-blend art only: the overlay is a
// straight-alpha layer, so nothing here relies on blend modes. Timings follow the bang-motion recipe
// numbers (MIT, Bang Tutorial), re-implemented with Remotion interpolate/Easing — no GSAP.
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Box, FaceSpan, Graphic, OverlayProps } from "./types";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
// GSAP power2/3/4 → cubic / quart / quint
const power2In = Easing.in(Easing.cubic);
const power3Out = Easing.out(Easing.poly(4));
const power4Out = Easing.out(Easing.poly(5));
const power2InOut = Easing.inOut(Easing.cubic);
const backOut = (s: number) => Easing.out(Easing.back(s));

const sec = (s: number, fps: number) => Math.max(1, Math.round(s * fps));
const tween = (f: number, start: number, len: number, ease: (t: number) => number) =>
  interpolate(f, [start, start + len], [0, 1], { ...clamp, easing: ease });

const TITLE_SHADOW = "0 4px 28px rgba(0,0,0,.5)";
const FONT = "Inter";

/** Exit: every graphic leaves over its last 0.3 s (outUp: power2.in). */
function exitK(f: number, g: Graphic, fps: number): number {
  return 1 - tween(f, g.end_f - sec(0.3, fps), sec(0.3, fps), power2In);
}

function faceAt(faces: FaceSpan[], f: number): Box | null {
  return faces.find((s) => f >= s.start_f && f < s.end_f)?.box ?? null;
}

/** Luminance of a #RRGGBB colour, 0–1 (for readable text on an accent fill). */
export function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const inkOn = (bg: string) => (luminance(bg) > 0.55 ? "#0B0D12" : "#FFFFFF");

/** Count-up formatting: Indian digit grouping for big numbers, one decimal if the target has one. */
export function formatCount(v: number, target: number): string {
  const dec = Number.isInteger(target) ? 0 : 1;
  return v.toLocaleString("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

// ------------------------------------------------------------------ emoji pop: back.out(2) pop, then a gentle float

const EmojiPop: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const local = f - g.start_f;
  const k = tween(local, 0, sec(0.4, p.fps), backOut(2));
  const t = local / p.fps;
  const floatY = Math.sin(t * Math.PI * 2 / 1.6) * 12;
  const rot = Math.sin(t * Math.PI * 2 / 2.1 + 1) * 4;
  const size = 170;
  const face = faceAt(p.faces, g.start_f);
  let left = p.width - p.safe.right - size - 30;
  let top = p.safe.top + 60;
  if (g.position === "upper_left") left = p.safe.left + 30;
  if (g.position === "beside_face" && face) {
    const right = (face.x + face.w) * p.width;
    left = right + size * 0.2 + size <= p.width - p.safe.right ? right + size * 0.2 : face.x * p.width - size * 1.2;
    top = Math.max(p.safe.top, face.y * p.height - size * 0.3);
  }
  const out = exitK(f, g, p.fps);
  if (!g.uri) return null;
  return (
    <Img src={g.uri} style={{ position: "absolute", left, top, width: size, height: size,
                              transform: `translateY(${floatY}px) rotate(${rot}deg) scale(${k * out})`,
                              filter: "drop-shadow(0 10px 18px rgba(0,0,0,.35))" }} />
  );
};

// ------------------------------------------------------------------ keyword card: per-word "say" + an emphasis mark

const KeywordCard: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const local = f - g.start_f;
  const words = g.text.split(/\s+/).filter(Boolean);
  const maxW = p.width - p.safe.left - p.safe.right - 40;
  const chars = Math.max(1, g.text.length);
  const size = Math.round(Math.min(124, maxW / (chars * 0.6)));
  const stagger = sec(0.09, p.fps);
  const lastIn = (words.length - 1) * stagger + sec(0.55, p.fps);
  const style = g.style || "pill";
  // filled marks (pill/box) carry dark text: the fill lands first, then the words; lines/markers follow the words
  const filled = style === "pill" || style === "box";
  const markK = filled ? tween(local, 0, sec(0.35, p.fps), power3Out) : tween(local, lastIn + sec(0.2, p.fps), sec(0.5, p.fps), power3Out);
  const wordDelay = filled ? sec(0.15, p.fps) : 0;
  const ink = style === "pill" || style === "box" ? inkOn(g.accent) : "#FFFFFF";
  const top = g.position === "center" ? 0.4 * p.height : p.safe.top + 90;
  const out = exitK(f, g, p.fps);
  const mark: React.CSSProperties = {
    position: "absolute", left: -18, right: -18, transformOrigin: "left center", transform: `scaleX(${markK})`, zIndex: -1, borderRadius: 14,
    ...(style === "pill" ? { top: -6, bottom: -6, background: g.accent, borderRadius: 999 } : {}),
    ...(style === "box" ? { top: -8, bottom: -8, background: g.accent } : {}),
    ...(style === "marker" ? { top: "52%", bottom: "4%", background: g.accent, opacity: 0.8, transform: `scaleX(${markK}) rotate(-1.5deg)` } : {}),
    ...(style === "under" ? { top: "96%", height: Math.max(8, size * 0.09), background: g.accent } : {}),
  };
  return (
    <div style={{ position: "absolute", top, left: 0, right: 0, display: "flex", justifyContent: "center", opacity: out,
                  transform: `translateY(${(1 - out) * -40}px)` }}>
      <div style={{ position: "relative", isolation: "isolate", padding: "0 10px" }}>
        {style !== "plain" ? <div style={mark} /> : null}
        <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: size, lineHeight: 1.05, color: ink, whiteSpace: "nowrap",
                      textShadow: style === "pill" || style === "box" ? undefined : TITLE_SHADOW }}>
          {words.map((w, i) => {
            const k = tween(local, wordDelay + i * stagger, sec(0.55, p.fps), power4Out);
            return (
              <span key={i} style={{ display: "inline-block", margin: `0 ${size * 0.12}px`, opacity: k,
                                     transform: `translateY(${(1 - k) * 60}%) scaleY(${1 + 0.25 * (1 - k)})`, transformOrigin: "bottom" }}>
                {w}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ lower third: block reveal (clip-path inset, power3.out)

const LowerThird: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const local = f - g.start_f;
  const k = tween(local, 0, sec(0.5, p.fps), power3Out);
  const k2 = tween(local, sec(0.15, p.fps), sec(0.5, p.fps), power3Out);
  const [name, ...rest] = g.text.split(/\s*[·|—-]\s*/);
  const role = rest.join(" · ");
  const out = exitK(f, g, p.fps);
  const bar = g.style !== "tag";
  return (
    <div style={{ position: "absolute", left: p.safe.left + 20, top: p.safe.top + 40, opacity: out, clipPath: `inset(0 ${(1 - k) * 100}% 0 0)` }}>
      <div style={{ display: "flex", alignItems: "stretch", background: bar ? "rgba(11,13,18,0.82)" : g.accent, borderRadius: bar ? 10 : 999,
                    padding: bar ? "16px 28px 16px 22px" : "12px 30px", borderLeft: bar ? `8px solid ${g.accent}` : undefined }}>
        <div style={{ fontFamily: FONT, color: bar ? "#FFFFFF" : inkOn(g.accent) }}>
          <div style={{ fontWeight: 800, fontSize: 60, lineHeight: 1.1 }}>{name}</div>
          {role ? <div style={{ fontWeight: 500, fontSize: 38, lineHeight: 1.2, opacity: 0.85 * k2, transform: `translateY(${(1 - k2) * 12}px)` }}>{role}</div> : null}
        </div>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ callout: a hand-drawn mark that draws itself (0.7 s, power2.inOut)

const Callout: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const local = f - g.start_f;
  const draw = tween(local, 0, sec(0.7, p.fps), power2InOut);
  const face = faceAt(p.faces, g.start_f);
  let cx = g.x * p.width;
  let cy = g.y * p.height;
  let rx = 150;
  let ry = 150;
  if (g.position === "face" && face) {
    cx = (face.x + face.w / 2) * p.width;
    cy = (face.y + face.h / 2) * p.height;
    rx = (face.w * p.width) / 2 * 1.35;
    ry = (face.h * p.height) / 2 * 1.3;
  } else if (g.position === "face") {
    cx = p.width / 2;
    cy = 0.35 * p.height;
  }
  const sw = 11;
  const style = g.style;
  let d = "";
  if (style === "circle") {  // slightly open, slightly tilted: reads as drawn by hand
    d = `M ${cx + rx} ${cy} A ${rx} ${ry} 0 1 1 ${cx + rx * 0.96} ${cy - ry * 0.28}`;
  } else if (style === "box") {
    d = `M ${cx - rx} ${cy - ry} L ${cx + rx} ${cy - ry} L ${cx + rx} ${cy + ry} L ${cx - rx} ${cy + ry} Z`;
  } else if (style === "underline") {
    d = `M ${cx - rx} ${cy + ry} Q ${cx} ${cy + ry + 18} ${cx + rx} ${cy + ry - 6}`;
  } else {  // arrow from upper-right towards the point
    const sx = Math.min(p.width - p.safe.right - 20, cx + 260), sy = Math.max(p.safe.top + 40, cy - 300);
    const ex = cx + 40, ey = cy - 40;
    const a = Math.atan2(ey - sy, ex - sx), h = 46;
    d = `M ${sx} ${sy} Q ${(sx + ex) / 2 + 60} ${(sy + ey) / 2} ${ex} ${ey} M ${ex - h * Math.cos(a - 0.5)} ${ey - h * Math.sin(a - 0.5)} L ${ex} ${ey} L ${ex - h * Math.cos(a + 0.5)} ${ey - h * Math.sin(a + 0.5)}`;
  }
  const out = exitK(f, g, p.fps);
  const labelK = tween(local, sec(0.5, p.fps), sec(0.4, p.fps), power3Out);
  const labelTop = Math.min(cy + ry + 30, p.height - p.safe.bottom - 90);
  return (
    <AbsoluteFill style={{ opacity: out }}>
      <svg width={p.width} height={p.height} style={{ position: "absolute", inset: 0, transform: `rotate(${style === "circle" ? -3 : 0}deg)`,
                                                       transformOrigin: `${cx}px ${cy}px` }}>
        <path d={d} pathLength={1} fill="none" stroke={g.accent} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"
              strokeDasharray={1} strokeDashoffset={1 - draw} style={{ filter: "drop-shadow(0 3px 6px rgba(0,0,0,.4))" }} />
      </svg>
      {g.text ? (
        <div style={{ position: "absolute", top: labelTop, left: 0, right: 0, textAlign: "center", opacity: labelK }}>
          <span style={{ fontFamily: FONT, fontWeight: 800, fontSize: 48, color: inkOn(g.accent), background: g.accent, padding: "6px 18px",
                         borderRadius: 12 }}>{g.text}</span>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ counter: counts up (1.2 s, ease-out) on tabular figures

const Counter: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const local = f - g.start_f;
  const pop = tween(local, 0, sec(0.35, p.fps), backOut(1.6));
  const k = tween(local, sec(0.1, p.fps), sec(1.2, p.fps), Easing.out(Easing.cubic));
  const v = g.value * k;
  const shown = Number.isInteger(g.value) ? Math.round(v) : Math.round(v * 10) / 10;
  const [pre, post] = g.text.split("{n}");
  const out = exitK(f, g, p.fps);
  const top = g.position === "center" ? 0.4 * p.height : p.safe.top + 80;
  return (
    <div style={{ position: "absolute", top, left: 0, right: 0, textAlign: "center", opacity: out, transform: `scale(${0.6 + 0.4 * pop})` }}>
      <span style={{ fontFamily: FONT, fontWeight: 900, fontSize: 150, color: "#FFFFFF", textShadow: TITLE_SHADOW, fontVariantNumeric: "tabular-nums" }}>
        {pre}<span style={{ color: g.accent }}>{formatCount(shown, g.value)}</span>{post}
      </span>
    </div>
  );
};

// ------------------------------------------------------------------ text card: full-screen, wipe in, words rise (inUp), slow push

const TextCard: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const local = f - g.start_f;
  const dur = g.end_f - g.start_f;
  const wipe = tween(local, 0, sec(0.35, p.fps), power3Out);
  const leave = tween(f, g.end_f - sec(0.3, p.fps), sec(0.3, p.fps), power2In);
  const bg = g.style === "light" ? "#F4EFE6" : g.style === "color" ? g.accent : "#0B0D12";
  const ink = inkOn(bg);
  const words = g.text.split(/\s+/).filter(Boolean);
  const maxW = p.width - p.safe.left - p.safe.right - 40;
  const longest = Math.max(...words.map((w) => w.length), 1);
  const size = Math.round(Math.min(140, maxW / (longest * 0.62)));
  const breathe = 1 + 0.04 * interpolate(local, [0, dur], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ background: bg, clipPath: `inset(${(1 - wipe) * 100}% 0 0 0)`, transform: `translateY(${-leave * 100}%)`,
                           display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ maxWidth: maxW, textAlign: "center", fontFamily: FONT, fontWeight: 800, fontSize: size, lineHeight: 1.08, color: ink,
                    transform: `scale(${breathe})`, textWrap: "balance" }}>
        {words.map((w, i) => {
          const k = tween(local, sec(0.2, p.fps) + i * sec(0.08, p.fps), sec(0.6, p.fps), power4Out);
          return (
            <span key={i} style={{ display: "inline-block", margin: `0 ${size * 0.13}px`, opacity: k, transform: `translateY(${(1 - k) * 60}%)`,
                                   filter: `blur(${(1 - k) * 12}px)` }}>{w}</span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ CTA: slam in (scale 2.2 → 1), then a soft pulse

const CtaCard: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const local = f - g.start_f;
  const slam = tween(local, 0, sec(0.26, p.fps), Easing.in(Easing.poly(5)));
  const scale = 2.2 - 1.2 * slam;
  const pulse = local > sec(0.6, p.fps) ? 1 + 0.03 * Math.sin(((local - sec(0.6, p.fps)) / p.fps) * Math.PI * 2 / 1.4) : 1;
  const card = g.style === "card";
  const top = card ? 0.42 * p.height : p.safe.top + 60;
  return (
    <div style={{ position: "absolute", top, left: 0, right: 0, display: "flex", justifyContent: "center", opacity: Math.min(1, slam * 3) }}>
      <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: card ? 76 : 58, color: inkOn(g.accent), background: g.accent,
                    padding: card ? "34px 54px" : "18px 40px", borderRadius: card ? 36 : 999, transform: `scale(${scale * pulse})`,
                    boxShadow: "0 14px 40px rgba(0,0,0,.35)", maxWidth: p.width - p.safe.left - p.safe.right, textAlign: "center", textWrap: "balance" }}>
        {g.text}
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ whole-reel: progress bar, logo watermark

const ProgressBar: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const k = interpolate(f, [g.start_f, g.end_f - 1], [0, 1], clamp);
  return <div style={{ position: "absolute", left: 0, top: 0, height: 10, width: `${k * 100}%`, background: g.accent, boxShadow: "0 0 10px rgba(0,0,0,.3)" }} />;
};

const Logo: React.FC<{ g: Graphic; p: OverlayProps }> = ({ g, p }) => {
  const f = useCurrentFrame();
  const k = tween(f, g.start_f, sec(0.5, p.fps), power3Out);
  const right = g.position !== "top_left";
  return (
    <Img src={staticFile(g.uri)} style={{ position: "absolute", top: p.safe.top - 60, width: 140, opacity: 0.85 * k,
                                           ...(right ? { right: p.safe.right } : { left: p.safe.left }) }} />
  );
};

// ------------------------------------------------------------------ dispatch

const KINDS: Record<string, React.FC<{ g: Graphic; p: OverlayProps }>> = {
  emoji_pop: EmojiPop, keyword_card: KeywordCard, lower_third: LowerThird, callout: Callout, counter: Counter,
  text_card: TextCard, cta_card: CtaCard, progress_bar: ProgressBar, logo_watermark: Logo,
};

/** Full-screen cards sit under the captions; everything else over them. */
export const FULLSCREEN = new Set(["text_card"]);

export const Graphics: React.FC<{ graphics: Graphic[]; p: OverlayProps; layer: "under" | "over" }> = ({ graphics, p, layer }) => {
  const f = useCurrentFrame();
  const live = graphics.filter((g) => f >= g.start_f && f < g.end_f && FULLSCREEN.has(g.kind) === (layer === "under"));
  return (
    <>
      {live.map((g) => {
        const C = KINDS[g.kind];
        return C ? <C key={g.id} g={g} p={p} /> : null;
      })}
    </>
  );
};
