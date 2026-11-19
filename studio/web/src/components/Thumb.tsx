import { useState } from "react";
import { Icon } from "./icons";
import { cx } from "./ui";

/** 9:16 thumbnail: the frame at 1 s of the latest render, or a flat well until one exists (no decorative gradient). */
export function Thumb({ src, label, className, children }: { id: string; src: string | null; label: string; className?: string; children?: React.ReactNode }) {
  const [broken, setBroken] = useState(false);
  return (
    <div className={cx("relative aspect-[9/16] overflow-hidden bg-bg-inset", className)}>
      {src && !broken ? (
        <img src={src} alt={label} loading="lazy" onError={() => setBroken(true)} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center" role="img" aria-label={`${label} (no render yet)`}>
          <Icon name="film" size={24} className="text-fg-disabled" />
        </div>
      )}
      {children}
    </div>
  );
}
