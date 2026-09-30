"use client";
/** Legacy route: the field plan now lives in Field Ops. */
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Page() {
  const router = useRouter();
  useEffect(() => { router.replace(`/field${window.location.search}`); }, [router]);
  return <div className="p-6 text-[13px] text-muted">Field Ops has replaced this page. Redirecting…</div>;
}
