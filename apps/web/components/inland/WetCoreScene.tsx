"use client";
/**
 * WET-CORE MAP (React Three Fiber): the 25 x 30 EnMAP window over Shawka Dam.
 *
 * One tile per 30 m pixel. Tiles inside the locked polygon are raised; pixels
 * the selected mask calls wet rise as water columns, and switching layers
 * animates between them. The outline is the AOI projected into the window
 * (rebuilt from the DLR STAC grid; 84 px inside, as the package reports).
 * Only derived classifications are drawn: no EnMAP reflectance reaches the
 * browser. Heights are categorical (inside / outside / wet), not terrain.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { ThreeEvent, useFrame } from "@react-three/fiber";
import Canvas from "@/components/three/ZoomCanvas";
import { Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useReducedMotion } from "framer-motion";
import Label from "@/components/three/Label";
import { FP_COLOR, MASK_KEYS, type FingerprintPixel, type InlandSummary, type MaskKey } from "./types";
import { useInView } from "./visuals";

export interface PixelHover { row: number; col: number; inside: boolean; wet: Record<MaskKey, boolean>; fp: FingerprintPixel | null }

const TILE_IN = 0.62, TILE_OUT = 0.18, WATER = 1.7;

const WATER_VERT = /* glsl */ `
varying vec3 vN; varying vec3 vW; varying float vH;
void main() {
  vec4 p = vec4(position, 1.0);
  vec3 n = normal;
  #ifdef USE_INSTANCING
    p = instanceMatrix * p;
    n = mat3(instanceMatrix) * n;
  #endif
  vec4 w = modelMatrix * p;
  vW = w.xyz;
  vN = normalize(mat3(modelMatrix) * n);
  vH = position.y + 0.5;
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

const WATER_FRAG = /* glsl */ `
uniform float uTime;
varying vec3 vN; varying vec3 vW; varying float vH;
void main() {
  vec3 N = normalize(vN);
  vec3 V = normalize(cameraPosition - vW);
  float fres = pow(1.0 - max(dot(N, V), 0.0), 2.4);
  float c = sin(vW.x * 3.1 + uTime * 1.7) * sin(vW.z * 2.7 - uTime * 1.3) + 0.5 * sin((vW.x + vW.z) * 4.3 + uTime * 2.1);
  float caust = smoothstep(0.55, 1.35, c);
  vec3 deep = vec3(0.02, 0.18, 0.42), shallow = vec3(0.10, 0.62, 0.92);
  vec3 col = mix(deep, shallow, clamp(vH, 0.0, 1.0));
  float top = step(0.9, N.y);
  col += top * caust * vec3(0.45, 0.85, 1.0) * 0.6;
  col += fres * vec3(0.30, 0.80, 1.0) * 0.9;
  gl_FragColor = vec4(col, 0.94);
}`;

function Window({ s, layer, onHover, reduce, hover }: {
  s: InlandSummary; layer: MaskKey; onHover: (h: PixelHover | null) => void; reduce: boolean; hover: [number, number] | null;
}) {
  const [rows, cols] = s.window.shape;
  const n = rows * cols;
  const X = (c: number) => c - cols / 2 + 0.5, Z = (r: number) => r - rows / 2 + 0.5;
  const inside = useMemo(() => new Set(s.window.inside_polygon_px.map(([r, c]) => r * cols + c)), [s, cols]);
  const wetSets = useMemo(() => Object.fromEntries(MASK_KEYS.map((k) => [k, new Set(s.masks[k].px.map(([r, c]) => r * cols + c))])) as Record<MaskKey, Set<number>>, [s, cols]);
  const waterIdx = useMemo(() => [...new Set(MASK_KEYS.flatMap((k) => [...wetSets[k]]))].sort((a, b) => a - b), [wetSets]);
  const fpByIdx = useMemo(() => {
    const out: Record<string, Map<number, FingerprintPixel>> = {};
    for (const [d, a] of Object.entries(s.anomaly.per_date || {})) out[d] = new Map(a.pixels.map((p) => [p.row * cols + p.col, p]));
    return out;
  }, [s, cols]);
  const fp = fpByIdx[layer];

  // ---- land tiles (static geometry, colour changes on hover)
  const tiles = useRef<THREE.InstancedMesh>(null);
  useEffect(() => {
    const m = tiles.current; if (!m) return;
    const o = new THREE.Object3D();
    for (let i = 0; i < n; i++) {
      const r = Math.floor(i / cols), c = i % cols, h = inside.has(i) ? TILE_IN : TILE_OUT;
      o.position.set(X(c), h / 2, Z(r)); o.scale.set(0.92, h, 0.92); o.updateMatrix();
      m.setMatrixAt(i, o.matrix);
    }
    m.instanceMatrix.needsUpdate = true;
  }, [n, cols, inside]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const m = tiles.current; if (!m) return;
    const cIn = new THREE.Color("#2A5C9E"), cOut = new THREE.Color("#0C1A33"), cHov = new THREE.Color("#FFC23D");
    const hv = hover ? hover[0] * cols + hover[1] : -1;
    for (let i = 0; i < n; i++) m.setColorAt(i, i === hv ? cHov : inside.has(i) ? cIn : cOut);
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, [hover, n, cols, inside]);

  // ---- water columns (animated between layers)
  const water = useRef<THREE.InstancedMesh>(null);
  const heights = useRef<Float32Array>(new Float32Array(0));
  const mat = useMemo(() => new THREE.ShaderMaterial({ vertexShader: WATER_VERT, fragmentShader: WATER_FRAG, uniforms: { uTime: { value: 0 } }, transparent: true }), []);
  useEffect(() => () => mat.dispose(), [mat]);
  useEffect(() => { heights.current = new Float32Array(waterIdx.length); }, [waterIdx]);
  const markers = useRef<THREE.Group>(null);
  const beam = useRef<THREE.Group>(null);
  useFrame(({ clock }, dt) => {
    const t = clock.elapsedTime;
    mat.uniforms.uTime.value = reduce ? 0 : t;
    const m = water.current;
    if (m) {
      const o = new THREE.Object3D();
      const k = reduce ? 1 : Math.min(1, dt * 4.5);
      waterIdx.forEach((idx, j) => {
        const target = wetSets[layer].has(idx) ? WATER + (reduce ? 0 : 0.12 * Math.sin(t * 1.8 + j * 0.9)) : 0.0001;
        heights.current[j] += (target - heights.current[j]) * k;
        const h = Math.max(0.0001, heights.current[j]);
        const r = Math.floor(idx / cols), c = idx % cols;
        o.position.set(X(c), TILE_IN + h / 2, Z(r)); o.scale.set(0.8, h, 0.8); o.updateMatrix();
        m.setMatrixAt(j, o.matrix);
      });
      m.instanceMatrix.needsUpdate = true;
    }
    if (markers.current && !reduce) markers.current.children.forEach((ch, j) => { ch.position.y = TILE_IN + WATER + 0.75 + 0.12 * Math.sin(t * 2 + j); ch.rotation.y = t * 0.8 + j; });
    if (beam.current) {
      beam.current.visible = !reduce;
      const period = 7, k = (t % period) / 4.2;
      beam.current.position.z = -rows / 2 - 1 + Math.min(1, k) * (rows + 2);
      (beam.current.children as THREE.Mesh[]).forEach((ch) => { (ch.material as THREE.MeshBasicMaterial).opacity = k <= 1 ? (ch.userData.base as number) : 0; });
    }
  });

  const move = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    const i = e.instanceId; if (i == null) return;
    const r = Math.floor(i / cols), c = i % cols;
    if (hover && hover[0] === r && hover[1] === c) return;
    onHover({ row: r, col: c, inside: inside.has(i), wet: Object.fromEntries(MASK_KEYS.map((k) => [k, wetSets[k].has(i)])) as Record<MaskKey, boolean>,
              fp: fp?.get(i) || fpByIdx["2024-04-24"]?.get(i) || null });
  };

  const poly = s.window.polygon_px.map(([c, r]) => [c - cols / 2, TILE_IN + 0.03, r - rows / 2] as [number, number, number]);
  const core = s.masks.persistent_core.px;
  const cx = core.length ? core.reduce((a, [, c]) => a + X(c), 0) / core.length : 0;
  const cz = core.length ? core.reduce((a, [r]) => a + Z(r), 0) / core.length : 0;
  return (
    <group>
      <instancedMesh ref={tiles} args={[undefined, undefined, n]} onPointerMove={move} onPointerOut={() => onHover(null)}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.55} metalness={0.15} />
      </instancedMesh>
      <instancedMesh ref={water} args={[undefined, undefined, Math.max(1, waterIdx.length)]} material={mat} raycast={() => null}>
        <boxGeometry args={[1, 1, 1]} />
      </instancedMesh>
      <Line points={poly} color="#27C3F3" lineWidth={2.4} />
      <Line points={poly.map(([x, y, z]) => [x, y + 0.02, z] as [number, number, number])} color="#27C3F3" lineWidth={9} transparent opacity={0.16} />
      {fp && (
        <group ref={markers}>
          {[...fp.values()].map((p) => (
            <mesh key={`${p.row}-${p.col}`} position={[X(p.col), TILE_IN + WATER + 0.75, Z(p.row)]} raycast={() => null}>
              <octahedronGeometry args={[0.24]} />
              <meshBasicMaterial color={FP_COLOR[p.top_class || ""] || "#93A6CB"} />
            </mesh>
          ))}
        </group>
      )}
      {layer === "mndwi_core" && <Label text="Water index: 0 pixels" position={[cx, TILE_IN + 2.6, cz]} color="#FF8A3D" size={0.6} bold />}
      <pointLight position={[cx, 3.2, cz]} color="#27C3F3" intensity={layer === "mndwi_core" ? 4 : 14} distance={12} decay={1.6} />
      <group ref={beam}>
        <mesh position={[0, 1.6, 0]} raycast={() => null} userData={{ base: 0.09 }}>
          <planeGeometry args={[cols + 2, 3.2]} />
          <meshBasicMaterial color="#27C3F3" transparent opacity={0.09} side={THREE.DoubleSide} depthWrite={false} blending={THREE.AdditiveBlending} />
        </mesh>
        <mesh position={[0, TILE_IN + 0.04, 0]} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null} userData={{ base: 0.55 }}>
          <planeGeometry args={[cols + 2, 0.12]} />
          <meshBasicMaterial color="#9BE7FF" transparent opacity={0.55} depthWrite={false} blending={THREE.AdditiveBlending} />
        </mesh>
      </group>
      {/* north arrow and 300 m scale bar */}
      <Line points={[[-cols / 2 - 2, 0.05, -rows / 2 + 2], [-cols / 2 - 2, 0.05, -rows / 2 - 1.2]]} color="#EAF1FF" lineWidth={2} />
      <Line points={[[-cols / 2 - 2.5, 0.05, -rows / 2 - 0.4], [-cols / 2 - 2, 0.05, -rows / 2 - 1.2], [-cols / 2 - 1.5, 0.05, -rows / 2 - 0.4]]} color="#EAF1FF" lineWidth={2} />
      <Label text="N" position={[-cols / 2 - 2, 0.5, -rows / 2 - 2]} color="#EAF1FF" size={0.8} bold />
      <Line points={[[-cols / 2, 0.05, rows / 2 + 1.4], [-cols / 2 + 10, 0.05, rows / 2 + 1.4]]} color="#FFC23D" lineWidth={2.4} />
      <Label text="300 m (10 px)" position={[-cols / 2 + 5, 0.5, rows / 2 + 2.4]} color="#FFC23D" size={0.62} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} raycast={() => null}>
        <planeGeometry args={[140, 140]} />
        <meshStandardMaterial color="#050C1C" roughness={1} />
      </mesh>
      <gridHelper args={[90, 90, "#16284D", "#0C1A33"]} position={[0, -0.01, 0]} />
    </group>
  );
}

export default function WetCoreScene({ s, layer, onHover, height = 420 }: {
  s: InlandSummary; layer: MaskKey; onHover: (h: PixelHover | null) => void; height?: number | string;
}) {
  const reduce = !!useReducedMotion();
  const { ref, inView } = useInView<HTMLDivElement>();
  const [hover, setHover] = useState<[number, number] | null>(null);
  const [auto, setAuto] = useState(true);
  const handle = (h: PixelHover | null) => { setHover(h ? [h.row, h.col] : null); onHover(h); };
  return (
    <div ref={ref} style={{ height }} className="relative">
      <Canvas camera={{ position: [-12.5, 15.5, 19.5], fov: 38 }} dpr={[1, 1.75]} gl={{ antialias: true }} frameloop={inView ? "always" : "never"}>
        <color attach="background" args={["#040915"]} />
        <fog attach="fog" args={["#040915", 34, 80]} />
        <ambientLight intensity={0.55} />
        <directionalLight position={[12, 20, 9]} intensity={1.15} />
        <directionalLight position={[-14, 8, -10]} intensity={0.35} color="#4D93FF" />
        <Window s={s} layer={layer} onHover={handle} reduce={reduce} hover={hover} />
        <OrbitControls enablePan={false} enableZoom={false} enableDamping maxPolarAngle={1.32} target={[0, 0, 1.5]}
          autoRotate={auto && !reduce} autoRotateSpeed={0.45} onStart={() => setAuto(false)} />
      </Canvas>
    </div>
  );
}
