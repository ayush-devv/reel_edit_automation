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
      ai: { DEFAULT: color.accent.ai, glow: color.accent.glow },
      cyan: color.accent.cyan,
      st: color.status,
      layer: color.layer,
    },
    fontFamily: {
      sans: ["Inter", "system-ui", "sans-serif"],
      mono: ["JetBrains Mono", "ui-monospace", "monospace"],
    },
    fontSize: {
      display: ["32px", { lineHeight: "40px", fontWeight: "700" }],
      title: ["20px", { lineHeight: "28px", fontWeight: "600" }],
      body: ["14px", { lineHeight: "20px", fontWeight: "400" }],
      label: ["12px", { lineHeight: "16px", fontWeight: "500", letterSpacing: "0.02em" }],
      mono: ["12px", { lineHeight: "16px", fontWeight: "500" }],
    },
    borderRadius: { none: "0", input: "6px", card: "10px", panel: "16px", phone: "28px", full: "9999px" },
    extend: {
      transitionTimingFunction: { std: motion.ease },
      transitionDuration: { hover: `${motion.hover}ms`, panel: `${motion.panel}ms`, screen: `${motion.screen}ms` },
    },
  },
  plugins: [],
} satisfies Config;
