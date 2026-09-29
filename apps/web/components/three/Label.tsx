"use client";
/**
 * Text label for React Three Fiber scenes, drawn into a CanvasTexture sprite.
 * Avoids drei <Html>, which mounts a separate React root per label and trips
 * React 19's "unmount while rendering" guard when scenes update.
 */
import React, { useEffect, useMemo } from "react";
import * as THREE from "three";

export default function Label({ text, position, color = "#93A6CB", size = 0.16, bold = false }: {
  text: string; position: [number, number, number]; color?: string; size?: number; bold?: boolean;
}) {
  const { tex, aspect } = useMemo(() => {
    const scale = 4, fontPx = 22 * scale;
    const c = document.createElement("canvas");
    const ctx = c.getContext("2d")!;
    const font = `${bold ? 700 : 600} ${fontPx}px Inter, system-ui, sans-serif`;
    ctx.font = font;
    const w = Math.ceil(ctx.measureText(text).width) + 16 * scale, h = Math.ceil(fontPx * 1.35);
    c.width = w; c.height = h;
    ctx.font = font;
    ctx.fillStyle = color;
    ctx.textBaseline = "middle";
    ctx.fillText(text, 8 * scale, h / 2);
    const t = new THREE.CanvasTexture(c);
    t.anisotropy = 4;
    t.needsUpdate = true;
    return { tex: t, aspect: w / h };
  }, [text, color, bold]);
  useEffect(() => () => tex.dispose(), [tex]);
  return (
    <sprite position={position} scale={[size * aspect, size, 1]} renderOrder={10}>
      <spriteMaterial map={tex} transparent depthTest={false} depthWrite={false} />
    </sprite>
  );
}
