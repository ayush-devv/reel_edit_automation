// FR-1 ambient backdrop: translucent film frames drifting slowly in deep space.
// Stops (still frame) while any job runs; the caller swaps in a static image under reduced motion.
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { color } from "../theme/tokens";
import { Scene3D } from "./common";

const N = 22;

function frameGeometry(): THREE.ShapeGeometry {
  // 9:16 frame outline with rounded corners (a hollow card).
  const w = 0.9;
  const h = 1.6;
  const r = 0.12;
  const t = 0.035;
  const rr = (s: THREE.Shape | THREE.Path, x: number, y: number, ww: number, hh: number, rad: number) => {
    s.moveTo(x + rad, y);
    s.lineTo(x + ww - rad, y);
    s.quadraticCurveTo(x + ww, y, x + ww, y + rad);
    s.lineTo(x + ww, y + hh - rad);
    s.quadraticCurveTo(x + ww, y + hh, x + ww - rad, y + hh);
    s.lineTo(x + rad, y + hh);
    s.quadraticCurveTo(x, y + hh, x, y + hh - rad);
    s.lineTo(x, y + rad);
    s.quadraticCurveTo(x, y, x + rad, y);
  };
  const outer = new THREE.Shape();
  rr(outer, -w / 2, -h / 2, w, h, r);
  const hole = new THREE.Path();
  rr(hole, -w / 2 + t, -h / 2 + t, w - 2 * t, h - 2 * t, r - t);
  outer.holes.push(hole);
  return new THREE.ShapeGeometry(outer, 8);
}

function Frames() {
  const group = useRef<THREE.Group>(null);
  const geo = useMemo(frameGeometry, []);
  const fill = useMemo(() => new THREE.PlaneGeometry(0.83, 1.53), []);
  const items = useMemo(
    () =>
      Array.from({ length: N }, (_, i) => {
        const rnd = (s: number) => {
          const x = Math.sin(i * 12.9898 + s * 78.233) * 43758.5453;
          return x - Math.floor(x);
        };
        return {
          pos: new THREE.Vector3((rnd(1) - 0.5) * 16, (rnd(2) - 0.5) * 8, -2 - rnd(3) * 12),
          rot: new THREE.Euler((rnd(4) - 0.5) * 0.6, (rnd(5) - 0.5) * 1.2, (rnd(6) - 0.5) * 0.5),
          speed: 0.05 + rnd(7) * 0.08,
          scale: 0.7 + rnd(8) * 0.9,
          tint: rnd(9) > 0.7 ? color.accent.glow : rnd(9) > 0.45 ? color.accent.cyan : "#8a90a6",
          phase: rnd(10) * Math.PI * 2,
        };
      }),
    [],
  );
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    group.current?.children.forEach((m, i) => {
      const it = items[i];
      m.position.y = it.pos.y + Math.sin(t * it.speed + it.phase) * 0.35;
      m.position.x = it.pos.x + Math.cos(t * it.speed * 0.7 + it.phase) * 0.25;
      m.rotation.y = it.rot.y + Math.sin(t * it.speed * 0.5 + it.phase) * 0.15;
    });
    if (group.current) group.current.rotation.y = Math.sin(t * 0.02) * 0.05;
  });
  return (
    <group ref={group}>
      {items.map((it, i) => (
        <group key={i} position={it.pos} rotation={it.rot} scale={it.scale}>
          <mesh geometry={geo}>
            <meshBasicMaterial color={it.tint} transparent opacity={0.32} side={THREE.DoubleSide} depthWrite={false} />
          </mesh>
          <mesh geometry={fill}>
            <meshBasicMaterial color={it.tint} transparent opacity={0.035} side={THREE.DoubleSide} depthWrite={false} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

export default function AmbientScene({ busy }: { busy: boolean }) {
  return (
    <Scene3D busy={busy} busyMode="still" label="Decorative backdrop of floating film frames" className="absolute inset-0" camera={{ position: [0, 0, 6], fov: 50 }} shadows={false}>
      <fog attach="fog" args={[color.bg.base, 6, 18]} />
      <Frames />
    </Scene3D>
  );
}
