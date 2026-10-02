"use client";
/**
 * DEVIATION RIBBON (React Three Fiber): the 28-observation Sentinel-2 / Landsat
 * baseline at Shawka Dam, as z-scores against each sensor's own two-year mean.
 *
 * X = time, depth = index lane, height = z. The translucent slabs are the
 * |z| = 1.5 flag threshold; flagged points glow. The violet pillar is the
 * 2024-04-24 EnMAP date, which falls in the baseline's own coverage gap.
 */
import React, { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useReducedMotion } from "framer-motion";
import Label from "@/components/three/Label";
import type { InlandSummary, Observation } from "./types";
import { easeOutCubic, useInView } from "./visuals";

export const INDEX_LANES: { key: string; label: string }[] = [
  { key: "NDCI_chl_proxy", label: "NDCI · chlorophyll proxy" },
  { key: "NDTI_turbidity_proxy", label: "NDTI · turbidity proxy" },
  { key: "RedTideIndex_proxy", label: "red-edge ratio ('RedTideIndex')" },
  { key: "NDWI_water_check", label: "NDWI · water check" },
];
const SENSOR = { "sentinel-2-l2a": { name: "Sentinel-2", color: "#27C3F3" }, "landsat-c2-l2": { name: "Landsat", color: "#FFC23D" } } as Record<string, { name: string; color: string }>;
const T0 = Date.parse("2023-09-01"), T1 = Date.parse("2025-11-20"), XW = 15, YS = 0.55;
const xOf = (d: string) => -XW / 2 + ((Date.parse(d) - T0) / (T1 - T0)) * XW;
const zOf = (lane: number) => -2.25 + lane * 1.5;

export interface RibbonHover { date: string; sensor: string; index: string; z: number; flagged: boolean }

function Ribbon({ obs, zt, onHover, reduce }: { obs: Observation[]; zt: number; onHover: (h: RibbonHover | null) => void; reduce: boolean }) {
  const grow = useRef<THREE.Group>(null);
  const halos = useRef<THREE.Group>(null);
  const born = useRef<number | null>(null);
  useFrame(({ clock }) => {
    if (born.current == null) born.current = clock.elapsedTime;
    const k = reduce ? 1 : easeOutCubic((clock.elapsedTime - born.current) / 1.4);
    if (grow.current) grow.current.scale.y = Math.max(0.001, k);
    if (halos.current) halos.current.children.forEach((h, i) => { const s = 1 + (reduce ? 0 : 0.35 * (0.5 + 0.5 * Math.sin(clock.elapsedTime * 3 + i))); h.scale.setScalar(s); });
  });
  const series = useMemo(() => INDEX_LANES.flatMap((lane, li) => Object.keys(SENSOR).map((sensor) => ({
    lane: li, key: lane.key, sensor,
    pts: obs.filter((o) => o.sensor === sensor && Number.isFinite(o.z[lane.key])).map((o) => ({ o, p: [xOf(o.date), o.z[lane.key] * YS, zOf(li)] as [number, number, number] })),
  }))), [obs]);
  const flagged = series.flatMap((s) => s.pts.filter(({ o }) => Math.abs(o.z[s.key]) > zt).map((q) => ({ ...q, s })));
  return (
    <group>
      <group ref={grow}>
        {series.map((s) => s.pts.length > 1 && (
          <Line key={`${s.key}-${s.sensor}`} points={s.pts.map((q) => q.p)} color={SENSOR[s.sensor].color} lineWidth={1.8} transparent opacity={0.85} />
        ))}
        {series.flatMap((s) => s.pts.map(({ o, p }) => {
          const hit = Math.abs(o.z[s.key]) > zt;
          return (
            <mesh key={`${s.key}-${o.item_id}`} position={p}
              onPointerOver={(e) => { e.stopPropagation(); onHover({ date: o.date, sensor: SENSOR[s.sensor].name, index: INDEX_LANES[s.lane].label, z: o.z[s.key], flagged: hit }); }}
              onPointerOut={() => onHover(null)}>
              <sphereGeometry args={[hit ? 0.14 : 0.075, 16, 12]} />
              <meshBasicMaterial color={hit ? "#FF4D5E" : SENSOR[s.sensor].color} />
            </mesh>
          );
        }))}
        {/* stems from the zero plane make height readable from any angle */}
        {series.flatMap((s) => s.pts.map(({ o, p }) => (
          <Line key={`stem-${s.key}-${o.item_id}`} points={[[p[0], 0, p[2]], p]} color={SENSOR[s.sensor].color} lineWidth={0.8} transparent opacity={0.28} />
        )))}
        <group ref={halos}>
        {flagged.map(({ o, p, s }) => (
          <mesh key={`halo-${s.key}-${o.item_id}`} position={p} raycast={() => null}>
            <sphereGeometry args={[0.26, 16, 12]} />
            <meshBasicMaterial color="#FF4D5E" transparent opacity={0.18} depthWrite={false} blending={THREE.AdditiveBlending} />
          </mesh>
        ))}
        </group>
      </group>
    </group>
  );
}

export default function DeviationRibbon({ s, height = 360, onHover }: { s: InlandSummary; height?: number | string; onHover: (h: RibbonHover | null) => void }) {
  const reduce = !!useReducedMotion();
  const { ref, inView } = useInView<HTMLDivElement>();
  const zt = s.temporal.z_threshold;
  const enmap = "2024-04-24";
  const clusterX0 = xOf("2025-08-25"), clusterX1 = xOf("2025-11-08");
  const ticks = ["2023-09-01", "2024-03-01", "2024-09-01", "2025-03-01", "2025-09-01"];
  return (
    <div ref={ref} style={{ height }} className="relative">
      <Canvas camera={{ position: [0.6, 7.2, 14.2], fov: 42 }} dpr={[1, 1.75]} gl={{ antialias: true }} frameloop={inView ? "always" : "never"}>
        <color attach="background" args={["#040915"]} />
        <fog attach="fog" args={["#040915", 16, 34]} />
        <group position={[1.1, -0.6, 0]}>
          {/* zero plane and threshold slabs */}
          <mesh rotation={[-Math.PI / 2, 0, 0]} raycast={() => null}><planeGeometry args={[XW + 1, 6.4]} /><meshBasicMaterial color="#0A1630" transparent opacity={0.85} side={THREE.DoubleSide} /></mesh>
          <gridHelper args={[16, 16, "#1E3563", "#12244A"]} position={[0, 0.002, 0]} scale={[1, 1, 0.4]} />
          {[1, -1].map((sg) => (
            <mesh key={sg} rotation={[-Math.PI / 2, 0, 0]} position={[0, sg * zt * YS, 0]} raycast={() => null}>
              <planeGeometry args={[XW + 1, 6.4]} />
              <meshBasicMaterial color="#FF4D5E" transparent opacity={0.07} side={THREE.DoubleSide} depthWrite={false} />
            </mesh>
          ))}
          <Label text={`|z| = ${zt} flag threshold`} position={[XW / 2 + 0.2, zt * YS + 0.25, -3.2]} color="#FF8A9A" size={0.32} />
          {/* EnMAP pillar and the late-2025 cluster */}
          <Line points={[[xOf(enmap), -1.9, -3.2], [xOf(enmap), 2.2, -3.2], [xOf(enmap), 2.2, 3.2], [xOf(enmap), -1.9, 3.2]]} color="#8B7BFF" lineWidth={1.6} transparent opacity={0.8} />
          <mesh position={[xOf(enmap), 0.15, 0]} raycast={() => null}><boxGeometry args={[0.06, 4.1, 6.4]} /><meshBasicMaterial color="#8B7BFF" transparent opacity={0.12} depthWrite={false} /></mesh>
          <Label text="EnMAP 2024-04-24 (in the baseline gap)" position={[xOf(enmap), 2.55, -3.2]} color="#B9AFFF" size={0.32} />
          <mesh position={[(clusterX0 + clusterX1) / 2, 0.15, 0]} raycast={() => null}><boxGeometry args={[clusterX1 - clusterX0, 4.1, 6.4]} /><meshBasicMaterial color="#FFC23D" transparent opacity={0.06} depthWrite={false} /></mesh>
          <Label text="Sep–Oct 2025: both sensors" position={[(clusterX0 + clusterX1) / 2, 2.55, 3.2]} color="#FFD27A" size={0.32} />
          {INDEX_LANES.map((l, i) => <Label key={l.key} text={l.label} position={[-XW / 2 - 2.1, 0.05, zOf(i)]} color="#93A6CB" size={0.32} />)}
          {ticks.map((d) => <Label key={d} text={d.slice(0, 7)} position={[xOf(d), -0.05, 3.75]} color="#5D7299" size={0.32} />)}
          <Ribbon obs={s.temporal.observations} zt={zt} onHover={onHover} reduce={reduce} />
        </group>
        <OrbitControls enablePan={false} enableZoom={false} enableDamping maxPolarAngle={1.45} />
      </Canvas>
    </div>
  );
}
