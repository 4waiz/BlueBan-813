"use client";
/** Shared helpers for the inland 3D scenes. */
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

/**
 * Display colour for a wavelength. Visible light uses an approximate spectral
 * hue; NIR and SWIR (invisible) get a false-colour ramp from deep red through
 * magenta to steel blue, so every band stays distinguishable.
 */
export function wavelengthColor(nm: number): THREE.Color {
  const c = new THREE.Color();
  if (nm < 700) {
    const stops: [number, string][] = [[380, "#7A3CFF"], [440, "#3D5BFF"], [490, "#27C3F3"], [510, "#23D484"],
      [580, "#F5E33D"], [620, "#FF8A3D"], [700, "#FF3D4F"]];
    for (let i = 1; i < stops.length; i++) {
      if (nm <= stops[i][0]) {
        const [a, ca] = stops[i - 1], [b, cb] = stops[i];
        return c.set(ca).lerp(new THREE.Color(cb), Math.max(0, (nm - a) / (b - a)));
      }
    }
  }
  const ir: [number, string][] = [[700, "#FF3D4F"], [1000, "#E0389A"], [1400, "#A55BFF"], [1900, "#6C7CFF"], [2500, "#4A88C9"]];
  for (let i = 1; i < ir.length; i++) {
    if (nm <= ir[i][0]) {
      const [a, ca] = ir[i - 1], [b, cb] = ir[i];
      return c.set(ca).lerp(new THREE.Color(cb), (nm - a) / (b - a));
    }
  }
  return c.set("#4A88C9");
}

/** True while the element is on screen; the 3D canvases stop rendering when it is not. */
export function useInView<T extends HTMLElement>(margin = "120px") {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [margin]);
  return { ref, inView };
}

export const easeOutCubic = (k: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, k)), 3);
