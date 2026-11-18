// Design tokens from docs/product/design-system.md — the single source for Tailwind and the 3D scenes.
export const color = {
  bg: { base: "#0B0D12", raised: "#12151C", overlay: "#1A1E27", inset: "#07080C" },
  line: { subtle: "#232836", strong: "#343B4D" },
  text: { primary: "#E8EAF0", secondary: "#A3A9B8", muted: "#858C9E" },
  accent: { ai: "#6A4BF0", glow: "#9D85FF", cyan: "#36D6E7" },
  status: { sendable: "#2BD47D", hold: "#FFB020", fail: "#FF4D5E", queued: "#858C9E" },
  layer: {
    video: "#4C8DFF",
    colour: "#FF7AB6",
    punch: "#36D6E7",
    broll: "#2BD47D",
    captions: "#FFD400",
    titles: "#FF8A3D",
  },
} as const;

export const motion = {
  hover: 120,
  panel: 200,
  screen: 400,
  explode: 600,
  ease: "cubic-bezier(0.2, 0, 0, 1)",
} as const;
