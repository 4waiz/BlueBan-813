"use client";
/**
 * Route transition: on client-side navigation each screen fades in under one
 * push-broom scan line. Opacity only, never a transform, so fixed-position
 * overlays inside pages keep viewport positioning. The first, server-rendered
 * load is left alone (no hidden content before hydration), and reduced-motion
 * users get no animation.
 */
import React, { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

let firstLoad = true;

export default function Template({ children }: { children: React.ReactNode }) {
  const reduce = useReducedMotion();
  const [animated] = useState(() => !firstLoad);
  // The scan line is removed once it has crossed: parked at the bottom edge it
  // would add a pixel of overflow and a needless scrollbar to one-screen pages.
  const [scanDone, setScanDone] = useState(false);
  useEffect(() => { firstLoad = false; }, []);
  const on = animated && !reduce;
  return (
    <motion.div className="relative h-full" initial={on ? { opacity: 0 } : false} animate={{ opacity: 1 }} transition={{ duration: 0.32, ease: "easeOut" }}>
      {on && !scanDone && (
        <motion.div aria-hidden className="pointer-events-none absolute inset-x-0 z-40 h-px"
          style={{ background: "linear-gradient(90deg, transparent, #27C3F3 25%, #CFF4FF 50%, #27C3F3 75%, transparent)", boxShadow: "0 0 16px 2px rgba(39,195,243,0.55)" }}
          initial={{ top: "0%", opacity: 0.95 }} animate={{ top: "calc(100% - 1px)", opacity: 0 }} transition={{ duration: 0.75, ease: "easeInOut" }}
          onAnimationComplete={() => setScanDone(true)} />
      )}
      {children}
    </motion.div>
  );
}
