// Design tokens: the "Cutting Room" system (docs/product/design-audit.md §4, Penpot token set `cutting-room`).
// The single source for Tailwind and the 3D scenes.
// Colour means a signal: amber = your move / you are here, violet = the AI is working, status colours = state.
// Everything else is graphite.
export const color = {
  bg: {
    base: "#0F1012", // bg/app
    raised: "#16171A", // surface/1
    overlay: "#1D1F23", // surface/2
    high: "#26282D", // surface/3
    inset: "#08090A", // bg/well, behind footage
  },
  line: { subtle: "#2A2D32", strong: "#3A3E45", control: "#666A72" },
  text: { primary: "#ECEDEE", secondary: "#A9ACB2", muted: "#90949C", disabled: "#5C6067" },
  signal: { DEFAULT: "#E8A33D", hover: "#F0B458", pressed: "#CC8A28", on: "#1A1305" },
  accent: {
    /** AI working: the running stage, Editor messages, a live render. Never a button. */
    ai: "#9B8CFF",
    glow: "#9B8CFF",
    /** Information and timecode links. */
    info: "#6EA2E0",
  },
  status: { sendable: "#3CCB7F", hold: "#E8A33D", fail: "#F5606C", queued: "#90949C", info: "#6EA2E0" },
  layer: {
    video: "#6F8FC6",
    colour: "#C58AA8",
    punch: "#6DB2B7",
    broll: "#74AF8C",
    captions: "#CBB35C",
    titles: "#C98B60",
  },
} as const;

export const motion = {
  hover: 120,
  panel: 200,
  screen: 400,
  explode: 600,
  ease: "cubic-bezier(0.2, 0, 0, 1)",
} as const;
