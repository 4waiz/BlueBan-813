"use client";

/**
 * The hero object: an interactive dark-ocean view of the detected event.
 *
 * Layers are stacked in the order a water operator reads them:
 *   1. true-colour imagery (what the sensor saw)
 *   2. the anomaly field (what the detector found)
 *   3. event contours (where the boundary is)
 *   4. drift particles and track (where it may go)
 *   5. assets and sample points (what matters and where to go)
 *
 * Basemap: a plain dark canvas plus our own raster overlays. No external tile
 * provider is used, which keeps the demo working offline and avoids sending
 * the AOI to a third party.
 */

import maplibregl, { Map as MLMap, LngLatBoundsLike } from "maplibre-gl";
import React, { useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

import { CLASS_COLOR, ExposureRecord, ForecastStep, SamplePoint } from "@/lib/api";

export type RasterKey = "rgb" | "anomaly" | "ndci" | "turbidity";

export interface OceanMapProps {
  bounds: number[];                     // [w, s, e, n]
  raster: RasterKey;
  rasterOpacity?: number;
  showEvents?: boolean;
  showWater?: boolean;
  exposures?: ExposureRecord[];
  samples?: SamplePoint[];
  forecast?: ForecastStep[];
  forecastIndex?: number;
  showTrack?: boolean;
  focus?: [number, number] | null;
  onPickCoord?: (lon: number, lat: number) => void;
  pickMode?: boolean;
  className?: string;
  interactive?: boolean;
}

// A minimal self-contained style. No external tile provider: the AOI is never
// sent to a third party, and the demo works with no network. `glyphs` must be
// omitted entirely rather than set to undefined, which MapLibre rejects.
const EMPTY_STYLE: any = {
  version: 8,
  sources: {},
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#070A16" } },
  ],
};

export default function OceanMap({
  bounds, raster, rasterOpacity = 1, showEvents = true, showWater = false,
  exposures = [], samples = [], forecast = [], forecastIndex = 0,
  showTrack = true, focus = null, onPickCoord, pickMode = false,
  className = "", interactive = true,
}: OceanMapProps) {
  const holder = useRef<HTMLDivElement | null>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const [ready, setReady] = useState(false);

  /* ------------------------------------------------------------ init once */
  useEffect(() => {
    if (!holder.current || map.current) return;
    const [w, s, e, n] = bounds;
    const m = new maplibregl.Map({
      container: holder.current,
      style: EMPTY_STYLE,
      bounds: [[w, s], [e, n]] as LngLatBoundsLike,
      fitBoundsOptions: { padding: 28 },
      attributionControl: false,
      interactive,
      maxZoom: 16,
      dragRotate: false,
      pitchWithRotate: false,
    });
    m.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution:
        "Tanager © Planet Labs PBC (CC-BY-4.0) · Sentinel © ESA/Copernicus",
    }), "bottom-right");
    if (interactive) m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    m.on("load", () => {
      const rb: [[number, number], [number, number], [number, number], [number, number]] =
        [[w, n], [e, n], [e, s], [w, s]];

      (["rgb", "anomaly", "ndci", "turbidity"] as RasterKey[]).forEach((k) => {
        m.addSource(`src-${k}`, { type: "image", url: `/api/layers/${k}`, coordinates: rb });
        m.addLayer({
          id: `lyr-${k}`, type: "raster", source: `src-${k}`,
          paint: { "raster-opacity": 0, "raster-fade-duration": 220,
                   "raster-resampling": "linear" },
        });
      });

      m.addSource("src-water", { type: "geojson", data: "/api/layers/water" });
      m.addLayer({
        id: "lyr-water-line", type: "line", source: "src-water",
        paint: { "line-color": "#3186FF", "line-width": 0.8, "line-opacity": 0 },
      });

      m.addSource("src-events", { type: "geojson", data: "/api/layers/events" });
      m.addLayer({
        id: "lyr-events-fill", type: "fill", source: "src-events",
        paint: {
          "fill-color": ["match", ["get", "class"],
            "SEDIMENT_LIKE", CLASS_COLOR.SEDIMENT_LIKE,
            "BLOOM_LIKE", CLASS_COLOR.BLOOM_LIKE,
            "CYANO_LIKE", CLASS_COLOR.CYANO_LIKE,
            "CDOM_LIKE", CLASS_COLOR.CDOM_LIKE,
            "BOTTOM_INFLUENCED", CLASS_COLOR.BOTTOM_INFLUENCED,
            "UNKNOWN_ANOMALY", CLASS_COLOR.UNKNOWN_ANOMALY,
            "#8A93B8"],
          "fill-opacity": 0.16,
        },
      });
      m.addLayer({
        id: "lyr-events-line", type: "line", source: "src-events",
        paint: {
          "line-color": ["match", ["get", "class"],
            "SEDIMENT_LIKE", CLASS_COLOR.SEDIMENT_LIKE,
            "BLOOM_LIKE", CLASS_COLOR.BLOOM_LIKE,
            "CYANO_LIKE", CLASS_COLOR.CYANO_LIKE,
            "CDOM_LIKE", CLASS_COLOR.CDOM_LIKE,
            "BOTTOM_INFLUENCED", CLASS_COLOR.BOTTOM_INFLUENCED,
            "UNKNOWN_ANOMALY", CLASS_COLOR.UNKNOWN_ANOMALY,
            "#8A93B8"],
          "line-width": ["case", ["==", ["get", "is_primary"], true], 2.1, 1.0],
          "line-opacity": 0.95,
        },
      });

      m.addSource("src-particles", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "lyr-particles", type: "circle", source: "src-particles",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 1.4, 14, 3.4],
          "circle-color": ["case", ["==", ["get", "beached"], true], "#F5C451", "#4A93FF"],
          "circle-opacity": 0.55,
          "circle-blur": 0.35,
        },
      });

      m.addSource("src-track", {
        type: "geojson", data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "lyr-track", type: "line", source: "src-track",
        paint: { "line-color": "#4A93FF", "line-width": 1.4,
                 "line-dasharray": [2, 2], "line-opacity": 0.8 },
      });

      m.on("click", "lyr-events-fill", (ev) => {
        const f = ev.features?.[0];
        if (!f) return;
        const p: any = f.properties ?? {};
        new maplibregl.Popup({ closeButton: false, offset: 10 })
          .setLngLat(ev.lngLat)
          .setHTML(
            `<div style="letter-spacing:.14em;font-size:9px;color:#5A6490;text-transform:uppercase">region ${p.label ?? ""}</div>
             <div style="margin-top:6px;color:#F4F6FF">${p.class_label ?? p.class ?? "anomaly"}</div>
             <div style="margin-top:4px;color:#8A93B8">${Number(p.area_km2 ?? 0).toFixed(3)} km² · confidence ${Number(p.class_confidence ?? 0).toFixed(2)}</div>
             <div style="margin-top:4px;color:#5A6490">mean RX ${Number(p.mean_rx ?? 0).toFixed(0)}</div>`)
          .addTo(m);
      });
      m.on("mouseenter", "lyr-events-fill", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "lyr-events-fill", () => { m.getCanvas().style.cursor = ""; });

      setReady(true);
    });

    // In a flex/grid layout the container can still be zero-height on the tick
    // MapLibre initialises. That leaves the canvas sized to nothing AND makes
    // the initial fitBounds compute a meaningless zoom, so the imagery ends up
    // off-screen. Resize on every box change, and re-fit the first time the
    // container actually has area.
    let fitted = false;
    const ro = new ResizeObserver((entries) => {
      m.resize();
      const box = entries[0]?.contentRect;
      if (!fitted && box && box.width > 40 && box.height > 40) {
        fitted = true;
        m.fitBounds([[w, s], [e, n]] as LngLatBoundsLike,
                    { padding: 28, duration: 0 });
      }
    });
    ro.observe(holder.current);

    map.current = m;
    return () => { ro.disconnect(); m.remove(); map.current = null; };
    // Bounds are fixed for the AOI; re-initialising on every prop change would
    // reset the user's pan and zoom mid-inspection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* --------------------------------------------------------- raster switch */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (["rgb", "anomaly", "ndci", "turbidity"] as RasterKey[]).forEach((k) => {
      if (m.getLayer(`lyr-${k}`)) {
        m.setPaintProperty(`lyr-${k}`, "raster-opacity",
          k === raster ? rasterOpacity : 0);
      }
    });
  }, [raster, rasterOpacity, ready]);

  /* ------------------------------------------------------- vector toggles */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    if (m.getLayer("lyr-events-fill")) {
      m.setPaintProperty("lyr-events-fill", "fill-opacity", showEvents ? 0.16 : 0);
      m.setPaintProperty("lyr-events-line", "line-opacity", showEvents ? 0.95 : 0);
    }
    if (m.getLayer("lyr-water-line")) {
      m.setPaintProperty("lyr-water-line", "line-opacity", showWater ? 0.35 : 0);
    }
  }, [showEvents, showWater, ready]);

  /* -------------------------------------------------------------- forecast */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const psrc = m.getSource("src-particles") as maplibregl.GeoJSONSource | undefined;
    const tsrc = m.getSource("src-track") as maplibregl.GeoJSONSource | undefined;
    if (!psrc || !tsrc) return;

    const step = forecast[forecastIndex];
    psrc.setData({
      type: "FeatureCollection",
      features: (step?.particles ?? []).map((c) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: c },
        properties: { beached: (step?.beached_fraction ?? 0) > 0.5 },
      })),
    } as any);

    tsrc.setData({
      type: "FeatureCollection",
      features: showTrack && forecast.length > 1 ? [{
        type: "Feature",
        geometry: { type: "LineString", coordinates: forecast.map((s) => s.centroid) },
        properties: {},
      }] : [],
    } as any);
  }, [forecast, forecastIndex, showTrack, ready]);

  /* ------------------------------------------------------- DOM markers */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    markers.current.forEach((x) => x.remove());
    markers.current = [];

    exposures.forEach((e) => {
      const el = document.createElement("div");
      const strong = e.exposure_score >= 0.4;
      el.style.cssText = "cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:3px";
      el.innerHTML = `
        <div style="width:13px;height:13px;transform:rotate(45deg);
             border:1.6px solid ${strong ? "#FF7A45" : "#8A93B8"};
             background:${strong ? "rgba(255,122,69,.28)" : "rgba(138,147,184,.18)"};
             box-shadow:0 0 12px -2px ${strong ? "#FF7A45" : "transparent"}"></div>
        <div style="font-family:var(--font-mono);font-size:8.5px;letter-spacing:.12em;
             color:${strong ? "#FF7A45" : "#8A93B8"};white-space:nowrap;text-shadow:0 0 6px #070A16">
          ${e.asset.id}
        </div>`;
      const mk = new maplibregl.Marker({ element: el })
        .setLngLat([e.asset.lon, e.asset.lat])
        .setPopup(new maplibregl.Popup({ closeButton: false, offset: 14 }).setHTML(
          `<div style="letter-spacing:.14em;font-size:9px;color:#5A6490;text-transform:uppercase">${e.asset.type_label}</div>
           <div style="margin-top:6px;color:#F4F6FF">${e.asset.name}</div>
           <div style="margin-top:6px;color:#8A93B8">${e.distance_km.toFixed(2)} km ${e.direction} · exposure ${e.exposure_score.toFixed(3)}</div>
           <div style="margin-top:3px;color:${e.eta_hours !== null ? "#FF7A45" : "#5A6490"}">
             ${e.eta_hours !== null ? `drift contact +${e.eta_hours}h` : "no modelled contact"}</div>`))
        .addTo(m);
      markers.current.push(mk);
    });

    samples.forEach((s) => {
      const el = document.createElement("div");
      el.style.cssText = "cursor:pointer;display:flex;align-items:center;justify-content:center";
      el.innerHTML = `
        <div style="width:19px;height:19px;border:1.4px solid #3FD1A0;border-radius:50%;
             background:rgba(63,209,160,.16);display:flex;align-items:center;justify-content:center;
             font-family:var(--font-mono);font-size:8.5px;color:#3FD1A0;letter-spacing:.02em">
          ${s.id.replace("S", "")}
        </div>`;
      const mk = new maplibregl.Marker({ element: el })
        .setLngLat([s.lon, s.lat])
        .setPopup(new maplibregl.Popup({ closeButton: false, offset: 14 }).setHTML(
          `<div style="letter-spacing:.14em;font-size:9px;color:#5A6490;text-transform:uppercase">${s.id} · ${s.role.replace(/_/g, " ")}</div>
           <div style="margin-top:6px;color:#C9D0EE;max-width:260px;line-height:1.5">${s.rationale}</div>
           <div style="margin-top:6px;color:#5A6490">${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}</div>`))
        .addTo(m);
      markers.current.push(mk);
    });
  }, [exposures, samples, ready]);

  /* ----------------------------------------------------------------- focus */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !focus) return;
    m.easeTo({ center: focus, zoom: Math.max(m.getZoom(), 12.4), duration: 900 });
  }, [focus, ready]);

  /* -------------------------------------------------------------- picking */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const h = (ev: maplibregl.MapMouseEvent) => {
      if (pickMode && onPickCoord) onPickCoord(ev.lngLat.lng, ev.lngLat.lat);
    };
    m.on("click", h);
    m.getCanvas().style.cursor = pickMode ? "crosshair" : "";
    return () => { m.off("click", h); };
  }, [pickMode, onPickCoord, ready]);

  return (
    <div className={`relative ${className}`} style={{ minHeight: 320 }}>
      {/* Positioning is set inline, not via a utility class. MapLibre's own
          stylesheet declares `.maplibregl-map { position: relative }` and is
          injected after Tailwind's utilities, so a `.absolute` class loses and
          the container collapses to zero height. */}
      <div ref={holder} style={{ position: "absolute", inset: 0 }} />
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="hud-label">initialising ocean view</div>
        </div>
      )}
    </div>
  );
}
