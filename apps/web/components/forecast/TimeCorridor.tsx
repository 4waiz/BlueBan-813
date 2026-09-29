"use client";
/**
 * Space-time corridor for the drift SCENARIO (pipeline/forecast.py).
 * X/Y = geography (local metres), Z = FORECAST TIME. Z is never depth.
 * The drift is wind-only (3 % of the 10 m wind + diffusion): a scenario
 * trajectory estimate, not a validated ocean forecast.
 */
import React, { useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import Label from "@/components/three/Label";
import * as THREE from "three";

export interface DriftStep { hours: number; centroid: [number, number]; spread_radius_m: number; particles?: [number, number][]; bearing_deg?: number; displacement_m?: number }

function Corridor({ steps, sel }: { steps: DriftStep[]; sel: number }) {
  const o = steps[0].centroid;
  const toXY = (lon: number, lat: number) => {
    const x = (lon - o[0]) * 111320 * Math.cos((o[1] * Math.PI) / 180), y = (lat - o[1]) * 110540;
    return [x, y] as [number, number];
  };
  const maxR = Math.max(...steps.map((s) => s.spread_radius_m + Math.hypot(...toXY(...s.centroid))), 500);
  const k = 1.2 / maxR, zk = 2.4 / Math.max(1, steps[steps.length - 1].hours);
  const cols = ["#FF4D5E", "#FF8A3D", "#FFC23D", "#23D484", "#27C3F3", "#4D93FF"];
  const pts = steps.map((s) => { const [x, y] = toXY(...s.centroid); return new THREE.Vector3(x * k, y * k, s.hours * zk - 1.2); });
  return (
    <group rotation={[-1.05, 0, 0.55]}>
      <gridHelper args={[3, 12, "#16284D", "#0D1C3B"]} rotation={[Math.PI / 2, 0, 0]} position={[0, 0, -1.2]} />
      <Line points={pts} color="#EAF1FF" lineWidth={1.2} transparent opacity={0.6} />
      {steps.map((s, i) => {
        const [x, y] = toXY(...s.centroid);
        const r = Math.max(0.03, s.spread_radius_m * k);
        return (
          <group key={s.hours} position={[x * k, y * k, s.hours * zk - 1.2]}>
            <mesh><circleGeometry args={[r, 48]} /><meshBasicMaterial color={cols[i % cols.length]} transparent opacity={i === sel ? 0.55 : 0.2} side={THREE.DoubleSide} depthWrite={false} /></mesh>
            {(s.particles || []).slice(0, 180).map((p, j) => { const [px, py] = toXY(p[0], p[1]); return <mesh key={j} position={[(px - x) * k, (py - y) * k, 0.001]}><circleGeometry args={[0.008, 6]} /><meshBasicMaterial color={cols[i % cols.length]} /></mesh>; })}
            <Label text={s.hours === 0 ? "Now" : `+${s.hours}h`} position={[r + 0.18, 0, 0]} color={cols[i % cols.length]} size={0.12} bold />
          </group>
        );
      })}
      <Line points={[[-1.5, -1.5, -1.2], [-1.5, -1.5, 1.2]]} color="#93A6CB" lineWidth={1} />
      <Label text="TIME (not depth)" position={[-1.5, -1.5, 1.4]} size={0.12} bold />
    </group>
  );
}

export default function TimeCorridor({ steps, height = 260, wind }: { steps: DriftStep[] | null; height?: number | string; wind?: { speed_kmh?: number; from?: string } | null }) {
  const [sel, setSel] = useState(0);
  const ok = useMemo(() => (steps || []).filter((s) => s.centroid && Number.isFinite(s.centroid[0])), [steps]);
  if (!ok.length) return <div className="grid place-items-center text-[12px] text-dim" style={{ height }}>No drift scenario for this incident</div>;
  return (
    <div className="relative" style={{ height }}>
      <Canvas camera={{ position: [0, -0.4, 4.6], fov: 38 }} dpr={[1, 1.75]}>
        <color attach="background" args={["#040915"]} />
        <Corridor steps={ok} sel={sel} />
        <OrbitControls enablePan={false} minDistance={2.5} maxDistance={7} />
      </Canvas>
      {wind && <div className="panel-flat absolute right-2 top-9 px-2 py-1 text-[10.5px] text-muted">Wind {wind.speed_kmh?.toFixed(0)} km/h from {wind.from}</div>}
      <div className="absolute left-2 top-2 rounded bg-void/80 px-2 py-1 text-[10px] font-bold tracking-wider text-caution">SCENARIO TRAJECTORY ESTIMATE · wind-only</div>
      <div className="absolute inset-x-2 bottom-2 flex items-center gap-2">
        {ok.map((s, i) => (
          <button key={s.hours} onClick={() => setSel(i)} className={`flex-1 rounded-md border px-1 py-1 text-[11px] font-semibold ${i === sel ? "border-beam bg-beam/20 text-ink" : "border-edge text-muted"}`}>{s.hours === 0 ? "Now" : `+${s.hours}h`}</button>
        ))}
      </div>
    </div>
  );
}
