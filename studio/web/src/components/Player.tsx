import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { ReelPlayer } from "../lib/reelPlayer";
import { usePlayerTime } from "../lib/reelPlayer";
import { drawPlatformUI, drawSafeZones } from "../lib/overlays";
import { use3D } from "../hooks/useMedia";
import { useStatus } from "../hooks/status";
import { Icon } from "./icons";
import { cx, IconButton, Mono, Toggle } from "./ui";

const PhoneScene = lazy(() => import("../three/PhoneScene"));

const fmt = (t: number) => {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
};

/** Mounts an existing DOM element (the player's <video>/<canvas> or an overlay canvas) inside React. */
function Mount({ el, className }: { el: HTMLElement | null; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = ref.current;
    if (!host || !el) return;
    el.className = "absolute inset-0 h-full w-full object-cover";
    host.appendChild(el);
    return () => {
      if (el.parentElement === host) host.removeChild(el);
    };
  }, [el]);
  return <div ref={ref} className={className} />;
}

/** Flat phone: the reduced-motion / no-WebGL equivalent of the 3D phone, also used for full-screen playback. */
export function FlatPhone({ player, ui, safe, big }: { player: ReelPlayer; ui: HTMLCanvasElement | null; safe: HTMLCanvasElement | null; big?: boolean }) {
  return (
    <div
      className={cx("relative mx-auto overflow-hidden rounded-phone border-[6px] border-bg-high bg-black ring-1 ring-line-strong", big ? "h-[86vh] aspect-[9/16]" : "h-[560px] aspect-[9/16]")}
      data-gl="off"
    >
      <Mount el={player.element} className="absolute inset-0" />
      {ui && <Mount el={ui} className="pointer-events-none absolute inset-0" />}
      {safe && <Mount el={safe} className="pointer-events-none absolute inset-0" />}
    </div>
  );
}

export function PhonePreview({ player, client }: { player: ReelPlayer; client: string }) {
  const can3D = use3D();
  const { busy } = useStatus();
  const [overlayUI, setOverlayUI] = useState(false);
  const [safeZones, setSafeZones] = useState(false);
  const [full, setFull] = useState(false);
  const [reset, setReset] = useState(0);
  const t = usePlayerTime(player);
  const uiCanvas = useMemo(() => (typeof document !== "undefined" ? drawPlatformUI(client) : null), [client]);
  const safeCanvas = useMemo(() => (typeof document !== "undefined" ? drawSafeZones() : null), []);
  const playing = player.isPlaying();
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    if (full && !d.open) d.showModal?.();
    if (!full && d.open) d.close?.();
  }, [full]);

  // Flat full-screen and the 3D phone can't both own the same DOM element: 3D only reads it as a texture,
  // but the flat views mount it, so render the flat phone only where it is visible.
  const showFlatInline = !can3D && !full;

  return (
    <div className="flex flex-col gap-4">
      {/* Monitor well: the darkest surface, so the footage is the brightest thing on screen. */}
      <div className="stage-lit relative h-[600px] overflow-hidden rounded-surface">
        {can3D ? (
          <Suspense fallback={null}>
            <PhoneScene
              player={player}
              overlayUI={overlayUI}
              safeZones={safeZones}
              uiCanvas={uiCanvas}
              safeCanvas={safeCanvas}
              busy={busy}
              resetSignal={reset}
              onReset={() => setReset((r) => r + 1)}
            />
          </Suspense>
        ) : showFlatInline ? (
          <div className="flex h-full items-center justify-center">
            <FlatPhone player={player} ui={overlayUI ? uiCanvas : null} safe={safeZones ? safeCanvas : null} />
          </div>
        ) : null}
        {can3D && <p className="pointer-events-none absolute bottom-3 left-0 right-0 text-center text-meta text-fg-muted">Drag to rotate · double-click to reset</p>}
      </div>

      <div>
        <div className="flex items-center gap-3">
          <IconButton icon={playing ? "pause" : "play"} label={playing ? "Pause" : "Play"} onClick={() => (playing ? player.pause() : player.play())} className="h-9 w-9 border border-line-strong bg-bg-overlay text-fg-primary hover:bg-bg-high" />
          <Mono className="w-12 text-fg-secondary">{fmt(t)}</Mono>
          <input
            type="range"
            min={0}
            max={player.duration || 1}
            step={0.05}
            value={t}
            aria-label="Scrub"
            onChange={(e) => player.seek(Number(e.target.value))}
            className="h-1 flex-1 cursor-pointer accent-[#F2A93B]"
          />
          <Mono className="w-12 text-right text-fg-muted">{fmt(player.duration)}</Mono>
          <IconButton icon={player.isMuted() ? "mute" : "volume"} label={player.isMuted() ? "Unmute" : "Mute"} onClick={() => player.setMuted(!player.isMuted())} />
          <IconButton icon="expand" label="Full-screen flat playback" onClick={() => setFull(true)} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 border-t border-line-subtle pt-4">
          <Toggle checked={overlayUI} onChange={setOverlayUI} label="Platform UI" description="Generic buttons and caption area" />
          <Toggle checked={safeZones} onChange={setSafeZones} label="Safe zones" description="Where captions must stay" />
        </div>
      </div>

      <dialog
        ref={dialogRef}
        onClose={() => setFull(false)}
        className="m-auto rounded-surface border border-line-strong bg-bg-base p-4 text-fg-primary shadow-menu backdrop:bg-black/80"
        aria-label="Full-screen playback"
      >
        {full && (
          <div className="flex flex-col items-center gap-3">
            <FlatPhone player={player} ui={overlayUI ? uiCanvas : null} safe={safeZones ? safeCanvas : null} big />
            <div className="flex gap-2">
              <IconButton icon={playing ? "pause" : "play"} label={playing ? "Pause" : "Play"} onClick={() => (playing ? player.pause() : player.play())} />
              <button type="button" className="inline-flex h-8 items-center gap-2 rounded-control px-3 text-fg-secondary hover:bg-bg-overlay" onClick={() => setFull(false)}>
                <Icon name="x" size={16} /> Close
              </button>
            </div>
          </div>
        )}
      </dialog>
    </div>
  );
}
