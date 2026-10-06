"use client";
/**
 * Engine selection. NEXT_PUBLIC_DATA_MODE=live talks to the FastAPI backend;
 * anything else (the static Cloudflare deployment) runs the in-browser
 * workspace seeded from /pipeline/workspace/seed.json.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { Engine } from "./types";
import { HttpEngine } from "./http";
import { LocalEngine } from "./local";

export const DATA_MODE: "live" | "static" =
  (process.env.NEXT_PUBLIC_DATA_MODE as "live" | "static") === "live" ? "live" : "static";
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
export const pipelineUrl = (p: string) => `${BASE_PATH}/pipeline/${p.replace(/^\//, "")}`;

let engine: Engine | null = null;
export function getEngine(): Engine {
  if (!engine) engine = DATA_MODE === "live" ? new HttpEngine("/api") : new LocalEngine(pipelineUrl("workspace/seed.json"));
  return engine;
}

// A tiny change bus so every panel re-reads after any write.
const listeners = new Set<() => void>();
export function notifyChanged() { listeners.forEach((f) => f()); }
export function onChanged(f: () => void) { listeners.add(f); return () => { listeners.delete(f); }; }

/** Load something from the engine and reload it whenever the workspace changes. */
export function useEngineQuery<T>(fn: (e: Engine) => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const load = useCallback(async () => {
    try { setData(await fnRef.current(getEngine())); setError(null); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, []);
  // A new query (changed deps) is "loading" until it answers; reloads after a
  // workspace write keep showing the current data instead of flashing a spinner.
  useEffect(() => { setLoading(true); load(); return onChanged(load); }, [load, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, loading, reload: load };
}

/** Run a write against the engine, then broadcast the change. */
export async function mutate<T>(fn: (e: Engine) => Promise<T>): Promise<T> {
  const out = await fn(getEngine());
  notifyChanged();
  return out;
}

export function useStatic<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    let dead = false;
    fetch(pipelineUrl(path)).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${path}`))))
      .then((d) => { if (!dead) setData(d); }).catch((e) => { if (!dead) setError(e.message); });
    return () => { dead = true; };
  }, [path]);
  return { data, error };
}

const OPERATOR_KEY = "blueban813.operator";
export function getOperator(): string {
  try { return localStorage.getItem(OPERATOR_KEY) || ""; } catch { return ""; }
}
export function setOperator(name: string) {
  try { localStorage.setItem(OPERATOR_KEY, name.trim()); } catch { /* ignore */ }
  notifyChanged();
}
