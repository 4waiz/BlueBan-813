"use client";

/**
 * API - the integration surface.
 *
 * A water authority will not adopt a dashboard; it will adopt something its
 * existing SCADA, GIS or alerting stack can call. This screen documents that
 * surface and lets a reviewer fire every endpoint live.
 */

import React, { useEffect, useState } from "react";
import { Play, Copy, Check } from "lucide-react";

import { Panel, Chip, KV, Caveat } from "@/components/hud";
import { api } from "@/lib/api";

interface Ep {
  method: "GET" | "POST";
  path: string;
  purpose: string;
  group: string;
}

function endpoints(eventId: string): Ep[] { return [
  { method: "GET", path: "/api/health", purpose: "Liveness probe.", group: "system" },
  { method: "GET", path: "/api/status", purpose: "Which pipeline artefacts exist, plus the data policy. Lets a client degrade honestly instead of guessing.", group: "system" },
  { method: "GET", path: "/api/config", purpose: "Project configuration: AOI, sensor cascade, algorithm parameters.", group: "system" },
  { method: "GET", path: "/api/events", purpose: "Event index with state, severity, confidence and class.", group: "events" },
  { method: "GET", path: `/api/events/${eventId}`, purpose: "The full water-event object: geometry, classification, anomaly statistics, indices, quality, temporal assessment, forecast, exposure, samples.", group: "events" },
  { method: "GET", path: `/api/events/${eventId}/spectrum`, purpose: "Background, event and per-region mean spectra with dispersion, difference, z-scores and per-band SNR.", group: "events" },
  { method: "GET", path: `/api/events/${eventId}/forecast`, purpose: "Drift steps with particle positions, the wind series used, and the model's own limitations.", group: "events" },
  { method: "GET", path: `/api/events/${eventId}/samples`, purpose: "Field-sampling plan as GeoJSON. Add ?fmt=csv for a field-ready CSV.", group: "events" },
  { method: "GET", path: `/api/events/${eventId}/provenance`, purpose: "Complete traceability record including source checksums.", group: "events" },
  { method: "GET", path: "/api/layers", purpose: "Available map layers with AOI bounds and the native grid.", group: "layers" },
  { method: "GET", path: "/api/layers/anomaly", purpose: "Colour-mapped anomaly raster (PNG, transparent off-water).", group: "layers" },
  { method: "GET", path: "/api/layers/events", purpose: "Detected event polygons as GeoJSON, with class and confidence per region.", group: "layers" },
  { method: "GET", path: "/api/validation", purpose: "Every experiment, including the ones that found no effect.", group: "validation" },
  { method: "GET", path: "/api/hyperspectral-lift", purpose: "The five-second answer to \"did 813 add measurable value?\", with confidence intervals.", group: "validation" },
  { method: "GET", path: "/api/timeseries", purpose: "Multi-year Sentinel-2 monitoring record per zone.", group: "validation" },
  { method: "GET", path: "/api/assets", purpose: "Operator assets and the supported asset taxonomy.", group: "assets" },
  { method: "POST", path: "/api/assets", purpose: "Register an operator asset. Body: {name, type, lon, lat, sensitivity?, notes?}.", group: "assets" },
  { method: "GET", path: "/api/docs-list", purpose: "Documentation exposed to the Evidence drawer.", group: "docs" },
]; }

const GROUPS = ["system", "events", "layers", "validation", "assets", "docs"];

export default function ApiScreen() {
  const [result, setResult] = useState<{ path: string; status: number; body: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  // The event id is read from the live index rather than written into this
  // page, so the endpoint list stays correct when the pipeline is re-run.
  const [eventId, setEventId] = useState<string>("");
  const [example, setExample] = useState<string>("");

  useEffect(() => {
    api.events()
      .then((d) => setEventId(d.events?.[0]?.event_id ?? ""))
      .catch(() => setEventId(""));
    api.assets()
      .then((d) => {
        const a = d.assets?.[0];
        setExample(a
          ? JSON.stringify({ name: a.name, type: a.type, lon: a.lon, lat: a.lat })
          : JSON.stringify({ name: "<asset name>", type: "<ASSET_TYPE>",
                             lon: 0, lat: 0 }));
      })
      .catch(() => setExample(JSON.stringify(
        { name: "<asset name>", type: "<ASSET_TYPE>", lon: 0, lat: 0 })));
  }, []);

  const ENDPOINTS = endpoints(eventId || "<event-id>");

  async function call(ep: Ep) {
    if (ep.method !== "GET") {
      setResult({ path: ep.path, status: 0,
                  body: "POST is not fired from this page to avoid writing state "
                        + "by accident. Use curl:\n\n"
                        + `curl -X POST ${ep.path} \\\n  -H 'Content-Type: application/json' \\\n`
                        + `  -d '${example}'` });
      return;
    }
    setBusy(ep.path);
    try {
      const r = await fetch(ep.path, { cache: "no-store" });
      const ct = r.headers.get("content-type") ?? "";
      let body: string;
      if (ct.includes("json")) {
        const j = await r.json();
        body = JSON.stringify(j, null, 1);
        if (body.length > 14000) body = body.slice(0, 14000) + "\n… truncated for display";
      } else if (ct.startsWith("image/")) {
        const b = await r.blob();
        body = `binary ${ct}, ${(b.size / 1024).toFixed(1)} kB`;
      } else {
        body = (await r.text()).slice(0, 14000);
      }
      setResult({ path: ep.path, status: r.status, body });
    } catch (e: any) {
      setResult({ path: ep.path, status: 0, body: String(e) });
    } finally { setBusy(null); }
  }

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3">
      <Panel title="Integration surface" accent="#3186FF">
        <p className="text-[11.5px] leading-[1.75] text-muted">
          A water authority does not adopt a dashboard; it adopts something its
          existing SCADA, GIS or alerting stack can call. Every value this
          interface displays comes from these endpoints, so anything you can see
          here you can also pull into another system.
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-6 mt-3">
          <KV k="Base URL" v="/api (proxied to :8813)" />
          <KV k="Auth" v="none in the PoC" color="#F5C451" />
          <KV k="Formats" v="JSON · GeoJSON · PNG · CSV" />
          <KV k="Docs" v="/docs (OpenAPI)" />
        </div>
        <Caveat>
          The PoC API is unauthenticated and read-only apart from asset
          registration. Production deployment requires authentication, rate
          limiting and audit logging before it is exposed outside a trusted
          network.
        </Caveat>
      </Panel>

      <div className="grid xl:grid-cols-[1fr_1fr] gap-3">
        <div className="space-y-3">
          {GROUPS.map((g, gi) => (
            <Panel key={g} title={g} tight delay={gi * 60}>
              <div className="divide-y divide-edge/40">
                {ENDPOINTS.filter((e) => e.group === g).map((ep) => (
                  <div key={ep.method + ep.path} className="px-2.5 py-2.5 row-hover">
                    <div className="flex items-center gap-2">
                      <Chip label={ep.method}
                            color={ep.method === "GET" ? "#3FD1A0" : "#F5C451"} />
                      <span className="hud-value text-[10.5px] text-ink flex-1 truncate">
                        {ep.path}
                      </span>
                      <button onClick={() => {
                                navigator.clipboard?.writeText(
                                  `${location.origin}${ep.path}`);
                                setCopied(ep.path);
                                setTimeout(() => setCopied(null), 1400);
                              }}
                              className="tap text-dim hover:text-beam shrink-0"
                              title="Copy URL">
                        {copied === ep.path ? <Check size={11} className="text-nominal" />
                                            : <Copy size={11} />}
                      </button>
                      <button onClick={() => call(ep)} disabled={busy === ep.path}
                              className="chamfer-sm hud-label px-2 py-1 tap shrink-0
                                         border border-beam/50 text-beam2
                                         hover:bg-beam/10 disabled:opacity-40
                                         flex items-center gap-1">
                        <Play size={9} /> {busy === ep.path ? "…" : "run"}
                      </button>
                    </div>
                    <p className="text-[10px] leading-[1.55] text-dim mt-1.5">{ep.purpose}</p>
                  </div>
                ))}
              </div>
            </Panel>
          ))}
        </div>

        <Panel title="Response" accent={result?.status === 200 ? "#3FD1A0" : "#F5C451"}
               right={result ? (
                 <Chip label={result.status === 200 ? "200 OK"
                              : result.status === 0 ? "LOCAL" : String(result.status)}
                       color={result.status === 200 ? "#3FD1A0" : "#F5C451"} />
               ) : undefined}>
          {!result ? (
            <p className="text-[11px] text-dim leading-relaxed">
              Run any endpoint on the left to see its live response. Nothing is
              mocked: this is the same data the interface renders.
            </p>
          ) : (
            <>
              <div className="hud-value text-[10.5px] text-muted mb-2 break-all">
                {result.path}
              </div>
              <pre className="text-[10px] leading-[1.55] text-muted whitespace-pre-wrap
                              font-mono max-h-[660px] overflow-y-auto
                              bg-void/60 chamfer-sm p-2.5 border border-edge/60">
                {result.body}
              </pre>
            </>
          )}
        </Panel>
      </div>

      <Panel title="Reproducing every number from scratch">
        <pre className="text-[10.5px] leading-[1.8] text-muted font-mono
                        bg-void/60 chamfer-sm p-3 border border-edge/60 overflow-x-auto">
{`# 1. dependencies
pip install -r requirements.txt

# 2. hyperspectral scene (0.9 GB, CC-BY-4.0, no authentication)
python scripts/fetch_tanager.py 20250601_104901_58_4001

# 3. multi-year Sentinel-2 baseline  (~13 min, 1692 reads)
python scripts/build_baseline.py --years 6 --max-cloud 15

# 4. Tanager <-> Sentinel-3 OLCI matchups
python scripts/build_matchup.py

# 5. experiments
python experiments/validate_simulator.py
python experiments/hyperspectral_ablation.py
BLUEBAN_REGIME=hard python experiments/detectability_ablation.py
BLUEBAN_REGIME=easy python experiments/detectability_ablation.py

# 6. the event object and every map layer
python scripts/build_demo_event.py

# 7. serve
uvicorn services.api.main:app --port 8813
cd apps/web && npm run dev`}
        </pre>
      </Panel>
    </div>
  );
}
