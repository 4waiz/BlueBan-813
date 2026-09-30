"use client";
/**
 * Legacy route. The drift view is now the SCENARIO TRAJECTORY ESTIMATE inside
 * each incident: a wind-only scenario, not a hydrodynamic forecast.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Page() {
  const router = useRouter();
  useEffect(() => { router.replace(`/incident${window.location.search}`); }, [router]);
  return <div className="p-6 text-[13px] text-muted">The drift scenario now lives in the incident view. Redirecting…</div>;
}
