"use client";

/**
 * DATA - the evidence drawer.
 *
 * Every result in this product is traceable to a scene, a licence and an
 * algorithm. This screen is where a reviewer checks that claim, including the
 * checksum of the file the numbers came from.
 */

import React, { useEffect, useState } from "react";
import { FileText, ExternalLink, ShieldCheck, AlertTriangle } from "lucide-react";

import { Panel, Loading, ErrorBox, KV, Chip, Caveat, Readout, SimulatedBadge } from "@/components/hud";
import { api, fmt, fmtInt, pct, utc } from "@/lib/api";

export default function DataScreen() {
  const [prov, setProv] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [docs, setDocs] = useState<{ key: string; file: string; bytes: number }[]>([]);
  const [doc, setDoc] = useState<{ key: string; text: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [openSrc, setOpenSrc] = useState<number | null>(0);

  useEffect(() => {
    (async () => {
      try {
        const idx = await api.events();
        const id = idx.events[0].event_id;
        const [p, s, d] = await Promise.all([
          api.provenance(id), api.status(),
          api.docsList().catch(() => ({ docs: [] })),
        ]);
        setProv(p); setStatus(s); setDocs(d.docs ?? []);
      } catch (e: any) { setErr(e.message ?? String(e)); }
    })();
  }, []);

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!prov) return <Loading what="provenance record" />;

  const sources = prov.sources ?? [];
  const alg = prov.algorithm ?? {};

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3">
      <Panel title="Data policy" accent="#4A93FF">
        <div className="grid md:grid-cols-[1fr_auto] gap-4 items-start">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={14} className="text-beam2" />
              <span className="hud-value text-[13px] text-beam2">
                No Satellite 813 data is used anywhere in this system
              </span>
            </div>
            <p className="text-[11.5px] leading-[1.75] text-muted">
              Satellite 813 is incubation-only for this programme phase, and the
              official participant guide instructs teams not to design a PoC that
              depends on it. Every hyperspectral measurement here is real Planet
              Tanager-1 data. Everything labelled 813 is a clearly marked
              simulation built from that data by convolving it onto 813&apos;s
              published band configuration.
            </p>
          </div>
          <div className="shrink-0"><SimulatedBadge /></div>
        </div>
        {status && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-6 mt-3">
            <KV k="Real 813 pixels" v={status.data_policy?.real_813_data_used ? "yes" : "NONE"}
                color="#4A93FF" />
            <KV k="813 status" v={status.data_policy?.["813_status"]} />
            <KV k="In-situ available" v={status.data_policy?.in_situ_available ? "yes" : "NONE"}
                color="#F5C451" />
            <KV k="Events built" v={fmtInt(status.events_available)} />
          </div>
        )}
      </Panel>

      <Panel title="Sources" accent="#3FD1A0"
             right={<Chip label={`${sources.length} DATASETS`} color="#3FD1A0" />}>
        <div className="space-y-2">
          {sources.map((s: any, i: number) => {
            const on = openSrc === i;
            const sim = (s.satellite ?? "").includes("SIMULATED");
            return (
              <div key={i} className="panel-quiet chamfer-sm panel-in"
                   style={{ animationDelay: `${i * 60}ms`,
                            borderColor: sim ? "rgba(74,147,255,0.4)" : undefined }}>
                <button onClick={() => setOpenSrc(on ? null : i)}
                        className="w-full text-left px-3 py-2.5 tap flex items-center gap-3">
                  <span className="w-[6px] h-[6px] chamfer-sm shrink-0"
                        style={{ background: sim ? "#4A93FF" : "#3FD1A0" }} />
                  <span className="min-w-0 flex-1">
                    <span className="hud-value text-[11.5px] text-ink">{s.satellite}</span>
                    <span className="hud-label ml-2">{s.sensor}</span>
                    <span className="block hud-label mt-[3px] normal-case truncate"
                          style={{ letterSpacing: "0.05em" }}>
                      {s.product} · {s.processing_level}
                    </span>
                  </span>
                  {sim && <SimulatedBadge compact />}
                  <Chip label={s.licence ?? "-"} color="#5A6490" />
                </button>

                {on && (
                  <div className="px-3 pb-3 pt-1 border-t border-edge/50">
                    <div className="grid md:grid-cols-2 gap-x-6">
                      <KV k="Scene ID" v={s.scene_id} />
                      <KV k="Acquisition" v={utc(s.acquisition_utc)} />
                      <KV k="Provider" v={s.provider} />
                      <KV k="Licence" v={s.licence} />
                      <KV k="Native resolution"
                          v={Array.isArray(s.native_resolution_m)
                              ? `${s.native_resolution_m.join(" / ")} m`
                              : s.native_resolution_m ? `${s.native_resolution_m} m` : "-"} />
                      <KV k="Units" v={s.units || "-"} />
                      {s.bands_used?.length > 0 && (
                        <KV k="Bands used" v={`${s.bands_used.length} bands`} />
                      )}
                      {s.wavelengths_nm?.length > 0 && (
                        <KV k="Wavelength range"
                            v={`${fmt(s.wavelengths_nm[0], 1)}-${fmt(s.wavelengths_nm.at(-1), 1)} nm`} />
                      )}
                      {s.quality_mask && <KV k="Quality masks" v={s.quality_mask} />}
                      {s.sha256 && (
                        <KV k="SHA-256"
                            v={<span className="break-all text-[10px]">{s.sha256}</span>} />
                      )}
                      {s.local_path && <KV k="Local path" v={s.local_path} />}
                    </div>
                    {s.access_url && (
                      <a href={s.access_url} target="_blank" rel="noreferrer"
                         className="mt-2.5 inline-flex items-center gap-1.5 hud-label
                                    hover:text-beam transition-colors"
                         style={{ color: "#4A93FF" }}>
                        source URL <ExternalLink size={10} />
                      </a>
                    )}
                    {s.notes && (
                      <p className="text-[10.5px] leading-[1.65] text-dim mt-2.5">{s.notes}</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Panel>

      <div className="grid lg:grid-cols-[1.4fr_1fr] gap-3">
        <Panel title="Algorithm" accent="#3186FF">
          <Readout label={alg.name ?? "-"} value={alg.description ?? "-"}
                   size="sm" mono={false} color="#C9D0EE" />
          {alg.reference && (
            <p className="hud-label mt-2 normal-case" style={{ letterSpacing: "0.05em" }}>
              {alg.reference}
            </p>
          )}
          <div className="mt-3 grid sm:grid-cols-2 gap-x-6">
            {Object.entries(alg.parameters ?? {}).map(([k, v]) => (
              <KV key={k} k={k.replace(/_/g, " ")}
                  v={typeof v === "object" ? JSON.stringify(v) : String(v)} />
            ))}
          </div>
          {alg.assumptions?.length > 0 && (
            <div className="mt-3">
              <div className="hud-label mb-2">assumptions</div>
              <ul className="space-y-1.5">
                {alg.assumptions.map((a: string) => (
                  <li key={a} className="flex gap-2 text-[10.5px] leading-[1.55] text-muted">
                    <span className="text-dim">›</span><span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {alg.limitations?.length > 0 && (
            <div className="mt-3">
              <div className="hud-label mb-2" style={{ color: "#FF7A45" }}>limitations</div>
              <ul className="space-y-1.5">
                {alg.limitations.map((a: string) => (
                  <li key={a} className="flex gap-2 text-[10.5px] leading-[1.55] text-caution/90">
                    <span className="text-alert">-</span><span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>

        <div className="flex flex-col gap-3">
          <Panel title="Record integrity" accent="#3FD1A0">
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck size={14} className="text-nominal" />
              <span className="hud-value text-[12px] text-nominal">
                schema v{prov.schema_version}
              </span>
            </div>
            <KV k="Result ID" v={prov.result_id} />
            <KV k="Result kind" v={prov.result_kind} />
            <KV k="Code version" v={prov.code_version} />
            <KV k="Processed" v={utc(prov.processed_utc)} />
            <KV k="Python" v={prov.environment?.python} />
            <KV k="Platform" v={prov.environment?.platform} />
          </Panel>

          <Panel title="Documentation" tight>
            <div className="divide-y divide-edge/40">
              {docs.length === 0 && (
                <p className="text-[11px] text-dim p-2">No documents exposed by the API.</p>
              )}
              {docs.map((d) => (
                <button key={d.key}
                        onClick={async () => {
                          if (doc?.key === d.key) { setDoc(null); return; }
                          try {
                            const text = await api.doc(d.key);
                            setDoc({ key: d.key, text });
                          } catch { setDoc({ key: d.key, text: "Could not load." }); }
                        }}
                        className="w-full text-left px-2.5 py-2 row-hover tap flex items-center gap-2">
                  <FileText size={11} className="text-dim shrink-0" />
                  <span className="hud-value text-[10.5px] text-ink flex-1 truncate">
                    {d.file}
                  </span>
                  <span className="hud-label shrink-0">{Math.round(d.bytes / 1024)} kB</span>
                </button>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      {doc && (
        <Panel title={doc.key} accent="#4A93FF"
               right={
                 <button onClick={() => setDoc(null)} className="hud-label tap hover:text-beam">
                   close
                 </button>
               }>
          <pre className="text-[10.5px] leading-[1.7] text-muted whitespace-pre-wrap
                          font-mono max-h-[520px] overflow-y-auto">{doc.text}</pre>
        </Panel>
      )}

      <Panel title="Attribution required when reusing this data" accent="#F5C451">
        <div className="space-y-2 text-[11px] leading-[1.7] text-muted">
          <p className="hud-value text-[10.5px]">
            Tanager STAC Data, available at www.planet.com/data/stac © 2025 Planet
            Labs PBC. All Rights Reserved. (CC-BY-4.0)
          </p>
          <p className="hud-value text-[10.5px]">
            Contains modified Copernicus Sentinel data (Sentinel-2 MSI,
            Sentinel-3 OLCI), processed by ESA and accessed via Microsoft
            Planetary Computer.
          </p>
          <p className="hud-value text-[10.5px]">
            Landsat 8/9 courtesy of the U.S. Geological Survey.
          </p>
          <p className="hud-value text-[10.5px]">
            ERA5 reanalysis generated by ECMWF for the Copernicus Climate Change
            Service, accessed through the Open-Meteo historical archive API.
          </p>
        </div>
        <Caveat>
          No raw Earth observation imagery is committed to this repository. Only
          code, metadata, checksums and derived outputs are published.
        </Caveat>
      </Panel>
    </div>
  );
}
