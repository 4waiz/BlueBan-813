"use client";

/**
 * ASSETS - operator-configured infrastructure and its exposure.
 *
 * BLUEBAN 813 ships no infrastructure database. Intake coordinates for
 * desalination and industrial plants are frequently treated as sensitive, and
 * guessing them from imagery then publishing them would be both unreliable and
 * irresponsible. Everything here was placed by an operator, or is a clearly
 * labelled demonstration fixture.
 */

import React, { useEffect, useState } from "react";
import { MapPin, Plus, Crosshair, Upload } from "lucide-react";

import OceanMap, { RasterKey } from "@/components/OceanMap";
import { MapLegend } from "@/components/MapControls";
import {
  Panel, Loading, ErrorBox, KV, Chip, Caveat, Meter, Readout,
} from "@/components/hud";
import { api, WaterEvent, ExposureRecord, fmt, pct } from "@/lib/api";

export default function Assets() {
  const [event, setEvent] = useState<WaterEvent | null>(null);
  const [bounds, setBounds] = useState<number[] | null>(null);
  const [scales, setScales] = useState<Record<string, any> | null>(null);
  const [types, setTypes] = useState<Record<string, any>>({});
  const [policy, setPolicy] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [focus, setFocus] = useState<[number, number] | null>(null);

  const [pickMode, setPickMode] = useState(false);
  const [draft, setDraft] = useState<{ name: string; type: string; lon: string; lat: string }>(
    { name: "", type: "DESALINATION_INTAKE", lon: "", lat: "" });
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const idx = await api.events();
        const id = idx.events[0].event_id;
        const [e, l, a] = await Promise.all([
          api.event(id), api.layers(), api.assets().catch(() => null),
        ]);
        setEvent(e); setBounds(l.bounds_lonlat); setScales(l.grid?.scales ?? null);
        if (a) { setTypes(a.types ?? {}); setPolicy(a.policy ?? ""); }
        setSel(e.exposure[0]?.asset.id ?? null);
      } catch (e: any) { setErr(e.message ?? String(e)); }
    })();
  }, []);

  async function save() {
    const lon = Number(draft.lon), lat = Number(draft.lat);
    if (!draft.name.trim() || !Number.isFinite(lon) || !Number.isFinite(lat)) {
      setSaveMsg("Name and a valid coordinate are required.");
      return;
    }
    setSaving(true); setSaveMsg(null);
    try {
      await api.addAsset({ name: draft.name.trim(), type: draft.type, lon, lat });
      setSaveMsg("Asset stored. Re-run the pipeline to score its exposure "
                 + "against the current event.");
      setDraft({ name: "", type: draft.type, lon: "", lat: "" });
    } catch (e: any) {
      setSaveMsg(`Could not store the asset: ${e.message ?? e}. `
                 + "The static build has no write endpoint.");
    } finally { setSaving(false); }
  }

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!event || !bounds) return <Loading what="asset register" />;

  const exposures = event.exposure;
  const chosen = exposures.find((e) => e.asset.id === sel) ?? exposures[0];

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px] gap-3 p-3 h-full min-h-0">
      <div className="panel chamfer relative min-h-[340px] overflow-hidden scanlines panel-in">
        <div className="absolute inset-0">
          <OceanMap
            bounds={bounds} raster="rgb" rasterOpacity={0.95}
            showEvents showFlow={false} showParticles={false}
            exposures={exposures} samples={[]}
            glowAt={event.geometry.centroid_lonlat}
            glowRadiusM={event.geometry.equivalent_radius_m}
            focus={focus} focusZoom={13}
            pickMode={pickMode}
            onPickCoord={(lon, lat) => {
              setDraft((d) => ({ ...d, lon: lon.toFixed(6), lat: lat.toFixed(6) }));
              setPickMode(false);
            }}
            className="w-full h-full" />
        </div>
        <div className="absolute top-2.5 left-2.5 z-10">
          <MapLegend raster="rgb" collapsed scale={scales?.rgb} />
        </div>
        {pickMode && (
          <div className="absolute inset-x-0 top-3 flex justify-center z-10 pointer-events-none">
            <div className="chamfer-sm px-3 py-1.5 bg-beam/20 border border-beam
                            hud-label blink-soft" style={{ color: "#F4F6FF" }}>
              click the map to place the asset
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3 min-w-0 overflow-y-auto pr-1">
        <Panel title="Exposure ranking" accent="#FF7A45"
               right={<Chip label={`${exposures.length} ASSETS`} />}>
          <div className="space-y-2">
            {exposures.map((e, i) => {
              const on = e.asset.id === sel;
              const strong = e.exposure_score >= 0.4;
              return (
                <button key={e.asset.id}
                        onClick={() => { setSel(e.asset.id); setFocus([e.asset.lon, e.asset.lat]); }}
                        className={`w-full text-left px-2.5 py-2 chamfer-sm tap panel-in
                                    ${on ? "bg-beam/10" : "row-hover"}`}
                        style={{
                          animationDelay: `${i * 55}ms`,
                          border: `1px solid ${on ? "#3186FF" : "rgba(27,36,68,0.8)"}`,
                        }}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="hud-value text-[11px] text-ink truncate">
                      {e.asset.id} · {e.asset.name}
                    </span>
                    <span className="hud-value text-[13px] shrink-0"
                          style={{ color: strong ? "#FF7A45" : "#8A93B8" }}>
                      {fmt(e.exposure_score, 3)}
                    </span>
                  </div>
                  <div className="hud-label mt-1">{e.asset.type_label}</div>
                  <div className="mt-1.5">
                    <Meter label="" value={e.exposure_score} max={1}
                           display={`${fmt(e.distance_km, 2)} km ${e.direction}`}
                           color={strong ? "#FF7A45" : "#5A6490"} />
                  </div>
                  {e.eta_hours !== null && (
                    <div className="hud-label mt-1" style={{ color: "#FF7A45" }}>
                      drift contact +{e.eta_hours} h
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </Panel>

        {chosen && (
          <Panel title={`${chosen.asset.id} assessment`} accent="#FF7A45"
                 right={
                   <button onClick={() => setFocus([chosen.asset.lon, chosen.asset.lat])}
                           className="hud-label tap flex items-center gap-1 hover:text-beam">
                     <Crosshair size={11} /> centre
                   </button>
                 }>
            <div className="grid grid-cols-2 gap-3">
              <Readout label="Exposure" animate={chosen.exposure_score} digits={3}
                       value={fmt(chosen.exposure_score, 3)} size="lg"
                       color={chosen.exposure_score >= 0.4 ? "#FF7A45" : "#8A93B8"} />
              <Readout label="Separation" animate={chosen.distance_km} digits={2}
                       value={fmt(chosen.distance_km, 2)} unit="km" size="lg" />
            </div>
            <div className="mt-3">
              <KV k="Type" v={chosen.asset.type_label} />
              <KV k="Sensitivity" v={fmt(chosen.asset.sensitivity, 2)} />
              <KV k="Bearing from event"
                  v={`${fmt(chosen.bearing_from_event_deg, 0)}° ${chosen.direction}`} />
              <KV k="Closest approach"
                  v={`${fmt(chosen.closest_approach_m / 1000, 2)} km at +${fmt(chosen.closest_approach_hours, 0)} h`} />
              <KV k="Drift intersects" v={chosen.intersects_forecast ? "yes" : "no"}
                  color={chosen.intersects_forecast ? "#FF7A45" : "#8A93B8"} />
              <KV k="ETA" v={chosen.eta_hours !== null ? `+${fmt(chosen.eta_hours, 0)} h` : "none"}
                  color={chosen.eta_hours !== null ? "#FF7A45" : undefined} />
              <KV k="Source" v={chosen.asset.source} />
            </div>

            <div className="mt-3">
              <div className="hud-label mb-2">why this asset matters</div>
              <p className="text-[10.5px] leading-[1.65] text-muted">
                {chosen.asset.why_it_matters}
              </p>
              {chosen.asset.primary_concerns.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {chosen.asset.primary_concerns.map((c) => (
                    <Chip key={c} label={c} color="#8A93B8" />
                  ))}
                </div>
              )}
            </div>

            <div className="mt-3">
              <div className="hud-label mb-2">basis for this score</div>
              <ul className="space-y-1.5">
                {chosen.basis.map((b, i) => (
                  <li key={i} className="flex gap-2 text-[10.5px] leading-[1.55] text-muted">
                    <span className="text-dim shrink-0">{i + 1}.</span><span>{b}</span>
                  </li>
                ))}
              </ul>
            </div>
            {chosen.asset.notes && <Caveat>{chosen.asset.notes}</Caveat>}
          </Panel>
        )}

        <Panel title="Add an asset" accent="#3186FF">
          <div className="space-y-2.5">
            <Field label="Name">
              <input value={draft.name}
                     onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                     placeholder="asset name"
                     className="w-full bg-void/70 border border-edge chamfer-sm px-2 py-1.5
                                hud-value text-[11px] text-ink outline-none
                                focus:border-beam transition-colors" />
            </Field>
            <Field label="Type">
              <select value={draft.type}
                      onChange={(e) => setDraft({ ...draft, type: e.target.value })}
                      className="w-full bg-void/70 border border-edge chamfer-sm px-2 py-1.5
                                 hud-value text-[11px] text-ink outline-none
                                 focus:border-beam transition-colors">
                {Object.entries(types).length === 0
                  ? <option value="DESALINATION_INTAKE">DESALINATION INTAKE</option>
                  : Object.entries(types).map(([k, v]: any) => (
                      <option key={k} value={k}>{v.label}</option>))}
              </select>
            </Field>
            <p className="hud-label normal-case" style={{ letterSpacing: "0.05em" }}>
              hints show the AOI centre; pick on the map for an exact position
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Latitude">
                <input value={draft.lat}
                       onChange={(e) => setDraft({ ...draft, lat: e.target.value })}
                       placeholder="36.9670"
                       className="w-full bg-void/70 border border-edge chamfer-sm px-2 py-1.5
                                  hud-value text-[11px] text-ink outline-none
                                  focus:border-beam transition-colors" />
              </Field>
              <Field label="Longitude">
                <input value={draft.lon}
                       onChange={(e) => setDraft({ ...draft, lon: e.target.value })}
                       placeholder="7.6633"
                       className="w-full bg-void/70 border border-edge chamfer-sm px-2 py-1.5
                                  hud-value text-[11px] text-ink outline-none
                                  focus:border-beam transition-colors" />
              </Field>
            </div>
            <div className="flex gap-2 pt-1">
              <button onClick={() => setPickMode(!pickMode)}
                      className="chamfer-sm hud-label px-2.5 py-1.5 tap flex items-center gap-1.5
                                 border"
                      style={{ borderColor: pickMode ? "#3186FF" : "#1B2444",
                               color: pickMode ? "#4A93FF" : "#5A6490",
                               background: pickMode ? "rgba(49,134,255,0.14)" : "transparent" }}>
                <MapPin size={11} /> {pickMode ? "click map…" : "pick on map"}
              </button>
              <button onClick={save} disabled={saving}
                      className="chamfer-sm hud-label px-2.5 py-1.5 tap flex items-center gap-1.5
                                 border border-nominal/50 text-nominal
                                 hover:bg-nominal/10 disabled:opacity-40">
                <Plus size={11} /> {saving ? "storing…" : "add asset"}
              </button>
            </div>
            {saveMsg && (
              <p className="text-[10.5px] leading-[1.6] text-caution mt-1">{saveMsg}</p>
            )}
          </div>

          <div className="mt-3 pt-3 border-t border-edge/50">
            <div className="hud-label mb-2 flex items-center gap-1.5">
              <Upload size={11} /> bulk import
            </div>
            <p className="text-[10.5px] leading-[1.6] text-dim">
              GeoJSON point features and CSV with <span className="hud-value">lon</span>/
              <span className="hud-value">lat</span> (or{" "}
              <span className="hud-value">longitude</span>/
              <span className="hud-value">latitude</span>) columns are supported by{" "}
              <span className="hud-value text-muted">pipeline/exposure.py</span>. Optional
              columns: <span className="hud-value">id, name, type, sensitivity, notes</span>.
            </p>
          </div>

          {policy && <Caveat>{policy}</Caveat>}
        </Panel>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="hud-label block mb-1">{label}</span>
      {children}
    </label>
  );
}
