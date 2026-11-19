// Design tokens: "Cinematic studio" (Cutting Room layout + a colour story). The single source for Tailwind and 3D.
//
// Colour theory: a cool blue-graphite base (hue ~220°) so warm light reads warm; a near-complementary pair as the
// two working accents (amber ~38° = act / you are here, teal ~174° = live / links / highlights), and violet
// (~252°, forming a triad with them) reserved for the AI working. Status colours keep their universal meanings.
// Every text colour is ≥ 4.6:1 on every surface; control borders ≥ 3:1 (checked with a WCAG script).
export const color = {
  bg: {
    base: "#0B0E14", // app background, deep blue-graphite
    raised: "#121722", // panels, rail
    overlay: "#1A2030", // controls, rows
    high: "#232A3B", // selected, pressed
    inset: "#06080C", // behind footage
  },
  line: { subtle: "#262E3D", strong: "#354055", control: "#64708A" },
  text: { primary: "#EEF1F6", secondary: "#AEB6C4", muted: "#8E97A8", disabled: "#5A6375" },
  signal: { DEFAULT: "#F2A93B", hover: "#F7BC5E", pressed: "#D48F25", on: "#1A1205" },
  accent: {
    /** AI working: the running stage, Editor messages, a live render. Never a button. */
    ai: "#A08CFF",
    glow: "#A08CFF",
    /** Teal: links, timecodes, live/connected, highlights — the cool partner of amber. */
    info: "#45D0C1",
    teal: "#45D0C1",
  },
  status: { sendable: "#3CCB7F", hold: "#F2A93B", fail: "#F5606C", queued: "#8E97A8", info: "#45D0C1" },
  layer: {
    video: "#5B8DEF",
    colour: "#E07BB0",
    punch: "#3DD6C3",
    broll: "#6CC488",
    captions: "#F2C94C",
    titles: "#F2994A",
  },
} as const;

/** Light used for depth: amber key from the upper left, teal rim from the right (CSS + 3D share these). */
export const light = {
  warm: "rgba(242, 169, 59, 0.16)",
  cool: "rgba(69, 208, 193, 0.12)",
  ai: "rgba(160, 140, 255, 0.14)",
} as const;

export const motion = {
  hover: 120,
  panel: 200,
  screen: 400,
  explode: 600,
  ease: "cubic-bezier(0.2, 0, 0, 1)",
} as const;
