// FR-4 3D phone: a rounded 9:16 device playing the reel as a video texture, optional generic platform UI
// and safe-zone glow layers. Drag to orbit ±35°, double-click to reset, idle sway ±3°.
import { ContactShadows, RoundedBox } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { ReelPlayer } from "../lib/reelPlayer";
import { color } from "../theme/tokens";
import { Scene3D, StudioLights } from "./common";

const BODY_W = 1.92;
const BODY_H = 3.62;
const SCREEN_W = 1.8;
const SCREEN_H = SCREEN_W * (16 / 9);
const MAX = (35 * Math.PI) / 180;
const SWAY = (3 * Math.PI) / 180;

/** Rounded-rectangle screen with UVs normalised to 0..1 (ShapeGeometry UVs are in shape units). */
function screenGeometry(w: number, h: number, r: number): THREE.ShapeGeometry {
  const s = new THREE.Shape();
  const x = -w / 2;
  const y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  const g = new THREE.ShapeGeometry(s, 12);
  const pos = g.attributes.position;
  const uv = g.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, (pos.getX(i) - x) / w, (pos.getY(i) - y) / h);
  uv.needsUpdate = true;
  return g;
}

function useElementTexture(el: HTMLVideoElement | HTMLCanvasElement | null) {
  const tex = useMemo(() => {
    if (!el) return null;
    const t = el instanceof HTMLVideoElement ? new THREE.VideoTexture(el) : new THREE.CanvasTexture(el);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 4;
    return t;
  }, [el]);
  useEffect(() => () => tex?.dispose(), [tex]);
  return tex;
}

function Phone({ player, overlayUI, safeZones, uiCanvas, safeCanvas, resetSignal }: PhoneProps & { resetSignal: number }) {
  const group = useRef<THREE.Group>(null);
  const reel = useElementTexture(player.element);
  const ui = useElementTexture(uiCanvas);
  const safe = useElementTexture(safeCanvas);
  const geo = useMemo(() => screenGeometry(SCREEN_W, SCREEN_H, 0.16), []);
  const { gl } = useThree();
  const drag = useRef({ active: false, x: 0, y: 0, ry: 0, rx: 0, tx: 0, ty: 0 });

  useEffect(() => {
    drag.current.tx = 0;
    drag.current.ty = 0;
  }, [resetSignal]);

  useEffect(() => {
    const el = gl.domElement;
    const down = (e: PointerEvent) => {
      drag.current.active = true;
      drag.current.x = e.clientX;
      drag.current.y = e.clientY;
      drag.current.rx = drag.current.ty;
      drag.current.ry = drag.current.tx;
      el.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!drag.current.active) return;
      const d = drag.current;
      d.tx = THREE.MathUtils.clamp(d.ry + (e.clientX - d.x) * 0.006, -MAX, MAX);
      d.ty = THREE.MathUtils.clamp(d.rx + (e.clientY - d.y) * 0.004, -MAX / 2, MAX / 2);
    };
    const up = () => (drag.current.active = false);
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    el.style.cursor = "grab";
    return () => {
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
    };
  }, [gl]);

  useFrame(({ clock }, dt) => {
    const g = group.current;
    if (!g) return;
    const t = clock.elapsedTime;
    const d = drag.current;
    const sway = d.active ? 0 : Math.sin(t * 0.6) * SWAY;
    const k = 1 - Math.pow(0.0005, dt);
    g.rotation.y += (d.tx + sway - g.rotation.y) * k;
    g.rotation.x += (d.ty + Math.sin(t * 0.45) * SWAY * 0.4 - g.rotation.x) * k;
    if (reel && player.kind === "canvas") reel.needsUpdate = true;
  });

  return (
    <group ref={group}>
      {/* body */}
      <RoundedBox args={[BODY_W, BODY_H, 0.16]} radius={0.2} smoothness={8} castShadow>
        <meshPhysicalMaterial color="#1b1f2a" metalness={0.85} roughness={0.28} clearcoat={1} clearcoatRoughness={0.15} />
      </RoundedBox>
      {/* bezel glass */}
      <mesh position={[0, 0, 0.081]}>
        <planeGeometry args={[BODY_W - 0.06, BODY_H - 0.06]} />
        <meshPhysicalMaterial color="#020203" metalness={0} roughness={0.08} clearcoat={1} transparent opacity={0.98} />
      </mesh>
      {/* the reel */}
      <mesh geometry={geo} position={[0, 0, 0.084]}>
        {reel ? <meshBasicMaterial map={reel} toneMapped={false} /> : <meshBasicMaterial color="#000" />}
      </mesh>
      {overlayUI && ui && (
        <mesh geometry={geo} position={[0, 0, 0.086]}>
          <meshBasicMaterial map={ui} transparent toneMapped={false} depthWrite={false} />
        </mesh>
      )}
      {safeZones && safe && (
        <mesh geometry={geo} position={[0, 0, 0.088]}>
          <meshBasicMaterial map={safe} transparent toneMapped={false} depthWrite={false} blending={THREE.AdditiveBlending} />
        </mesh>
      )}
      {/* camera pill */}
      <mesh position={[0, SCREEN_H / 2 - 0.11, 0.09]} rotation-z={Math.PI / 2}>
        <capsuleGeometry args={[0.05, 0.26, 4, 16]} />
        <meshBasicMaterial color="#000" />
      </mesh>
      {/* side button */}
      <mesh position={[BODY_W / 2 + 0.008, 0.7, 0]}>
        <boxGeometry args={[0.02, 0.4, 0.06]} />
        <meshStandardMaterial color="#232A3B" metalness={0.9} roughness={0.3} />
      </mesh>
    </group>
  );
}

interface PhoneProps {
  player: ReelPlayer;
  overlayUI: boolean;
  safeZones: boolean;
  uiCanvas: HTMLCanvasElement | null;
  safeCanvas: HTMLCanvasElement | null;
}

export default function PhoneScene(props: PhoneProps & { busy: boolean; resetSignal: number; onReset: () => void }) {
  return (
    <Scene3D
      busy={props.busy}
      label="The reel playing on a 3D phone. Drag to rotate, double-click to reset."
      className="h-full w-full touch-none"
      camera={{ position: [0, 0.05, 7.6], fov: 36 }}
      onDoubleClick={props.onReset}
    >
      <StudioLights intensity={1} shadowSize={4} />
      {/* Warm key, cool rim on the phone body. The screen is an unlit video texture, so the footage keeps its true colour. */}
      <spotLight position={[-4, 5, 4]} angle={0.5} penumbra={1} intensity={26} color={color.signal.DEFAULT} />
      <spotLight position={[4, 3, 3]} angle={0.5} penumbra={1} intensity={20} color={color.accent.teal} />
      <group position={[0, 0.2, 0]}>
        <Phone {...props} />
      </group>
      <ContactShadows position={[0, -1.95, 0]} opacity={0.65} scale={8} blur={2.6} far={3} color="#000000" />
    </Scene3D>
  );
}
