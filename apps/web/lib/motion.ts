"use client";

/**
 * Motion utilities.
 *
 * Animation here is instrumentation, not decoration: numbers settle the way a
 * real gauge settles, panels arrive in reading order, and anything that moves
 * is either carrying data or directing attention. Every hook honours
 * `prefers-reduced-motion` and drops straight to the final value.
 */

import { useEffect, useRef, useState } from "react";

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Ease used across the app: fast out, gentle settle. Matches a damped needle. */
export function easeOutExpo(t: number): number {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

export function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/**
 * Animates a number toward `target`, re-animating whenever the target changes.
 * Returns the current displayed value.
 */
export function useCountUp(target: number | null | undefined, ms = 900,
                           ease = easeOutExpo): number {
  const valid = target !== null && target !== undefined && Number.isFinite(target);
  const to = valid ? (target as number) : 0;
  const [v, setV] = useState(() => (prefersReducedMotion() ? to : 0));
  const from = useRef(0);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    if (!valid) return;
    if (prefersReducedMotion() || ms <= 0) { setV(to); return; }
    const start = performance.now();
    const a = from.current;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const next = a + (to - a) * ease(t);
      setV(next);
      if (t < 1) raf.current = requestAnimationFrame(tick);
      else from.current = to;
    };
    raf.current = requestAnimationFrame(tick);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [to, valid, ms]);

  return valid ? v : NaN;
}

/** True once the element has entered the viewport, for staggered reveals. */
export function useReveal<T extends HTMLElement>(delayMs = 0) {
  const ref = useRef<T | null>(null);
  const [on, setOn] = useState(() => prefersReducedMotion());

  useEffect(() => {
    if (prefersReducedMotion()) { setOn(true); return; }
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) {
        const t = setTimeout(() => setOn(true), delayMs);
        io.disconnect();
        return () => clearTimeout(t);
      }
    }, { threshold: 0.08 });
    io.observe(el);
    return () => io.disconnect();
  }, [delayMs]);

  return { ref, on };
}

/**
 * A monotonic clock that only runs while `playing`, exposed as elapsed seconds.
 * Used to drive the forecast timeline and the animated vector field.
 */
export function useAnimationClock(playing: boolean, speed = 1) {
  const [t, setT] = useState(0);
  const raf = useRef<number | null>(null);
  const last = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) { last.current = null; return; }
    const tick = (now: number) => {
      if (last.current !== null) {
        setT((prev) => prev + ((now - last.current!) / 1000) * speed);
      }
      last.current = now;
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      last.current = null;
    };
  }, [playing, speed]);

  return [t, setT] as const;
}

/** Linear interpolation between two lon/lat positions. */
export function lerpLngLat(a: [number, number], b: [number, number], t: number):
  [number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}
