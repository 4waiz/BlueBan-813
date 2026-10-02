/** Shape of outputs/inland/summary.json (scripts/inland/build_inland_bundle.py). */

export type MaskKey = "2022-09-08" | "2024-04-24" | "persistent_core" | "mndwi_core";
export const MASK_KEYS: MaskKey[] = ["2022-09-08", "2024-04-24", "persistent_core", "mndwi_core"];

export interface MaskEntry {
  label: string; method: string; px: [number, number][]; n: number;
  n_inside_reconstructed_polygon: number; wet_fraction_of_polygon_pct: number | null; source: string;
}

export interface SweepRow { px_raw: number; px_final: number; px_outside_polygon: number; connected_components: number; darkness_max?: number; mndwi_min?: number }

export interface FingerprintPixel {
  row: number; col: number; rx_score: number; rx_threshold: number; sam_rad: number; d620: number | null;
  top_class: string | null; label: string | null; scores: Record<string, number> | null;
}

export interface AnomalyDate {
  test_pixels: number; background_pixels: number; threshold_score: number; n_components: number;
  explained_variance: number; n_events: number; fingerprint_top_class_counts: Record<string, number>;
  small_sample_caveat: string | null; pixels: FingerprintPixel[];
}

export interface Observation {
  datetime: string; date: string; sensor: "sentinel-2-l2a" | "landsat-c2-l2" | string; item_id: string;
  z: Record<string, number>; max_abs_z: number; flagged: boolean; flagged_index: string | null;
}

export interface ReviewFlag { id: string; severity: "high" | "medium" | "low" | "info"; title: string; plain?: string; detail: string; evidence: string }

export interface InlandSummary {
  generated_utc: string;
  site: { id: string; name: string; emirate: string; kind: string; polygon: [number, number][]; bbox: number[]; centroid: [number, number]; status: string };
  caveats: string[];
  licence: { enmap: string; attribution: string; withheld: string[] };
  scenes: Record<string, { id: string; self: string; datetime: string; "eo:cloud_cover": number; "view:sun_elevation": number; "proj:epsg": number; "proj:shape": number[] }>;
  window: {
    shape: [number, number]; resolution_m: number; epsg: number; polygon_px: [number, number][];
    inside_polygon_px: [number, number][]; n_inside_reconstructed: number; polygon_size_m: [number, number];
    polygon_area_m2: number; method: string;
  };
  masks: Record<MaskKey, MaskEntry> & {
    px_inside_locked_polygon_reported: number;
    threshold_sweep_persistent_core: SweepRow[];
    mndwi_threshold_sweep: SweepRow[];
    bad_bands_dropped_per_date: Record<string, number[]>;
  };
  anomaly: {
    available: boolean; method: string; background_d620_n?: number; test_mask_px?: number; background_mask_px?: number;
    background_is_superset_of_test?: boolean; per_date?: Record<string, AnomalyDate>;
  };
  temporal: {
    z_threshold: number; n_observations: number; n_flagged: number; observations: Observation[];
    per_sensor_n: Record<string, number>;
    chance_level: { p_one_index: number; n_indices: number; expected_flags_if_indices_perfectly_correlated: number; expected_flags_if_indices_independent: number; note: string };
  };
  baseline: { n: number; rows: { date: string; sensor: string; NDCI: number | null; NDTI: number | null; RTI: number | null; NDWI: number | null }[] };
  water_presence_periods: { period: string; ndwi_gt0_pct: [number, number]; ndwi_gt01_pct: [number, number] }[];
  satellite813: {
    simulation_support: Record<string, { n_with_real_support: number; n_without_real_support: number; unsupported_ranges_nm: [number, number, number][] }> | null;
    spec813: { n_bands: number; centres_nm: number[]; fwhm_nm: number; spatial_resolution_m: number; status: string };
    enmap_bands_package: { n: number; nm: number; fwhm: number }[];
    band_table_check: { delta_2022_minus_package_nm: number[]; delta_2024_minus_package_nm: number[] };
    coverage_comparison: Record<string, { overlap_range_nm: [number, number]; spatial_resolution_ratio_enmap_over_813: number }> | null;
  };
  flags: ReviewFlag[];
  docs: string[];
}

export const FP_COLOR: Record<string, string> = {
  BACKGROUND_WATER: "#5D7299", CDOM_LIKE: "#FFC23D", BLOOM_LIKE: "#23D484", SEDIMENT_LIKE: "#FF8A3D",
  SURFACE_SCUM_OR_FLOATING: "#FF4D5E",
};

export const SEVERITY_COLOR: Record<string, string> = { high: "#FF4D5E", medium: "#FFC23D", low: "#93A6CB", info: "#27C3F3" };
