"use client";
/**
 * SPECTRAL DATA CUBE viewer (React Three Fiber).
 *
 * X = image column, Y = image row, Z = WAVELENGTH. This is a picture of a
 * data structure, not of a physical ocean volume, and the viewer says so.
 * Cubes are display-ready reductions written offline by
 * scripts/build_cubes.py (uint8-quantised, spatially downsampled): a browser
 * never receives a raw gigabyte cube.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { ThreeEvent, useFrame } from "@react-three/fiber";
import Canvas from "@/components/three/ZoomCanvas";
import { Line, OrbitControls } from "@react-three/drei";
import Label from "@/components/three/Label";
import * as THREE from "three";
import { useReducedMotion } from "framer-motion";
import { pipelineUrl } from "@/lib/engine";

export interface CubeMeta {
  name: string; sensor: string; simulated: boolean; source: string;
  shape: [number, number, number]; wavelengths_nm: number[]; valid_band: boolean[];
  scale: { offset: number; step: number }; units: string; date?: string; bounds?: number[];
  band_centres_813?: number[]; note?: string;
}

function turbo(t: number): [number, number, number] {
  t = Math.min(1, Math.max(0, t));
  const r = 34.61 + t * (1172.33 - t * (10793.56 - t * (33300.12 - t * (38394.49 - t * 14825.05))));
  const g = 23.31 + t * (557.33 + t * (1225.33 - t * (3574.96 - t * (1073.77 + t * 707.56))));
  const b = 27.2 + t * (3211.1 - t * (15327.97 - t * (27814 - t * (22569.18 - t * 6838.66))));
  return [Math.max(0, Math.min(255, r)), Math.max(0, Math.min(255, g)), Math.max(0, Math.min(255, b))];
}

function Slices({ meta, data, sel, onPick, scanning }: { meta: CubeMeta; data: Uint8Array; sel: number; onPick: (r: number, c: number) => void; scanning: boolean }) {
  const [nb, rows, cols] = meta.shape;
  const aspect = cols / rows;
  const w = 2.2 * Math.min(1, aspect), h = 2.2 * Math.min(1, 1 / aspect), depth = 2.6;
  const zOf = (i: number) => -depth / 2 + (i / Math.max(1, nb - 1)) * depth;
  const textures = useMemo(() => {
    const out: (THREE.DataTexture | null)[] = [];
    for (let b = 0; b < nb; b++) {
      if (!meta.valid_band[b]) { out.push(null); continue; }
      const px = rows * cols, rgba = new Uint8Array(px * 4);
      let lo = 255, hi = 0;
      for (let i = 0; i < px; i++) { const v = data[b * px + i]; if (v && v < lo) lo = v; if (v > hi) hi = v; }
      for (let i = 0; i < px; i++) {
        const v = data[b * px + i];
        const [r, g, bl] = turbo((v - lo) / Math.max(1, hi - lo));
        rgba[i * 4] = r; rgba[i * 4 + 1] = g; rgba[i * 4 + 2] = bl; rgba[i * 4 + 3] = v === 0 ? 0 : 255;
      }
      const tex = new THREE.DataTexture(rgba, cols, rows, THREE.RGBAFormat);
      tex.flipY = true; tex.needsUpdate = true; tex.magFilter = THREE.NearestFilter;
      out.push(tex);
    }
    return out;
  }, [meta, data, nb, rows, cols]);
  useEffect(() => () => textures.forEach((t) => t?.dispose()), [textures]);
  const scan = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (scan.current) { scan.current.visible = scanning; scan.current.position.z = zOf(((clock.elapsedTime * 0.25) % 1) * (nb - 1)); }
  });
  const pick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    const uv = e.uv; if (!uv) return;
    onPick(Math.min(rows - 1, Math.floor((1 - uv.y) * rows)), Math.min(cols - 1, Math.floor(uv.x * cols)));
  };
  return (
    <group rotation={[-0.35, 0.55, 0]}>
      {textures.map((tex, b) => tex ? (
        <mesh key={b} position={[0, 0, zOf(b)]} onClick={b === sel ? pick : undefined}>
          <planeGeometry args={[w, h]} />
          <meshBasicMaterial map={tex} transparent opacity={b === sel ? 1 : 0.06 + 0.1 * (1 - Math.abs(b - sel) / nb)} side={THREE.DoubleSide} depthWrite={b === sel} />
        </mesh>
      ) : (
        <Line key={b} points={[[-w / 2, -h / 2, zOf(b)], [w / 2, -h / 2, zOf(b)], [w / 2, h / 2, zOf(b)], [-w / 2, h / 2, zOf(b)], [-w / 2, -h / 2, zOf(b)]]} color="#FF4D5E" lineWidth={0.6} dashed dashSize={0.05} gapSize={0.05} transparent opacity={0.35} />
      ))}
      <mesh ref={scan} position={[0, 0, 0]}><planeGeometry args={[w * 1.04, h * 1.04]} /><meshBasicMaterial color="#27C3F3" transparent opacity={0.16} side={THREE.DoubleSide} depthWrite={false} /></mesh>
      <lineSegments>
        <edgesGeometry args={[new THREE.BoxGeometry(w, h, depth)]} />
        <lineBasicMaterial color="#4D93FF" transparent opacity={0.45} />
      </lineSegments>
      <Line points={[[w / 2 + 0.12, -h / 2, -depth / 2], [w / 2 + 0.12, -h / 2, depth / 2]]} color="#FFC23D" lineWidth={1.4} />
      {[0, Math.floor((nb - 1) / 2), nb - 1].map((b) => (
        <Label key={b} text={`${Math.round(meta.wavelengths_nm[b])} nm`} position={[w / 2 + 0.42, -h / 2, zOf(b)]} color="#FFC23D" size={0.13} />
      ))}
      <Label text="X, Y = image pixels · Z = wavelength" position={[0, h / 2 + 0.2, 0]} size={0.11} />
    </group>
  );
}

export default function CubeViewer({ name, height = 300, onSpectrum, compact = false, sweep = false }: {
  name: string; height?: number | string; compact?: boolean;
  /** Step the wavelength slice automatically (Judge Mode); off under reduced motion. */
  sweep?: boolean;
  onSpectrum?: (s: { wavelengths_nm: number[]; values: (number | null)[]; row: number; col: number }) => void;
}) {
  const [meta, setMeta] = useState<CubeMeta | null>(null);
  const [data, setData] = useState<Uint8Array | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState(0);
  const [scanning, setScanning] = useState(sweep);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!sweep || reduce || !meta) return;
    const t = setInterval(() => setSel((s) => (s + 1) % meta.shape[0]), 900);
    return () => clearInterval(t);
  }, [sweep, reduce, meta]);
  useEffect(() => {
    let dead = false;
    setMeta(null); setData(null); setErr(null);
    Promise.all([fetch(pipelineUrl(`cube/${name}.json`)).then((r) => (r.ok ? r.json() : Promise.reject(new Error("cube not built")))),
                 fetch(pipelineUrl(`cube/${name}.bin`)).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error("cube data missing"))))])
      .then(([m, b]) => { if (dead) return; setMeta(m); setData(new Uint8Array(b)); setSel(Math.max(0, m.wavelengths_nm.findIndex((w: number) => w >= 665))); })
      .catch((e) => { if (!dead) setErr(e.message); });
    return () => { dead = true; };
  }, [name]);
  const pick = (r: number, c: number) => {
    if (!meta || !data || !onSpectrum) return;
    const [nb, rows, cols] = meta.shape, px = rows * cols;
    const vals = Array.from({ length: nb }, (_, b) => {
      const v = data[b * px + r * cols + c];
      return !meta.valid_band[b] || v === 0 ? null : meta.scale.offset + v * meta.scale.step;
    });
    onSpectrum({ wavelengths_nm: meta.wavelengths_nm, values: vals, row: r, col: c });
  };
  if (err) return <div className="grid place-items-center text-[12px] text-dim" style={{ height }}>3D cube not available ({err})</div>;
  if (!meta || !data) return <div className="grid place-items-center text-[12px] text-dim" style={{ height }}>Loading 3D cube…</div>;
  return (
    <div style={{ height }} className="relative">
      <Canvas camera={{ position: [0, 0, 4.4], fov: 42 }} dpr={[1, 1.75]} gl={{ antialias: true }}>
        <color attach="background" args={["#040915"]} />
        <Slices meta={meta} data={data} sel={sel} onPick={pick} scanning={scanning && !reduce} />
        <OrbitControls enablePan enableZoom minDistance={2.2} maxDistance={8} />
      </Canvas>
      <div className={`absolute left-2 top-2 truncate rounded bg-void/80 px-2 py-1 text-[10px] font-bold tracking-wider text-muted ${compact ? "max-w-[calc(100%-1rem)]" : "max-w-[48%]"}`}
        title="The cube's depth axis is wavelength, not sea depth">
        {compact ? "Depth = wavelength" : "Cube depth = wavelength, not sea depth"}
      </div>
      <div className="absolute inset-x-2 bottom-2 flex items-center gap-2">
        <span className="hud-value shrink-0 whitespace-nowrap rounded bg-void/80 px-1.5 py-0.5 text-[11px] text-caution">{Math.round(meta.wavelengths_nm[sel])} nm</span>
        <input type="range" min={0} max={meta.shape[0] - 1} value={sel} onChange={(e) => setSel(Number(e.target.value))} className="w-full min-w-0 flex-1 accent-[#FFC23D]" aria-label="Wavelength slice" />
        {!compact && <button onClick={() => setScanning((s) => !s)} className="btn shrink-0 whitespace-nowrap px-2 py-1 text-[11px]">{scanning ? "Stop scan" : "Scan"}</button>}
      </div>
      {!compact && <div className="absolute right-2 top-2 max-w-[48%] text-right text-[10px] text-muted">{meta.sensor}{meta.simulated ? " · SIMULATED" : ""} · click the bright slice for one pixel&apos;s spectrum</div>}
    </div>
  );
}
