import { Canvas, useThree, type CanvasProps } from "@react-three/fiber";
import { Environment, Lightformer } from "@react-three/drei";
import { useEffect, useMemo, type ReactNode } from "react";
import * as THREE from "three";

/**
 * Invalidate at a fixed low rate while a render job runs (NFR-1: ≤ 15 fps during renders).
 * With frameloop="demand" nothing draws unless invalidated.
 */
function FpsCap({ fps }: { fps: number }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const t = setInterval(() => invalidate(), 1000 / fps);
    return () => clearInterval(t);
  }, [fps, invalidate]);
  return null;
}

export interface Scene3DProps {
  children: ReactNode;
  /** A job is running somewhere: cap to 12 fps ("cap") or freeze on the current frame ("still"). */
  busy: boolean;
  busyMode?: "cap" | "still";
  label: string;
  className?: string;
  camera?: CanvasProps["camera"];
  onDoubleClick?: () => void;
  shadows?: boolean;
}

/** Canvas with the studio defaults. `data-gl="on"` lets the screenshot script assert real WebGL. */
export function Scene3D({ children, busy, busyMode = "cap", label, className, camera, onDoubleClick, shadows = true }: Scene3DProps) {
  return (
    <div className={className} data-gl="on" role="img" aria-label={label} onDoubleClick={onDoubleClick}>
      <Canvas
        dpr={[1, 2]}
        shadows={shadows ? "soft" : false}
        frameloop={busy ? "demand" : "always"}
        camera={camera}
        gl={{ antialias: true, powerPreference: "low-power", alpha: true }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.05;
        }}
      >
        {busy && busyMode === "cap" && <FpsCap fps={12} />}
        {children}
      </Canvas>
    </div>
  );
}

/**
 * Local studio lighting: an environment built from Lightformers (rendered on the GPU once, no HDRI
 * download — drei presets would fetch from a CDN), plus a soft key light for shadows.
 */
export function StudioLights({ intensity = 1, shadowSize = 6 }: { intensity?: number; shadowSize?: number }) {
  return (
    <>
      <ambientLight intensity={0.15 * intensity} />
      <directionalLight
        position={[4, 7, 5]}
        intensity={1.2 * intensity}
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-bias={-0.0004}
        shadow-camera-left={-shadowSize}
        shadow-camera-right={shadowSize}
        shadow-camera-top={shadowSize}
        shadow-camera-bottom={-shadowSize}
      />
      <Environment resolution={256} frames={1}>
        <color attach="background" args={["#06080C"]} />
        <Lightformer form="rect" intensity={2.2} color="#ffffff" position={[0, 5, -6]} scale={[10, 2, 1]} />
        <Lightformer form="rect" intensity={1.6} color="#F2A93B" position={[-6, 1, 0]} rotation-y={Math.PI / 2} scale={[8, 3, 1]} />
        <Lightformer form="rect" intensity={1.4} color="#45D0C1" position={[6, 1, 0]} rotation-y={-Math.PI / 2} scale={[8, 3, 1]} />
        <Lightformer form="ring" intensity={1.5} color="#ffffff" position={[0, 3, 6]} scale={3} />
      </Environment>
    </>
  );
}

let glowTex: THREE.Texture | null = null;
/** Soft radial gradient for additive glow sprites (a cheap stand-in for bloom). */
export function useGlowTexture(): THREE.Texture {
  return useMemo(() => {
    if (glowTex) return glowTex;
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const ctx = c.getContext("2d")!;
    const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.25, "rgba(255,255,255,0.45)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
    glowTex = new THREE.CanvasTexture(c);
    glowTex.colorSpace = THREE.SRGBColorSpace;
    return glowTex;
  }, []);
}

export const easeOut = (x: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);
