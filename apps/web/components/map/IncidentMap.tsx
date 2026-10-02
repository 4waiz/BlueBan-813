"use client";
/**
 * The hero incident map.
 *
 * MapLibre GL 5: 2D map, 3D globe (globe projection + terrain + pitch) and a
 * synchronised split view for before / after. Every raster shown is a pipeline
 * product for this incident; layers that do not exist for the incident are
 * disabled with the reason, never faked.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { Map as MLMap, GeoJSONSource, LngLatBoundsLike } from "maplibre-gl";
import { motion } from "framer-motion";
import {
  Crosshair, Globe2, Layers, Map as MapIcon, Maximize2, Pause, Play, Ruler, Search, SplitSquareHorizontal,
  SquareDashedMousePointer, MapPinPlus, RotateCcw,
} from "lucide-react";
import type { Aoi, AssetRow, Incident, IncidentSummary, LayerRef, Sample } from "@/lib/engine/types";
import { pipelineUrl } from "@/lib/engine";
import { registerIcons } from "./icons";
import { fmt, STATE_COLOR, toast } from "@/components/ui";

export type MapTool = "none" | "draw-aoi" | "place-asset" | "measure";
export type MapMode = "2d" | "3d" | "split";

const EOX = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg";
const DEM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const ATTR = 'Basemap: <a href="https://s2maps.eu" target="_blank">Sentinel-2 cloudless 2021</a> by EOX IT Services GmbH (modified Copernicus Sentinel data 2021) · Terrain: AWS Terrain Tiles · © <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>';

const PLACES: [string, number, number][] = [
  ["Abu Dhabi", 54.37, 24.47], ["Dubai", 55.27, 25.2], ["Sharjah", 55.39, 25.35], ["Ajman", 55.44, 25.41],
  ["Umm Al Quwain", 55.55, 25.56], ["Ras Al Khaimah", 55.94, 25.79], ["Fujairah", 56.33, 25.12],
  ["Khor Fakkan", 56.35, 25.34], ["Kalba", 56.35, 25.05], ["Dibba", 56.27, 25.62], ["Al Taweelah", 54.68, 24.78],
  ["Mussafah", 54.5, 24.36], ["Jebel Ali", 55.03, 25.0],
];

function baseStyle(): maplibregl.StyleSpecification {
  return {
    version: 8,
    sources: {
      s2c: { type: "raster", tiles: [EOX], tileSize: 256, maxzoom: 15, attribution: ATTR },
      dem: { type: "raster-dem", tiles: [DEM], tileSize: 256, maxzoom: 13, encoding: "terrarium" },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#040915" } },
      { id: "s2c", type: "raster", source: "s2c", paint: { "raster-saturation": -0.1, "raster-contrast": 0.08, "raster-brightness-max": 0.92 } },
    ],
    sky: { "sky-color": "#061126", "horizon-color": "#0b2a57", "sky-horizon-blend": 0.6, "atmosphere-blend": 0.9 },
  } as maplibregl.StyleSpecification;
}

const corners = (b: [number, number, number, number]) => [[b[0], b[3]], [b[2], b[3]], [b[2], b[1]], [b[0], b[1]]] as [[number, number], [number, number], [number, number], [number, number]];

function haversine(a: [number, number], b: [number, number]) {
  const R = 6371000, r = Math.PI / 180;
  const dphi = (b[1] - a[1]) * r, dl = (b[0] - a[0]) * r;
  const h = Math.sin(dphi / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export interface PixelValues { lon: number; lat: number; values: Record<string, number | null>; date?: string }

interface Props {
  incident: Incident | null;
  incidents: IncidentSummary[];
  aois: Aoi[];
  assets: AssetRow[];
  stations?: GeoJSON.FeatureCollection | null;
  samples?: Sample[];
  onSelectIncident?: (id: string) => void;
  onMoveSample?: (s: Sample, lon: number, lat: number) => void;
  onDrawAoi?: (bbox: [number, number, number, number]) => void;
  onPlaceAsset?: (lon: number, lat: number) => void;
  /** What the pin tool adds on this screen (defaults to an asset). */
  placeLabel?: string;
  onPixel?: (p: PixelValues) => void;
  compact?: boolean;
  initialMode?: MapMode;
  showTimeline?: boolean;
  className?: string;
}

const LAYER_ORDER = ["rgb", "ndci", "ndci_z", "mci", "turbidity", "tur_z", "anomaly", "hue", "s813", "olci", "sar", "thermal", "water"];

export default function IncidentMap(props: Props) {
  const { incident, incidents, aois, assets, stations, samples = [], compact = false, initialMode = "3d", showTimeline = true } = props;
  const wrap = useRef<HTMLDivElement>(null);
  const el = useRef<HTMLDivElement>(null);
  const elB = useRef<HTMLDivElement>(null);
  const miniEl = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const mapB = useRef<MLMap | null>(null);
  const mini = useRef<MLMap | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const sampleMarkers = useRef<maplibregl.Marker[]>([]);
  const [ready, setReady] = useState(false);
  const [mode, setMode] = useState<MapMode>(initialMode);
  const [tool, setTool] = useState<MapTool>("none");
  const [panel, setPanel] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [active, setActive] = useState<Record<string, boolean>>({ rgb: true, ndci: true, water: false, assets: true, stations: true, aois: true });
  const [tIdx, setTIdx] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [measure, setMeasure] = useState<[number, number][]>([]);
  const [search, setSearch] = useState("");
  const pixels = useRef<{ meta: { bounds: number[]; shape: [number, number]; fields: string[]; scale?: Record<string, number> } | null; data: Record<string, Float32Array> }>({ meta: null, data: {} });
  const toolRef = useRef(tool);
  toolRef.current = tool;
  const lastMode = useRef<MapMode | null>(null);

  const rasters: LayerRef[] = useMemo(() => incident?.layers?.rasters || [], [incident]);
  const timeline = incident?.layers?.timeline || [];
  const rasterBy = useMemo(() => Object.fromEntries(rasters.map((r) => [r.key, r])), [rasters]);

  // ------------------------------------------------------------------ init
  useEffect(() => {
    if (!el.current || map.current) return;
    const m = new maplibregl.Map({
      container: el.current, style: baseStyle(), center: [55.2, 25.0], zoom: 6.4, pitch: initialMode === "3d" ? 48 : 0,
      bearing: initialMode === "3d" ? -12 : 0, maxPitch: 75, attributionControl: { compact: true }, canvasContextAttributes: { antialias: true },
    });
    m.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: "metric" }), "bottom-right");
    map.current = m;
    m.on("load", async () => {
      await registerIcons(m);
      if (initialMode === "3d") { try { m.setProjection({ type: "globe" }); m.setTerrain({ source: "dem", exaggeration: 1.3 }); } catch { /* older GPU */ } }
      setReady(true);
    });
    m.on("error", () => { /* tile errors are non-fatal */ });
    return () => { m.remove(); map.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // mini map
  useEffect(() => {
    if (compact || !miniEl.current || mini.current) return;
    const mm = new maplibregl.Map({ container: miniEl.current, style: baseStyle(), center: [54.9, 24.6], zoom: 4.6, interactive: false, attributionControl: false });
    mm.on("load", () => {
      mm.addSource("vp", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      mm.addLayer({ id: "vp-fill", type: "fill", source: "vp", paint: { "fill-color": "#23D484", "fill-opacity": 0.18 } });
      mm.addLayer({ id: "vp-line", type: "line", source: "vp", paint: { "line-color": "#23D484", "line-width": 1.5 } });
    });
    mini.current = mm;
    return () => { mm.remove(); mini.current = null; };
  }, [compact]);

  const syncMini = useCallback(() => {
    const m = map.current, mm = mini.current;
    if (!m || !mm || !mm.getSource("vp")) return;
    const b = m.getBounds();
    mm.jumpTo({ center: m.getCenter(), zoom: Math.max(2.5, m.getZoom() - 4) });
    (mm.getSource("vp") as GeoJSONSource).setData({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[b.getWest(), b.getNorth()], [b.getEast(), b.getNorth()], [b.getEast(), b.getSouth()], [b.getWest(), b.getSouth()], [b.getWest(), b.getNorth()]]] } });
  }, []);
  useEffect(() => { const m = map.current; if (!m || !ready) return; m.on("moveend", syncMini); syncMini(); return () => { m.off("moveend", syncMini); }; }, [ready, syncMini]);

  // ------------------------------------------------------------ mode switch
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const changed = lastMode.current !== null && lastMode.current !== mode;
    lastMode.current = mode;
    try {
      // Only animate when the operator actually switches mode: an ease on first
      // load would cancel the fit-to-incident flight and strand the camera.
      if (mode === "3d") { m.setProjection({ type: "globe" }); m.setTerrain({ source: "dem", exaggeration: 1.3 }); if (changed) m.easeTo({ pitch: 50, bearing: -12, duration: 600 }); }
      else { m.setTerrain(null); m.setProjection({ type: "mercator" }); if (changed) m.easeTo({ pitch: 0, bearing: 0, duration: 400 }); }
    } catch { /* ignore */ }
    if (mode === "split" && elB.current && !mapB.current) {
      const b = new maplibregl.Map({ container: elB.current, style: baseStyle(), center: m.getCenter(), zoom: m.getZoom(), attributionControl: false });
      mapB.current = b;
      let lock = false;
      const sync = (src: MLMap, dst: MLMap) => () => { if (lock) return; lock = true; dst.jumpTo({ center: src.getCenter(), zoom: src.getZoom(), bearing: src.getBearing(), pitch: src.getPitch() }); lock = false; };
      m.on("move", sync(m, b)); b.on("move", sync(b, m));
      b.on("load", () => { setBLayers(b); });
    }
    if (mode !== "split" && mapB.current) { mapB.current.remove(); mapB.current = null; }
    setTimeout(() => { m.resize(); mapB.current?.resize(); }, 50);
  }, [mode, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------ overlays (vector)
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const put = (id: string, data: GeoJSON.GeoJSON) => {
      const s = m.getSource(id) as GeoJSONSource | undefined;
      if (s) s.setData(data as GeoJSON.FeatureCollection); else m.addSource(id, { type: "geojson", data: data as GeoJSON.FeatureCollection });
    };
    put("aois", { type: "FeatureCollection", features: aois.filter((a) => a.id.startsWith("AE-")).map((a) => ({ type: "Feature", properties: { id: a.id, name: a.name }, geometry: { type: "Polygon", coordinates: [[[a.bbox[0], a.bbox[1]], [a.bbox[2], a.bbox[1]], [a.bbox[2], a.bbox[3]], [a.bbox[0], a.bbox[3]], [a.bbox[0], a.bbox[1]]]] } })) });
    put("assets", { type: "FeatureCollection", features: assets.filter((a) => a.type !== "PUBLIC_BEACH").map((a) => ({ type: "Feature", properties: { ...a, icon: `ic-${a.type}` }, geometry: { type: "Point", coordinates: [a.lon, a.lat] } })) });
    put("stations", stations || { type: "FeatureCollection", features: [] });
    put("incidents", { type: "FeatureCollection", features: incidents.filter((i) => i.centroid_lon != null).map((i) => ({ type: "Feature", properties: { id: i.id, status: i.status, color: STATE_COLOR[i.status] || "#93A6CB", role: i.role || "operational" }, geometry: { type: "Point", coordinates: [i.centroid_lon!, i.centroid_lat!] } })) });
    put("incident-geom", incident?.geometry ? { type: "Feature", properties: {}, geometry: incident.geometry } : { type: "FeatureCollection", features: [] });
    put("measure", { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: measure } });
    put("draw", { type: "FeatureCollection", features: [] });
    const add = (spec: maplibregl.LayerSpecification) => { if (!m.getLayer(spec.id)) m.addLayer(spec); };
    add({ id: "aois-line", type: "line", source: "aois", paint: { "line-color": "#4D93FF", "line-width": 1.2, "line-dasharray": [3, 2], "line-opacity": 0.8 } });
    add({ id: "incident-fill", type: "fill", source: "incident-geom", paint: { "fill-color": "#FF4D5E", "fill-opacity": 0.12 } });
    add({ id: "incident-line", type: "line", source: "incident-geom", paint: { "line-color": "#FF4D5E", "line-width": 2 } });
    add({ id: "stations", type: "symbol", source: "stations", layout: { "icon-image": ["case", ["==", ["get", "kind"], "AUTOMATED_BUOY"], "ic-BUOY", "ic-STATION"], "icon-size": 0.62, "icon-allow-overlap": true } });
    add({ id: "assets", type: "symbol", source: "assets", layout: { "icon-image": ["get", "icon"], "icon-size": 0.72, "icon-allow-overlap": true } });
    add({ id: "incidents-halo", type: "circle", source: "incidents", paint: { "circle-radius": 16, "circle-color": ["get", "color"], "circle-opacity": 0.18, "circle-stroke-width": 1, "circle-stroke-color": ["get", "color"] } });
    add({ id: "incidents", type: "circle", source: "incidents", paint: { "circle-radius": 6, "circle-color": ["get", "color"], "circle-stroke-width": 2, "circle-stroke-color": "#040915" } });
    add({ id: "measure", type: "line", source: "measure", paint: { "line-color": "#FFC23D", "line-width": 2, "line-dasharray": [2, 1] } });
    add({ id: "draw-fill", type: "fill", source: "draw", paint: { "fill-color": "#27C3F3", "fill-opacity": 0.15 } });
    add({ id: "draw-line", type: "line", source: "draw", paint: { "line-color": "#27C3F3", "line-width": 1.5 } });
    for (const [id, key] of [["assets", "assets"], ["stations", "stations"], ["aois-line", "aois"]] as const)
      m.setLayoutProperty(id, "visibility", active[key] ? "visible" : "none");
  }, [ready, aois, assets, stations, incidents, incident, measure, active]);

  // popups / clicks
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const pop = new maplibregl.Popup({ closeButton: false, offset: 14 });
    const enter = (e: maplibregl.MapLayerMouseEvent) => {
      m.getCanvas().style.cursor = "pointer";
      const f = e.features?.[0];
      if (!f) return;
      const p = f.properties as Record<string, string>;
      const html = f.layer.id === "assets" ? `<div style="font-weight:700">${p.name}</div><div style="color:#93A6CB;font-size:11px">${p.type.replace(/_/g, " ")} · ${p.source}</div>`
        : f.layer.id === "stations" ? `<div style="font-weight:700">${p.name}</div><div style="color:#93A6CB;font-size:11px">EAD ${p.kind === "AUTOMATED_BUOY" ? "automated buoy" : "sampling site"} · location only, no readings</div>`
        : `<div style="font-weight:700">${p.id}</div><div style="color:#93A6CB;font-size:11px">${p.status.replace(/_/g, " ")}${p.role === "negative_control" ? " · known false alarm (kept as a test)" : ""}</div>`;
      pop.setLngLat(e.lngLat).setHTML(html).addTo(m);
    };
    const leave = () => { m.getCanvas().style.cursor = ""; pop.remove(); };
    const clickInc = (e: maplibregl.MapLayerMouseEvent) => { const id = (e.features?.[0]?.properties as { id?: string })?.id; if (id) props.onSelectIncident?.(id); };
    for (const l of ["assets", "stations", "incidents"]) { m.on("mouseenter", l, enter); m.on("mouseleave", l, leave); }
    m.on("click", "incidents", clickInc);
    return () => { for (const l of ["assets", "stations", "incidents"]) { m.off("mouseenter", l, enter); m.off("mouseleave", l, leave); } m.off("click", "incidents", clickInc); pop.remove(); };
  }, [ready]); // eslint-disable-line react-hooks/exhaustive-deps

  // city labels (DOM pills, matching the target design)
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || compact) return;
    markers.current.forEach((x) => x.remove());
    markers.current = PLACES.map(([n, lon, lat]) => {
      const d = document.createElement("div"); d.className = "map-pill"; d.textContent = n;
      return new maplibregl.Marker({ element: d, anchor: "left", offset: [6, 0] }).setLngLat([lon, lat]).addTo(m);
    });
    return () => { markers.current.forEach((x) => x.remove()); };
  }, [ready, compact]);

  // ------------------------------------------------------ incident rasters
  const setRasterLayers = useCallback((m: MLMap, which: "A" | "B") => {
    if (!incident) return;
    for (const key of LAYER_ORDER) {
      const r = rasterBy[key];
      const id = `r-${key}`;
      let url = r?.url;
      if (r && timeline.length && tIdx != null && (key === "rgb" || key === "ndci" || key === "ndci_z")) {
        const t = timeline[which === "B" ? timeline.length - 1 : tIdx];
        if (t) url = key === "rgb" ? t.rgb : t.index || url;
      }
      if (!r || !url) { if (m.getLayer(id)) m.removeLayer(id); if (m.getSource(id)) m.removeSource(id); continue; }
      const full = pipelineUrl(url);
      const src = m.getSource(id) as maplibregl.ImageSource | undefined;
      if (src) src.updateImage({ url: full, coordinates: corners(r.bounds) });
      else m.addSource(id, { type: "image", url: full, coordinates: corners(r.bounds) });
      if (!m.getLayer(id)) m.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": key === "rgb" ? 1 : 0.82, "raster-fade-duration": 200, "raster-resampling": key === "rgb" ? "linear" : "nearest" } }, m.getLayer("aois-line") ? "aois-line" : undefined);
      m.setLayoutProperty(id, "visibility", active[key] || (which === "B" && key === "rgb") ? "visible" : "none");
    }
  }, [incident, rasterBy, timeline, tIdx, active]);

  const setBLayers = useCallback((b: MLMap) => setRasterLayers(b, "B"), [setRasterLayers]);

  useEffect(() => { const m = map.current; if (m && ready) setRasterLayers(m, "A"); if (mapB.current?.isStyleLoaded()) setRasterLayers(mapB.current, "B"); }, [ready, setRasterLayers]);

  // fly to incident
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !incident) return;
    const b = incident.layers?.bounds;
    if (b) m.fitBounds([[b[0], b[1]], [b[2], b[3]]] as LngLatBoundsLike, { padding: compact ? 20 : { top: 70, bottom: 40, left: 40, right: 70 }, duration: 1400, maxZoom: 13, pitch: mode === "3d" ? 40 : 0, bearing: mode === "3d" ? -10 : 0 });
    else if (incident.centroid) m.flyTo({ center: incident.centroid, zoom: 10.5, duration: 1400 });
    setTIdx(timeline.length ? timeline.length - 1 : null);
    const defaults = (incident.layers as unknown as { default?: string[] })?.default;
    if (defaults) setActive((a) => ({ ...a, ...Object.fromEntries(LAYER_ORDER.map((k) => [k, defaults.includes(k)])) }));
    // pixel grid for click-inspection
    pixels.current = { meta: null, data: {} };
    const px = incident.layers?.pixels;
    if (px) {
      fetch(pipelineUrl(px.meta)).then((r) => r.json()).then(async (meta) => {
        const buf = await fetch(pipelineUrl(px.url)).then((r) => r.arrayBuffer());
        const n = meta.shape[0] * meta.shape[1];
        const all = new Int16Array(buf);
        const data: Record<string, Float32Array> = {};
        meta.fields.forEach((f: string, k: number) => {
          const sc = meta.scale?.[f] ?? 1, arr = new Float32Array(n);
          for (let i = 0; i < n; i++) { const v = all[k * n + i]; arr[i] = v === -32768 ? NaN : v * sc; }
          data[f] = arr;
        });
        pixels.current = { meta, data };
      }).catch(() => { pixels.current = { meta: null, data: {} }; });
    }
  }, [incident?.id, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  // timeline playback
  useEffect(() => {
    if (!playing || !timeline.length) return;
    const t = setInterval(() => setTIdx((i) => (i == null ? 0 : (i + 1) % timeline.length)), 900);
    return () => clearInterval(t);
  }, [playing, timeline.length]);

  // samples (draggable)
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    sampleMarkers.current.forEach((x) => x.remove());
    sampleMarkers.current = samples.map((s) => {
      const d = document.createElement("div");
      const c = STATE_COLOR[s.status] || "#EAF1FF";
      d.innerHTML = `<div style="display:flex;align-items:center;gap:4px;cursor:grab"><div style="width:14px;height:14px;border-radius:50%;background:${c};border:2px solid #040915;box-shadow:0 0 10px ${c}"></div><span class="map-pill" style="font-size:10px">${s.code} ${s.role}</span></div>`;
      const mk = new maplibregl.Marker({ element: d, draggable: !!props.onMoveSample, anchor: "left" }).setLngLat([s.lon, s.lat]).addTo(m);
      mk.on("dragend", () => { const p = mk.getLngLat(); props.onMoveSample?.(s, p.lng, p.lat); });
      return mk;
    });
    return () => { sampleMarkers.current.forEach((x) => x.remove()); };
  }, [ready, samples]); // eslint-disable-line react-hooks/exhaustive-deps

  // tools: pixel inspect / draw AOI / place asset / measure
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    let start: maplibregl.LngLat | null = null;
    const onDown = (e: maplibregl.MapMouseEvent) => {
      if (toolRef.current !== "draw-aoi") return;
      e.preventDefault(); m.dragPan.disable(); start = e.lngLat;
    };
    const onMove = (e: maplibregl.MapMouseEvent) => {
      if (toolRef.current !== "draw-aoi" || !start) return;
      const a = start, b = e.lngLat;
      (m.getSource("draw") as GeoJSONSource).setData({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[a.lng, a.lat], [b.lng, a.lat], [b.lng, b.lat], [a.lng, b.lat], [a.lng, a.lat]]] } });
    };
    const onUp = (e: maplibregl.MapMouseEvent) => {
      if (toolRef.current !== "draw-aoi" || !start) return;
      m.dragPan.enable();
      const a = start, b = e.lngLat; start = null;
      const bbox: [number, number, number, number] = [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)];
      if (bbox[2] - bbox[0] < 0.01 || bbox[3] - bbox[1] < 0.01) { toast("Area too small: drag a bigger box", "err"); return; }
      setTool("none");
      props.onDrawAoi?.(bbox);
    };
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const t = toolRef.current;
      if (t === "place-asset") { setTool("none"); props.onPlaceAsset?.(e.lngLat.lng, e.lngLat.lat); return; }
      if (t === "measure") { setMeasure((pts) => [...pts, [e.lngLat.lng, e.lngLat.lat]]); return; }
      if (t !== "none") return;
      const px = pixels.current;
      if (!px.meta) return;
      const [w, s, ea, n] = px.meta.bounds, [rows, cols] = px.meta.shape;
      const c = Math.floor(((e.lngLat.lng - w) / (ea - w)) * cols), r = Math.floor(((n - e.lngLat.lat) / (n - s)) * rows);
      if (r < 0 || c < 0 || r >= rows || c >= cols) return;
      const values: Record<string, number | null> = {};
      for (const f of px.meta.fields) { const v = px.data[f]?.[r * cols + c]; values[f] = v != null && Number.isFinite(v) ? v : null; }
      props.onPixel?.({ lon: e.lngLat.lng, lat: e.lngLat.lat, values, date: timeline[tIdx ?? 0]?.date });
    };
    m.on("mousedown", onDown); m.on("mousemove", onMove); m.on("mouseup", onUp); m.on("click", onClick);
    return () => { m.off("mousedown", onDown); m.off("mousemove", onMove); m.off("mouseup", onUp); m.off("click", onClick); };
  }, [ready, tIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { const m = map.current; if (m) m.getCanvas().style.cursor = tool === "none" ? "" : "crosshair"; if (tool !== "measure") setMeasure([]); }, [tool]);

  const measureM = measure.length > 1 ? measure.slice(1).reduce((s, p, i) => s + haversine(measure[i], p), 0) : 0;

  const doSearch = () => {
    const q = search.trim().toLowerCase();
    if (!q || !map.current) return;
    const hit = PLACES.find(([n]) => n.toLowerCase().includes(q));
    const a = aois.find((x) => x.name.toLowerCase().includes(q) || x.id.toLowerCase().includes(q));
    const s = assets.find((x) => x.name.toLowerCase().includes(q));
    if (a) map.current.fitBounds([[a.bbox[0], a.bbox[1]], [a.bbox[2], a.bbox[3]]], { padding: 40 });
    else if (s) map.current.flyTo({ center: [s.lon, s.lat], zoom: 12 });
    else if (hit) map.current.flyTo({ center: [hit[1], hit[2]], zoom: 10 });
    else toast(`No place, area or asset matches "${search}"`, "err");
  };

  const layerDefs: { key: string; label: string; note?: string }[] = [
    { key: "rgb", label: "True colour" }, { key: "ndci", label: "Chlorophyll index (NDCI)" },
    { key: "ndci_z", label: "Chlorophyll vs past years" }, { key: "mci", label: "Chlorophyll peak (MCI)" },
    { key: "turbidity", label: "Turbidity (not calibrated)" }, { key: "anomaly", label: "Spectral anomaly score" },
    { key: "hue", label: "Water colour (hue)" }, { key: "s813", label: "Simulated 813 (hyperspectral)" },
    { key: "olci", label: "Sentinel-3 check" }, { key: "sar", label: "Sentinel-1 radar" },
    { key: "thermal", label: "Landsat thermal" }, { key: "water", label: "Water mask" },
  ];

  return (
    <div ref={wrap} className={`relative h-full w-full overflow-hidden rounded-[10px] ${props.className || ""}`}>
      <div className="absolute inset-0 flex">
        <div ref={el} className={mode === "split" ? "h-full w-1/2" : "h-full w-full"} />
        {mode === "split" && <div ref={elB} className="h-full w-1/2 border-l-2 border-cyan" />}
      </div>
      {mode === "split" && (
        <>
          <div className="map-pill absolute left-3 top-16 z-10">BEFORE · {timeline[tIdx ?? 0]?.date || "earlier"}</div>
          <div className="map-pill absolute right-16 top-16 z-10">INCIDENT · {timeline[timeline.length - 1]?.date || incident?.observation_time?.slice(0, 10)}</div>
        </>
      )}

      {/* top toolbar */}
      {!compact && (
        <div className="absolute left-3 right-16 top-3 z-10 flex flex-wrap items-center gap-2">
          <div className="panel-flat flex p-1">
            {([["2d", "2D Map", <MapIcon key="m" size={14} />], ["3d", "3D Globe", <Globe2 key="g" size={14} />], ["split", "Before / after", <SplitSquareHorizontal key="s" size={14} />]] as const).map(([k, l, ic]) => (
              <button key={k} onClick={() => setMode(k)} className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-semibold ${mode === k ? "bg-beam text-white shadow-beam" : "text-muted hover:text-ink"}`}>{ic}{l}</button>
            ))}
          </div>
          {timeline.length > 0 && showTimeline && (
            <div className="panel-flat flex min-w-[320px] flex-1 items-center gap-3 px-3 py-1.5">
              <span className="hud-value text-[11.5px] text-ink">{timeline[tIdx ?? 0]?.date}</span>
              <input name="timeline" type="range" min={0} max={timeline.length - 1} value={tIdx ?? 0} onChange={(e) => { setPlaying(false); setTIdx(Number(e.target.value)); }} className="flex-1 accent-[#2F7BFF]" aria-label="Image date" />
              <span className="text-[10.5px] text-muted">{timeline.length} images</span>
              <button onClick={() => setPlaying((p) => !p)} className="grid h-7 w-7 place-items-center rounded-full bg-beam text-white" aria-label={playing ? "Pause" : "Play"}>{playing ? <Pause size={13} /> : <Play size={13} />}</button>
            </div>
          )}
        </div>
      )}

      {/* right tool column */}
      {!compact && (
        <div className="panel-flat absolute right-3 top-3 z-10 flex flex-col gap-1 p-1">
          <ToolBtn title="Search places, areas and assets" active={searchOpen} onClick={() => { setSearchOpen((v) => !v); setPanel(true); }} icon={<Search size={16} />} />
          <ToolBtn title="Layers" active={panel} onClick={() => setPanel((p) => !p)} icon={<Layers size={16} />} />
          <ToolBtn title="Add a monitored area (drag a box)" active={tool === "draw-aoi"} onClick={() => setTool(tool === "draw-aoi" ? "none" : "draw-aoi")} icon={<SquareDashedMousePointer size={16} />} />
          <ToolBtn title={props.placeLabel || "Add your own asset (e.g. a desalination plant)"} active={tool === "place-asset"} onClick={() => setTool(tool === "place-asset" ? "none" : "place-asset")} icon={<MapPinPlus size={16} />} />
          <ToolBtn title="Measure distance" active={tool === "measure"} onClick={() => setTool(tool === "measure" ? "none" : "measure")} icon={<Ruler size={16} />} />
          <ToolBtn title="Zoom to incident" onClick={() => { const b = incident?.layers?.bounds; if (b && map.current) map.current.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 60 }); }} icon={<Crosshair size={16} />} />
          <ToolBtn title="Reset view" onClick={() => map.current?.flyTo({ center: [55.2, 25.0], zoom: 6.4, pitch: mode === "3d" ? 48 : 0, bearing: 0 })} icon={<RotateCcw size={16} />} />
          <ToolBtn title="Full screen" onClick={() => wrap.current?.requestFullscreen?.()} icon={<Maximize2 size={16} />} />
        </div>
      )}

      {/* layer panel */}
      {!compact && panel && (
        <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} className="panel absolute right-14 top-14 z-10 max-h-[calc(100%-120px)] w-[228px] overflow-y-auto p-2.5">
          {searchOpen && <div className="mb-2 flex gap-1">
            <input name="map-search" autoFocus value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doSearch()} placeholder="Place, area or asset" className="w-full rounded-md border border-line bg-deep px-2 py-1.5 text-[12px] outline-none focus:border-beam2" />
            <button onClick={doSearch} className="btn px-2 py-1"><Search size={13} /></button>
          </div>}
          <div className="hud-kicker mb-1 mt-2">Incident layers</div>
          {layerDefs.map((l) => {
            const avail = !!rasterBy[l.key] || (l.key === "water" && !!rasterBy.water);
            return (
              <label key={l.key} className={`flex items-center justify-between gap-2 py-[3px] text-[11.5px] ${avail ? "text-ink" : "text-dim"}`} title={avail ? rasterBy[l.key]?.label : "Not available for this incident"}>
                <span className="truncate">{l.label}</span>
                <input type="checkbox" disabled={!avail} checked={!!active[l.key] && avail} onChange={(e) => setActive((a) => ({ ...a, [l.key]: e.target.checked }))} className="accent-[#2F7BFF]" />
              </label>
            );
          })}
          <div className="hud-kicker mb-1 mt-3">Context</div>
          {[["assets", "Key assets (OpenStreetMap)"], ["stations", "EAD monitoring stations"], ["aois", "Monitored areas"]].map(([k, l]) => (
            <label key={k} className="flex items-center justify-between py-1 text-[12px] text-ink"><span>{l}</span>
              <input type="checkbox" checked={!!active[k]} onChange={(e) => setActive((a) => ({ ...a, [k]: e.target.checked }))} className="accent-[#2F7BFF]" /></label>
          ))}
          {rasters.filter((r) => active[r.key] && r.legend).slice(0, 2).map((r) => (
            <div key={r.key} className="mt-3">
              <div className="flex justify-between text-[10.5px] text-muted"><span>{r.legend!.label}</span><span>{r.legend!.units}</span></div>
              <div className="mt-1 h-2 rounded" style={{ background: r.legend!.cmap === "div" ? "linear-gradient(90deg,#2F7BFF,#0A1630,#FF4D5E)" : "linear-gradient(90deg,#1b1f7a,#1f78b4,#22c47a,#f4d03f,#f39c12,#e0283e)" }} />
              <div className="flex justify-between text-[10px] text-muted"><span>{fmt.num(r.legend!.min)}</span><span>{fmt.num(r.legend!.max)}</span></div>
            </div>
          ))}
        </motion.div>
      )}

      {tool !== "none" && !compact && (
        <div className="map-pill absolute bottom-14 left-1/2 z-10 -translate-x-1/2 text-[12px]">
          {tool === "draw-aoi" ? "Drag a box on the map to add a monitored area" : tool === "place-asset" ? `Click the map: ${(props.placeLabel || "Add your asset").toLowerCase()}` : `Measure: click points · ${fmt.km(measureM)}`}
        </div>
      )}

      {!compact && (
        <div className="panel absolute bottom-9 right-3 z-10 h-[118px] w-[170px] overflow-hidden p-0">
          <div ref={miniEl} className="h-full w-full" />
        </div>
      )}
    </div>
  );
}

function ToolBtn({ icon, title, onClick, active }: { icon: React.ReactNode; title: string; onClick: () => void; active?: boolean }) {
  return <button title={title} aria-label={title} onClick={onClick} className={`grid h-8 w-8 place-items-center rounded-md ${active ? "bg-beam text-white" : "text-muted hover:bg-panel2 hover:text-ink"}`}>{icon}</button>;
}
