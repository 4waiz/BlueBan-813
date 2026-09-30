/**
 * One registry of the sensors BLUEBAN 813 talks about: the Satellite View card
 * and the full-screen orbit viewer both read it.
 *
 * Swath widths are the published instrument values (sources in `swath_src`).
 * Satellite 813 has no published orbit, altitude or swath, so the viewer draws
 * it on an explicitly ILLUSTRATIVE orbit with an abstract marker.
 */
import type { Incident } from "./engine/types";

export type SensorKey = "813" | "S2" | "S3" | "S1" | "LS" | "PACE" | "TAN";

export interface SensorSpec {
  key: SensorKey;
  name: string;
  kind: string;
  range: string;
  res: string;
  /** Full swath width in km; null when not published. */
  swath_km: number | null;
  swath_src: string;
  /** Band centres and widths in nm, for the band-layout strip. */
  bands: [number, number][];
  note: string;
  color: string;
  /** TLE keys (config/tle_eo.json) of the spacecraft carrying the sensor. */
  sats: string[];
  optical: boolean;
  illustrative?: boolean;
  status: (i: Incident | null) => string;
}

const hasSource = (i: Incident | null, s: string) =>
  (i?.provenance?.sources || []).some((x) => `${x.sensor || ""} ${x.satellite || ""}`.includes(s));
const hasAgreement = (i: Incident | null, ...keys: string[]) =>
  Object.keys(i?.sensor_agreement || {}).some((k) => keys.some((q) => k.includes(q)));

export const SENSORS: Record<SensorKey, SensorSpec> = {
  "813": {
    key: "813", name: "Satellite 813", kind: "Aquatic hyperspectral", range: "400 – 1700 nm", res: "20 m (spec) · ~205 bands",
    swath_km: null, swath_src: "not published", color: "#FFC23D", sats: ["813"], optical: true, illustrative: true,
    bands: Array.from({ length: 64 }, (_, i) => [400 + i * 20, 6] as [number, number]),
    note: "No 813 product is accessible to the team (authenticated audit, 30 Sep 2026). Every 813 value shown is SIMULATED from real Planet Tanager-1 data. Orbit and spacecraft are not published: the viewer shows an illustrative orbit and an abstract marker.",
    status: () => "SIMULATED",
  },
  S2: {
    key: "S2", name: "Sentinel-2 MSI", kind: "Multispectral, L2A BOA reflectance", range: "443 – 2190 nm, 13 bands", res: "10 / 20 / 60 m · 2–5 day revisit",
    swath_km: 290, swath_src: "ESA Sentinel-2 User Handbook", color: "#27C3F3", sats: ["S2A", "S2B", "S2C"], optical: true,
    bands: [[443, 21], [492, 66], [560, 36], [665, 31], [704, 15], [740, 15], [783, 20], [833, 106], [865, 21], [945, 20], [1375, 31], [1610, 91], [2190, 175]],
    note: "Primary high-resolution detection sensor. Sen2Cor L2A, glint-corrected by SWIR offset; per-pixel seasonal anomaly detection.",
    status: (i) => (hasSource(i, "Sentinel-2") || hasSource(i, "MSI") ? "IN EVIDENCE" : "BASELINE"),
  },
  S3: {
    key: "S3", name: "Sentinel-3 OLCI", kind: "Ocean colour, WFR L2", range: "400 – 1020 nm, 21 bands", res: "300 m · daily",
    swath_km: 1270, swath_src: "ESA Sentinel-3 OLCI User Guide", color: "#23D484", sats: ["S3A", "S3B"], optical: true,
    bands: [[400, 15], [412, 10], [443, 10], [490, 10], [510, 10], [560, 10], [620, 10], [665, 10], [674, 7], [681, 7], [709, 10], [754, 7], [761, 3], [764, 3], [768, 2], [779, 15], [865, 20], [885, 10], [900, 10], [940, 20], [1020, 40]],
    note: "Wide-area context and cross-sensor reference (CHL_NN, TSM_NN), never ground truth. Planetary Computer archive ends 2026-02-23.",
    status: (i) => (hasAgreement(i, "OLCI", "S3") ? "CROSS-CHECK" : "CONTEXT"),
  },
  S1: {
    key: "S1", name: "Sentinel-1 SAR", kind: "C-band SAR, VV/VH", range: "5.405 GHz", res: "10 m GRD · 6–12 day",
    swath_km: 250, swath_src: "ESA Sentinel-1 IW mode", color: "#8B7BFF", sats: ["S1A", "S1C", "S1D"], optical: false, bands: [],
    note: "Optional surface-dark-anomaly mode. A dark patch is an oil-spill LOOKALIKE set (low wind, biogenic film, rain cell), never 'oil' on its own.",
    status: (i) => (hasAgreement(i, "SAR", "S1") ? "IN EVIDENCE" : "OPTIONAL"),
  },
  LS: {
    key: "LS", name: "Landsat 8/9", kind: "OLI + TIRS", range: "443 – 2200 nm + 10.9 µm thermal", res: "30 m / 100 m thermal · 8 day",
    swath_km: 185, swath_src: "USGS Landsat 8/9 Data Users Handbook", color: "#FF8A3D", sats: ["L8", "L9"], optical: true,
    bands: [[443, 16], [482, 60], [561, 57], [655, 37], [865, 28], [1609, 85], [2201, 187]],
    note: "Thermal context (surface temperature). Not used in any reported number unless listed in the incident's provenance.",
    status: () => "CONTEXT",
  },
  PACE: {
    key: "PACE", name: "PACE OCI", kind: "Hyperspectral ocean colour (NASA)", range: "340 – 890 nm (5 nm) + 7 SWIR bands", res: "1.2 km · 1–2 day",
    swath_km: 2663, swath_src: "NASA PACE OCI", color: "#FF6FB5", sats: ["PACE"], optical: true,
    bands: Array.from({ length: 56 }, (_, i) => [345 + i * 10, 5] as [number, number]),
    note: "Context only. PACE OCI imaged a Gulf of Oman bloom likely containing Noctiluca on 17 Mar 2024 (NASA Earth Observatory).",
    status: () => "CONTEXT",
  },
  TAN: {
    key: "TAN", name: "Planet Tanager-1", kind: "Imaging spectrometer (VSWIR)", range: "~380 – 2500 nm, >420 channels", res: "30–35 m · tasked",
    swath_km: 18, swath_src: "Planet Tanager documentation", color: "#E0E6F5", sats: ["TAN1"], optical: true,
    bands: Array.from({ length: 70 }, (_, i) => [385 + i * 30, 5] as [number, number]),
    note: "Source of the real hyperspectral pixels behind the SIMULATED 813 product and the 813 ablation (Gulf of Annaba scene).",
    status: () => "SIMULATION SOURCE",
  },
};

/** Which sensor a TLE key belongs to. */
export const SAT_SENSOR: Record<string, SensorKey> = Object.values(SENSORS)
  .reduce((acc, s) => { s.sats.forEach((k) => { acc[k] = s.key; }); return acc; }, {} as Record<string, SensorKey>);

/** Colour of a band centre on the band-layout strip (visible / NIR / SWIR). */
export const bandColor = (nm: number) => (nm < 700 ? "#27C3F3" : nm < 1000 ? "#4D93FF" : "#8B7BFF");
