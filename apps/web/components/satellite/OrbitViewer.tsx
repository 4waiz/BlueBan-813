"use client";
/**
 * FULL-SCREEN SATELLITE VIEW (three.js through React Three Fiber).
 *
 * What is real here:
 *  - Earth: NASA Blue Marble (day) and Black Marble (night lights), lit by the
 *    Sun's actual position for the simulated instant; the ocean carries a
 *    specular highlight, i.e. the sun glint the water mask has to handle.
 *  - Spacecraft: every position is SGP4-propagated from public TLEs (CelesTrak
 *    snapshot, epoch shown) with satellite.js. Ground tracks, the published
 *    swath widths, the push-broom scan line and the predicted UAE passes all
 *    follow from those elements.
 *
 * What is not: Satellite 813's orbit, altitude, swath and spacecraft are not
 * published. It flies an ILLUSTRATIVE sun-synchronous orbit with an abstract
 * marker, and its only drawn property is its published 400-1700 nm band set.
 */
import React, { memo, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { advance, Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { eciToGeodetic, gstime, jday, propagate, sunPos, twoline2satrec, type SatRec } from "satellite.js";
import {
  Crosshair, Eye, EyeOff, Globe2, LocateFixed, Maximize, Minimize, Pause, Play, Radar, RotateCcw, X,
} from "lucide-react";
import { useReducedMotion } from "framer-motion";
import Label from "@/components/three/Label";
import { bandColor, SAT_SENSOR, SENSORS, type SensorKey } from "@/lib/sensors";
import type { Aoi, Incident } from "@/lib/engine/types";

const RE = 6371.0;
const MU = 398600.4418;
const DEG = Math.PI / 180;
const TEX = "https://unpkg.com/three-globe@2.45.2/example/img/";

export interface TleSet { fetched_utc: string; source: string; satellites: { key: string; name: string; norad: number; role: string; line1: string; line2: string; epoch: string }[] }

type SatDef = {
  key: string; name: string; sensor: SensorKey; color: string; role: string; norad?: number; epoch?: string;
  satrec?: SatRec;
  synth?: { a: number; inc: number; raan0: number; u0: number; t0: number };
};
type LLA = { lat: number; lon: number; alt: number; vel: number };
type Pass = { sat: string; t: number; aois: string[]; dir: "asc" | "desc"; offset_km: number; sunlit: boolean };

// --------------------------------------------------------------------------- orbit maths
const wrapPi = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));
function toVec(lat: number, lon: number, altKm = 0, out = new THREE.Vector3()) {
  const r = 1 + altKm / RE;
  return out.set(r * Math.cos(lat) * Math.cos(lon), r * Math.sin(lat), -r * Math.cos(lat) * Math.sin(lon));
}
function satLLA(s: SatDef, d: Date): LLA | null {
  if (s.satrec) {
    const pv = propagate(s.satrec, d) as unknown as { position?: { x: number; y: number; z: number } | false; velocity?: { x: number; y: number; z: number } } | null;
    if (!pv || !pv.position || !pv.velocity) return null;
    const g = eciToGeodetic(pv.position as never, gstime(d));
    return { lat: g.latitude, lon: g.longitude, alt: g.height, vel: Math.hypot(pv.velocity.x, pv.velocity.y, pv.velocity.z) };
  }
  const o = s.synth!;
  const dt = (d.getTime() - o.t0) / 1000;
  const n = Math.sqrt(MU / o.a ** 3);
  const u = o.u0 + n * dt;
  const raan = o.raan0 + (2 * Math.PI / (365.2422 * 86400)) * dt;       // sun-synchronous precession
  const xo = o.a * Math.cos(u), yo = o.a * Math.sin(u);
  const ci = Math.cos(o.inc), si = Math.sin(o.inc), cO = Math.cos(raan), sO = Math.sin(raan);
  const x = xo * cO - yo * ci * sO, y = xo * sO + yo * ci * cO, z = yo * si;
  return { lat: Math.atan2(z, Math.hypot(x, y)), lon: wrapPi(Math.atan2(y, x) - gstime(d)), alt: o.a - RE, vel: n * o.a };
}
function sunDirection(d: Date, out = new THREE.Vector3()) {
  const s = sunPos(jday(d));
  const g = gstime(d);
  const [x, y, z] = s.rsun;
  const xe = Math.cos(g) * x + Math.sin(g) * y, ye = -Math.sin(g) * x + Math.cos(g) * y;
  return out.set(xe, z, -ye).normalize();
}
function havKm(la1: number, lo1: number, la2: number, lo2: number) {
  const a = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2;
  return 2 * RE * Math.asin(Math.min(1, Math.sqrt(a)));
}
/** Swath edge points (unit sphere) across the track at p, heading t. */
function swathEdges(p: THREE.Vector3, t: THREE.Vector3, halfKm: number, lift = 1.0025) {
  const c = new THREE.Vector3().crossVectors(t, p).normalize();
  const th = halfKm / RE;
  const a = p.clone().multiplyScalar(Math.cos(th)).addScaledVector(c, Math.sin(th)).normalize().multiplyScalar(lift);
  const b = p.clone().multiplyScalar(Math.cos(th)).addScaledVector(c, -Math.sin(th)).normalize().multiplyScalar(lift);
  return [a, b];
}

// --------------------------------------------------------------------------- shaders
const earthVert = /* glsl */ `
varying vec2 vUv; varying vec3 vN; varying vec3 vW;
void main() { vUv = uv; vN = normalize(mat3(modelMatrix) * normal); vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`;
const earthFrag = /* glsl */ `
uniform sampler2D dayMap; uniform sampler2D nightMap; uniform sampler2D waterMap; uniform sampler2D bumpMap;
uniform vec3 sunDir; uniform float nightOn; uniform float glintOn;
varying vec2 vUv; varying vec3 vN; varying vec3 vW;
void main() {
  vec3 n = normalize(vN);
  // bump relief from the topology map (screen-space derivative trick)
  float h = texture2D(bumpMap, vUv).r;
  vec3 dpdx = dFdx(vW), dpdy = dFdy(vW);
  float dhx = dFdx(h), dhy = dFdy(h);
  vec3 r1 = cross(dpdy, n), r2 = cross(n, dpdx);
  float det = dot(dpdx, r1);
  vec3 grad = sign(det) * (dhx * r1 + dhy * r2);
  vec3 nb = normalize(abs(det) * n - 0.018 * grad);
  float ndl = dot(nb, sunDir);
  float ndlS = dot(n, sunDir);
  vec3 day = texture2D(dayMap, vUv).rgb;
  vec3 night = texture2D(nightMap, vUv).rgb;
  float water = texture2D(waterMap, vUv).r;
  float dayMix = smoothstep(-0.10, 0.16, ndlS);
  vec3 lit = day * (0.03 + 1.12 * max(ndl, 0.0));
  float nightW = 1.0 - smoothstep(-0.18, 0.04, ndlS);
  vec3 city = night * vec3(1.0, 0.8, 0.52) * 1.9 * nightOn * nightW;
  vec3 earthshine = day * vec3(0.05, 0.07, 0.12) * nightW;
  vec3 col = mix(city + earthshine, lit, dayMix);
  // sun glint on open water
  vec3 v = normalize(cameraPosition - vW);
  vec3 hv = normalize(sunDir + v);
  float nh = max(dot(n, hv), 0.0);
  float spec = (pow(nh, 420.0) * 0.55 + pow(nh, 38.0) * 0.07) * water * smoothstep(0.0, 0.25, ndlS) * glintOn;
  col += vec3(1.0, 0.94, 0.84) * spec;
  // atmospheric scattering toward the limb, warm at the terminator
  float fres = pow(1.0 - max(dot(n, v), 0.0), 2.6);
  col = mix(col, vec3(0.32, 0.58, 1.0) * (0.35 + 0.65 * max(ndlS, 0.0)), fres * 0.62 * smoothstep(-0.25, 0.35, ndlS));
  float term = smoothstep(-0.08, 0.04, ndlS) - smoothstep(0.04, 0.22, ndlS);
  col += vec3(0.55, 0.22, 0.05) * term * 0.10;
  gl_FragColor = vec4(col, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;
const atmoVert = /* glsl */ `
varying vec3 vN; varying vec3 vW;
void main() { vN = normalize(mat3(modelMatrix) * normal); vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`;
const atmoFrag = /* glsl */ `
uniform vec3 sunDir; varying vec3 vN; varying vec3 vW;
void main() {
  vec3 v = normalize(cameraPosition - vW);
  float rim = pow(clamp(1.0 - abs(dot(normalize(vN), v)), 0.0, 1.0), 4.0);
  float day = smoothstep(-0.35, 0.45, dot(normalize(vW), sunDir));
  vec3 c = mix(vec3(0.05, 0.12, 0.35), vec3(0.35, 0.65, 1.0), day);
  gl_FragColor = vec4(c * rim * (0.25 + 1.35 * day), rim * (0.3 + 0.7 * day));
}`;
const cloudFrag = /* glsl */ `
uniform sampler2D cloudMap; uniform vec3 sunDir; uniform float opacity; varying vec2 vUv; varying vec3 vN;
void main() {
  float c = texture2D(cloudMap, vUv).a;           // coverage is stored in alpha
  float ndl = dot(normalize(vN), sunDir);
  float lit = 0.04 + 1.0 * max(ndl, 0.0);
  float a = c * opacity * (0.25 + 0.75 * smoothstep(-0.25, 0.1, ndl));
  gl_FragColor = vec4(vec3(lit), a);
  #include <colorspace_fragment>
}`;
const cloudVert = /* glsl */ `
varying vec2 vUv; varying vec3 vN;
void main() { vUv = uv; vN = normalize(mat3(modelMatrix) * normal); gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(position, 1.0); }`;
const fanVert = /* glsl */ `
attribute float s; attribute float hgt; varying float vS; varying float vH;
void main() { vS = s; vH = hgt; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const fanFrag = /* glsl */ `
uniform float time; varying float vS; varying float vH;
vec3 spectral(float nm) {
  if (nm < 440.0) return mix(vec3(0.45, 0.0, 0.8), vec3(0.0, 0.2, 1.0), (nm - 400.0) / 40.0);
  if (nm < 490.0) return mix(vec3(0.0, 0.2, 1.0), vec3(0.0, 0.85, 1.0), (nm - 440.0) / 50.0);
  if (nm < 510.0) return mix(vec3(0.0, 0.85, 1.0), vec3(0.0, 1.0, 0.35), (nm - 490.0) / 20.0);
  if (nm < 580.0) return mix(vec3(0.0, 1.0, 0.35), vec3(1.0, 1.0, 0.0), (nm - 510.0) / 70.0);
  if (nm < 645.0) return mix(vec3(1.0, 1.0, 0.0), vec3(1.0, 0.25, 0.0), (nm - 580.0) / 65.0);
  if (nm < 700.0) return mix(vec3(1.0, 0.25, 0.0), vec3(0.85, 0.0, 0.05), (nm - 645.0) / 55.0);
  if (nm < 1000.0) return mix(vec3(0.75, 0.0, 0.12), vec3(0.55, 0.1, 0.55), (nm - 700.0) / 300.0);   // NIR (false colour)
  return mix(vec3(0.5, 0.2, 0.7), vec3(0.45, 0.45, 0.6), (nm - 1000.0) / 700.0);                  // SWIR (false colour)
}
void main() {
  float nm = 400.0 + vS * 1300.0;
  vec3 c = spectral(nm);
  float band = 0.72 + 0.28 * step(0.22, fract(vS * 205.0));          // 205 narrow bands
  float sweep = exp(-pow((fract(time * 0.18) - vS) * 9.0, 2.0));       // scanning highlight
  float a = (0.10 + 0.55 * sweep) * (1.0 - vH * 0.85);
  gl_FragColor = vec4(c * band * (0.8 + 1.4 * sweep), a);
}`;

// --------------------------------------------------------------------------- scene pieces
function useGlowTexture() {
  return useMemo(() => {
    const c = document.createElement("canvas"); c.width = c.height = 128;
    const g = c.getContext("2d")!;
    const r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.18, "rgba(255,255,255,0.9)");
    r.addColorStop(0.4, "rgba(255,255,255,0.28)"); r.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = r; g.fillRect(0, 0, 128, 128);
    const t = new THREE.CanvasTexture(c); t.needsUpdate = true; return t;
  }, []);
}

function Earth({ sun, night, glint }: { sun: React.MutableRefObject<THREE.Vector3>; night: boolean; glint: boolean }) {
  const [day, nightT, water, bump] = useLoader(THREE.TextureLoader, [`${TEX}earth-blue-marble.jpg`, `${TEX}earth-night.jpg`, `${TEX}earth-water.png`, `${TEX}earth-topology.png`]);
  const { gl } = useThree();
  const mat = useMemo(() => {
    [day, nightT].forEach((t) => { t.colorSpace = THREE.SRGBColorSpace; });
    [day, nightT, water, bump].forEach((t) => { t.anisotropy = Math.min(8, gl.capabilities.getMaxAnisotropy()); });
    return new THREE.ShaderMaterial({
      vertexShader: earthVert, fragmentShader: earthFrag,
      uniforms: { dayMap: { value: day }, nightMap: { value: nightT }, waterMap: { value: water }, bumpMap: { value: bump }, sunDir: { value: new THREE.Vector3(1, 0, 0) }, nightOn: { value: 1 }, glintOn: { value: 1 } },
    });
  }, [day, nightT, water, bump, gl]);
  useFrame(() => { mat.uniforms.sunDir.value.copy(sun.current); mat.uniforms.nightOn.value = night ? 1 : 0; mat.uniforms.glintOn.value = glint ? 1 : 0; });
  return <mesh material={mat}><sphereGeometry args={[1, 160, 160]} /></mesh>;
}

function Clouds({ sun }: { sun: React.MutableRefObject<THREE.Vector3> }) {
  const tex = useLoader(THREE.TextureLoader, "https://unpkg.com/globe.gl@2.46.2/example/clouds/clouds.png");
  const mat = useMemo(() => new THREE.ShaderMaterial({ vertexShader: cloudVert, fragmentShader: cloudFrag, uniforms: { cloudMap: { value: tex }, sunDir: { value: new THREE.Vector3(1, 0, 0) }, opacity: { value: 0.62 } }, transparent: true, depthWrite: false }), [tex]);
  useFrame(() => mat.uniforms.sunDir.value.copy(sun.current));
  return <mesh material={mat} scale={1.006}><sphereGeometry args={[1, 128, 128]} /></mesh>;
}

function EarthFallback() {
  return <mesh><sphereGeometry args={[1, 64, 64]} /><meshStandardMaterial color="#0b2a57" roughness={0.9} /></mesh>;
}

function Atmosphere({ sun }: { sun: React.MutableRefObject<THREE.Vector3> }) {
  const mat = useMemo(() => new THREE.ShaderMaterial({ vertexShader: atmoVert, fragmentShader: atmoFrag, uniforms: { sunDir: { value: new THREE.Vector3(1, 0, 0) } }, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.BackSide }), []);
  useFrame(() => mat.uniforms.sunDir.value.copy(sun.current));
  return <mesh material={mat} scale={1.055}><sphereGeometry args={[1, 96, 96]} /></mesh>;
}

function Stars() {
  const tex = useLoader(THREE.TextureLoader, `${TEX}night-sky.png`);
  useMemo(() => { tex.colorSpace = THREE.SRGBColorSpace; }, [tex]);
  return <mesh><sphereGeometry args={[60, 48, 48]} /><meshBasicMaterial map={tex} side={THREE.BackSide} color="#8fa0c8" depthWrite={false} /></mesh>;
}

/** Positions of every spacecraft, recomputed each frame from the sim clock. */
const Constellation = memo(function Constellation({ sats, clock, positions, selected, hovered, visible, labels, glow, onSelect, onHover }: {
  sats: SatDef[]; clock: React.MutableRefObject<number>; positions: React.MutableRefObject<Map<string, { v: THREE.Vector3; lla: LLA }>>;
  selected: string | null; hovered: string | null; visible: Set<SensorKey>; labels: boolean; glow: THREE.Texture;
  onSelect: (k: string) => void; onHover: (k: string | null) => void;
}) {
  const groups = useRef<Record<string, THREE.Group | null>>({});
  const pulse = useRef<THREE.Sprite>(null);
  useFrame(({ clock: c, camera }) => {
    const d = new Date(clock.current);
    for (const s of sats) {
      const lla = satLLA(s, d);
      const g = groups.current[s.key];
      if (!lla || !g) continue;
      const prev = positions.current.get(s.key);
      const v = toVec(lla.lat, lla.lon, lla.alt, prev?.v || new THREE.Vector3());
      positions.current.set(s.key, { v, lla });
      g.position.copy(v);
      g.scale.setScalar(Math.min(2.5, Math.max(0.05, camera.position.distanceTo(v) / 2.4)));   // constant on-screen size
    }
    if (pulse.current && selected) {
      const p = positions.current.get(selected);
      if (p) { pulse.current.position.copy(p.v); const k = (0.07 + 0.03 * Math.sin(c.elapsedTime * 3)) * Math.min(2.5, Math.max(0.05, camera.position.distanceTo(p.v) / 2.4)); pulse.current.scale.set(k, k, 1); }
    }
  });
  return (
    <group>
      {sats.map((s) => {
        const on = visible.has(s.sensor);
        const sel = s.key === selected, hov = s.key === hovered;
        return (
          <group key={s.key} ref={(g) => { groups.current[s.key] = g; }} visible={on}>
            <sprite scale={sel ? [0.07, 0.07, 1] : hov ? [0.06, 0.06, 1] : [0.045, 0.045, 1]} raycast={() => null}>
              <spriteMaterial map={glow} color={s.color} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
            </sprite>
            <mesh onClick={(e) => { e.stopPropagation(); if (on) onSelect(s.key); }}
              onPointerOver={(e) => { e.stopPropagation(); if (on) { onHover(s.key); document.body.style.cursor = "pointer"; } }}
              onPointerOut={() => { onHover(null); document.body.style.cursor = ""; }}>
              <sphereGeometry args={[0.022, 12, 12]} />
              <meshBasicMaterial color={s.color} transparent opacity={s.synth ? 0.35 : 0.9} />
            </mesh>
            {s.synth && <mesh raycast={() => null}><octahedronGeometry args={[0.03, 0]} /><meshBasicMaterial color={s.color} wireframe /></mesh>}
            {labels && on && <Label text={s.synth ? `${s.name} · illustrative` : s.name} position={[0.035, 0.035, 0]} size={sel ? 0.05 : 0.036} color={sel ? "#FFFFFF" : s.color} bold={sel} />}
          </group>
        );
      })}
      {selected && <sprite ref={pulse} raycast={() => null}><spriteMaterial map={glow} color="#FFFFFF" transparent opacity={0.35} depthWrite={false} blending={THREE.AdditiveBlending} /></sprite>}
    </group>
  );
});

/** Orbit path at altitude, ground track, swath ribbon, FOV fan and push-broom line for one satellite. */
function Coverage({ sat, clock, showOrbit, showSwath, playing }: { sat: SatDef; clock: React.MutableRefObject<number>; showOrbit: boolean; showSwath: boolean; playing: boolean }) {
  const spec = SENSORS[sat.sensor];
  const halfKm = (spec.swath_km ?? 60) / 2;
  const N = 240, STEP = 25;                      // samples, seconds: -40 min .. +60 min
  const built = useRef({ at: -1e15 });
  const orbit = useMemo(() => {
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(N * 3), 3));
    g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(N * 3), 3));
    return new THREE.Line(g, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.95 }));
  }, []);
  const ground = useMemo(() => {
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(N * 3), 3));
    return new THREE.Line(g, new THREE.LineDashedMaterial({ color: sat.color, dashSize: 0.012, gapSize: 0.008, transparent: true, opacity: 0.55 }));
  }, [sat.color]);
  const ribbon = useMemo(() => {
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(N * 2 * 3), 3));
    const idx: number[] = []; for (let i = 0; i < N - 1; i++) { const a = 2 * i; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    g.setIndex(idx);
    return new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: sat.color, transparent: true, opacity: sat.synth ? 0.1 : 0.16, side: THREE.DoubleSide, depthWrite: false }));
  }, [sat.color, sat.synth]);
  const scan = useMemo(() => {
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(6), 3));
    return new THREE.Line(g, new THREE.LineBasicMaterial({ color: "#FFFFFF", transparent: true, opacity: 0.95 }));
  }, []);
  const fanM = 48;
  const fan = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(fanM * 3 * 3), 3));
    const s = new Float32Array(fanM * 3), h = new Float32Array(fanM * 3);
    for (let k = 0; k < fanM; k++) { const sc = (k + 0.5) / fanM; s.set([sc, k / fanM, (k + 1) / fanM], k * 3); h.set([1, 0, 0], k * 3); }
    g.setAttribute("s", new THREE.BufferAttribute(s, 1)); g.setAttribute("hgt", new THREE.BufferAttribute(h, 1));
    const mat = sat.synth
      ? new THREE.ShaderMaterial({ vertexShader: fanVert, fragmentShader: fanFrag, uniforms: { time: { value: 0 } }, transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending })
      : new THREE.MeshBasicMaterial({ color: sat.color, transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending });
    return new THREE.Mesh(g, mat);
  }, [sat.synth, sat.color]);
  useEffect(() => () => { [orbit, ground, ribbon, scan, fan].forEach((o) => { o.geometry.dispose(); (o.material as THREE.Material).dispose(); }); }, [orbit, ground, ribbon, scan, fan]);

  const tmp = useMemo(() => ({ p: new THREE.Vector3(), q: new THREE.Vector3(), t: new THREE.Vector3() }), []);
  useFrame(({ clock: c }) => {
    const now = clock.current;
    // rebuild the long geometry when the clock has moved > 20 s of sim time
    if (Math.abs(now - built.current.at) > 20000) {
      built.current.at = now;
      const op = orbit.geometry.attributes.position as THREE.BufferAttribute, oc = orbit.geometry.attributes.color as THREE.BufferAttribute;
      const gp = ground.geometry.attributes.position as THREE.BufferAttribute, rp = ribbon.geometry.attributes.position as THREE.BufferAttribute;
      const col = new THREE.Color(sat.color);
      const pts: THREE.Vector3[] = [];
      for (let i = 0; i < N; i++) {
        const d = new Date(now + (i - 96) * STEP * 1000);
        const l = satLLA(sat, d);
        if (!l) { pts.push(pts[pts.length - 1] || new THREE.Vector3()); continue; }
        toVec(l.lat, l.lon, l.alt, tmp.p); op.setXYZ(i, tmp.p.x, tmp.p.y, tmp.p.z);
        const f = i < 96 ? 0.25 + 0.5 * (i / 96) : 1.0 - 0.55 * ((i - 96) / (N - 96));
        oc.setXYZ(i, col.r * f, col.g * f, col.b * f);
        const gv = toVec(l.lat, l.lon, 0).multiplyScalar(1.0015); gp.setXYZ(i, gv.x, gv.y, gv.z);
        pts.push(toVec(l.lat, l.lon, 0));
      }
      for (let i = 0; i < N; i++) {
        const a = pts[Math.max(0, i - 1)], b = pts[Math.min(N - 1, i + 1)];
        tmp.t.subVectors(b, a).normalize();
        const [e1, e2] = swathEdges(pts[i], tmp.t, halfKm);
        rp.setXYZ(2 * i, e1.x, e1.y, e1.z); rp.setXYZ(2 * i + 1, e2.x, e2.y, e2.z);
      }
      op.needsUpdate = oc.needsUpdate = gp.needsUpdate = rp.needsUpdate = true;
      ground.computeLineDistances();
      orbit.geometry.computeBoundingSphere(); ribbon.geometry.computeBoundingSphere(); ground.geometry.computeBoundingSphere();
    }
    // live pieces: push-broom line under the spacecraft, FOV fan
    const d0 = new Date(now), d1 = new Date(now + 10000);
    const l0 = satLLA(sat, d0), l1 = satLLA(sat, d1);
    if (!l0 || !l1) return;
    const g0 = toVec(l0.lat, l0.lon, 0), g1 = toVec(l1.lat, l1.lon, 0);
    tmp.t.subVectors(g1, g0).normalize();
    const [e1, e2] = swathEdges(g0, tmp.t, halfKm, 1.003);
    const sp = scan.geometry.attributes.position as THREE.BufferAttribute;
    sp.setXYZ(0, e1.x, e1.y, e1.z); sp.setXYZ(1, e2.x, e2.y, e2.z); sp.needsUpdate = true; scan.geometry.computeBoundingSphere();
    (scan.material as THREE.LineBasicMaterial).opacity = 0.6 + 0.4 * Math.abs(Math.sin(c.elapsedTime * 4));
    const apex = toVec(l0.lat, l0.lon, l0.alt);
    const fp = fan.geometry.attributes.position as THREE.BufferAttribute;
    for (let k = 0; k < fanM; k++) {
      const a = e1.clone().lerp(e2, k / fanM).normalize().multiplyScalar(1.003);
      const b = e1.clone().lerp(e2, (k + 1) / fanM).normalize().multiplyScalar(1.003);
      fp.setXYZ(k * 3, apex.x, apex.y, apex.z); fp.setXYZ(k * 3 + 1, a.x, a.y, a.z); fp.setXYZ(k * 3 + 2, b.x, b.y, b.z);
    }
    fp.needsUpdate = true; fan.geometry.computeBoundingSphere();
    if (sat.synth) (fan.material as THREE.ShaderMaterial).uniforms.time.value = playing ? c.elapsedTime : 0;
  });
  return (
    <group>
      {showOrbit && <primitive object={orbit} />}
      {showOrbit && <primitive object={ground} />}
      {showSwath && <primitive object={ribbon} />}
      {showSwath && <primitive object={scan} />}
      <primitive object={fan} />
    </group>
  );
}

const AoiLayer = memo(function AoiLayer({ aois, incident, glow }: { aois: Aoi[]; incident: Incident | null; glow: THREE.Texture }) {
  const ring = useRef<THREE.Mesh>(null);
  const items = useMemo(() => aois.map((a) => {
    const [x0, y0, x1, y1] = a.bbox;
    const uae = a.id.startsWith("AE");
    const pts = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]].map(([lo, la]) => toVec(la * DEG, lo * DEG, 0).multiplyScalar(1.0022));
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: uae ? "#27C3F3" : "#93A6CB", transparent: true, opacity: 0.9 }));
    return { id: a.id, uae, line, c: toVec(((y0 + y1) / 2) * DEG, ((x0 + x1) / 2) * DEG, 0).multiplyScalar(1.003) };
  }), [aois]);
  useEffect(() => () => items.forEach((it) => { it.line.geometry.dispose(); (it.line.material as THREE.Material).dispose(); }), [items]);
  const inc = useMemo(() => (incident?.centroid ? toVec(incident.centroid[1] * DEG, incident.centroid[0] * DEG, 0).multiplyScalar(1.004) : null), [incident?.centroid]); // eslint-disable-line react-hooks/exhaustive-deps
  const q = useMemo(() => (inc ? new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), inc.clone().normalize()) : null), [inc]);
  useFrame(({ clock }) => { if (ring.current) { const f = (clock.elapsedTime * 0.7) % 1; const k = 1 + 0.6 * f; ring.current.scale.set(k, k, k); (ring.current.material as THREE.MeshBasicMaterial).opacity = 0.9 * (1 - f); } });
  return (
    <group>
      {items.map((it) => (
        <group key={it.id}>
          <primitive object={it.line} />
          <sprite position={it.c} scale={[0.02, 0.02, 1]} raycast={() => null}><spriteMaterial map={glow} color={it.uae ? "#27C3F3" : "#93A6CB"} transparent depthWrite={false} blending={THREE.AdditiveBlending} /></sprite>
        </group>))}
      {inc && q && (
        <group position={inc} quaternion={q}>
          <mesh ref={ring} raycast={() => null}><ringGeometry args={[0.006, 0.009, 48]} /><meshBasicMaterial color="#FF4D5E" transparent side={THREE.DoubleSide} depthWrite={false} /></mesh>
          <mesh raycast={() => null}><circleGeometry args={[0.004, 24]} /><meshBasicMaterial color="#FF4D5E" side={THREE.DoubleSide} /></mesh>
        </group>
      )}
    </group>
  );
});

/** Sim clock + Sun + camera behaviour. */
function Rig({ clock, speed, playing, sun, follow, flyTo, positions, controls, onUserMove }: {
  clock: React.MutableRefObject<number>; speed: number; playing: boolean; sun: React.MutableRefObject<THREE.Vector3>;
  follow: string | null; flyTo: React.MutableRefObject<THREE.Vector3 | null>;
  positions: React.MutableRefObject<Map<string, { v: THREE.Vector3; lla: LLA }>>;
  controls: React.MutableRefObject<{ target: THREE.Vector3; update: () => void; enabled: boolean } | null>; onUserMove: () => void;
}) {
  const { camera } = useThree();
  const tmp = useMemo(() => ({ a: new THREE.Vector3(), b: new THREE.Vector3(), prev: new THREE.Vector3() }), []);
  useEffect(() => { const c = controls.current as unknown as { addEventListener?: (e: string, f: () => void) => void; removeEventListener?: (e: string, f: () => void) => void } | null; c?.addEventListener?.("start", onUserMove); return () => c?.removeEventListener?.("start", onUserMove); }, [controls, onUserMove]);
  useFrame((_, dt) => {
    if (playing) clock.current += dt * 1000 * speed;
    sunDirection(new Date(clock.current), sun.current);
    const ctl = controls.current;
    if (follow) {
      const p = positions.current.get(follow);
      if (p) {
        tmp.a.copy(p.v).normalize();
        const moveDir = tmp.b.subVectors(p.v, tmp.prev).normalize();
        tmp.prev.copy(p.v);
        const want = p.v.clone().addScaledVector(tmp.a, 0.28).addScaledVector(moveDir, -0.42);
        camera.position.lerp(want, 0.06);
        if (ctl) { ctl.target.lerp(p.v.clone().multiplyScalar(0.985), 0.12); ctl.update(); }
      }
    } else if (flyTo.current) {
      camera.position.lerp(flyTo.current, 0.055);
      if (ctl) { ctl.target.lerp(new THREE.Vector3(0, 0, 0), 0.1); ctl.update(); }
      if (camera.position.distanceTo(flyTo.current) < 0.01) flyTo.current = null;
    }
  });
  return null;
}

// --------------------------------------------------------------------------- UI helpers
const fmtUTC = (ms: number) => new Date(ms).toISOString().replace("T", " ").slice(0, 19) + " UTC";
const fmtGST = (ms: number) => new Date(ms + 4 * 3600e3).toISOString().slice(11, 16) + " GST";
const SPEEDS = [1, 30, 120, 600, 3600];

function BandStrip({ k }: { k: SensorKey }) {
  const s = SENSORS[k];
  if (!s.bands.length) return <div className="text-[11px] text-muted">Active microwave (C-band, 5.405 GHz): no optical bands.</div>;
  const lo = 340, hi = Math.max(1750, ...s.bands.map(([c]) => c + 20)), W = 300;
  const x = (nm: number) => 6 + ((nm - lo) / (hi - lo)) * (W - 12);
  return (
    <svg viewBox={`0 0 ${W} 58`} className="h-[58px] w-full">
      <defs><linearGradient id="vis" x1="0" x2="1"><stop offset="0" stopColor="#6a00ff" /><stop offset="0.25" stopColor="#0080ff" /><stop offset="0.45" stopColor="#00ff66" /><stop offset="0.7" stopColor="#ffee00" /><stop offset="1" stopColor="#ff2200" /></linearGradient></defs>
      <rect x={x(400)} y={2} width={x(700) - x(400)} height={4} fill="url(#vis)" opacity={0.8} />
      {s.bands.map(([c, fw], i) => <rect key={i} x={x(c - fw / 2)} y={10} width={Math.max(1, x(c + fw / 2) - x(c - fw / 2))} height={30} fill={bandColor(c)} opacity={0.8} />)}
      {[400, 700, 1000, 1300, 1700].filter((t) => t <= hi).map((t) => <text key={t} x={x(t)} y={54} fill="#5D7299" fontSize="9" textAnchor="middle">{t}</text>)}
    </svg>
  );
}

// --------------------------------------------------------------------------- main
export default function OrbitViewer({ tle, aois, incident, initialSensor = "S2", onExit }: {
  tle: TleSet; aois: Aoi[]; incident: Incident | null; initialSensor?: string; onExit: () => void;
}) {
  const reduce = useReducedMotion();
  const sats: SatDef[] = useMemo(() => {
    const out: SatDef[] = tle.satellites.map((t) => ({
      key: t.key, name: t.name.replace("SENTINEL-", "Sentinel-").replace("LANDSAT ", "Landsat ").replace("TANAGER-1", "Tanager-1"),
      sensor: SAT_SENSOR[t.key] || "S2", color: SENSORS[SAT_SENSOR[t.key] || "S2"].color, role: t.role, norad: t.norad, epoch: t.epoch,
      satrec: twoline2satrec(t.line1, t.line2),
    }));
    // Satellite 813: ILLUSTRATIVE sun-synchronous orbit (500 km, 97.4 deg, 10:30 descending node).
    const t0 = Date.parse(tle.fetched_utc);
    const rtasc = sunPos(jday(new Date(t0))).rtasc;
    out.unshift({ key: "813", name: "Satellite 813", sensor: "813", color: SENSORS["813"].color, role: "Illustrative orbit: not published",
      synth: { a: RE + 500, inc: 97.4 * DEG, raan0: rtasc + 157.5 * DEG, u0: 0, t0 } });
    return out;
  }, [tle]);

  const clock = useRef<number>(Date.now());
  const sun = useRef(new THREE.Vector3(1, 0, 0));
  const positions = useRef(new Map<string, { v: THREE.Vector3; lla: LLA }>());
  const controls = useRef<{ target: THREE.Vector3; update: () => void; enabled: boolean } | null>(null);
  const flyTo = useRef<THREE.Vector3 | null>(null);
  const startMs = useRef(Date.now());

  const firstSel = useMemo(() => {
    const k = (Object.keys(SENSORS) as SensorKey[]).includes(initialSensor as SensorKey) ? (initialSensor as SensorKey) : "S2";
    return SENSORS[k].sats[0];
  }, [initialSensor]);
  const [selected, setSelected] = useState<string | null>(firstSel);
  const [hovered, setHovered] = useState<string | null>(null);
  const [follow, setFollow] = useState<string | null>(null);
  const [playing, setPlaying] = useState(!reduce);
  const [speed, setSpeed] = useState(60);
  const [visible, setVisible] = useState<Set<SensorKey>>(new Set(["813", "S2", "S3", "S1", "LS", "PACE", "TAN"]));
  const [layers, setLayers] = useState({ orbits: true, swaths: true, labels: true, night: true, glint: true, atmosphere: true, aois: true, clouds: true });
  const [tick, setTick] = useState(0);
  const [passes, setPasses] = useState<Pass[] | null>(null);
  const [fs, setFs] = useState(false);
  const glow = useGlowTexture();
  // Dev aid: ?manualloop=1 steps frames from a timer, for automated checks in a hidden browser tab.
  const manual = useMemo(() => process.env.NODE_ENV !== "production" && typeof window !== "undefined" && new URLSearchParams(window.location.search).has("manualloop"), []);
  useEffect(() => { if (!manual) return; const t = setInterval(() => advance(performance.now()), 60); return () => clearInterval(t); }, [manual]);
  useEffect(() => { if (process.env.NODE_ENV !== "production") (window as unknown as Record<string, unknown>).__orbit = { positions: positions.current, sats, clock }; }, [sats]);

  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), 250); return () => clearInterval(t); }, []);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === " ") { e.preventDefault(); setPlaying((p) => !p); }
      if (e.key.toLowerCase() === "f" && selected) setFollow((f) => (f ? null : selected));
      if (e.key === "Escape" && !document.fullscreenElement) onExit();
    };
    const f = () => setFs(!!document.fullscreenElement);
    window.addEventListener("keydown", h); document.addEventListener("fullscreenchange", f);
    return () => { window.removeEventListener("keydown", h); document.removeEventListener("fullscreenchange", f); };
  }, [selected, onExit]);

  const sel = sats.find((s) => s.key === selected) || null;
  const selSpec = sel ? SENSORS[sel.sensor] : null;

  // predicted UAE passes for the selected sensor's spacecraft (next 7 days of sim time), computed in slices
  useEffect(() => {
    if (!sel || !selSpec) return;
    setPasses(null);
    if (sel.synth || selSpec.swath_km == null) { setPasses([]); return; }
    let dead = false;
    const uae = aois.filter((a) => a.id.startsWith("AE")).map((a) => ({ id: a.id, lat: ((a.bbox[1] + a.bbox[3]) / 2) * DEG, lon: ((a.bbox[0] + a.bbox[2]) / 2) * DEG }));
    const reach = selSpec.swath_km / 2 + 25;
    const band = (reach + 150) / RE;                                    // latitude band worth checking (rad)
    const t0 = clock.current, T = 7 * 86400e3, STEP = 20000, SLICE = 3 * 3600e3;
    const craft = selSpec.sats.map((k) => sats.find((x) => x.key === k)).filter(Boolean) as SatDef[];
    type Cur = { best: number; t: number; aois: Set<string>; lat0: number; lat1: number };
    const state: (Cur | null)[] = craft.map(() => null);
    const out: Pass[] = [];
    const nUAE = toVec(24.5 * DEG, 55 * DEG, 0);
    const close = (ci: number, name: string) => {
      const cur = state[ci];
      if (!cur) return;
      const sd = sunDirection(new Date(cur.t));
      out.push({ sat: name, t: cur.t, aois: [...cur.aois], dir: cur.lat1 > cur.lat0 ? "asc" : "desc", offset_km: Math.round(cur.best), sunlit: sd.dot(nUAE) > Math.sin(10 * DEG) });
      state[ci] = null;
    };
    let from = t0;
    const step = () => {
      if (dead) return;
      const to = Math.min(t0 + T, from + SLICE);
      craft.forEach((s, ci) => {
        for (let t = from; t < to; t += STEP) {
          const l = satLLA(s, new Date(t));
          if (!l || Math.abs(l.lat - 24.5 * DEG) > band) { close(ci, s.name); continue; }
          let best = Infinity; const hit: string[] = [];
          for (const a of uae) { const km = havKm(l.lat, l.lon, a.lat, a.lon); if (km < reach) hit.push(a.id); best = Math.min(best, km); }
          const cur = state[ci];
          if (hit.length) {
            if (!cur) state[ci] = { best, t, aois: new Set(hit), lat0: l.lat, lat1: l.lat };
            else { hit.forEach((h) => cur.aois.add(h)); cur.lat1 = l.lat; if (best < cur.best) { cur.best = best; cur.t = t; } }
          } else close(ci, s.name);
        }
      });
      from = to;
      const list = out.filter((p) => !selSpec.optical || p.sunlit).sort((a, b) => a.t - b.t).slice(0, 10);
      setPasses(list);
      if (from < t0 + T && list.length < 10) setTimeout(step, 0);
    };
    const id = setTimeout(step, 30);
    return () => { dead = true; clearTimeout(id); };
  }, [selected, sats, aois]); // eslint-disable-line react-hooks/exhaustive-deps

  const select = useCallback((k: string) => {
    setSelected(k);
    const p = positions.current.get(k);
    setFollow((f) => { if (!f && p) flyTo.current = p.v.clone().normalize().multiplyScalar(2.2); return f ? k : f; });
  }, []);
  const onUserMove = useCallback(() => { flyTo.current = null; setFollow(null); }, []);
  function camUAE() { setFollow(null); flyTo.current = toVec(24.2 * DEG, 55.2 * DEG, 0).multiplyScalar(1.7).add(new THREE.Vector3(0, -0.25, 0)); }
  function camGlobe() { setFollow(null); flyTo.current = (positions.current.get(selected || "")?.v.clone() || toVec(20 * DEG, 50 * DEG, 0)).normalize().multiplyScalar(3.4); }
  function toggleFs() { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.(); }

  const live = selected ? positions.current.get(selected) : undefined;
  const period = sel?.satrec ? (2 * Math.PI) / sel.satrec.no : sel?.synth ? (2 * Math.PI * Math.sqrt(sel.synth.a ** 3 / MU)) / 60 : null;
  const inc = sel?.satrec ? sel.satrec.inclo / DEG : sel?.synth ? sel.synth.inc / DEG : null;
  const tleAgeDays = sel?.epoch ? (clock.current - Date.parse(sel.epoch)) / 86400e3 : null;
  const sunlit = live ? sun.current.dot(live.v.clone().normalize()) > -0.05 : null;
  void tick;

  const groups = (Object.keys(SENSORS) as SensorKey[]);
  return (
    <div className="relative h-full w-full overflow-hidden bg-[#02040b] text-ink">
      <Canvas camera={{ position: toVec(22 * DEG, 56 * DEG, 0).multiplyScalar(2.6).toArray() as [number, number, number], fov: 42, near: 0.01, far: 150 }}
        dpr={[1, 2]} gl={{ antialias: true, preserveDrawingBuffer: manual }} frameloop={manual ? "never" : "always"} onPointerMissed={() => setHovered(null)}>
        <color attach="background" args={["#02040b"]} />
        <ambientLight intensity={0.2} />
        <Suspense fallback={null}><Stars /></Suspense>
        <Suspense fallback={<EarthFallback />}><Earth sun={sun} night={layers.night} glint={layers.glint} /></Suspense>
        {layers.clouds && <Suspense fallback={null}><Clouds sun={sun} /></Suspense>}
        {layers.atmosphere && <Atmosphere sun={sun} />}
        {layers.aois && <AoiLayer aois={aois} incident={incident} glow={glow} />}
        <Constellation sats={sats} clock={clock} positions={positions} selected={selected} hovered={hovered} visible={visible} labels={layers.labels} glow={glow} onSelect={select} onHover={setHovered} />
        {sel && visible.has(sel.sensor) && <Coverage key={sel.key} sat={sel} clock={clock} showOrbit={layers.orbits} showSwath={layers.swaths} playing={playing} />}
        <Rig clock={clock} speed={speed} playing={playing} sun={sun} follow={follow} flyTo={flyTo} positions={positions} controls={controls} onUserMove={onUserMove} />
        <OrbitControls ref={controls as never} enablePan={false} enableDamping dampingFactor={0.08} rotateSpeed={0.45} zoomSpeed={0.7} minDistance={1.08} maxDistance={14} />
      </Canvas>

      {/* top bar */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-3 p-3">
        <div className="pointer-events-auto rounded-lg border border-edge bg-void/75 px-4 py-2 backdrop-blur">
          <div className="hud-kicker">Satellite view · live orbits</div>
          <div className="font-display text-[20px] font-bold tracking-wide">Who is watching the UAE coast</div>
          <div className="hud-value text-[12px] text-cyan">{fmtUTC(clock.current)} · {fmtGST(clock.current)} {speed > 1 && playing ? <span className="text-caution">· ×{speed}</span> : null}{!playing && <span className="text-muted"> · paused</span>}</div>
        </div>
        <div className="pointer-events-auto flex gap-2">
          <button onClick={toggleFs} className="btn px-3 py-2" title="Browser full screen">{fs ? <Minimize size={16} /> : <Maximize size={16} />}</button>
          <button onClick={onExit} className="btn px-3 py-2" title="Close (Esc)"><X size={16} /> Close</button>
        </div>
      </div>

      {/* sensors list */}
      <div className="absolute left-3 top-[104px] max-h-[calc(100%-230px)] w-[250px] overflow-y-auto rounded-lg border border-edge bg-void/75 p-2 backdrop-blur short:top-[92px]">
        {groups.map((g) => {
          const spec = SENSORS[g];
          const on = visible.has(g);
          return (
            <div key={g} className="mb-1.5">
              <div className="flex items-center justify-between px-1">
                <span className="flex items-center gap-2 text-[11px] font-bold tracking-[0.12em]" style={{ color: spec.color }}>{spec.name.toUpperCase()}</span>
                <button onClick={() => setVisible((v) => { const n = new Set(v); if (n.has(g)) n.delete(g); else n.add(g); return n; })} className="text-muted hover:text-ink" title={on ? "Hide" : "Show"}>{on ? <Eye size={13} /> : <EyeOff size={13} />}</button>
              </div>
              {sats.filter((s) => s.sensor === g).map((s) => (
                <button key={s.key} onClick={() => select(s.key)} disabled={!on}
                  className={`flex w-full items-center justify-between rounded-md px-2 py-1 text-left text-[12px] ${selected === s.key ? "bg-beam/20 text-ink" : on ? "text-muted hover:bg-white/5 hover:text-ink" : "text-dim"}`}>
                  <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: s.color, boxShadow: `0 0 8px ${s.color}` }} />{s.name}{s.synth && <span className="rounded border border-caution/60 px-1 text-[9px] font-bold text-caution">ILLUSTRATIVE</span>}</span>
                  <span className="hud-value text-[10.5px]">{positions.current.get(s.key) ? `${Math.round(positions.current.get(s.key)!.lla.alt)} km` : ""}</span>
                </button>))}
            </div>);
        })}
      </div>

      {/* selected spacecraft */}
      {sel && selSpec && (
        <div className="absolute right-3 top-[104px] max-h-[calc(100%-230px)] w-[330px] overflow-y-auto rounded-lg border border-edge bg-void/80 p-3 backdrop-blur short:top-[92px]">
          <div className="flex items-center justify-between">
            <div className="font-display text-[19px] font-bold">{sel.name}</div>
            {sel.synth ? <span className="rounded border border-caution/60 px-1.5 py-0.5 text-[10px] font-bold text-caution">ILLUSTRATIVE ORBIT</span> : <span className="hud-value text-[11px] text-muted">NORAD {sel.norad}</span>}
          </div>
          <div className="text-[12px]" style={{ color: selSpec.color }}>{selSpec.kind}</div>
          <div className="mt-1 text-[11.5px] text-muted">{sel.role}</div>
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px]">
            <div className="kv"><span>Latitude</span><span className="hud-value">{live ? `${(live.lla.lat / DEG).toFixed(2)}°` : "…"}</span></div>
            <div className="kv"><span>Longitude</span><span className="hud-value">{live ? `${(live.lla.lon / DEG).toFixed(2)}°` : "…"}</span></div>
            <div className="kv"><span>Altitude</span><span className="hud-value">{live ? `${live.lla.alt.toFixed(0)} km` : "…"}</span></div>
            <div className="kv"><span>Speed</span><span className="hud-value">{live ? `${live.lla.vel.toFixed(2)} km/s` : "…"}</span></div>
            <div className="kv"><span>Period</span><span className="hud-value">{period ? `${period.toFixed(1)} min` : "n/a"}</span></div>
            <div className="kv"><span>Inclination</span><span className="hud-value">{inc ? `${inc.toFixed(2)}°` : "n/a"}</span></div>
            <div className="kv"><span>Swath</span><span className="hud-value">{selSpec.swath_km ? `${selSpec.swath_km.toLocaleString()} km` : "not published"}</span></div>
            <div className="kv"><span>In sunlight</span><span className="hud-value">{sunlit == null ? "…" : sunlit ? "yes" : "no (eclipse)"}</span></div>
          </div>
          <div className="mt-1 text-[10.5px] text-dim">{sel.synth ? "813 orbit, altitude, swath and spacecraft are not published: 500 km sun-synchronous orbit shown for illustration; the marker is abstract." : `TLE epoch ${sel.epoch?.slice(0, 16).replace("T", " ")} UTC (${tleAgeDays != null ? `${Math.abs(tleAgeDays).toFixed(1)} d ${tleAgeDays >= 0 ? "old" : "ahead"}` : ""}) · SGP4 · swath: ${selSpec.swath_src}`}</div>
          <div className="mt-3 hud-kicker">Band layout · {selSpec.range}</div>
          <BandStrip k={sel.sensor} />
          <div className="mt-2 hud-kicker">{sel.synth ? "Spectral fan" : `Next UAE passes · 7 days (${selSpec.optical ? "daylight, " : ""}within the swath)`}</div>
          {sel.synth ? <p className="text-[11.5px] text-muted">The fan below the marker is the published 813 band set: 205 narrow bands from 400 to 1700 nm, visible colours then false colours for the near- and short-wave infrared, swept the way a push-broom imager reads a line.</p>
            : passes == null ? <p className="text-[11.5px] text-muted">Predicting…</p>
              : passes.length === 0 ? <p className="text-[11.5px] text-muted">No UAE pass in the next 7 days of simulated time.</p>
                : <ul className="mt-1 space-y-1">{passes.map((p, i) => (
                  <li key={i} className="flex items-center justify-between rounded-md border border-edge bg-deep/60 px-2 py-1 text-[11.5px]">
                    <span><b>{p.sat}</b> <span className="text-dim">{p.dir === "desc" ? "↓" : "↑"}</span> <span className="text-muted">{p.aois.slice(0, 3).join(", ")}{p.aois.length > 3 ? ` +${p.aois.length - 3}` : ""}</span></span>
                    <span className="hud-value text-[11px] text-cyan" title={fmtUTC(p.t)}>{new Date(p.t).toISOString().slice(5, 16).replace("T", " ")}Z</span>
                  </li>))}</ul>}
          <p className="mt-2 text-[10.5px] text-dim">{selSpec.note}</p>
          <div className="mt-2 flex gap-2">
            <button onClick={() => setFollow(follow ? null : sel.key)} className={`btn flex-1 px-2 py-1.5 text-[12px] ${follow ? "border-beam bg-beam/20" : ""}`}><LocateFixed size={14} /> {follow ? "Following" : "Follow (F)"}</button>
            <button onClick={() => { const p = positions.current.get(sel.key); if (p) { setFollow(null); flyTo.current = p.v.clone().normalize().multiplyScalar(1.9); } }} className="btn px-2 py-1.5 text-[12px]"><Crosshair size={14} /> Go to</button>
          </div>
        </div>)}

      {/* time + layers */}
      <div className="absolute inset-x-3 bottom-3 flex flex-wrap items-center gap-2 rounded-lg border border-edge bg-void/80 px-3 py-2 backdrop-blur">
        <button onClick={() => setPlaying((p) => !p)} className="btn px-3 py-1.5">{playing ? <Pause size={15} /> : <Play size={15} />}</button>
        {SPEEDS.map((s) => <button key={s} onClick={() => { setSpeed(s); setPlaying(true); }} className={`rounded-md border px-2 py-1 text-[11px] font-semibold ${speed === s ? "border-beam bg-beam/20 text-ink" : "border-edge text-muted hover:text-ink"}`}>×{s}</button>)}
        <button onClick={() => { clock.current = Date.now(); startMs.current = Date.now(); setSpeed(1); }} className="btn px-2 py-1 text-[11px]"><RotateCcw size={13} /> Now</button>
        <input type="range" min={-12} max={48} step={0.05} value={Math.max(-12, Math.min(48, (clock.current - startMs.current) / 3600e3))}
          onChange={(e) => { clock.current = startMs.current + Number(e.target.value) * 3600e3; }} className="min-w-[160px] flex-1 accent-[#27C3F3]" aria-label="Time offset (hours)" />
        <span className="hud-value w-[62px] text-[11px] text-muted">{((clock.current - startMs.current) / 3600e3 >= 0 ? "+" : "") + ((clock.current - startMs.current) / 3600e3).toFixed(1)} h</span>
        <span className="mx-1 h-5 w-px bg-edge" />
        {([["orbits", "Orbits"], ["swaths", "Swaths"], ["labels", "Labels"], ["aois", "AOIs"], ["night", "City lights"], ["glint", "Sun glint"], ["clouds", "Clouds (static)"], ["atmosphere", "Atmosphere"]] as [keyof typeof layers, string][]).map(([k, lab]) => (
          <button key={k} onClick={() => setLayers((l) => ({ ...l, [k]: !l[k] }))} className={`rounded-md border px-2 py-1 text-[11px] ${layers[k] ? "border-cyan/60 text-ink" : "border-edge text-dim"}`}>{lab}</button>))}
        <span className="mx-1 h-5 w-px bg-edge" />
        <button onClick={camUAE} className="btn px-2 py-1 text-[11px]"><Radar size={13} /> UAE</button>
        <button onClick={camGlobe} className="btn px-2 py-1 text-[11px]"><Globe2 size={13} /> Globe</button>
      </div>

      <div className="pointer-events-none absolute bottom-[62px] left-3 max-w-[60%] text-[10px] text-dim">
        Earth: NASA Blue Marble / Black Marble; cloud layer is a static texture, not the actual cloud cover · orbits: {tle.source}, snapshot {tle.fetched_utc.slice(0, 10)}, SGP4 (satellite.js) · swaths from published instrument specs · Satellite 813 orbit and marker are illustrative
      </div>
      {hovered && hovered !== selected && positions.current.get(hovered) && (
        <div className="pointer-events-none absolute left-1/2 top-[86px] -translate-x-1/2 rounded-md border border-edge bg-void/85 px-3 py-1 text-[12px]">
          {sats.find((s) => s.key === hovered)?.name} · {Math.round(positions.current.get(hovered)!.lla.alt)} km · click to select
        </div>)}
    </div>
  );
}
