// Home hero: your reels as lit 9:16 posters on a slow curved wall. Warm key light from the left, cool rim from
// the right, each poster glowing in its own colour. Hover lifts a poster; click opens the project.
// Decorative duplicate of the accessible project list below it (which stays the keyboard path).
import { Html, Image as DreiImage } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { color } from "../theme/tokens";
import { Scene3D, useGlowTexture } from "./common";

export interface WallItem {
  id: string;
  name: string;
  status: string; // label, e.g. "Hold · 2"
  statusColor: string;
  thumb: string | null;
  tint: string; // "r, g, b"
}

const W = 1.15;
const H = W * (16 / 9);
const R = 7.5;

function rgb(t: string) {
  const [r, g, b] = t.split(",").map((x) => Number(x) / 255);
  return new THREE.Color(r, g, b);
}

function Poster({ item, angle, onOpen }: { item: WallItem; angle: number; onOpen: (id: string) => void }) {
  const g = useRef<THREE.Group>(null);
  const [hover, setHover] = useState(false);
  const glow = useGlowTexture();
  const tint = useMemo(() => rgb(item.tint), [item.tint]);
  const pos = useMemo(() => new THREE.Vector3(Math.sin(angle) * R, 0, R - Math.cos(angle) * R), [angle]);
  useFrame((_, dt) => {
    if (!g.current) return;
    const k = 1 - Math.exp(-dt * 10);
    const s = hover ? 1.09 : 1;
    g.current.scale.setScalar(THREE.MathUtils.lerp(g.current.scale.x, s, k));
    g.current.position.y = THREE.MathUtils.lerp(g.current.position.y, hover ? 0.18 : 0, k);
  });
  return (
    <group position={pos} rotation-y={-angle}>
      <group
        ref={g}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHover(true);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          setHover(false);
          document.body.style.cursor = "";
        }}
        onClick={(e) => {
          e.stopPropagation();
          onOpen(item.id);
        }}
      >
        {/* The reel's own colour, glowing behind it. */}
        <sprite position={[0, 0, -0.08]} scale={[W * 2.6, H * 1.7, 1]}>
          <spriteMaterial map={glow} color={tint} transparent opacity={hover ? 0.55 : 0.28} blending={THREE.AdditiveBlending} depthWrite={false} />
        </sprite>
        {item.thumb ? (
          <Suspense fallback={<mesh><planeGeometry args={[W, H]} /><meshBasicMaterial color={color.bg.high} /></mesh>}>
            <DreiImage url={item.thumb} scale={[W, H]} radius={0.06} toneMapped={false} />
          </Suspense>
        ) : (
          <mesh>
            <planeGeometry args={[W, H]} />
            <meshBasicMaterial color={color.bg.high} />
          </mesh>
        )}
        {/* Status bar under the poster: its colour plus, on hover, the name and status in words. */}
        <mesh position={[0, -H / 2 - 0.09, 0]}>
          <planeGeometry args={[W, 0.035]} />
          <meshBasicMaterial color={item.statusColor} toneMapped={false} />
        </mesh>
        {hover && (
          <Html position={[0, -H / 2 - 0.32, 0]} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
            <div style={{ whiteSpace: "nowrap", textAlign: "center", font: "500 13px/18px Inter, sans-serif", color: color.text.primary, textShadow: "0 1px 8px rgba(0,0,0,.9)" }}>
              {item.name}
              <div style={{ font: "400 12px/16px Inter, sans-serif", color: item.statusColor }}>{item.status}</div>
            </div>
          </Html>
        )}
      </group>
    </group>
  );
}

function Wall({ items, onOpen }: { items: WallItem[]; onOpen: (id: string) => void }) {
  const group = useRef<THREE.Group>(null);
  const span = Math.min(1.25, 0.24 * (items.length - 1));
  const angles = items.map((_, i) => (items.length === 1 ? 0 : -span / 2 + (span * i) / (items.length - 1)));
  useFrame(({ clock, pointer }) => {
    if (!group.current) return;
    // A slow drift plus a little parallax toward the pointer.
    const target = Math.sin(clock.elapsedTime * 0.12) * 0.08 + pointer.x * 0.12;
    group.current.rotation.y = THREE.MathUtils.lerp(group.current.rotation.y, target, 0.04);
    group.current.rotation.x = THREE.MathUtils.lerp(group.current.rotation.x, -pointer.y * 0.04, 0.04);
  });
  return (
    <group ref={group} position={[0, 0.15, -0.5]}>
      {items.map((it, i) => (
        <Poster key={it.id} item={it} angle={angles[i]} onOpen={onOpen} />
      ))}
    </group>
  );
}

function Floor() {
  const glow = useGlowTexture();
  return (
    <group position={[0, -1.35, -1]}>
      {/* Warm and cool pools of light on the floor: the studio's key and rim. */}
      <sprite position={[-3.2, 0, 0]} scale={[9, 3, 1]}>
        <spriteMaterial map={glow} color={color.signal.DEFAULT} transparent opacity={0.22} blending={THREE.AdditiveBlending} depthWrite={false} />
      </sprite>
      <sprite position={[3.4, 0.2, 0]} scale={[9, 3, 1]}>
        <spriteMaterial map={glow} color={color.accent.teal} transparent opacity={0.2} blending={THREE.AdditiveBlending} depthWrite={false} />
      </sprite>
    </group>
  );
}

export default function ReelWall({ items, onOpen, busy }: { items: WallItem[]; onOpen: (id: string) => void; busy: boolean }) {
  return (
    <Scene3D busy={busy} label="Your recent reels on a 3D wall. The same projects are listed below." className="h-full w-full" camera={{ position: [0, 0.2, 3.6], fov: 44 }} shadows={false}>
      <Floor />
      <Wall items={items} onOpen={onOpen} />
    </Scene3D>
  );
}
