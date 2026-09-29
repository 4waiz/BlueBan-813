/**
 * Nominal next Sentinel-2 overpass over the monitored AOIs.
 *
 * Each Sentinel-2 satellite repeats the same relative orbit every 10 days. For
 * every (platform, relative orbit) pair seen in an AOI's archive, the next
 * nominal pass is the last observed one plus a whole number of 10-day cycles.
 * This is a schedule, not a promise: acquisition plans change and clouds can
 * make a pass useless, which is why the UI labels it NOMINAL.
 */
import type { Aoi } from "./engine/types";

const REPEAT_MS = 10 * 86400e3;

export function nextPass(aois: Aoi[], now: Date) {
  let best: { at: Date; platform: string; orbit: number; aoi: string } | null = null;
  for (const a of aois) {
    for (const p of ((a as unknown as { pass_pattern?: { platform: string; relative_orbit: number; last: string }[] }).pass_pattern || [])) {
      const last = new Date(p.last);
      if (Number.isNaN(last.getTime())) continue;
      const k = Math.max(1, Math.ceil((now.getTime() - last.getTime()) / REPEAT_MS));
      let at = new Date(last.getTime() + k * REPEAT_MS);
      if (at <= now) at = new Date(at.getTime() + REPEAT_MS);
      if (!best || at < best.at) best = { at, platform: p.platform, orbit: p.relative_orbit, aoi: a.id };
    }
  }
  if (!best) return null;
  const mins = Math.round((best.at.getTime() - now.getTime()) / 60000);
  const inText = mins >= 1440 ? `${Math.floor(mins / 1440)}d ${Math.floor((mins % 1440) / 60)}h` : `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`;
  return { ...best, inText };
}
