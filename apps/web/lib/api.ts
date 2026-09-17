/**
 * Typed client for the BLUEBAN 813 API.
 *
 * Every value rendered in the interface comes through here. There are no
 * fallback constants and no placeholder numbers: if the pipeline has not
 * produced an artefact, the UI shows that it is missing rather than inventing
 * a plausible-looking value.
 */

export type Priority = "NORMAL" | "WATCH" | "INVESTIGATE" | "HIGH_PRIORITY" | "UNKNOWN";

export interface EventSummary {
  event_id: string;
  aoi: string;
  country: string;
  acquisition_utc: string;
  state: Priority;
  severity: number;
  confidence: number;
  class: string;
  class_label: string;
  area_km2: number;
}

export interface RiskComponent {
  name: string;
  value: number | null;
  weight: number;
  description: string;
}

export interface FiredRule {
  rule: string;
  level: string;
  veto?: boolean;
}

export interface EvidenceItem {
  name: string;
  value: number | null;
  supports: string;
  weight: number;
  description: string;
}

export interface Classification {
  top_class: string;
  label: string;
  scores: Record<string, number>;
  confidence: number;
  evidence: EvidenceItem[];
  caveats: string[];
  disclaimer: string;
}

export interface ForecastStep {
  hours: number;
  timestamp: string;
  centroid: [number, number];
  displacement_m: number;
  bearing_deg: number;
  spread_radius_m: number;
  beached_fraction: number;
  particles?: [number, number][];
}

export interface AssetRecord {
  id: string;
  name: string;
  type: string;
  type_label: string;
  lon: number;
  lat: number;
  sensitivity: number;
  notes: string;
  source: string;
  why_it_matters: string;
  primary_concerns: string[];
}

export interface ExposureRecord {
  asset: AssetRecord;
  distance_m: number;
  distance_km: number;
  bearing_from_event_deg: number;
  direction: string;
  closest_approach_m: number;
  closest_approach_hours: number | null;
  intersects_forecast: boolean;
  eta_hours: number | null;
  exposure_score: number;
  basis: string[];
}

export interface SamplePoint {
  id: string;
  role: string;
  role_question: string;
  lon: number;
  lat: number;
  priority: number;
  rationale: string;
  expected_variables: string[];
  anomaly_score: number | null;
  distance_from_shore_m: number | null;
  distance_to_asset_m: number | null;
}

export interface WaterEvent {
  event_id: string;
  generated_utc: string;
  aoi: { id: string; name: string; country: string; bounds_lonlat: number[] };
  observation: {
    primary_sensor: string;
    scene_id: string;
    acquisition_utc: string;
    pixel_size_m: number;
    epsg_native: number;
    sun_elevation_deg: number;
    view_off_nadir_deg: number;
  };
  state: Priority;
  severity: number;
  confidence: number;
  assessment: {
    severity: number;
    confidence: number;
    priority: Priority;
    priority_reason: string;
    severity_components: RiskComponent[];
    confidence_components: RiskComponent[];
    rules_fired: FiredRule[];
    note: string;
  };
  geometry: {
    centroid_lonlat: [number, number];
    area_km2: number;
    pixel_count: number;
    equivalent_radius_m: number;
    median_distance_from_shore_m: number;
    region_label: string;
  };
  classification: Classification;
  anomaly: Record<string, any>;
  indices: Record<string, any>;
  quality: Record<string, any>;
  temporal: { baseline_available: boolean; assessment: any };
  forecast: { metadata: any; steps: ForecastStep[] };
  exposure: ExposureRecord[];
  samples: SamplePoint[];
  all_regions: any[];
  provenance_summary: {
    completeness: number;
    missing_fields: string[];
    n_sources: number;
    code_version: string;
  };
  satellite_813: Record<string, any>;
}

export interface SpectraPayload {
  event_id: string;
  wavelengths_nm: number[];
  background: SpectrumStats;
  event: SpectrumStats;
  difference: (number | null)[];
  z_score: (number | null)[];
  snr: (number | null)[];
  bad_band_ranges_nm: number[][];
  diagnostic_features: Record<string, { centre_nm: number; meaning: string; reference: string }>;
  band_depth_windows: Record<string, { left: number; centre: number; right: number; meaning: string }>;
  sensor_bands: { sentinel2: Record<string, number>; n_813_bands_in_range: number };
  regions: Record<string, { mean: (number | null)[]; n_pixels: number; class: string }>;
}

export interface SpectrumStats {
  wavelengths_nm: number[];
  mean: (number | null)[];
  median: (number | null)[];
  std: (number | null)[];
  p05: (number | null)[];
  p95: (number | null)[];
  n_pixels: number;
}

/* --------------------------------------------------------------- transport */

/**
 * Two deployment modes share one client.
 *
 * "live"   - the FastAPI service is reachable at /api (Next.js proxies it).
 * "static" - the site is a static export (Cloudflare Pages), and the pipeline
 *            artefacts were baked into /data at build time. There is no server,
 *            so every read maps onto a file and writes are unavailable.
 *
 * Keeping the mapping in one place means no page or component needs to know
 * which mode it is running in.
 */
export const DATA_MODE: "live" | "static" =
  (process.env.NEXT_PUBLIC_DATA_MODE as "live" | "static") ?? "live";

export const IS_STATIC = DATA_MODE === "static";

// Deliberately not "/data": that is also an app route, and sharing the
// prefix invites a future filename collision with the page itself.
const STATIC_ROOT = "/pipeline";

const LAYER_FILES: Record<string, string> = {
  rgb: "rgb_water.png",
  anomaly: "anomaly.png",
  ndci: "ndci.png",
  turbidity: "turbidity.png",
  events: "event_polygons.geojson",
  water: "water_mask.geojson",
  sensor_spec_813: "sensor_spec_813.json",
};

/** Absolute URL for a map layer, correct in both modes. */
export function layerUrl(name: string): string {
  if (!IS_STATIC) return `/api/layers/${name}`;
  return `${STATIC_ROOT}/layers/${LAYER_FILES[name] ?? `${name}.json`}`;
}

/** Map an API path onto a static artefact path. */
function staticPath(apiPath: string): string {
  const [bare, query] = apiPath.split("?");
  const p = bare.replace(/^\/api\//, "");

  if (p === "health") return `${STATIC_ROOT}/health.json`;
  if (p === "status") return `${STATIC_ROOT}/status.json`;
  if (p === "config") return `${STATIC_ROOT}/config.json`;
  if (p === "events") return `${STATIC_ROOT}/events/index.json`;
  if (p === "layers") return `${STATIC_ROOT}/layers/index.json`;
  if (p === "validation") return `${STATIC_ROOT}/validation/index.json`;
  if (p === "hyperspectral-lift") return `${STATIC_ROOT}/validation/lift.json`;
  if (p === "timeseries") return `${STATIC_ROOT}/validation/s2_timeseries.json`;
  if (p === "assets") return `${STATIC_ROOT}/assets.json`;
  if (p === "docs-list") return `${STATIC_ROOT}/docs/index.json`;

  const doc = p.match(/^docs\/(.+)$/);
  if (doc) return `${STATIC_ROOT}/docs/${doc[1]}.md`;

  const layer = p.match(/^layers\/(.+)$/);
  if (layer) return layerUrl(layer[1]);

  const ev = p.match(/^events\/([^/]+)$/);
  if (ev) return `${STATIC_ROOT}/events/${ev[1]}.json`;

  const sub = p.match(/^events\/([^/]+)\/(.+)$/);
  if (sub) {
    const [, id, what] = sub;
    if (what === "spectrum") return `${STATIC_ROOT}/events/${id}_spectra.json`;
    if (what === "forecast") return `${STATIC_ROOT}/events/${id}_forecast.json`;
    if (what === "provenance") return `${STATIC_ROOT}/events/${id}_provenance.json`;
    if (what === "samples") {
      return query?.includes("fmt=csv")
        ? `${STATIC_ROOT}/events/${id}_samples.csv`
        : `${STATIC_ROOT}/events/${id}_samples.geojson`;
    }
  }
  return `${STATIC_ROOT}/${p}.json`;
}

/** The URL a browser should actually fetch for a logical API path. */
export function resolve(apiPath: string): string {
  return IS_STATIC ? staticPath(apiPath) : apiPath;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(resolve(path), { cache: "no-store" });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {
      /* body was not JSON */
    }
    throw new Error(`${r.status} ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => get<{ status: string; version: string }>("/api/health"),
  status: () => get<any>("/api/status"),
  config: () => get<any>("/api/config"),
  events: () => get<{ events: EventSummary[]; generated_utc: string }>("/api/events"),
  event: (id: string) => get<WaterEvent>(`/api/events/${id}`),
  spectrum: (id: string) => get<SpectraPayload>(`/api/events/${id}/spectrum`),
  forecast: (id: string) => get<any>(`/api/events/${id}/forecast`),
  samples: (id: string) => get<any>(`/api/events/${id}/samples`),
  provenance: (id: string) => get<any>(`/api/events/${id}/provenance`),
  layers: () => get<any>("/api/layers"),
  validation: () => get<any>("/api/validation"),
  lift: () => get<any>("/api/hyperspectral-lift"),
  timeseries: (zone?: string) =>
    get<any>(`/api/timeseries${zone ? `?zone=${encodeURIComponent(zone)}` : ""}`),
  assets: () => get<{ assets: AssetRecord[]; types: Record<string, any>; policy: string }>("/api/assets"),
  addAsset: async (a: {
    name: string; type: string; lon: number; lat: number;
    sensitivity?: number | null; notes?: string;
  }) => {
    if (IS_STATIC) {
      // A static export has no write endpoint. Rather than fail silently, keep
      // the asset in this browser so the operator can still see it scored
      // against the current event, and say plainly that it is local only.
      const key = "blueban.localAssets";
      const prev = JSON.parse(localStorage.getItem(key) ?? "[]");
      const rec = { ...a, id: `L${prev.length + 1}`, source: "browser_local" };
      localStorage.setItem(key, JSON.stringify([...prev, rec]));
      throw new Error(
        "This deployment is a static export with no write endpoint. The asset "
        + "was stored in this browser only. Run the API locally to persist it "
        + "and score its exposure.");
    }
    const r = await fetch("/api/assets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(a),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  docsList: () => get<{ docs: { key: string; file: string; bytes: number }[] }>("/api/docs-list"),
  doc: async (key: string) => {
    const r = await fetch(resolve(`/api/docs/${key}`), { cache: "no-store" });
    if (!r.ok) throw new Error(`${r.status}`);
    return r.text();
  },
};

/* ------------------------------------------------------------------ format */

export const PRIORITY_COLOR: Record<string, string> = {
  NORMAL: "#3FD1A0",
  WATCH: "#F5C451",
  INVESTIGATE: "#FF7A45",
  HIGH_PRIORITY: "#FF4D4D",
  UNKNOWN: "#5A6490",
};

export const CLASS_COLOR: Record<string, string> = {
  BACKGROUND_WATER: "#3FD1A0",
  SEDIMENT_LIKE: "#F5C451",
  BLOOM_LIKE: "#FF7A45",
  CYANO_LIKE: "#FF4D4D",
  CDOM_LIKE: "#C77DFF",
  SURFACE_FILM_LIKE: "#FF4D4D",
  BOTTOM_INFLUENCED: "#4A93FF",
  UNKNOWN_ANOMALY: "#8A93B8",
};

export function fmt(n: number | null | undefined, digits = 2, dash = "-"): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return dash;
  return n.toFixed(digits);
}

export function fmtInt(n: number | null | undefined, dash = "-"): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return dash;
  return Math.round(n).toLocaleString("en-US");
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "-";
  return `${(n * 100).toFixed(digits)}%`;
}

export function utc(s: string | null | undefined): string {
  if (!s) return "-";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z").replace("Z", " UTC");
}

export function bearingToCompass(deg: number): string {
  const pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
               "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return pts[Math.floor(((deg + 11.25) % 360) / 22.5)];
}
