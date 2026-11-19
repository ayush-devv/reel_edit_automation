import type { Config } from "tailwindcss";
import { color, motion } from "./src/theme/tokens";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: "#FFFFFF",
      black: "#000000",
      bg: color.bg,
      line: color.line,
      fg: color.text,
      /** Amber: primary action, focus, playhead, current location, toggle on, hold/warn. */
      signal: color.signal,
      /** Violet: the AI is working. */
      ai: { DEFAULT: color.accent.ai, glow: color.accent.glow },
      info: color.accent.info,
      teal: color.accent.teal,
      /** Legacy alias of `info` (no cyan in Cutting Room). */
      cyan: color.accent.info,
      st: color.status,
      layer: color.layer,
    },
    fontFamily: {
      sans: ["Inter", "system-ui", "sans-serif"],
      mono: ["JetBrains Mono", "ui-monospace", "monospace"],
    },
    // Type scale (design-audit §5): 12 · 13 · 14 · 16 · 20 · 24 · 28, weights 400/500/600.
    fontSize: {
      display: ["28px", { lineHeight: "36px", fontWeight: "600" }],
      title: ["20px", { lineHeight: "28px", fontWeight: "600" }],
      section: ["16px", { lineHeight: "24px", fontWeight: "600" }],
      body: ["14px", { lineHeight: "20px", fontWeight: "400" }],
      ui: ["13px", { lineHeight: "18px", fontWeight: "500" }],
      label: ["12px", { lineHeight: "16px", fontWeight: "500" }],
      meta: ["12px", { lineHeight: "16px", fontWeight: "400" }],
      mono: ["13px", { lineHeight: "18px", fontWeight: "500" }],
      "timecode-lg": ["24px", { lineHeight: "32px", fontWeight: "500" }],
    },
    // Radius: 4 controls, 8 surfaces, pill. `phone` is the device mock only.
    borderRadius: { none: "0", input: "4px", control: "4px", card: "8px", panel: "8px", surface: "8px", phone: "28px", full: "9999px" },
    extend: {
      transitionTimingFunction: { std: motion.ease },
      transitionDuration: { hover: `${motion.hover}ms`, panel: `${motion.panel}ms`, screen: `${motion.screen}ms` },
      boxShadow: { menu: "0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.45)" },
    },
  },
  plugins: [],
} satisfies Config;
