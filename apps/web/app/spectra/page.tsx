"use client";
/**
 * SPECTRAL LAB: 2D scientific plot + 3D spectral data cube + "What did 813 add?".
 */
import React, { Suspense, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { Box, LineChart } from "lucide-react";
import { useEngineQuery, useStatic } from "@/lib/engine";
import SpectrumPlot, { DIAGNOSTIC } from "@/components/spectra/SpectrumPlot";
import { Chip, fmt, Panel, SimBadge, WhyButton } from "@/components/ui";

const CubeViewer = dynamic(() => import("@/components/spectra/CubeViewer"), { ssr: false });

type Arm = { f1: number; precision: number; recall: number; roc_auc: number; confusion_matrix: { tp: number; fp: number; fn: number; tn: number }; n_features: number };
type Lift = { results: { spatial_blocked: Record<string, Arm> }; hyperspectral_lift?: Record<string, unknown>; caveats?: string[]; n_samples: number; n_positive: number; n_spatial_blocks: number };
type OlciLift = { targets: Record<string, { n: number; units: string; spatial_blocked: Record<string, { r2: number; rmse: number; r2_ci95: { lo: number; hi: number } }> }>; matchup_dt_hours: { median: number }; n_matchups: number };

function What813Added() {
  const hard = useStatic<Lift>("validation/detectability_lift_hard.json").data;
  const easy = useStatic<Lift>("validation/detectability_lift_easy.json").data;
  const olci = useStatic<OlciLift>("validation/hyperspectral_lift.json").data;
  const arms = (l: Lift | null | undefined) => l?.results?.spatial_blocked || {};
  const h = arms(hard), e = arms(easy);
  const s2 = h["S2_multispectral_11band"], h813 = h["813_hyperspectral_205band"];
  const fpCut = s2 && h813 ? 1 - h813.confusion_matrix.fp / s2.confusion_matrix.fp : null;
  return (
    <Panel title="What did 813 add?" kicker="Measured, not assumed · 813 simulated from real Tanager pixels" right={<SimBadge />} bodyClass="space-y-3 p-3 text-[12px]">
      <div className="grid gap-2 md:grid-cols-3">
        <div className="rounded-md border border-nominal/40 bg-nominal/5 p-3">
          <div className="hud-kicker">Borderline cases</div>
          <div className="hud-value mt-1 text-[22px] font-bold text-nominal">{fpCut != null ? `−${(fpCut * 100).toFixed(0)}%` : "…"}</div>
          <div className="text-muted">false alarms at the same catch rate ({s2?.confusion_matrix.fp} → {h813?.confusion_matrix.fp} of {hard?.n_samples?.toLocaleString()} test pixels). Score (F1) {fmt.num(s2?.f1, 4)} → {fmt.num(h813?.f1, 4)}.</div>
        </div>
        <div className="rounded-md border border-edge bg-deep/60 p-3">
          <div className="hud-kicker">Obvious plumes</div>
          <div className="hud-value mt-1 text-[22px] font-bold text-muted">no gain</div>
          <div className="text-muted">Both are near perfect: F1 {fmt.num(e["S2_multispectral_11band"]?.f1, 4)} vs {fmt.num(e["813_hyperspectral_205band"]?.f1, 4)}. An obvious plume does not need hyperspectral data.</div>
        </div>
        <div className="rounded-md border border-critical/40 bg-critical/5 p-3">
          <div className="hud-kicker">Concentration vs Sentinel-3</div>
          <div className="hud-value mt-1 text-[22px] font-bold text-critical">not shown</div>
          <div className="text-muted">Fit to Sentinel-3 chlorophyll (R²): {fmt.num(olci?.targets?.CHL_NN_log10?.spatial_blocked?.S2_multispectral_11band?.r2, 3)} for S2 vs {fmt.num(olci?.targets?.CHL_NN_log10?.spatial_blocked?.["813_hyperspectral_205band"]?.r2, 3)} for 813. Both near zero. {olci?.n_matchups} matched pairs, {fmt.num(olci?.matchup_dt_hours?.median, 1)} h time offset. A weak test, reported anyway.</div>
        </div>
      </div>
      <p className="text-dim">Every test uses the same real Tanager pixels, so only the bands differ. Answer keys come from an anomaly score and Sentinel-3, not water samples. <WhyButton title="How the 813 test works">
        <div className="space-y-2 text-[12.5px] text-muted">
          <p>All three tests use the same real Tanager pixels over the Gulf of Annaba. Each pixel is resampled to the Sentinel-2 bands and to the published 813 band set, so the band set is the only difference.</p>
          <p>Pixels are tested in {hard?.n_spatial_blocks} separate map blocks (spatially blocked cross-validation). The model is never tested on pixels next to the ones it learned from.</p>
          <p>Borderline cases include pixels close to the decision line. Obvious plumes leave those out.</p>
          <p>For the first two tests, the answer key is a full-spectrum RX anomaly score, not ground truth. The third uses Sentinel-3 chlorophyll (CHL_NN), a second-satellite check, not a lab value.</p>
          <p>Repeating this over the UAE needs the Tarif Tanager scene (download pending approval) and water-sample results (not public).</p>
        </div>
      </WhyButton></p>
    </Panel>
  );
}

function Lab() {
  const router = useRouter();
  const id = useSearchParams().get("id");
  const list = useEngineQuery((e) => e.listIncidents());
  const iid = id || list.data?.[0]?.id || null;
  const q = useEngineQuery((e) => (iid ? e.getIncident(iid) : Promise.resolve(null)), [iid]);
  const inc = q.data;
  const [mode, setMode] = useState<"2d" | "3d">("2d");
  const [showDiff, setShowDiff] = useState(true);
  const [hl, setHl] = useState<number | null>(675);
  const [pick, setPick] = useState<{ wavelengths_nm: number[]; values: (number | null)[]; row: number; col: number } | null>(null);
  const hyper = (inc?.spectral?.wavelengths_nm?.length || 0) > 30;
  const range: [number, number] = hyper ? [400, 900] : [430, 900];
  const pickSpec = useMemo(() => pick ? { wavelengths_nm: pick.wavelengths_nm, event: pick.values, background: pick.values.map(() => null) } : null, [pick]);
  return (
    <div className="grid h-full min-h-0 gap-3 p-3 short:gap-2 short:p-2 grid-rows-[minmax(0,1fr)_auto]">
      <div className="grid min-h-0 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel title="Spectral Lab" kicker={inc ? `${inc.id} · ${inc.spectral?.sensor || "no spectrum"}` : ""} right={
          <div className="flex items-center gap-2">
            <select value={iid || ""} onChange={(e) => router.replace(`/spectra?id=${e.target.value}`)} className="rounded-md border border-line bg-deep px-2 py-1 text-[12px]">{(list.data || []).map((i) => <option key={i.id} value={i.id}>{i.id}</option>)}</select>
            <button onClick={() => setMode("2d")} className={`btn px-2 py-1 text-[11px] ${mode === "2d" ? "border-beam" : ""}`}><LineChart size={13} /> 2D plot</button>
            <button onClick={() => setMode("3d")} className={`btn px-2 py-1 text-[11px] ${mode === "3d" ? "border-beam" : ""}`}><Box size={13} /> 3D cube</button>
          </div>} bodyClass="min-h-0 p-3">
          {mode === "2d" ? (inc?.spectral ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="min-h-0 flex-1"><SpectrumPlot spec={inc.spectral} fill range={range} showDiff={showDiff} highlight={hl} /></div>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-[11.5px]">
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} className="accent-[#FFC23D]" /> Show difference from normal water</label>
                <span className="text-muted">Key wavelengths:</span>
                {DIAGNOSTIC.map(([c, n]) => <button key={c} onClick={() => setHl(c)} className={`rounded px-2 py-0.5 ${hl === c ? "bg-caution/20 text-caution" : "text-muted hover:text-ink"}`}>{c} nm · {n}</button>)}
              </div>
            </div>) : <p className="text-muted">No spectrum for this incident.</p>)
            : inc?.cube ? <div className="grid h-full min-h-0 grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-3">
                <div className="min-h-[300px] overflow-hidden rounded-md border border-edge"><CubeViewer name={inc.cube} height="100%" onSpectrum={setPick} /></div>
                <div className="flex min-h-0 flex-col">{pickSpec ? <><div className="hud-kicker mb-1">Pixel spectrum · row {pick!.row}, col {pick!.col}</div><div className="min-h-0 flex-1"><SpectrumPlot spec={pickSpec} fill range={[400, pick!.wavelengths_nm[pick!.wavelengths_nm.length - 1] > 1000 ? 1700 : 900]} showBands={false} /></div></> : <p className="text-[12px] text-muted">Click the bright slice to see one pixel&apos;s spectrum. Drag the slider or press Scan to move through the bands. Red dashed frames are bands with no valid data. They stay empty, never filled in.</p>}</div>
              </div>
            : <p className="text-muted" title="Cubes are built offline: scripts/build_incidents.py for Sentinel-2. The Tanager / simulated-813 cube needs the Tanager scene.">No 3D cube for this incident.</p>}
        </Panel>
        <Panel title="Reading the spectrum" bodyClass="space-y-2 p-3 text-[12px]">
          {inc && <div className="flex items-center gap-2"><Chip label={inc.status} />{inc.spectral?.simulated ? <SimBadge /> : <Chip label={hyper ? "REAL HYPERSPECTRAL" : "REAL MULTISPECTRAL"} color="#23D484" />}</div>}
          <p className="text-muted" title="Normal water is the median of water pixels outside the event and away from its edge.">Red is the event. Blue is normal water nearby. The shaded band is its usual range (5–95 %). The dashed line shows what the event adds.</p>
          <ul className="list-disc space-y-1 pl-5 text-muted">
            <li><b className="text-ink">675 nm dip + 705 nm peak</b>: chlorophyll. Points to a bloom.</li>
            <li><b className="text-ink">Broad rise 560–665 nm</b>, weak at 443: particles in the water. Points to sediment.</li>
            <li><b className="text-ink">620 nm feature</b>: blue-green algae pigment. Needs narrow bands (Sentinel-2 has none there).</li>
            <li><b className="text-ink">Raised near-infrared</b>: something floating at the surface (floating algae index).</li>
          </ul>
          <p className="text-[11px] text-dim">A spectrum is a clue, not proof. Only a water sample can identify a species or a toxin.</p>
        </Panel>
      </div>
      <What813Added />
    </div>
  );
}

export default function Page() { return <Suspense><Lab /></Suspense>; }
