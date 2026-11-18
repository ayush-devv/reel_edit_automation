import { useState } from "react";
import { Icon } from "./icons";
import { cx } from "./ui";

function hue(id: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

/** 9:16 thumbnail: the frame at 1 s of the latest render, or a quiet placeholder until one exists. */
export function Thumb({ id, src, label, className, children }: { id: string; src: string | null; label: string; className?: string; children?: React.ReactNode }) {
  const [broken, setBroken] = useState(false);
  const h = hue(id);
  return (
    <div className={cx("relative aspect-[9/16] overflow-hidden bg-bg-inset", className)}>
      {src && !broken ? (
        <img src={src} alt={label} loading="lazy" onError={() => setBroken(true)} className="h-full w-full object-cover" />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center"
          style={{
            background: `radial-gradient(120% 70% at 70% 20%, hsla(${h},45%,40%,0.35), transparent 60%), radial-gradient(90% 60% at 20% 90%, hsla(${(h + 60) % 360},40%,35%,0.25), transparent 60%), #0d0f15`,
          }}
          role="img"
          aria-label={`${label} (no render yet)`}
        >
          <Icon name="film" size={26} className="text-fg-muted/70" />
        </div>
      )}
      {children}
    </div>
  );
}
