// Guided adjustments (FR-8). The engine validator is the authority (422 issues); these client-side checks
// mirror its numeric ranges (engine/src/reel/schemas/plan.py comments) so obvious mistakes show instantly.
import type { AdjustKind, ValidatorIssue } from "../api/types";

export const LOOKS = [
  { id: "none", note: "no look — correction only" },
  { id: "clean", note: "neutral, slightly crisper contrast" },
  { id: "warm", note: "warm, friendly skin" },
  { id: "cool", note: "cooler, calmer, techy" },
  { id: "punchy", note: "high contrast + saturation" },
  { id: "film", note: "lifted blacks, soft highlights" },
  { id: "teal_orange", note: "cinematic teal shadows, warm skin" },
] as const;

interface Ctx {
  families: string[];
  tracks: string[];
}

const RANGES: Partial<Record<AdjustKind, [number, number, string]>> = {
  look_strength: [0, 1, "Look strength must be between 0 and 1."],
  music_gain_db: [-30, -6, "Music level must be between −30 and −6 dB."],
  grain: [0, 0.6, "Grain must be between 0 and 0.6."],
  vignette: [0, 0.7, "Vignette must be between 0 and 0.7."],
};

const issue = (code: string, path: string, message: string, fix: string): ValidatorIssue => ({ code, path, message, fix });

export function validateAdjust(kind: AdjustKind, value: unknown, ctx: Ctx): ValidatorIssue[] {
  const range = RANGES[kind];
  if (range) {
    const n = Number(value);
    if (value === "" || value === null || !Number.isFinite(n)) return [issue("not_a_number", kind, "Enter a number.", `Use a value between ${range[0]} and ${range[1]}.`)];
    if (n < range[0] || n > range[1]) return [issue("out_of_range", kind, range[2], `Use a value between ${range[0]} and ${range[1]}.`)];
    return [];
  }
  switch (kind) {
    case "max_pause_ms": {
      const n = Number(value);
      if (!Number.isInteger(n) || (n !== 0 && (n < 300 || n > 3000)))
        return [issue("pause_range", "story.max_pause_ms", "Pause limit must be 0 (keep every pause) or between 300 and 3000 ms.", "Use 400 ms (the default) or 0.")];
      return [];
    }
    case "caption_family":
      return ctx.families.includes(String(value)) ? [] : [issue("unknown_family", "captions.family", `Caption family '${String(value)}' does not exist.`, `Use one of ${ctx.families.join(", ")}.`)];
    case "look":
      return LOOKS.some((l) => l.id === value) ? [] : [issue("unknown_look", "grade.look", `Look '${String(value)}' does not exist.`, `Use one of ${LOOKS.map((l) => l.id).join(", ")}.`)];
    case "music_track":
      return value === "none" || ctx.tracks.includes(String(value)) ? [] : [issue("unknown_track", "music.track", `Track '${String(value)}' is not in the music library.`, "Pick a track from Libraries → Music, or none.")];
    case "caption_token": {
      const v = value as { key?: unknown; value?: unknown } | null;
      if (!v || typeof v.key !== "string" || !v.key || typeof v.value !== "string")
        return [issue("bad_token", "captions.tokens", "A caption token needs a key and a value.", "For example emph_color = #FF5FA2.")];
      if (/color$/.test(v.key) && !/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(v.value))
        return [issue("bad_color", `captions.tokens.${v.key}`, "Colours must be hex, like #FF5FA2.", "Use the colour picker.")];
      return [];
    }
    case "sfx_off":
    case "punch_ins_off":
      return typeof value === "boolean" ? [] : [issue("not_boolean", kind, "Choose on or off.", "")];
    default:
      return [];
  }
}
