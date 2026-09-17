"use client";

/**
 * The hero object: an interactive dark-ocean view of the detected event.
 *
 * Two rendering surfaces are stacked deliberately:
 *
 *   MapLibre  - georeferenced rasters, event polygons, DOM markers. Everything
 *               that must be spatially exact and clickable.
 *   Canvas    - the animated layer: wind streamlines, drift particle trails and
 *               the event glow. These are re-projected from lon/lat on every
 *               map frame, so they stay locked to the ground while panning and
 *               zooming, but they never touch MapLibre's style diffing, which
 *               keeps a 60 fps animation from thrashing the GL layer tree.
 *
 * Basemap: a plain dark canvas plus our own raster overlays. No external tile
 * provider is used, which keeps the demo working offline and avoids sending the
 * AOI to a third party.
 */

import maplibregl, { Map as MLMap, LngLatBoundsLike } from "maplibre-gl";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

import { CLASS_COLOR, ExposureRecord, ForecastStep, SamplePoint, layerUrl } from "@/lib/api";
import { lerpLngLat, prefersReducedMotion } from "@/lib/motion";

export type RasterKey = "rgb" | "anomaly" | "ndci" | "turbidity";

export interface WindVector {
  /** Eastward and northward surface-drift components, m/s. */
  u: number;
  v: number;
}

export interface OceanMapProps {
  bounds: number[];                     // [w, s, e, n]
  raster: RasterKey;
  rasterOpacity?: number;
  showEvents?: boolean;
  showWater?: boolean;
  exposures?: ExposureRecord[];
  samples?: SamplePoint[];
  forecast?: ForecastStep[];
  /** Fractional position along the forecast horizons, e.g. 1.5 = halfway 6h→12h. */
  forecastT?: number;
  showTrack?: boolean;
  showParticles?: boolean;
  /** Animated streamlines showing the drift field that moves the plume. */
  drift?: WindVector | null;
  showFlow?: boolean;
  glowAt?: [number, number] | null;
  glowRadiusM?: number;
  focus?: [number, number] | null;
  focusZoom?: number;
  onPickCoord?: (lon: number, lat: number) => void;
  pickMode?: boolean;
  onHover?: (lon: number, lat: number) => void;
  className?: string;
  interactive?: boolean;
  compact?: boolean;
}

const EMPTY_STYLE: any = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#070A16" } }],
};

const RASTER_KEYS: RasterKey[] = ["rgb", "anomaly", "ndci", "turbidity"];

/* --------------------------------------------------------------- streamlines */

interface Streamer { lon: number; lat: number; age: number; life: number; }

/** Ground metres covered by one screen pixel at the map's current view. */
function metresPerPixel(m: MLMap): number {
  const c = m.getCenter();
  const a = m.project([c.lng, c.lat]);
  const b = m.project([c.lng + 0.01, c.lat]);
  const px = Math.max(1e-6, Math.abs(b.x - a.x));
  return (0.01 * 111320 * Math.cos((c.lat * Math.PI) / 180)) / px;
}

export default function OceanMap({
  bounds, raster, rasterOpacity = 1, showEvents = true, showWater = false,
  exposures = [], samples = [], forecast = [], forecastT = 0,
  showTrack = true, showParticles = true, drift = null, showFlow = true,
  glowAt = null, glowRadiusM = 700,
  focus = null, focusZoom = 12.4, onPickCoord, pickMode = false, onHover,
  className = "", interactive = true, compact = false,
}: OceanMapProps) {
  const holder = useRef<HTMLDivElement | null>(null);
  const overlay = useRef<HTMLCanvasElement | null>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const [ready, setReady] = useState(false);
  const [hoverLL, setHoverLL] = useState<[number, number] | null>(null);
  const [zoomLevel, setZoomLevel] = useState<number>(0);

  // Animated state lives in refs so the render loop never triggers React work.
  const streamers = useRef<Streamer[]>([]);
  const driftRef = useRef<WindVector | null>(drift);
  const partRef = useRef<[number, number][]>([]);
  const trailRef = useRef<[number, number][][]>([]);
  const glowRef = useRef<{ at: [number, number] | null; r: number }>(
    { at: glowAt, r: glowRadiusM });
  const flagsRef = useRef({ showFlow, showParticles, showTrack });
  const trackRef = useRef<[number, number][]>([]);
  const raf = useRef<number | null>(null);
  const phase = useRef(0);

  useEffect(() => { driftRef.current = drift; }, [drift]);
  useEffect(() => { glowRef.current = { at: glowAt, r: glowRadiusM }; },
            [glowAt, glowRadiusM]);
  useEffect(() => { flagsRef.current = { showFlow, showParticles, showTrack }; },
            [showFlow, showParticles, showTrack]);

  /* ---------------------------------------------- interpolated particle set */
  useEffect(() => {
    if (!forecast.length) { partRef.current = []; trackRef.current = []; return; }
    trackRef.current = forecast.map((s) => s.centroid as [number, number]);

    const i0 = Math.max(0, Math.min(forecast.length - 1, Math.floor(forecastT)));
    const i1 = Math.min(forecast.length - 1, i0 + 1);
    const frac = forecastT - i0;
    const a = forecast[i0]?.particles ?? [];
    const b = forecast[i1]?.particles ?? [];

    // Particle order is stable across horizons (the advection keeps the array
    // index per particle), so index-wise interpolation follows each particle
    // rather than morphing the cloud as a blob.
    const n = Math.min(a.length, b.length);
    const out: [number, number][] = [];
    for (let i = 0; i < n; i++) {
      out.push(lerpLngLat(a[i] as [number, number], b[i] as [number, number], frac));
    }
    if (!n && a.length) out.push(...(a as [number, number][]));
    partRef.current = out;
  }, [forecast, forecastT]);

  /* ------------------------------------------------------------ init once */
  useEffect(() => {
    if (!holder.current || map.current) return;
    const [w, s, e, n] = bounds;
    const m = new maplibregl.Map({
      container: holder.current,
      style: EMPTY_STYLE,
      bounds: [[w, s], [e, n]] as LngLatBoundsLike,
      fitBoundsOptions: { padding: compact ? 12 : 30 },
      attributionControl: false,
      interactive,
      maxZoom: 16,
      minZoom: 7,
      dragRotate: false,
      pitchWithRotate: false,
      fadeDuration: 180,
    });
    m.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution:
        "Tanager © Planet Labs PBC (CC-BY-4.0) · Sentinel © ESA/Copernicus · ERA5 © ECMWF",
    }), "bottom-right");
    if (interactive) {
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      m.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: "metric" }),
                   "bottom-left");
    }

    m.on("load", () => {
      const rb: [[number, number], [number, number], [number, number], [number, number]] =
        [[w, n], [e, n], [e, s], [w, s]];

      RASTER_KEYS.forEach((k) => {
        m.addSource(`src-${k}`, { type: "image", url: layerUrl(k), coordinates: rb });
        m.addLayer({
          id: `lyr-${k}`, type: "raster", source: `src-${k}`,
          // MapLibre honours "<prop>-transition" in the style spec, but its
          // TS types omit those keys, hence the cast.
          paint: {
            "raster-opacity": 0,
            "raster-opacity-transition": { duration: 450, delay: 0 },
            "raster-fade-duration": 200,
            "raster-resampling": "linear",
          } as any,
        });
      });

      m.addSource("src-water", { type: "geojson", data: layerUrl("water") });
      m.addLayer({
        id: "lyr-water-line", type: "line", source: "src-water",
        paint: {
          "line-color": "#3186FF", "line-width": 0.9, "line-opacity": 0,
          "line-opacity-transition": { duration: 350, delay: 0 },
        } as any,
      });

      const classMatch = (fallback: string) => ([
        "match", ["get", "class"],
        "SEDIMENT_LIKE", CLASS_COLOR.SEDIMENT_LIKE,
        "BLOOM_LIKE", CLASS_COLOR.BLOOM_LIKE,
        "CYANO_LIKE", CLASS_COLOR.CYANO_LIKE,
        "CDOM_LIKE", CLASS_COLOR.CDOM_LIKE,
        "BOTTOM_INFLUENCED", CLASS_COLOR.BOTTOM_INFLUENCED,
        "SURFACE_FILM_LIKE", CLASS_COLOR.SURFACE_FILM_LIKE,
        "UNKNOWN_ANOMALY", CLASS_COLOR.UNKNOWN_ANOMALY,
        fallback] as any);

      m.addSource("src-events", { type: "geojson", data: layerUrl("events") });
      m.addLayer({
        id: "lyr-events-fill", type: "fill", source: "src-events",
        paint: {
          "fill-color": classMatch("#8A93B8"),
          "fill-opacity": 0,
          "fill-opacity-transition": { duration: 400, delay: 0 },
        } as any,
      });
      m.addLayer({
        id: "lyr-events-glow", type: "line", source: "src-events",
        paint: {
          "line-color": classMatch("#8A93B8"),
          "line-width": ["case", ["==", ["get", "is_primary"], true], 9, 4],
          "line-blur": 7, "line-opacity": 0,
          "line-opacity-transition": { duration: 400, delay: 0 },
        } as any,
      });
      m.addLayer({
        id: "lyr-events-line", type: "line", source: "src-events",
        paint: {
          "line-color": classMatch("#8A93B8"),
          "line-width": ["case", ["==", ["get", "is_primary"], true], 2.2, 1.0],
          "line-opacity": 0,
          "line-opacity-transition": { duration: 400, delay: 0 },
        } as any,
      });

      m.on("click", "lyr-events-fill", (ev) => {
        const f = ev.features?.[0];
        if (!f) return;
        const p: any = f.properties ?? {};
        new maplibregl.Popup({ closeButton: false, offset: 10, maxWidth: "280px" })
          .setLngLat(ev.lngLat)
          .setHTML(
            `<div style="letter-spacing:.14em;font-size:9px;color:#5A6490;text-transform:uppercase">region ${p.label ?? ""}${p.is_primary === true || p.is_primary === "true" ? " · primary" : ""}</div>
             <div style="margin-top:6px;color:#F4F6FF">${p.class_label ?? p.class ?? "anomaly"}</div>
             <div style="margin-top:4px;color:#8A93B8">${Number(p.area_km2 ?? 0).toFixed(3)} km² · hypothesis confidence ${Number(p.class_confidence ?? 0).toFixed(2)}</div>
             <div style="margin-top:4px;color:#5A6490">mean RX ${Number(p.mean_rx ?? 0).toFixed(0)} · peak ${Number(p.max_rx ?? 0).toFixed(0)}</div>`)
          .addTo(m);
      });
      m.on("mouseenter", "lyr-events-fill", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "lyr-events-fill", () => { m.getCanvas().style.cursor = ""; });

      setZoomLevel(m.getZoom());
      setReady(true);
    });

    m.on("zoom", () => setZoomLevel(m.getZoom()));
    m.on("mousemove", (ev) => {
      setHoverLL([ev.lngLat.lng, ev.lngLat.lat]);
      onHover?.(ev.lngLat.lng, ev.lngLat.lat);
    });
    m.on("mouseout", () => setHoverLL(null));

    // A flex or grid container can still be zero-height on the tick MapLibre
    // initialises. That leaves the canvas sized to nothing AND makes the first
    // fitBounds compute a meaningless zoom, so the imagery ends up off-screen.
    let fitted = false;
    const ro = new ResizeObserver((entries) => {
      m.resize();
      const box = entries[0]?.contentRect;
      if (!fitted && box && box.width > 40 && box.height > 40) {
        fitted = true;
        m.fitBounds([[w, s], [e, n]] as LngLatBoundsLike,
                    { padding: compact ? 12 : 30, duration: 0 });
      }
      sizeOverlay();
    });
    ro.observe(holder.current);

    map.current = m;
    // Exposed for debugging and for the Judge Mode walkthrough, which needs to
    // drive the camera from outside the React tree.
    if (typeof window !== "undefined") (window as any).__bluebanMap = m;
    return () => { ro.disconnect(); m.remove(); map.current = null; };
    // Bounds are fixed for the AOI; re-initialising on prop change would reset
    // the operator's pan and zoom mid-inspection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ------------------------------------------------------ overlay sizing */
  const sizeOverlay = useCallback(() => {
    const c = overlay.current, h = holder.current;
    if (!c || !h) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const r = h.getBoundingClientRect();
    c.width = Math.max(1, Math.round(r.width * dpr));
    c.height = Math.max(1, Math.round(r.height * dpr));
    c.style.width = `${r.width}px`;
    c.style.height = `${r.height}px`;
  }, []);

  /* ------------------------------------------------- the animation loop */
  useEffect(() => {
    if (!ready) return;
    const m = map.current;
    const c = overlay.current;
    if (!m || !c) return;
    sizeOverlay();
    const reduced = prefersReducedMotion();

    const seedStreamers = (n: number) => {
      const b = m.getBounds();
      streamers.current = Array.from({ length: n }, () => ({
        lon: b.getWest() + Math.random() * (b.getEast() - b.getWest()),
        lat: b.getSouth() + Math.random() * (b.getNorth() - b.getSouth()),
        age: Math.random() * 100,
        life: 60 + Math.random() * 90,
      }));
    };
    seedStreamers(compact ? 90 : 220);

    let prev = performance.now();

    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - prev) / 1000);
      prev = now;
      phase.current += dt;

      const ctx = c.getContext("2d");
      if (!ctx) { raf.current = requestAnimationFrame(frame); return; }
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, c.width / dpr, c.height / dpr);

      const project = (lon: number, lat: number) => {
        const p = m.project([lon, lat]);
        return [p.x, p.y] as [number, number];
      };

      /* ---------------------------------------------- event glow (halo) */
      const g = glowRef.current;
      if (g.at) {
        const [gx, gy] = project(g.at[0], g.at[1]);
        // Convert the event radius into screen pixels at the current zoom so
        // the halo tracks the real footprint rather than floating at a fixed
        // size.
        const edge = m.project([
          g.at[0] + g.r / (111320 * Math.cos((g.at[1] * Math.PI) / 180)),
          g.at[1],
        ]);
        // A 1 km2 plume is only a few pixels across at AOI zoom, so the halo
        // has a screen-space floor: without it the hero object is invisible at
        // the very zoom the operator opens on.
        const rpx = Math.max(26, Math.abs(edge.x - gx));
        const truePx = Math.abs(edge.x - gx);
        const pulse = reduced ? 0.5 : 0.5 + 0.5 * Math.sin(phase.current * 1.5);
        const rad = ctx.createRadialGradient(gx, gy, 0, gx, gy, rpx * 2.1);
        rad.addColorStop(0, `rgba(255,122,69,${0.16 + pulse * 0.1})`);
        rad.addColorStop(0.45, "rgba(255,122,69,0.055)");
        rad.addColorStop(1, "rgba(255,122,69,0)");
        ctx.fillStyle = rad;
        ctx.beginPath();
        ctx.arc(gx, gy, rpx * 2.1, 0, Math.PI * 2);
        ctx.fill();

        if (!reduced) {
          // Expanding ring: a detection marker, the way a radar contact reads.
          const t = (phase.current * 0.42) % 1;
          ctx.strokeStyle = `rgba(255,122,69,${(1 - t) * 0.5})`;
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.arc(gx, gy, rpx * (0.7 + t * 1.5), 0, Math.PI * 2);
          ctx.stroke();
        }

        // Reticle plus a leader line when the polygon itself is too small to
        // read, so the operator can always find the detection.
        if (truePx < 16) {
          ctx.strokeStyle = "rgba(255,122,69,0.9)";
          ctx.lineWidth = 1.1;
          const k = 9, g2 = 4;
          ctx.beginPath();
          ctx.moveTo(gx - k, gy); ctx.lineTo(gx - g2, gy);
          ctx.moveTo(gx + g2, gy); ctx.lineTo(gx + k, gy);
          ctx.moveTo(gx, gy - k); ctx.lineTo(gx, gy - g2);
          ctx.moveTo(gx, gy + g2); ctx.lineTo(gx, gy + k);
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(gx, gy, 13, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(255,122,69,0.55)";
          ctx.stroke();
        }
      }

      /* ------------------------------------------------ drift streamlines */
      const d = driftRef.current;
      if (flagsRef.current.showFlow && d && (Math.abs(d.u) > 1e-4 || Math.abs(d.v) > 1e-4)) {
        const mLat = 110574;
        const speed = Math.hypot(d.u, d.v);
        ctx.lineCap = "round";

        // The real surface drift here is a few centimetres per second, which at
        // this zoom is a fraction of a pixel per second: animating it truthfully
        // would look frozen. The streamers are therefore normalised to move at a
        // fixed SCREEN speed, so they carry direction and coherence rather than
        // magnitude. The rose below prints the true speed, and the label says
        // the motion is exaggerated, so nothing is implied that is not measured.
        const mpp = metresPerPixel(m);
        const targetPxPerSec = 42;
        const gain = reduced ? 0 : (targetPxPerSec * mpp) / Math.max(speed, 1e-6);

        streamers.current.forEach((p) => {
          const [x0, y0] = project(p.lon, p.lat);
          const mLon = 111320 * Math.cos((p.lat * Math.PI) / 180);
          p.lon += (d.u * dt * gain) / mLon;
          p.lat += (d.v * dt * gain) / mLat;
          p.age += dt * 12;
          const [x1, y1] = project(p.lon, p.lat);

          const fade = Math.sin((p.age / p.life) * Math.PI);
          const alpha = Math.max(0, Math.min(0.5, fade * 0.42));
          ctx.strokeStyle = `rgba(74,147,255,${alpha})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x0, y0);
          ctx.lineTo(x1, y1);
          ctx.stroke();

          if (p.age > p.life) {
            const b = m.getBounds();
            p.lon = b.getWest() + Math.random() * (b.getEast() - b.getWest());
            p.lat = b.getSouth() + Math.random() * (b.getNorth() - b.getSouth());
            p.age = 0;
            p.life = 60 + Math.random() * 90;
          }
        });

        // Direction rose, so the field is readable even when static.
        const w = c.width / dpr, h = c.height / dpr;
        const cx = w - 54, cy = h - (compact ? 40 : 64);
        const ang = Math.atan2(d.u, d.v);
        ctx.save();
        ctx.translate(cx, cy);
        ctx.strokeStyle = "rgba(36,48,86,0.9)";
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(0, 0, 17, 0, Math.PI * 2); ctx.stroke();
        ctx.rotate(ang);
        ctx.strokeStyle = "#4A93FF";
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(0, 12); ctx.lineTo(0, -13);
        ctx.moveTo(-4.5, -7.5); ctx.lineTo(0, -13); ctx.lineTo(4.5, -7.5);
        ctx.stroke();
        ctx.restore();
        ctx.fillStyle = "#8A93B8";
        ctx.font = "9px ui-monospace, monospace";
        ctx.textAlign = "center";
        ctx.fillText(`${speed.toFixed(3)} m/s`, cx, cy + 30);
        ctx.fillStyle = "#4A5478";
        ctx.font = "7.5px ui-monospace, monospace";
        ctx.fillText("DRIFT · ANIM x", cx, cy + 40);
      }

      /* ------------------------------------------------ forecast centroid track */
      if (flagsRef.current.showTrack && trackRef.current.length > 1) {
        ctx.setLineDash([3, 4]);
        ctx.strokeStyle = "rgba(74,147,255,0.75)";
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        trackRef.current.forEach((ll, i) => {
          const [x, y] = project(ll[0], ll[1]);
          i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.setLineDash([]);
      }

      /* ------------------------------------------------ drift particles */
      if (flagsRef.current.showParticles && partRef.current.length) {
        const pts = partRef.current;
        // Keep a short history so moving particles leave a comet trail.
        trailRef.current.push(pts);
        if (trailRef.current.length > (reduced ? 1 : 5)) trailRef.current.shift();

        trailRef.current.forEach((snap, si) => {
          const a = ((si + 1) / trailRef.current.length) * 0.5;
          ctx.fillStyle = `rgba(74,147,255,${a * 0.55})`;
          const r = 1.1 + (si / trailRef.current.length) * 1.4;
          snap.forEach((ll) => {
            const [x, y] = project(ll[0], ll[1]);
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();
          });
        });
      }

      raf.current = requestAnimationFrame(frame);
    };

    raf.current = requestAnimationFrame(frame);
    const onResize = () => sizeOverlay();
    window.addEventListener("resize", onResize);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      window.removeEventListener("resize", onResize);
    };
  }, [ready, compact, sizeOverlay]);

  /* --------------------------------------------------------- raster switch */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    RASTER_KEYS.forEach((k) => {
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
      m.setPaintProperty("lyr-events-fill", "fill-opacity", showEvents ? 0.17 : 0);
      m.setPaintProperty("lyr-events-line", "line-opacity", showEvents ? 0.95 : 0);
      m.setPaintProperty("lyr-events-glow", "line-opacity", showEvents ? 0.3 : 0);
    }
    if (m.getLayer("lyr-water-line")) {
      m.setPaintProperty("lyr-water-line", "line-opacity", showWater ? 0.4 : 0);
    }
  }, [showEvents, showWater, ready]);

  /* ------------------------------------------------------- DOM markers */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    markers.current.forEach((x) => x.remove());
    markers.current = [];

    exposures.forEach((e, i) => {
      const el = document.createElement("div");
      const strong = e.exposure_score >= 0.4;
      const col = strong ? "#FF7A45" : "#8A93B8";
      el.style.cssText =
        "cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:3px;" +
        `animation:asset-in .45s cubic-bezier(.22,.61,.36,1) ${i * 70}ms both`;
      el.innerHTML = `
        <div style="position:relative;width:15px;height:15px;display:flex;align-items:center;justify-content:center">
          ${strong ? `<span style="position:absolute;inset:-5px;border:1px solid ${col};
                       transform:rotate(45deg);opacity:.5" class="pulse-ring"></span>` : ""}
          <span style="width:13px;height:13px;transform:rotate(45deg);border:1.6px solid ${col};
                background:${strong ? "rgba(255,122,69,.3)" : "rgba(138,147,184,.18)"};
                box-shadow:0 0 12px -2px ${strong ? col : "transparent"};
                transition:transform .18s ease"></span>
        </div>
        <div style="font-family:var(--font-mono);font-size:8.5px;letter-spacing:.12em;
             color:${col};white-space:nowrap;text-shadow:0 0 6px #070A16">${e.asset.id}</div>`;
      el.addEventListener("mouseenter", () => {
        const sq = el.querySelector("span:last-of-type") as HTMLElement | null;
        if (sq) sq.style.transform = "rotate(45deg) scale(1.28)";
      });
      el.addEventListener("mouseleave", () => {
        const sq = el.querySelector("span:last-of-type") as HTMLElement | null;
        if (sq) sq.style.transform = "rotate(45deg) scale(1)";
      });
      markers.current.push(
        new maplibregl.Marker({ element: el })
          .setLngLat([e.asset.lon, e.asset.lat])
          .setPopup(new maplibregl.Popup({ closeButton: false, offset: 14, maxWidth: "280px" })
            .setHTML(
              `<div style="letter-spacing:.14em;font-size:9px;color:#5A6490;text-transform:uppercase">${e.asset.type_label}</div>
               <div style="margin-top:6px;color:#F4F6FF">${e.asset.name}</div>
               <div style="margin-top:6px;color:#8A93B8">${e.distance_km.toFixed(2)} km ${e.direction} · exposure ${e.exposure_score.toFixed(3)}</div>
               <div style="margin-top:3px;color:${e.eta_hours !== null ? "#FF7A45" : "#5A6490"}">
                 ${e.eta_hours !== null ? `drift contact +${e.eta_hours} h` : "no modelled drift contact"}</div>`))
          .addTo(m));
    });

    samples.forEach((s, i) => {
      const el = document.createElement("div");
      el.style.cssText =
        "cursor:pointer;display:flex;align-items:center;justify-content:center;" +
        `animation:asset-in .45s cubic-bezier(.22,.61,.36,1) ${180 + i * 70}ms both`;
      el.innerHTML = `
        <div style="width:19px;height:19px;border:1.4px solid #3FD1A0;border-radius:50%;
             background:rgba(63,209,160,.18);display:flex;align-items:center;justify-content:center;
             font-family:var(--font-mono);font-size:8.5px;color:#3FD1A0;
             transition:transform .18s ease,box-shadow .18s ease">${s.id.replace("S", "")}</div>`;
      const inner = el.firstElementChild as HTMLElement;
      el.addEventListener("mouseenter", () => {
        inner.style.transform = "scale(1.25)";
        inner.style.boxShadow = "0 0 14px -2px #3FD1A0";
      });
      el.addEventListener("mouseleave", () => {
        inner.style.transform = "scale(1)";
        inner.style.boxShadow = "none";
      });
      markers.current.push(
        new maplibregl.Marker({ element: el })
          .setLngLat([s.lon, s.lat])
          .setPopup(new maplibregl.Popup({ closeButton: false, offset: 14, maxWidth: "300px" })
            .setHTML(
              `<div style="letter-spacing:.14em;font-size:9px;color:#5A6490;text-transform:uppercase">${s.id} · ${s.role.replace(/_/g, " ")}</div>
               <div style="margin-top:6px;color:#C9D0EE;line-height:1.55">${s.rationale}</div>
               <div style="margin-top:6px;color:#5A6490">${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}</div>`))
          .addTo(m));
    });
  }, [exposures, samples, ready]);

  /* ----------------------------------------------------------------- focus */
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !focus) return;
    m.easeTo({ center: focus, zoom: Math.max(m.getZoom(), focusZoom),
               duration: 950, easing: (t) => 1 - Math.pow(1 - t, 3) });
  }, [focus, focusZoom, ready]);

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

  const reset = useCallback(() => {
    const m = map.current;
    if (!m) return;
    const [w, s, e, n] = bounds;
    m.fitBounds([[w, s], [e, n]] as LngLatBoundsLike,
                { padding: compact ? 12 : 30, duration: 800 });
  }, [bounds, compact]);

  return (
    <div className={`relative ${className}`} style={{ minHeight: 300 }}>
      {/* Positioning is set inline, not via a utility class. MapLibre's own
          stylesheet declares `.maplibregl-map { position: relative }` and is
          injected after Tailwind's utilities, so an `.absolute` class loses and
          the container collapses to zero height. */}
      <div ref={holder} style={{ position: "absolute", inset: 0 }} />
      <canvas ref={overlay}
              style={{ position: "absolute", inset: 0, pointerEvents: "none" }} />

      {!ready && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3
                        pointer-events-none">
          <div className="relative w-32 h-[2px] bg-edge overflow-hidden">
            <div className="sweep absolute inset-y-0 w-1/3"
                 style={{ background: "linear-gradient(90deg,transparent,#3186FF,transparent)" }} />
          </div>
          <div className="hud-label">initialising ocean view</div>
        </div>
      )}

      {/* live cursor readout */}
      {ready && hoverLL && !compact && (
        <div className="absolute bottom-2 right-[124px] z-10 pointer-events-none
                        bg-void/88 backdrop-blur-sm chamfer-sm px-2.5 py-1.5 border border-edge">
          <span className="hud-value text-[10px] text-muted">
            {hoverLL[1].toFixed(5)}, {hoverLL[0].toFixed(5)}
          </span>
          <span className="hud-label ml-2.5">z{zoomLevel.toFixed(1)}</span>
        </div>
      )}

      {ready && interactive && !compact && (
        <button onClick={reset}
                className="absolute top-[86px] right-2.5 z-10 chamfer-sm hud-label px-2 py-1.5
                           bg-void/88 backdrop-blur-sm border border-edge
                           hover:border-beam hover:text-beam transition-colors">
          reset view
        </button>
      )}
    </div>
  );
}
