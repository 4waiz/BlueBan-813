"use client";

/**
 * Application shell: the persistent mission-control frame.
 *
 * Top strip carries identity and live mission state. The bottom dock is the
 * systems navigation, styled as cockpit hardware rather than web tabs.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { useEffect, useState } from "react";
import {
  Activity, Binoculars, FlaskConical, Radar, Ship, Waves,
  ShieldCheck, Database, Terminal, Presentation,
} from "lucide-react";

import { api, PRIORITY_COLOR, utc } from "@/lib/api";
import { StatusDot, SimulatedBadge } from "./hud";

const TABS = [
  { href: "/", label: "OVERVIEW", Icon: Radar },
  { href: "/watch", label: "WATCH", Icon: Binoculars },
  { href: "/spectra", label: "SPECTRA", Icon: Waves },
  { href: "/forecast", label: "FORECAST", Icon: Activity },
  { href: "/assets", label: "ASSETS", Icon: Ship },
  { href: "/samples", label: "SAMPLES", Icon: FlaskConical },
  { href: "/validation", label: "VALIDATION", Icon: ShieldCheck },
  { href: "/data", label: "DATA", Icon: Database },
  { href: "/api", label: "API", Icon: Terminal },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [state, setState] = useState<{
    id?: string; aoi?: string; country?: string; priority?: string;
    acq?: string; sim?: boolean;
  }>({});
  const [clock, setClock] = useState<string>("");

  useEffect(() => {
    const t = setInterval(
      () => setClock(new Date().toISOString().slice(11, 19) + "Z"), 1000);
    setClock(new Date().toISOString().slice(11, 19) + "Z");
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        const [ev, st] = await Promise.all([api.events(), api.status()]);
        if (dead) return;
        const e = ev.events?.[0];
        setState({
          id: e?.event_id, aoi: e?.aoi, country: e?.country,
          priority: e?.state, acq: e?.acquisition_utc,
          sim: st?.data_policy?.real_813_data_used === false,
        });
      } catch {
        /* the pages themselves surface the error in detail */
      }
    })();
    return () => { dead = true; };
  }, []);

  const pc = PRIORITY_COLOR[state.priority ?? "UNKNOWN"];

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* ------------------------------------------------------ top strip */}
      <header className="sticky top-0 z-40 border-b border-edge bg-void/92 backdrop-blur-md">
        <div className="flex items-stretch h-[54px]">
          <Link href="/" className="flex items-center gap-3 pl-4 pr-5 border-r border-edge shrink-0
                                    hover:bg-white/[0.03] transition-colors">
            <svg width="24" height="24" viewBox="0 0 24 24" className="shrink-0">
              <circle cx="12" cy="12" r="10.2" fill="none" stroke="#243056" strokeWidth="1"
                      strokeDasharray="1.5 3.5" />
              <path d="M4.6 13.4c1.9-2.1 3.7-2.1 5.6 0s3.7 2.1 5.6 0 3.7-2.1 5.6 0"
                    fill="none" stroke="#3186FF" strokeWidth="1.5" strokeLinecap="round" />
              <path d="M5.6 9.6c1.7-1.9 3.3-1.9 5 0s3.3 1.9 5 0 3.3-1.9 5 0"
                    fill="none" stroke="#3186FF" strokeWidth="1.1" strokeLinecap="round"
                    opacity="0.5" />
              <circle cx="12" cy="12" r="1.7" fill="#4A93FF" />
            </svg>
            <div className="leading-none">
              <div className="text-[14px] font-semibold tracking-wide2 text-ink">
                BLUEBAN <span className="text-beam">813</span>
              </div>
              <div className="hud-label mt-[3px]">water threat intelligence</div>
            </div>
          </Link>

          <div className="hidden lg:flex items-center gap-6 px-5 border-r border-edge min-w-0">
            <Field k="AOI" v={state.aoi ? `${state.aoi}, ${state.country}` : "—"} />
            <Field k="Event ID" v={state.id ?? "—"} />
            <Field k="Observation" v={state.acq ? utc(state.acq) : "—"} />
          </div>

          <div className="flex-1 min-w-0" />

          {state.sim && (
            <div className="hidden xl:flex items-center px-4 border-l border-edge">
              <SimulatedBadge />
            </div>
          )}

          <div className="flex items-center gap-2.5 px-4 border-l border-edge shrink-0">
            <StatusDot color={pc} pulse={state.priority === "HIGH_PRIORITY"} />
            <div className="leading-none">
              <div className="hud-label">system state</div>
              <div className="hud-value text-[12px] mt-[3px] tracking-wide2"
                   style={{ color: pc }}>
                {(state.priority ?? "STANDBY").replace("_", " ")}
              </div>
            </div>
          </div>

          <div className="hidden md:flex items-center px-4 border-l border-edge shrink-0">
            <div className="leading-none text-right">
              <div className="hud-label">UTC</div>
              <div className="hud-value text-[12px] mt-[3px] text-muted">{clock}</div>
            </div>
          </div>

          <Link href="/judge"
                className="flex items-center gap-2 px-4 border-l border-edge shrink-0
                           hover:bg-beam/10 transition-colors group"
                style={{ background: path === "/judge" ? "rgba(49,134,255,0.12)" : undefined }}>
            <Presentation size={15} className="text-beam" />
            <span className="hud-label hidden sm:inline" style={{ color: "#4A93FF" }}>
              judge mode
            </span>
          </Link>
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-hidden">{children}</main>

      {/* ------------------------------------------------------ bottom dock */}
      <nav className="sticky bottom-0 z-40 border-t border-edge bg-void/94 backdrop-blur-md">
        <div className="flex items-stretch overflow-x-auto">
          {TABS.map(({ href, label, Icon }) => {
            const on = path === href;
            return (
              <Link key={href} href={href}
                    className={`relative flex flex-col items-center justify-center gap-[5px]
                                px-4 sm:px-6 py-2.5 min-w-[74px] transition-colors
                                ${on ? "bg-beam/[0.1]" : "hover:bg-white/[0.035]"}`}>
                <Icon size={15} className={on ? "text-beam" : "text-dim"} strokeWidth={1.7} />
                <span className="hud-label whitespace-nowrap"
                      style={{ color: on ? "#4A93FF" : undefined }}>
                  {label}
                </span>
                {on && (
                  <span className="absolute bottom-0 left-2 right-2 h-[2px] bg-beam"
                        style={{ boxShadow: "0 0 10px 0 #3186FF" }} />
                )}
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div className="leading-none min-w-0">
      <div className="hud-label">{k}</div>
      <div className="hud-value text-[11.5px] mt-[4px] text-muted truncate max-w-[210px]">{v}</div>
    </div>
  );
}
