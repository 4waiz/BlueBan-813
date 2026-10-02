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
    key: "813", name: "Satellite 813", kind: "Hyperspectral, built for water", range: "400 – 1700 nm", res: "20 m (per spec) · ~205 bands",
    swath_km: null, swath_src: "not published", color: "#FFC23D", sats: ["813"], optical: true, illustrative: true,
    bands: Array.from({ length: 64 }, (_, i) => [400 + i * 20, 6] as [number, number]),
    note: "Every 813 value shown is SIMULATED from real Planet Tanager-1 data. The team has no access to real 813 data (checked while signed in, 30 Sep 2026). Its orbit and spacecraft are not published, so the 3D view shows an illustrative orbit and marker.",
    status: () => "SIMULATED",
  },
  S2: {
    key: "S2", name: "Sentinel-2", kind: "Multispectral camera", range: "443 – 2190 nm, 13 bands", res: "10 / 20 / 60 m · every 2–5 days",
    swath_km: 290, swath_src: "ESA Sentinel-2 User Handbook", color: "#27C3F3", sats: ["S2A", "S2B", "S2C"], optical: true,
    bands: [[443, 21], [492, 66], [560, 36], [665, 31], [704, 15], [740, 15], [783, 20], [833, 106], [865, 21], [945, 20], [1375, 31], [1610, 91], [2190, 175]],
    note: "Main detection satellite, at high resolution. Sun glint is removed, then each pixel is compared with the same season in past years.",
    status: (i) => (hasSource(i, "Sentinel-2") || hasSource(i, "MSI") ? "USED IN THIS INCIDENT" : "ROUTINE MONITORING"),
  },
  S3: {
    key: "S3", name: "Sentinel-3", kind: "Ocean-colour camera", range: "400 – 1020 nm, 21 bands", res: "300 m · daily",
    swath_km: 1270, swath_src: "ESA Sentinel-3 OLCI User Guide", color: "#23D484", sats: ["S3A", "S3B"], optical: true,
    bands: [[400, 15], [412, 10], [443, 10], [490, 10], [510, 10], [560, 10], [620, 10], [665, 10], [674, 7], [681, 7], [709, 10], [754, 7], [761, 3], [764, 3], [768, 2], [779, 15], [865, 20], [885, 10], [900, 10], [940, 20], [1020, 40]],
    note: "Wide-area view and a second-satellite check, never ground truth. Its Planetary Computer archive ends 2026-02-23.",
    status: (i) => (hasAgreement(i, "OLCI", "S3") ? "SECOND-SATELLITE CHECK" : "CONTEXT ONLY"),
  },
  S1: {
    key: "S1", name: "Sentinel-1 radar", kind: "Radar, sees through cloud", range: "5.405 GHz", res: "10 m · every 6–12 days",
    swath_km: 250, swath_src: "ESA Sentinel-1 IW mode", color: "#8B7BFF", sats: ["S1A", "S1C", "S1D"], optical: false, bands: [],
    note: "Optional check for dark slicks. A dark patch can be oil or a look-alike (calm wind, natural film, rain). It never means oil on its own.",
    status: (i) => (hasAgreement(i, "SAR", "S1") ? "USED IN THIS INCIDENT" : "OPTIONAL"),
  },
  LS: {
    key: "LS", name: "Landsat 8/9", kind: "Camera + thermal sensor", range: "443 – 2200 nm + 10.9 µm thermal", res: "30 m / 100 m thermal · 8 days",
    swath_km: 185, swath_src: "USGS Landsat 8/9 Data Users Handbook", color: "#FF8A3D", sats: ["L8", "L9"], optical: true,
    bands: [[443, 16], [482, 60], [561, 57], [655, 37], [865, 28], [1609, 85], [2201, 187]],
    note: "Adds water surface temperature for context. Not used in any reported number unless listed in the incident's sources.",
    status: () => "CONTEXT ONLY",
  },
  PACE: {
    key: "PACE", name: "PACE", kind: "Hyperspectral ocean colour (NASA)", range: "340 – 890 nm (5 nm steps) + 7 infrared bands", res: "1.2 km · every 1–2 days",
    swath_km: 2663, swath_src: "NASA PACE OCI", color: "#FF6FB5", sats: ["PACE"], optical: true,
    bands: Array.from({ length: 56 }, (_, i) => [345 + i * 10, 5] as [number, number]),
    note: "Context only. PACE saw a Gulf of Oman bloom, likely containing Noctiluca, on 17 Mar 2024 (NASA Earth Observatory).",
    status: () => "CONTEXT ONLY",
  },
  TAN: {
    key: "TAN", name: "Planet Tanager-1", kind: "Hyperspectral camera", range: "~380 – 2500 nm, >420 bands", res: "30–35 m · on request",
    swath_km: 18, swath_src: "Planet Tanager documentation", color: "#E0E6F5", sats: ["TAN1"], optical: true,
    bands: Array.from({ length: 70 }, (_, i) => [385 + i * 30, 5] as [number, number]),
    note: "Its real pixels (Gulf of Annaba scene) are the source of the SIMULATED 813 data and the 813 with-vs-without test.",
    status: () => "813 SIMULATION SOURCE",
  },
};

/** Which sensor a TLE key belongs to. */
export const SAT_SENSOR: Record<string, SensorKey> = Object.values(SENSORS)
  .reduce((acc, s) => { s.sats.forEach((k) => { acc[k] = s.key; }); return acc; }, {} as Record<string, SensorKey>);

/** Colour of a band centre on the band-layout strip (visible / NIR / SWIR). */
export const bandColor = (nm: number) => (nm < 700 ? "#27C3F3" : nm < 1000 ? "#4D93FF" : "#8B7BFF");
