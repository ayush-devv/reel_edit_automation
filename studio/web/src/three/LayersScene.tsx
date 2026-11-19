// FR-5 exploded timeline: each layer of the edit is a translucent plane along time, pulled apart in depth.
// Click a block to read the Editor's reason; collapse animates the stack back together (600 ms ease-out).
import { Html, OrbitControls, RoundedBox } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef, useState } from "react";
import * as THREE from "three";
import type { Layer, LayerBlock } from "../lib/layers";
import { color } from "../theme/tokens";
import { easeOut, Scene3D, StudioLights } from "./common";

const WIDTH = 12;
const PLANE_H = 0.62;
const GAP = 0.95;

interface Props {
  layers: Layer[];
  duration: number;
  time: number;
  exploded: boolean;
  selected: string | null;
  onSelect: (layer: Layer, block: LayerBlock) => void;
  busy: boolean;
}

function Block({ layer, block, x0, x1, selected, onSelect, audio }: { layer: Layer; block: LayerBlock; x0: number; x1: number; selected: boolean; onSelect: Props["onSelect"]; audio: boolean }) {
  const [hover, setHover] = useState(false);
  const w = Math.max(0.06, x1 - x0 - 0.03);
  const h = audio ? 0.14 : PLANE_H - 0.16;
  return (
    <RoundedBox
      args={[w, h, audio ? 0.05 : 0.08]}
      radius={0.025}
      smoothness={3}
      position={[(x0 + x1) / 2, 0, 0.04]}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(layer, block);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHover(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHover(false);
        document.body.style.cursor = "";
      }}
    >
      <meshStandardMaterial
        color={layer.color}
        emissive={layer.color}
        emissiveIntensity={selected ? 1.4 : hover ? 0.9 : 0.45}
        transparent
        opacity={selected || hover ? 0.98 : 0.82}
        roughness={0.4}
        metalness={0.1}
      />
    </RoundedBox>
  );
}

function LayerPlane({ layer, index, total, explode, toX, selected, onSelect }: { layer: Layer; index: number; total: number; explode: React.MutableRefObject<number>; toX: (t: number) => number; selected: string | null; onSelect: Props["onSelect"] }) {
  const g = useRef<THREE.Group>(null);
  const audio = layer.kind === "audio";
  useFrame(() => {
    if (!g.current) return;
    const e = explode.current;
    if (audio) {
      // stems: thin ribbons in front of and below the picture stack
      const k = index - total;
      g.current.position.z = 0.5 + k * 0.35 * e;
      g.current.position.y = -0.62 - k * 0.24 * (0.5 + 0.5 * e);
    } else {
      // picture layers: a staircase going back in depth, so every plane and label stays readable
      g.current.position.z = -index * GAP * e;
      g.current.position.y = index * 0.4 * e;
    }
  });
  return (
    <group ref={g}>
      {!audio && (
        <mesh receiveShadow>
          <planeGeometry args={[WIDTH + 0.3, PLANE_H]} />
          <meshPhysicalMaterial color={layer.color} transparent opacity={0.1} roughness={0.2} transmission={0.2} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      {!audio && (
        <lineSegments>
          <edgesGeometry args={[new THREE.PlaneGeometry(WIDTH + 0.3, PLANE_H)]} />
          <lineBasicMaterial color={layer.color} transparent opacity={0.55} />
        </lineSegments>
      )}
      {layer.blocks.map((b, i) => (
        <Block key={`${b.id}-${i}`} layer={layer} block={b} x0={toX(b.start)} x1={toX(b.end)} selected={selected === `${layer.id}:${b.id}:${b.start}`} onSelect={onSelect} audio={audio} />
      ))}
      <Html position={[-WIDTH / 2 - 0.35, 0, 0]} center={false} style={{ transform: "translate(-100%, -50%)", pointerEvents: "none" }} zIndexRange={[5, 0]}>
        <div style={{ font: "600 12px/16px Inter, sans-serif", color: layer.color, whiteSpace: "nowrap", textShadow: "0 1px 6px #000" }}>{layer.label}</div>
      </Html>
    </group>
  );
}

function Stack({ layers, duration, time, exploded, selected, onSelect }: Omit<Props, "busy">) {
  const explode = useRef(exploded ? 1 : 0);
  const anim = useRef({ from: explode.current, to: exploded ? 1 : 0, t: 1 });
  if (anim.current.to !== (exploded ? 1 : 0)) anim.current = { from: explode.current, to: exploded ? 1 : 0, t: 0 };
  const playhead = useRef<THREE.Mesh>(null);
  const toX = (t: number) => -WIDTH / 2 + (t / duration) * WIDTH;
  const pictures = layers.filter((l) => l.kind === "picture");
  const audios = layers.filter((l) => l.kind === "audio");

  useFrame((_, dt) => {
    const a = anim.current;
    if (a.t < 1) {
      a.t = Math.min(1, a.t + dt / 0.6);
      explode.current = a.from + (a.to - a.from) * easeOut(a.t);
    }
    if (playhead.current) {
      const e = explode.current;
      const depth = (pictures.length - 1) * GAP * e;
      const rise = (pictures.length - 1) * 0.4 * e;
      playhead.current.position.set(toX(time), rise / 2 - 0.35, -depth / 2 + 0.25);
      playhead.current.scale.set(1, rise + 2.2, depth + 1.6);
    }
  });

  return (
    <group position={[1.1, -0.2, 0]}>
      {pictures.map((l, i) => (
        <LayerPlane key={l.id} layer={l} index={i} total={pictures.length} explode={explode} toX={toX} selected={selected} onSelect={onSelect} />
      ))}
      {audios.map((l, i) => (
        <LayerPlane key={l.id} layer={l} index={pictures.length + i} total={pictures.length} explode={explode} toX={toX} selected={selected} onSelect={onSelect} />
      ))}
      <mesh ref={playhead} position={[toX(time), -0.35, 0]}>
        <boxGeometry args={[0.02, 1, 1]} />
        {/* Playhead: amber (you are here). */}
        <meshBasicMaterial color={color.signal.DEFAULT} transparent opacity={0.3} toneMapped={false} depthWrite={false} />
      </mesh>
    </group>
  );
}

export default function LayersScene({ busy, ...props }: Props) {
  return (
    <Scene3D busy={busy} label="Exploded layers of the edit along time. Use the flat view for a list of every block." className="h-full w-full" camera={{ position: [3.2, 2.4, 11.5], fov: 42 }}>
      <color attach="background" args={[color.bg.inset]} />
      <fog attach="fog" args={[color.bg.inset, 16, 32]} />
      <StudioLights intensity={0.8} shadowSize={9} />
      <Stack {...props} />
      <OrbitControls makeDefault enablePan={false} minDistance={7} maxDistance={18} minPolarAngle={0.7} maxPolarAngle={1.55} minAzimuthAngle={-0.8} maxAzimuthAngle={0.9} enableDamping target={[0.4, 0.6, -2]} />
    </Scene3D>
  );
}
