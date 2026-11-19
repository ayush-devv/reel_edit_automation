// A reel's own colour: the average of its thumbnail, lifted so it reads as light on a dark surface.
// Used for the per-project glow (CSS `--tint`) and the 3D reel wall. Cached per URL.
import { useEffect, useState } from "react";

const cache = new Map<string, string>();
export const DEFAULT_TINT = "69, 208, 193"; // teal

function tintOf(url: string): Promise<string> {
  const hit = cache.get(url);
  if (hit) return Promise.resolve(hit);
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onerror = () => resolve(DEFAULT_TINT);
    img.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = c.height = 12;
        const ctx = c.getContext("2d");
        if (!ctx) return resolve(DEFAULT_TINT);
        ctx.drawImage(img, 0, 0, 12, 12);
        const d = ctx.getImageData(0, 0, 12, 12).data;
        let r = 0, g = 0, b = 0, n = 0;
        for (let i = 0; i < d.length; i += 4) {
          if (Math.max(d[i], d[i + 1], d[i + 2]) < 24) continue; // ignore letterbox black
          r += d[i];
          g += d[i + 1];
          b += d[i + 2];
          n++;
        }
        const out = n ? lift([r / n, g / n, b / n]) : DEFAULT_TINT;
        cache.set(url, out);
        resolve(out);
      } catch {
        resolve(DEFAULT_TINT); // tainted canvas or no 2D context
      }
    };
    img.src = url;
  });
}

/** Push the colour away from grey and up in brightness so it glows; keeps its hue. */
function lift([r, g, b]: number[]): string {
  const avg = (r + g + b) / 3;
  const sat = (c: number) => avg + (c - avg) * 1.6;
  const max = Math.max(sat(r), sat(g), sat(b), 1);
  const k = 220 / max;
  return [sat(r), sat(g), sat(b)].map((c) => Math.round(Math.min(255, Math.max(0, c * k)))).join(", ");
}

/** "r, g, b" for each image, in order; DEFAULT_TINT until read (or when it can't be read). */
export function useImageTints(urls: (string | null)[]): string[] {
  const key = urls.map((u) => u ?? "").join("|");
  const [tints, setTints] = useState<string[]>(() => urls.map((u) => (u && cache.get(u)) || DEFAULT_TINT));
  useEffect(() => {
    let alive = true;
    const list = key ? key.split("|") : [];
    Promise.all(list.map((u) => (u ? tintOf(u) : Promise.resolve(DEFAULT_TINT)))).then((t) => alive && setTints(t));
    return () => {
      alive = false;
    };
  }, [key]);
  return tints;
}

export function useImageTint(url: string | null | undefined): string {
  return useImageTints([url ?? null])[0];
}
