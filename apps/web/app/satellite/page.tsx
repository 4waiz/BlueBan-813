"use client";
/**
 * Full-screen Satellite View: real orbits over a real Earth (see OrbitViewer).
 * Opened from the Satellite View panel; ?sensor=813|S2|S3|S1|LS|PACE|TAN picks
 * the first spacecraft to select.
 */
import React, { Suspense } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useEngineQuery, useStatic } from "@/lib/engine";
import type { TleSet } from "@/components/satellite/OrbitViewer";

const OrbitViewer = dynamic(() => import("@/components/satellite/OrbitViewer"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-[13px] text-muted">Loading Earth and orbits…</div>,
});

function View() {
  const router = useRouter();
  const sensor = useSearchParams().get("sensor") || "S2";
  const tle = useStatic<TleSet>("registers/tle_eo.json");
  const aois = useEngineQuery((e) => e.aois()).data || [];
  const list = useEngineQuery((e) => e.listIncidents()).data || [];
  const heroId = list.find((i) => i.role !== "negative_control" && i.aoi_id?.startsWith("AE") && i.status === "UNDER_REVIEW")?.id || list.find((i) => i.aoi_id?.startsWith("AE"))?.id || null;
  const hero = useEngineQuery((e) => (heroId ? e.getIncident(heroId) : Promise.resolve(null)), [heroId]).data || null;
  const exit = () => { if (window.history.length > 1) router.back(); else router.push("/"); };
  return (
    <div className="fixed inset-0 z-[80] bg-[#02040b]">
      {tle.error ? <div className="grid h-full place-items-center text-critical">Orbital elements missing (config/tle_eo.json): {String(tle.error)}</div>
        : tle.data ? <OrbitViewer tle={tle.data} aois={aois} incident={hero} initialSensor={sensor} onExit={exit} />
          : <div className="grid h-full place-items-center text-[13px] text-muted">Loading orbital elements…</div>}
    </div>
  );
}

export default function Page() { return <Suspense><View /></Suspense>; }
