// FR-3 pipeline stage: the 15 stages as lit platforms on a curved track over a dark reflective floor.
// Done nodes glow steady, the running node pulses (accent.ai.glow), skipped are dimmed, failed is red.
import { Html, MeshReflectorMaterial } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { Stage } from "../api/types";
import { STAGE_GROUPS, STAGE_LABEL } from "../lib/status";
import { color } from "../theme/tokens";
import { Scene3D, StudioLights, useGlowTexture } from "./common";

const N_PARTICLES = 36;

function makeCurve(n: number) {
  const pts: THREE.Vector3[] = [];
  for (let i = 0; i < 9; i++) {
    const u = i / 8;
    pts.push(new THREE.Vector3(-8.6 + u * 17.2, 0, -1.6 * Math.sin(u * Math.PI) + 0.35 * Math.sin(u * Math.PI * 3)));
  }
  const curve = new THREE.CatmullRomCurve3(pts);
  const ts = Array.from({ length: n }, (_, i) => 0.03 + (i / (n - 1)) * 0.94);
  return { curve, ts, positions: ts.map((t) => curve.getPointAt(t)) };
}

const STATUS_COLOR: Record<string, string> = {
  // Done is graphite, running is violet (the AI is working), failed is red; the rest is a hairline.
  done: color.text.muted,
  running: color.accent.ai,
  failed: color.status.fail,
  skipped: color.line.strong,
  pending: color.line.strong,
  queued: color.line.strong,
};

function Node({ stage, pos, selected, onSelect }: { stage: Stage; pos: THREE.Vector3; selected: boolean; onSelect: (n: string) => void }) {
  const core = useRef<THREE.Mesh>(null);
  const ring = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Sprite>(null);
  const glow = useGlowTexture();
  const st = stage.status;
  const c = STATUS_COLOR[st] ?? STATUS_COLOR.pending;
  const lit = st === "done" || st === "running" || st === "failed";
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (st === "running") {
      const k = 0.5 + 0.5 * Math.sin(t * 3.2);
      (core.current!.material as THREE.MeshStandardMaterial).emissiveIntensity = 1.6 + 1.8 * k;
      halo.current!.scale.setScalar(1.3 + 0.45 * k);
      (halo.current!.material as THREE.SpriteMaterial).opacity = 0.55 + 0.35 * k;
      const r = (t * 0.8) % 1;
      ring.current!.scale.setScalar(1 + r * 1.6);
      (ring.current!.material as THREE.MeshBasicMaterial).opacity = 0.6 * (1 - r);
    }
  });
  return (
    <group position={pos}>
      <mesh
        position={[0, 0.06, 0]}
        castShadow
        receiveShadow
        onClick={(e) => {
          e.stopPropagation();
          onSelect(stage.name);
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "")}
      >
        <cylinderGeometry args={[0.42, 0.48, 0.14, 48]} />
        <meshStandardMaterial color={selected ? "#2a2f45" : "#151925"} metalness={0.7} roughness={0.32} />
      </mesh>
      <mesh position={[0, 0.135, 0]} rotation-x={-Math.PI / 2}>
        <ringGeometry args={[0.36, 0.4, 48]} />
        <meshBasicMaterial color={selected ? color.signal.DEFAULT : c} transparent opacity={lit || selected ? 0.9 : 0.35} />
      </mesh>
      <mesh ref={core} position={[0, 0.34, 0]} castShadow>
        <sphereGeometry args={[st === "running" ? 0.17 : 0.13, 32, 32]} />
        <meshStandardMaterial
          color={lit ? c : "#22283a"}
          emissive={c}
          emissiveIntensity={st === "done" ? 1.3 : st === "failed" ? 2.4 : st === "running" ? 2.4 : 0.05}
          metalness={0.2}
          roughness={0.3}
          transparent={st === "skipped"}
          opacity={st === "skipped" ? 0.4 : 1}
        />
      </mesh>
      {lit && (
        <sprite ref={halo} position={[0, 0.34, 0]} scale={st === "running" ? 1.6 : 1.05}>
          <spriteMaterial map={glow} color={c} transparent opacity={st === "done" ? 0.45 : 0.75} blending={THREE.AdditiveBlending} depthWrite={false} />
        </sprite>
      )}
      {st === "running" && (
        <mesh ref={ring} position={[0, 0.14, 0]} rotation-x={-Math.PI / 2}>
          <ringGeometry args={[0.44, 0.5, 64]} />
          <meshBasicMaterial color={color.accent.glow} transparent opacity={0.5} depthWrite={false} />
        </mesh>
      )}
      {st === "failed" && <pointLight position={[0, 0.6, 0]} color={color.status.fail} intensity={2.5} distance={2.2} />}
      {st === "running" && <pointLight position={[0, 0.6, 0]} color={color.accent.glow} intensity={3} distance={2.6} />}
      <Html position={[0, -0.02, 0.62]} center zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
        <div
          style={{
            font: "500 12px/16px Inter, sans-serif",
            letterSpacing: "0.02em",
            whiteSpace: "nowrap",
            color: st === "failed" ? color.status.fail : st === "running" ? "#ffffff" : st === "done" ? color.text.secondary : color.text.muted,
            textShadow: "0 1px 6px rgba(0,0,0,0.9)",
          }}
        >
          {STAGE_LABEL[stage.name] ?? stage.name}
        </div>
      </Html>
    </group>
  );
}

function Track({ curve, upTo }: { curve: THREE.CatmullRomCurve3; upTo: number }) {
  const base = useMemo(() => new THREE.TubeGeometry(curve, 200, 0.022, 8, false), [curve]);
  const lit = useMemo(() => {
    if (upTo <= 0) return null;
    const pts = Array.from({ length: 64 }, (_, i) => curve.getPointAt((i / 63) * upTo));
    return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 120, 0.03, 8, false);
  }, [curve, upTo]);
  return (
    <group position={[0, 0.02, 0]}>
      <mesh geometry={base}>
        <meshStandardMaterial color="#232836" metalness={0.5} roughness={0.5} />
      </mesh>
      {lit && (
        <mesh geometry={lit}>
          <meshStandardMaterial color={color.accent.ai} emissive={color.accent.glow} emissiveIntensity={1.2} />
        </mesh>
      )}
    </group>
  );
}

/** Data particles flowing along the finished part of the track toward the running node. */
function Particles({ curve, upTo, active }: { curve: THREE.CatmullRomCurve3; upTo: number; active: boolean }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const tmp = useMemo(() => new THREE.Object3D(), []);
  const seeds = useMemo(() => Array.from({ length: N_PARTICLES }, (_, i) => (i / N_PARTICLES + Math.sin(i * 91.7) * 0.01 + 1) % 1), []);
  useFrame(({ clock }) => {
    const m = ref.current;
    if (!m) return;
    const t = clock.elapsedTime;
    seeds.forEach((s, i) => {
      const u = ((s + t * 0.06) % 1) * upTo;
      const p = curve.getPointAt(Math.max(0, Math.min(1, u)));
      tmp.position.set(p.x, 0.07 + Math.sin(t * 2 + i) * 0.02, p.z);
      const fade = Math.sin(((s + t * 0.06) % 1) * Math.PI);
      tmp.scale.setScalar(active ? 0.6 + fade * 0.6 : 0.0001);
      tmp.updateMatrix();
      m.setMatrixAt(i, tmp.matrix);
    });
    m.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, N_PARTICLES]}>
      <sphereGeometry args={[0.03, 8, 8]} />
      <meshBasicMaterial color={color.accent.ai} transparent opacity={0.9} blending={THREE.AdditiveBlending} depthWrite={false} />
    </instancedMesh>
  );
}

function CameraRig({ focusX }: { focusX: number }) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3(focusX * 0.55, 0, 0));
  useFrame((_, dt) => {
    const k = 1 - Math.pow(0.001, dt * 0.25); // slow dolly
    target.current.x += (focusX * 0.45 - target.current.x) * k;
    camera.position.x += (focusX * 0.35 - camera.position.x) * k;
    camera.lookAt(target.current.x, 0.05, -0.9);
  });
  return null;
}

export default function PipelineScene({ stages, selected, onSelect, busy }: { stages: Stage[]; selected: string | null; onSelect: (n: string) => void; busy: boolean }) {
  const { curve, ts, positions } = useMemo(() => makeCurve(stages.length), [stages.length]);
  const runIdx = stages.findIndex((s) => s.status === "running");
  const failIdx = stages.findIndex((s) => s.status === "failed");
  const lastDone = stages.reduce((a, s, i) => (s.status === "done" || s.status === "skipped" ? i : a), -1);
  const focus = runIdx >= 0 ? runIdx : failIdx >= 0 ? failIdx : Math.max(0, lastDone);
  const upTo = runIdx >= 0 ? ts[runIdx] : failIdx >= 0 ? ts[failIdx] : lastDone >= 0 ? ts[lastDone] : 0;
  const groups = STAGE_GROUPS.map((g) => {
    const idx = g.stages.map((s) => stages.findIndex((x) => x.name === s)).filter((i) => i >= 0);
    const mid = positions[idx[Math.floor((idx.length - 1) / 2)]] ?? new THREE.Vector3();
    const midB = positions[idx[Math.ceil((idx.length - 1) / 2)]] ?? mid;
    return { name: g.name, pos: new THREE.Vector3((mid.x + midB.x) / 2, 0.95, (mid.z + midB.z) / 2 - 0.2) };
  });
  const summary = stages.map((s) => `${STAGE_LABEL[s.name] ?? s.name}: ${s.status}`).join(", ");

  return (
    <Scene3D busy={busy} label={`Pipeline stage. ${summary}`} className="h-full w-full" camera={{ position: [0, 2.6, 6.4], fov: 40 }}>
      <color attach="background" args={[color.bg.inset]} />
      <fog attach="fog" args={[color.bg.inset, 9, 22]} />
      <StudioLights intensity={0.9} shadowSize={10} />
      <CameraRig focusX={positions[focus]?.x ?? 0} />
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.001, 0]} receiveShadow>
        <planeGeometry args={[60, 30]} />
        <MeshReflectorMaterial
          blur={[400, 120]}
          resolution={512}
          mixBlur={1}
          mixStrength={1.2}
          roughness={0.85}
          depthScale={1}
          minDepthThreshold={0.4}
          maxDepthThreshold={1.2}
          color="#090b10"
          metalness={0.6}
          mirror={0.4}
        />
      </mesh>
      <Track curve={curve} upTo={upTo} />
      <Particles curve={curve} upTo={upTo} active={runIdx >= 0} />
      {stages.map((s, i) => (
        <Node key={s.name} stage={s} pos={positions[i]} selected={selected === s.name} onSelect={onSelect} />
      ))}
      {groups.map((g) => (
        <Html key={g.name} position={g.pos} center zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
          <div style={{ font: "400 12px/16px Inter, sans-serif", color: color.text.muted, whiteSpace: "nowrap" }}>{g.name}</div>
        </Html>
      ))}
    </Scene3D>
  );
}
