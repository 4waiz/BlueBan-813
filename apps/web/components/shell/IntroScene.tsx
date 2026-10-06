"use client";
/**
 * The intro's 3D scene: a hyperspectral cube assembling band by band
 * (400 -> 2450 nm, false-coloured beyond the visible) under a push-broom scan
 * line, in a slow star field. Decorative: no data is drawn here.
 */
import React, { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import Canvas from "@/components/three/ZoomCanvas";
import * as THREE from "three";
import { easeOutCubic, wavelengthColor } from "@/components/inland/visuals";

const N = 36, SIDE = 1.9, DEPTH = 2.6;
const zOf = (i: number) => -DEPTH / 2 + (i / (N - 1)) * DEPTH;

function gridTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(255,255,255,0.10)";
  g.fillRect(0, 0, 128, 128);
  g.strokeStyle = "rgba(255,255,255,0.95)";
  g.lineWidth = 1.2;
  for (let i = 0; i <= 128; i += 16) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, 128); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(128, i); g.stroke(); }
  const t = new THREE.CanvasTexture(c);
  t.needsUpdate = true;
  return t;
}

function Cube() {
  const group = useRef<THREE.Group>(null);
  const slabs = useRef<THREE.Mesh[]>([]);
  const scan = useRef<THREE.Mesh>(null);
  const tex = useMemo(() => gridTexture(), []);
  useEffect(() => () => tex.dispose(), [tex]);
  const colors = useMemo(() => Array.from({ length: N }, (_, i) => wavelengthColor(400 + (i / (N - 1)) * 2050)), []);
  useFrame(({ clock, camera }) => {
    const t = clock.elapsedTime;
    slabs.current.forEach((m, i) => {
      const k = easeOutCubic((t - 0.1 - i * 0.032) / 0.6);
      m.position.y = (1 - k) * 2.4;
      m.scale.setScalar(0.55 + 0.45 * k);
      (m.material as THREE.MeshBasicMaterial).opacity = 0.15 * k;
    });
    if (group.current) { group.current.rotation.y = -0.75 + t * 0.32; group.current.rotation.x = 0.38 + 0.05 * Math.sin(t * 0.8); }
    if (scan.current) {
      const k = Math.max(0, t - 1.0) * 0.8;
      scan.current.position.z = -DEPTH / 2 - 0.1 + (k % 1) * (DEPTH + 0.2);
      (scan.current.material as THREE.MeshBasicMaterial).opacity = t > 1.0 ? 0.22 : 0;
    }
    camera.position.z = 8.2 - easeOutCubic(t / 3.2) * 1.1;
  });
  return (
    <group ref={group} position={[0, 0.75, 0]}>
      {colors.map((c, i) => (
        <mesh key={i} ref={(el) => { if (el) slabs.current[i] = el; }} position={[0, 2.4, zOf(i)]}>
          <planeGeometry args={[SIDE, SIDE]} />
          <meshBasicMaterial color={c} map={tex} transparent opacity={0} side={THREE.DoubleSide} depthWrite={false} blending={THREE.AdditiveBlending} />
        </mesh>
      ))}
      <lineSegments>
        <edgesGeometry args={[new THREE.BoxGeometry(SIDE, SIDE, DEPTH)]} />
        <lineBasicMaterial color="#4D93FF" transparent opacity={0.55} />
      </lineSegments>
      <mesh ref={scan}>
        <planeGeometry args={[SIDE * 1.12, SIDE * 1.12]} />
        <meshBasicMaterial color="#9BE7FF" transparent opacity={0} side={THREE.DoubleSide} depthWrite={false} blending={THREE.AdditiveBlending} />
      </mesh>
    </group>
  );
}

function Stars() {
  const ref = useRef<THREE.Points>(null);
  const geo = useMemo(() => {
    const n = 900, p = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const r = 7 + Math.random() * 16, th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
      p[i * 3] = r * Math.sin(ph) * Math.cos(th); p[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th); p[i * 3 + 2] = r * Math.cos(ph);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(p, 3));
    return g;
  }, []);
  useEffect(() => () => geo.dispose(), [geo]);
  useFrame((_, dt) => { if (ref.current) ref.current.rotation.y += dt * 0.03; });
  return (
    <points ref={ref} geometry={geo}>
      <pointsMaterial color="#9BB8FF" size={0.035} sizeAttenuation transparent opacity={0.8} />
    </points>
  );
}

export default function IntroScene() {
  return (
    <Canvas camera={{ position: [0, 0.2, 8.2], fov: 45 }} dpr={[1, 1.75]} gl={{ antialias: true, alpha: true }}>
      <Stars />
      <Cube />
    </Canvas>
  );
}
