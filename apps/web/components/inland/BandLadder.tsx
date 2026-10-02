"use client";
/**
 * EnMAP -> 813 BAND LADDER (React Three Fiber).
 *
 * Every EnMAP band (224, 418-2445 nm) and every simulated Satellite 813 band
 * (205, 400-1700 nm, 5 nm) as a bar on one wavelength axis. Red 813 bars have
 * no real EnMAP support (the simulator leaves them empty rather than invent
 * them); dim red EnMAP bars are the ones dropped for nodata. "Show F2" adds the
 * 2022-09-08 band table as DLR's STAC publishes it, with the bands that differ
 * from the table the package used drawn as links.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, ThreeEvent, useFrame } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useReducedMotion } from "framer-motion";
import Label from "@/components/three/Label";
import type { InlandSummary } from "./types";
import { easeOutCubic, useInView, wavelengthColor } from "./visuals";

const NM0 = 380, NM1 = 2470, XW = 19;
const xOf = (nm: number) => -XW / 2 + ((nm - NM0) / (NM1 - NM0)) * XW;
const wOf = (fwhm: number) => Math.max(0.055, (fwhm / (NM1 - NM0)) * XW * 0.9);
const Z_ENMAP = -0.9, Z_813 = 0.9, Z_2022 = -2.6;

export interface BandHover { sensor: string; band: string; nm: number; fwhm: number; note: string }

interface Bar { x: number; w: number; h: number; z: number; color: THREE.Color; info: BandHover; delay: number }

function Bars({ bars, onHover, reduce }: { bars: Bar[]; onHover: (h: BandHover | null) => void; reduce: boolean }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const born = useRef<number | null>(null);
  const done = useRef(false);
  useEffect(() => {
    const m = mesh.current; if (!m) return;
    bars.forEach((b, i) => m.setColorAt(i, b.color));
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    done.current = false; born.current = null;
  }, [bars]);
  useFrame(({ clock }) => {
    const m = mesh.current; if (!m || done.current) return;
    if (born.current == null) born.current = clock.elapsedTime;
    const t = clock.elapsedTime - born.current;
    const o = new THREE.Object3D();
    let all = true;
    bars.forEach((b, i) => {
      const k = reduce ? 1 : easeOutCubic((t - b.delay) / 0.6);
      if (k < 1) all = false;
      const h = Math.max(0.0001, b.h * k);
      o.position.set(b.x, h / 2, b.z); o.scale.set(b.w, h, 0.55); o.updateMatrix();
      m.setMatrixAt(i, o.matrix);
    });
    m.instanceMatrix.needsUpdate = true;
    done.current = all;
  });
  const move = (e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); if (e.instanceId != null) onHover(bars[e.instanceId].info); };
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, Math.max(1, bars.length)]} onPointerMove={move} onPointerOut={() => onHover(null)}>
      <boxGeometry args={[1, 1, 1]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

export default function BandLadder({ s, showF2, height = 360, onHover }: { s: InlandSummary; showF2: boolean; height?: number | string; onHover: (h: BandHover | null) => void }) {
  const reduce = !!useReducedMotion();
  const { ref, inView } = useInView<HTMLDivElement>();
  const sat = s.satellite813;
  const dropped = useMemo(() => new Set(Object.values(s.masks.bad_bands_dropped_per_date || {}).flat()), [s]);
  const unsupported = sat.simulation_support?.["2024-04-24"]?.unsupported_ranges_nm || [];
  const isUnsupported = (nm: number) => unsupported.some(([a, b]) => nm >= a - 0.01 && nm <= b + 0.01);
  const delta22 = sat.band_table_check.delta_2022_minus_package_nm;
  const bars = useMemo<Bar[]>(() => {
    const out: Bar[] = [];
    sat.enmap_bands_package.forEach((b, i) => {
      const bad = dropped.has(b.n);
      out.push({ x: xOf(b.nm), w: wOf(b.fwhm), h: bad ? 0.35 : 1.25, z: Z_ENMAP, delay: i * 0.006,
        color: bad ? new THREE.Color("#5A1C2A") : wavelengthColor(b.nm),
        info: { sensor: "EnMAP L2A", band: `B${String(b.n).padStart(3, "0")}`, nm: b.nm, fwhm: b.fwhm, note: bad ? "missing data, not used" : "EnMAP band" } });
    });
    sat.spec813.centres_nm.forEach((nm, i) => {
      const un = isUnsupported(nm);
      out.push({ x: xOf(nm), w: wOf(sat.spec813.fwhm_nm), h: un ? 0.3 : 1.25, z: Z_813, delay: 0.25 + i * 0.006,
        color: un ? new THREE.Color("#FF4D5E") : wavelengthColor(nm).lerp(new THREE.Color("#FFFFFF"), 0.12),
        info: { sensor: "Satellite 813 (SIMULATED)", band: `#${i + 1}`, nm, fwhm: sat.spec813.fwhm_nm, note: un ? "no EnMAP data here, so left empty" : "built from real EnMAP bands" } });
    });
    if (showF2) {
      sat.enmap_bands_package.forEach((b, i) => {
        const d = delta22[i] ?? 0, nm = b.nm + d, off = Math.abs(d) > 5;
        out.push({ x: xOf(nm), w: wOf(b.fwhm), h: off ? 1.05 : 0.55, z: Z_2022, delay: i * 0.004,
          color: off ? new THREE.Color(Math.abs(d) > 50 ? "#FF4D5E" : "#FFC23D") : new THREE.Color("#2A3F6E"),
          info: { sensor: "EnMAP Sep 2022 (real positions)", band: `B${String(b.n).padStart(3, "0")}`, nm, fwhm: b.fwhm,
                  note: off ? `${d.toFixed(1)} nm away from the table used (note F2)` : `matches the table used` } });
      });
    }
    return out;
  }, [sat, dropped, showF2, delta22]); // eslint-disable-line react-hooks/exhaustive-deps
  const links = useMemo(() => showF2 ? sat.enmap_bands_package.map((b, i) => ({ b, d: delta22[i] ?? 0 })).filter(({ d }) => Math.abs(d) > 5) : [], [showF2, sat, delta22]);
  const ov = sat.coverage_comparison?.["2024-04-24"]?.overlap_range_nm || [420, 1700];
  const ticks = [400, 700, 1000, 1400, 1700, 2000, 2400];
  return (
    <div ref={ref} style={{ height }} className="relative">
      <Canvas camera={{ position: [0.4, 7.6, 14.2], fov: 42 }} dpr={[1, 1.75]} gl={{ antialias: true }} frameloop={inView ? "always" : "never"}>
        <color attach="background" args={["#040915"]} />
        <group position={[0.4, -1.1, showF2 ? 0.9 : 0]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[(xOf(ov[0]) + xOf(ov[1])) / 2, 0.001, 0]} raycast={() => null}>
            <planeGeometry args={[xOf(ov[1]) - xOf(ov[0]), 3.2]} />
            <meshBasicMaterial color="#27C3F3" transparent opacity={0.07} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.002, showF2 ? -0.8 : 0]} raycast={() => null}>
            <planeGeometry args={[XW + 1.2, showF2 ? 5.4 : 3.6]} />
            <meshBasicMaterial color="#0A1630" />
          </mesh>
          <Bars bars={bars} onHover={onHover} reduce={reduce} />
          {links.map(({ b, d }) => (
            <Line key={b.n} points={[[xOf(b.nm), 0.02, Z_ENMAP - 0.3], [xOf(b.nm + d), 0.02, Z_2022 + 0.3]]} color={Math.abs(d) > 50 ? "#FF4D5E" : "#FFC23D"} lineWidth={1} transparent opacity={0.7} />
          ))}
          <Label text="EnMAP · 224 bands" position={[-XW / 2 + 2.4, 1.75, Z_ENMAP]} color="#EAF1FF" size={0.36} bold />
          <Label text="813 SIMULATED · 205 bands" position={[-XW / 2 + 2.6, 1.75, Z_813]} color="#FFC23D" size={0.36} bold />
          {showF2 && <Label text="Sep 2022 (real positions)" position={[xOf(1580), 1.5, Z_2022]} color="#FFD27A" size={0.36} bold />}
          <Label text={`both sensors ${ov[0]}–${ov[1]} nm`} position={[(xOf(ov[0]) + xOf(ov[1])) / 2, 1.85, 0]} color="#27C3F3" size={0.34} />
          {ticks.map((nm) => (
            <group key={nm}>
              <Line points={[[xOf(nm), 0, 1.75], [xOf(nm), 0, 1.95]]} color="#5D7299" lineWidth={1} />
              <Label text={`${nm} nm`} position={[xOf(nm), 0.05, 2.35]} color="#93A6CB" size={0.32} />
            </group>
          ))}
        </group>
        <OrbitControls enablePan={false} enableZoom={false} enableDamping maxPolarAngle={1.42} />
      </Canvas>
    </div>
  );
}
