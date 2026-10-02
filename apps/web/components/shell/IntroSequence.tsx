"use client";
/**
 * Opening sequence: a hyperspectral cube assembles band by band, then the
 * wordmark. About three seconds, once per browser session, skippable (click,
 * Esc, Enter or the button), and never shown under prefers-reduced-motion.
 * ?intro=1 forces it (demos), ?intro=0 suppresses it.
 *
 * The 3D scene is loaded on demand, so three.js does not enter every page's
 * first bundle; the app renders underneath the whole time.
 */
import React, { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion } from "framer-motion";

const IntroScene = dynamic(() => import("./IntroScene"), { ssr: false });
const KEY = "blueban813.intro.seen";
const WORD = "BLUEBAN";

export default function IntroSequence() {
  const [show, setShow] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("intro");
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let seen = false;
    try { seen = sessionStorage.getItem(KEY) === "1"; } catch { /* storage blocked: treat as not seen */ }
    if (q === "0" || (q !== "1" && (seen || reduce))) return;
    try { sessionStorage.setItem(KEY, "1"); } catch { /* ignore */ }
    setShow(true);
  }, []);

  const skip = useCallback(() => setLeaving(true), []);

  useEffect(() => {
    if (!show) return;
    const leave = setTimeout(() => setLeaving(true), 3300);
    const onKey = (e: KeyboardEvent) => { if (["Escape", "Enter", " "].includes(e.key)) skip(); };
    window.addEventListener("keydown", onKey);
    return () => { clearTimeout(leave); window.removeEventListener("keydown", onKey); };
  }, [show, skip]);

  return (
    // After the fade-out the sequence is over for good: `leaving` stays set and
    // `show` drops, which also removes the key listener and the timer.
    <AnimatePresence onExitComplete={() => setShow(false)}>
      {show && !leaving && (
        <motion.div key="intro" className="fixed inset-0 z-[100] cursor-pointer overflow-hidden bg-void" onClick={skip}
          initial={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.6, ease: "easeInOut" }}
          aria-label="BLUEBAN 813 opening sequence" role="presentation">
          <div className="absolute inset-0" style={{ background: "radial-gradient(ellipse at 50% 55%, rgba(47,123,255,0.18), transparent 60%)" }} />
          <div className="absolute inset-0"><IntroScene /></div>
          <div className="pointer-events-none absolute inset-x-0 bottom-[16%] flex flex-col items-center text-center">
            <div className="flex font-display text-[44px] font-extrabold tracking-[0.18em] text-ink sm:text-[64px]">
              {WORD.split("").map((ch, i) => (
                <motion.span key={i} initial={{ opacity: 0, y: 18, filter: "blur(8px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  transition={{ delay: 1.15 + i * 0.06, duration: 0.5, ease: "easeOut" }}>{ch}</motion.span>
              ))}
              <motion.span className="ml-[0.35em] bg-gradient-to-r from-cyan to-beam2 bg-clip-text text-transparent"
                initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 1.7, duration: 0.55, ease: "backOut" }}>813</motion.span>
            </div>
            <motion.div className="mt-2 text-[12px] font-semibold tracking-[0.42em] text-muted sm:text-[13px]"
              initial={{ opacity: 0, letterSpacing: "0.9em" }} animate={{ opacity: 1, letterSpacing: "0.42em" }} transition={{ delay: 2.0, duration: 0.8, ease: "easeOut" }}>
              UAE COASTAL &amp; INLAND WATER INTELLIGENCE
            </motion.div>
            <motion.div className="mt-5 h-px w-[220px] bg-gradient-to-r from-transparent via-cyan to-transparent"
              initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 2.2, duration: 0.7 }} />
          </div>
          <button onClick={(e) => { e.stopPropagation(); skip(); }}
            className="absolute bottom-5 right-5 rounded-md border border-line bg-panel/70 px-3 py-1.5 text-[11px] font-semibold tracking-[0.14em] text-muted hover:border-beam2 hover:text-ink"
            aria-label="Skip the opening sequence">SKIP · ESC</button>
          <div className="absolute bottom-5 left-5 text-[10.5px] tracking-[0.2em] text-dim">TEAM KANBAN</div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
