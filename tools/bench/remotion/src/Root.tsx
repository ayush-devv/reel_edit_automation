import React from "react";
import {
  AbsoluteFill,
  Composition,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FPS = 30;
const DURATION = 1800; // 60 s

// Synthetic word track: one word every ~0.33 s, like dense talking-head speech.
const WORDS = "the one trick nobody tells you about saving money is simple put ten percent away on salary day and never touch it".split(" ");
const words = Array.from({ length: 180 }, (_, i) => ({
  text: WORDS[i % WORDS.length],
  start: i * 10,
  end: i * 10 + 10,
  emph: i % 7 === 3,
}));

// Punch-in windows (frames) and cut points for flash transitions.
const PUNCHES = [
  { from: 60, to: 150 },
  { from: 420, to: 520 },
  { from: 900, to: 1000 },
  { from: 1400, to: 1500 },
];
const CUTS = [300, 540, 780, 1140, 1440];

const Base: React.FC = () => {
  const frame = useCurrentFrame();
  let scale = 1;
  for (const p of PUNCHES) {
    if (frame >= p.from && frame < p.to) {
      scale = interpolate(frame, [p.from, p.from + 8], [1, 1.18], {
        extrapolateRight: "clamp",
      });
    }
  }
  return (
    <AbsoluteFill style={{ transform: `scale(${scale})` }}>
      <OffthreadVideo src={staticFile("base.mp4")} muted />
    </AbsoluteFill>
  );
};

const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const groupStart = Math.floor(frame / 30) * 30; // 3 words per page
  const page = words.filter((w) => w.start >= groupStart && w.start < groupStart + 30);
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 700 }}>
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", justifyContent: "center", maxWidth: 900 }}>
        {page.map((w) => {
          const active = frame >= w.start && frame < w.end;
          const pop = spring({ frame: frame - w.start, fps, config: { damping: 12 } });
          return (
            <span
              key={w.start}
              style={{
                fontFamily: "Arial Black, Helvetica, sans-serif",
                fontWeight: 900,
                fontSize: 86,
                textTransform: "uppercase",
                color: active ? (w.emph ? "#FFD400" : "#FFFFFF") : "rgba(255,255,255,0.85)",
                transform: `scale(${active ? 0.8 + 0.25 * pop : 1})`,
                textShadow: "0 6px 18px rgba(0,0,0,0.6)",
                WebkitTextStroke: "3px #000",
                padding: "0 6px",
                background: active && w.emph ? "rgba(0,0,0,0.35)" : "transparent",
                borderRadius: 12,
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Flashes: React.FC = () => {
  const frame = useCurrentFrame();
  let opacity = 0;
  for (const c of CUTS) {
    opacity = Math.max(
      opacity,
      interpolate(frame, [c - 3, c, c + 6], [0, 0.8, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    );
  }
  return <AbsoluteFill style={{ backgroundColor: "white", opacity }} />;
};

const HookTitle: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (frame > 75) return null;
  const s = spring({ frame, fps, config: { damping: 10 } });
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: 320 }}>
      <div
        style={{
          transform: `scale(${s})`,
          background: "#FFD400",
          color: "#111",
          fontFamily: "Arial Black, Helvetica, sans-serif",
          fontSize: 72,
          fontWeight: 900,
          padding: "18px 32px",
          borderRadius: 18,
        }}
      >
        SAVE 10% EVERY MONTH
      </div>
    </AbsoluteFill>
  );
};

export const Reel: React.FC<{ noBase?: boolean }> = ({ noBase }) => (
  <AbsoluteFill style={{ backgroundColor: noBase ? "transparent" : "black" }}>
    {noBase ? null : <Base />}
    <Flashes />
    <HookTitle />
    <Captions />
  </AbsoluteFill>
);

export const Root: React.FC = () => (
  <Composition
    id="Reel"
    component={Reel}
    durationInFrames={DURATION}
    fps={FPS}
    width={1080}
    height={1920}
    defaultProps={{ noBase: false }}
  />
);
