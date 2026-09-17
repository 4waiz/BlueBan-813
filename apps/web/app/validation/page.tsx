"use client";

/**
 * VALIDATION - every experiment we ran, including the ones that found nothing.
 *
 * The section ordering is deliberate. The negative results come BEFORE the
 * headline, because a reviewer should see that we looked for the hyperspectral
 * advantage in several places and only found it in one.
 */

import React, { useEffect, useState } from "react";
import { Panel, Loading, ErrorBox, KV, Chip, Caveat, Readout } from "@/components/hud";
import { fmt, pct, api } from "@/lib/api";

export default function Validation() {
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.validation().then(setV).catch((e) => setErr(e.message ?? String(e)));
  }, []);

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!v) return <Loading what="validation artefacts" />;

  const head = v.summary?.headline?.[0];
  const op = head?.operational_reading;
  const sim = v.simulator_validation;
  const det = v.detectability_hard;
  const easy = v.detectability_easy;
  const olci = v.olci_retrieval_ablation;

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3">
      {/* ------------------------------------------------ the headline claim */}
      <Panel title="Why 813? - the measured answer" accent="#3186FF">
        <div className="grid lg:grid-cols-[1fr_1fr_1.2fr] gap-5 items-center">
          <div className="text-center panel-quiet chamfer p-4">
            <div className="hud-label mb-2">Multispectral baseline</div>
            <div className="hud-value text-[40px] leading-none text-muted">
              {fmt(head?.multispectral, 4)}
            </div>
            <div className="hud-label mt-2">F1 · Sentinel-2, 11 bands</div>
            <div className="hud-value text-[11px] text-dim mt-3">
              {op?.false_positives_multispectral} false alarms
            </div>
          </div>

          <div className="text-center panel-quiet chamfer p-4"
               style={{ borderColor: "rgba(49,134,255,0.45)" }}>
            <div className="hud-label mb-2" style={{ color: "#4A93FF" }}>
              + 813 hyperspectral
            </div>
            <div className="hud-value text-[40px] leading-none text-beam2">
              {fmt(head?.hyperspectral_813, 4)}
            </div>
            <div className="hud-label mt-2">F1 · 813 simulated, 205 bands</div>
            <div className="hud-value text-[11px] text-dim mt-3">
              {op?.false_positives_hyperspectral} false alarms
            </div>
          </div>

          <div className="panel-quiet chamfer p-4"
               style={{ borderColor: "rgba(63,209,160,0.45)" }}>
            <div className="hud-label mb-2" style={{ color: "#3FD1A0" }}>
              Hyperspectral lift
            </div>
            <div className="hud-value text-[40px] leading-none text-nominal">
              -{fmt(op?.relative_reduction_pct, 1)}%
            </div>
            <div className="text-[11px] leading-[1.6] text-muted mt-2">
              fewer false alarms at matched recall
            </div>
            <div className="mt-3 space-y-1">
              <KV k="ΔF1" v={`+${fmt(head?.absolute_gain, 4)}`} color="#3FD1A0" />
              <KV k="95% CI" v={`[${fmt(head?.ci95?.lo, 4)}, ${fmt(head?.ci95?.hi, 4)}]`} />
              <KV k="Significant" v={head?.significant ? "YES - CI excludes zero" : "no"}
                  color={head?.significant ? "#3FD1A0" : "#F5C451"} />
            </div>
          </div>
        </div>

        <p className="text-[11.5px] leading-[1.75] text-muted mt-4">
          Both arms are convolved from the <strong className="text-ink">same Tanager pixels</strong>,
          so acquisition time, atmosphere, illumination, geolocation and water
          state are identical between them. The only variable is spectral
          configuration. Splits are spatial blocks, never random.
        </p>
        <Caveat>
          Reference labels come from the full-spectrum (368-band) RX detector,
          not from in-situ measurement. This quantifies information loss at
          reduced spectral resolution; it does not establish that the detected
          anomaly is any particular substance.
        </Caveat>
      </Panel>

      {/* -------------------------------------------- the honest negatives */}
      <Panel title="Experiments that found no advantage" accent="#F5C451">
        <p className="text-[11.5px] leading-[1.7] text-muted mb-3">
          We looked for the hyperspectral advantage in three places and found it
          in one. These are the other two, reported because they were measured.
        </p>
        <div className="grid md:grid-cols-3 gap-3">
          {(v.summary?.honest_negatives ?? []).map((n: any, i: number) => (
            <div key={i} className="panel-quiet chamfer p-3">
              <div className="hud-label mb-2" style={{ color: "#F5C451" }}>
                {n.experiment}
              </div>
              {n.multispectral_r2 !== undefined && (
                <div className="flex items-baseline gap-3 mb-2">
                  <span className="hud-value text-[17px] text-muted">
                    {fmt(n.multispectral_r2, 3)}
                  </span>
                  <span className="text-dim text-[11px]">→</span>
                  <span className="hud-value text-[17px] text-beam2">
                    {fmt(n.hyperspectral_r2, 3)}
                  </span>
                  <span className="hud-label">R²</span>
                </div>
              )}
              {n.f1_gain !== undefined && (
                <div className="hud-value text-[17px] text-muted mb-2">
                  ΔF1 {fmt(n.f1_gain, 5)}
                </div>
              )}
              <p className="text-[10.5px] leading-[1.6] text-dim">{n.reading}</p>
            </div>
          ))}
        </div>
      </Panel>

      {/* ------------------------------------- the spatial-leakage finding */}
      {det && (
        <Panel title="Methodological finding: random splits inflate hyperspectral scores"
               accent="#FF7A45">
          <p className="text-[11.5px] leading-[1.7] text-muted mb-3">
            Neighbouring water pixels are near-duplicates. With a random
            train/test split they land on both sides and every score rises -
            far more for the high-dimensional arm, which has more capacity to
            memorise. This is the single easiest way to accidentally claim a
            hyperspectral advantage that does not exist.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="hud-label border-b border-edge">
                  <th className="text-left py-2 font-normal">Sensor arm</th>
                  <th className="text-right py-2 font-normal">R² random split</th>
                  <th className="text-right py-2 font-normal">R² spatially blocked</th>
                  <th className="text-right py-2 font-normal">Inflation</th>
                </tr>
              </thead>
              <tbody className="hud-value">
                {olci && Object.entries(olci.targets ?? {}).map(([tn, t]: any) =>
                  Object.keys(t.spatial_blocked ?? {}).map((arm) => {
                    const r = t.random_split[arm]?.r2;
                    const b = t.spatial_blocked[arm]?.r2;
                    return (
                      <tr key={tn + arm} className="border-b border-edge/35">
                        <td className="py-2 text-muted">
                          {tn.replace("_log10", "")} · {arm.replace(/_/g, " ")}
                        </td>
                        <td className="text-right text-caution">{fmt(r, 4)}</td>
                        <td className="text-right text-ink">{fmt(b, 4)}</td>
                        <td className="text-right text-alert">
                          {r !== undefined && b !== undefined ? `${fmt(r - b, 4)}` : "-"}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <Caveat>
            An earlier run of this experiment used a random split for the INNER
            component-selection loop too. It drove PLSR to the 20-component cap
            and produced an outer R² of -15.7. That was a flaw in our protocol,
            not a property of the data, and it is documented in the code.
          </Caveat>
        </Panel>
      )}

      {/* --------------------------------------------- simulator validation */}
      {sim && (
        <Panel title="Is the 813 simulator trustworthy?" accent="#4A93FF">
          <p className="text-[11.5px] leading-[1.7] text-muted mb-3">
            The Gulf of Annaba has a <strong className="text-ink">38-minute</strong> coincidence
            between Tanager-1 and Sentinel-2C, both effectively cloud-free. We ran
            the exact convolution used to build the 813 product, but targeting
            Sentinel-2&apos;s band set, and compared against what Sentinel-2 actually
            measured.
          </p>
          <div className="grid lg:grid-cols-2 gap-4">
            {(["land", "water"] as const).map((surf) => (
              <div key={surf}>
                <div className="hud-label mb-2"
                     style={{ color: surf === "land" ? "#3FD1A0" : "#F5C451" }}>
                  over {surf}
                  {surf === "land" ? " - both corrections in domain" : " - Sen2Cor out of domain"}
                </div>
                <table className="w-full text-[10.5px]">
                  <thead>
                    <tr className="hud-label border-b border-edge">
                      <th className="text-left py-1.5 font-normal">Band</th>
                      <th className="text-right py-1.5 font-normal">r</th>
                      <th className="text-right py-1.5 font-normal">slope</th>
                      <th className="text-right py-1.5 font-normal">RMSE</th>
                    </tr>
                  </thead>
                  <tbody className="hud-value">
                    {Object.entries(sim.per_band?.[surf] ?? {}).map(([b, m]: any) => (
                      <tr key={b} className="border-b border-edge/30">
                        <td className="py-1.5 text-muted">{b} · {m.wavelength_nm} nm</td>
                        <td className="text-right"
                            style={{ color: m.pearson_r > 0.9 ? "#3FD1A0"
                                            : m.pearson_r > 0.7 ? "#F5C451" : "#FF7A45" }}>
                          {fmt(m.pearson_r, 3)}
                        </td>
                        <td className="text-right text-muted">{fmt(m.regression_slope, 3)}</td>
                        <td className="text-right text-dim">{fmt(m.rmse, 4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <div className="mt-4 panel-quiet chamfer p-3">
            <div className="hud-label mb-2" style={{ color: "#4A93FF" }}>reading the result</div>
            <p className="text-[11px] leading-[1.7] text-muted">{sim.interpretation?.land_reads_as}</p>
            <p className="text-[11px] leading-[1.7] text-muted mt-2">{sim.interpretation?.water_reads_as}</p>
          </div>
        </Panel>
      )}

      {/* ---------------------------------------------- temporal baseline */}
      {v.temporal_baseline && (
        <Panel title="Temporal baseline - the test that changed the verdict" accent="#3FD1A0">
          <div className="grid lg:grid-cols-[320px_1fr] gap-5">
            <div>
              <Readout label="Observations in the record"
                       value={v.temporal_baseline.zones?.hotspot_inner_gulf?.n_observations ?? "-"}
                       size="lg" color="#3FD1A0"
                       sub="Sentinel-2, hotspot zone, 2020-2025" />
              <div className="mt-3">
                <KV k="Reference zone obs"
                    v={v.temporal_baseline.zones?.reference_offshore?.n_observations ?? "-"} />
                <KV k="Span" v="5.4 years" />
                <KV k="Cloud filter" v="≤ 15%" />
              </div>
              <Caveat>
                Without this record, a spatial anomaly detector cannot tell a
                pollution event from a permanently turbid harbour. Both look
                identical in one image.
              </Caveat>
            </div>
            <div>
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="hud-label border-b border-edge">
                    <th className="text-left py-2 font-normal">Variable</th>
                    <th className="text-right py-2 font-normal">Baseline median</th>
                    <th className="text-right py-2 font-normal">2025-06-01</th>
                    <th className="text-right py-2 font-normal">Seasonal pctile</th>
                    <th className="text-right py-2 font-normal">State</th>
                  </tr>
                </thead>
                <tbody className="hud-value">
                  {Object.entries(
                    v.temporal_baseline.zones?.hotspot_inner_gulf?.baselines ?? {}
                  ).map(([name, b]: any) => {
                    const ta = b.target_assessment;
                    if (!ta) return null;
                    const p = ta.seasonal_percentile;
                    return (
                      <tr key={name} className="border-b border-edge/35">
                        <td className="py-2 text-muted">{name}</td>
                        <td className="text-right text-dim">{fmt(b.median, 4)}</td>
                        <td className="text-right text-ink">{fmt(ta.value, 4)}</td>
                        <td className="text-right"
                            style={{ color: p >= 90 ? "#FF7A45" : p <= 25 ? "#3FD1A0" : "#8A93B8" }}>
                          {fmt(p, 1)}
                        </td>
                        <td className="text-right text-nominal">{ta.state}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="text-[11.5px] leading-[1.7] text-muted mt-3">
                On the observation date the Gulf of Annaba nearshore was
                <strong className="text-nominal"> cleaner than usual</strong>, not
                dirtier. The strong spatial contrast the detector found is a
                persistent feature of this coastline, so the system applied a
                temporal veto and reduced the event from HIGH PRIORITY to NORMAL.
              </p>
            </div>
          </div>
        </Panel>
      )}

      {/* ---------------------------------------------- what we cannot claim */}
      <Panel title="What this system has NOT validated" accent="#FF4D4D">
        <ul className="space-y-2 text-[11.5px] leading-[1.7] text-muted">
          {[
            "No in-situ or laboratory measurement was available for this AOI. No chlorophyll-a concentration in mg/m³ and no turbidity in NTU is reported anywhere in this product.",
            "The optical classification is a weighted hypothesis, not a chemical, biological or toxicological identification.",
            "The drift forecast is wind-driven advection, not a hydrodynamic model. It has not been validated against observed plume motion.",
            "The OLCI matchups carry a median -25.5 h offset; coastal water changes materially in a day.",
            "Bottom reflectance cannot be excluded as a contributor to the nearshore signal from a single scene.",
            "No real Satellite 813 data exists in this system. Every 813 product shown is simulated from Planet Tanager-1.",
          ].map((t, i) => (
            <li key={i} className="flex gap-2.5">
              <span className="text-critical shrink-0">-</span>
              <span>{t}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
