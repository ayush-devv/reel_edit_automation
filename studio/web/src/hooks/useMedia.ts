import { useEffect, useState } from "react";

function query(q: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(q).matches;
}

/** prefers-reduced-motion (NFR-5): no 3D motion, flat equivalents, crossfades only. */
export function useReducedMotion(): boolean {
  const q = "(prefers-reduced-motion: reduce)";
  const [v, setV] = useState(() => query(q));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const m = window.matchMedia(q);
    const on = () => setV(m.matches);
    m.addEventListener?.("change", on);
    return () => m.removeEventListener?.("change", on);
  }, []);
  return v;
}

let glCache: boolean | null = null;
/** True when the browser can create a WebGL context (false in jsdom and some locked-down setups). */
export function hasWebGL(): boolean {
  if (glCache !== null) return glCache;
  try {
    const c = document.createElement("canvas");
    glCache = !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    glCache = false;
  }
  return glCache;
}

/** 3D allowed: WebGL present and reduced motion off. */
export function use3D(): boolean {
  const reduced = useReducedMotion();
  return !reduced && hasWebGL();
}
