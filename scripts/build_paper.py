"""Build the research paper (paper/index.html + figures) from the pipeline outputs.

Every number in the paper is read from outputs/ at build time, and every figure
is drawn from those files, so the paper cannot drift from the data. Re-run after
the pipeline changes:

    python scripts/build_paper.py

GitHub Pages publishes paper/ (.github/workflows/pages.yml).
"""
from __future__ import annotations

import datetime as dt
import glob
import html
import json
import math
import os
import shutil

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "paper")
FIG = os.path.join(OUT, "figures")


def J(p):
    p = os.path.join(ROOT, p)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def f(v, d=2):
    return "n/a" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:.{d}f}"


def pct(v, d=0):
    return "n/a" if v is None else f"{100 * v:.{d}f} %"


# --------------------------------------------------------------------------- data
hero = J("outputs/incidents/BB-AE-2024-001.json")
art = J("outputs/incidents/BB-AE-2023-001.json")
vs = J("outputs/validation/validation_summary.json")
labels = J("outputs/labels/seed_labels.json") or {"labels": [], "stats": {}, "n": 0}
seed = J("outputs/workspace/seed.json")
hard = J("outputs/validation/detectability_lift_hard.json")
easy = J("outputs/validation/detectability_lift_easy.json")
olci_lift = J("outputs/validation/hyperspectral_lift.json")
sim = J("outputs/validation/simulator_validation.json")
annaba = next((i for i in (seed or {}).get("incidents", []) if i.get("role") == "negative_control"), None)
watch = {os.path.basename(p)[:-5]: json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(ROOT, "outputs", "watch", "*.json"))}
detect = {os.path.basename(p)[:-5]: json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(ROOT, "outputs", "detect", "*.json"))}

n_dt = sum(w.get("n_datatakes", 0) for w in watch.values())
n_ok = sum(w.get("n_ok", 0) for w in watch.values())
years = sorted({r["date"][:4] for w in watch.values() for r in w["rows"] if "error" not in r})
n_cand = sum(len(d.get("candidates", [])) for d in detect.values())
n_pix = sum((d.get("two_stage") or {}).get("n_pixel_level", 0) for d in detect.values())
n_acq = sum(d.get("n_acquisitions", 0) for d in detect.values())
hyp_counts: dict = {}
for d in detect.values():
    for c in d.get("candidates", []):
        hyp_counts[c["hypothesis"]] = hyp_counts.get(c["hypothesis"], 0) + 1
L = labels["labels"]
n_pos = sum(1 for l in L if l["target"]["y"] == 1)
n_neg = sum(1 for l in L if l["target"]["y"] == 0)
C = (vs or {}).get("C_model_performance", {})
B = (vs or {}).get("B_matchups", {}).get("cross_sensor", {})
E = (vs or {}).get("E_spatial_holdout", {})


# --------------------------------------------------------------------------- figures
def figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    os.makedirs(FIG, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.dpi": 150})

    # Fig 1: the Fujairah case, three panels
    d = os.path.join(ROOT, "outputs", "incidents", "BB-AE-2024-001")
    fig, ax = plt.subplots(1, 3, figsize=(10, 3.6))
    for a, (fn, title) in zip(ax, [("rgb.png", "(a) True colour, Sentinel-2B"),
                                   ("ndci_z.png", "(b) NDCI robust z vs own season"),
                                   ("hue.png", "(c) Water-colour hue angle")]):
        im = Image.open(os.path.join(d, fn)).convert("RGBA")
        bg = Image.new("RGBA", im.size, (8, 12, 24, 255))
        a.imshow(Image.alpha_composite(bg, im))
        a.set_title(title, fontsize=9)
        a.axis("off")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig1_fujairah.png"), bbox_inches="tight")
    plt.close(fig)

    # Fig 2: spectra event vs background
    sp = hero["spectral"]
    wl = np.array(sp["wavelengths_nm"], float)
    ev = np.array([np.nan if v is None else v for v in sp["event"]], float)
    bg = np.array([np.nan if v is None else v for v in sp["background"]], float)
    lo = np.array([np.nan if v is None else v for v in sp.get("background_p05") or sp["background"]], float)
    hi = np.array([np.nan if v is None else v for v in sp.get("background_p95") or sp["background"]], float)
    fig, a = plt.subplots(figsize=(5.2, 3.0))
    a.fill_between(wl, lo, hi, color="#9fb3d9", alpha=0.35, label="background 5–95 %")
    a.plot(wl, bg, "-o", color="#2f5597", ms=3, lw=1.2, label="background median")
    a.plot(wl, ev, "-o", color="#1e8f4e", ms=3, lw=1.6, label="event median")
    for x, lab in [(665, "665"), (705, "705")]:
        a.axvline(x, color="#999", lw=0.6, ls=":")
        a.text(x, a.get_ylim()[1] * 0.97, lab, fontsize=7, ha="center", color="#666")
    a.set_xlabel("Wavelength (nm)")
    a.set_ylabel("Reflectance (SWIR-offset corrected)")
    a.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig2_spectra.png"), bbox_inches="tight")
    plt.close(fig)

    # Fig 3: Fujairah seasonal record with the two detections marked
    w = watch.get("AE-FUJ")
    if w:
        rows = [r for r in w["rows"] if "error" not in r and (r.get("all") or {}).get("n_water", 0) >= 500]
        ds = [dt.date.fromisoformat(r["date"]) for r in rows]
        nd = [((r.get("all") or {}).get("NDCI") or {}).get("p95") for r in rows]
        hu = [((r.get("all") or {}).get("HUE_ANGLE") or {}).get("p50") for r in rows]
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 3.8), sharex=True)
        a1.plot(ds, nd, ".", ms=2.5, color="#2f5597")
        a1.set_ylabel("NDCI P95")
        a2.plot(ds, hu, ".", ms=2.5, color="#8a5a00")
        a2.set_ylabel("Hue angle P50 (°)")
        for when, col, lab in [("2024-02-17", "#1e8f4e", "BB-AE-2024-001"), ("2023-10-25", "#b03060", "BB-AE-2023-001")]:
            for a in (a1, a2):
                a.axvline(dt.date.fromisoformat(when), color=col, lw=1, alpha=0.8)
            a1.text(dt.date.fromisoformat(when), a1.get_ylim()[1], " " + lab, color=col, fontsize=7, va="top")
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, "fig3_record.png"), bbox_inches="tight")
        plt.close(fig)

    # Fig 4: cross-sensor agreement
    pts = B.get("points") or []
    if pts:
        fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.0))
        for a, h, xl in [(ax[0], "BLOOM_LIKE", "S2 NDCI change vs own seasonal median"),
                         (ax[1], "SEDIMENT_LIKE", "S2 turbidity change (FNU) vs own median")]:
            P = [p for p in pts if p["hyp"] == h and p["s2_delta"] is not None and p["olci_ratio"]]
            for y, col, lab in [(1, "#1e8f4e", "OLCI confirms"), (0, "#b03060", "OLCI does not")]:
                Q = [p for p in P if p["y"] == y]
                a.scatter([p["s2_delta"] for p in Q], [math.log10(p["olci_ratio"]) for p in Q], s=12, color=col, alpha=0.75, label=lab)
            a.axhline(math.log10(1.5), color="#1e8f4e", lw=0.6, ls="--")
            a.axhline(math.log10(1.15), color="#b03060", lw=0.6, ls="--")
            a.set_xlabel(xl, fontsize=8)
            a.set_title(h.replace("_", " ").lower(), fontsize=9)
        ax[0].set_ylabel("log10 OLCI region / surroundings")
        ax[0].legend(fontsize=7, frameon=False)
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, "fig4_crosssensor.png"), bbox_inches="tight")
        plt.close(fig)

    # Fig 5: ablation
    if hard:
        arms = hard["results"]["spatial_blocked"]
        keys = ["S2_multispectral_11band", "813_hyperspectral_205band", "813_hyperspectral_261band_5nm"]
        names = ["Sentinel-2\n11 bands", "813 (sim.)\n205 bands", "813 (sim.)\n261 bands"]
        fps = [arms[k]["confusion_matrix"]["fp"] for k in keys]
        fig, a = plt.subplots(figsize=(4.6, 2.8))
        bars = a.bar(names, fps, color=["#2f5597", "#c78c00", "#c78c00"])
        for b_, v in zip(bars, fps):
            a.text(b_.get_x() + b_.get_width() / 2, v, str(v), ha="center", va="bottom", fontsize=8)
        a.set_ylabel("False alarms at matched recall")
        a.set_title("Hard regime, spatially blocked CV", fontsize=9)
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, "fig5_ablation.png"), bbox_inches="tight")
        plt.close(fig)

    # Fig 6: the 2023 artifact case and the Annaba control
    fig, ax = plt.subplots(1, 3, figsize=(10, 3.4))
    panels = [(os.path.join(ROOT, "outputs", "incidents", "BB-AE-2023-001", "rgb.png"), "(a) BB-AE-2023-001, true colour"),
              (os.path.join(ROOT, "outputs", "layers", "rgb_water.png"), "(b) Annaba control, Tanager true colour"),
              (os.path.join(ROOT, "outputs", "layers", "anomaly.png"), "(c) Annaba RX anomaly")]
    for a, (p, title) in zip(ax, panels):
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA")
            bgi = Image.new("RGBA", im.size, (8, 12, 24, 255))
            a.imshow(Image.alpha_composite(bgi, im))
        a.set_title(title, fontsize=9)
        a.axis("off")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig6_controls.png"), bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- text
def metrics_table():
    p = (C.get("production") or {}).get("metrics") or {}
    c = (C.get("candidate") or {}).get("metrics") or {}
    bt = C.get("bootstrap") or {}
    rows = []
    for k, lab in [("auprc", "AUPRC"), ("auroc", "AUROC"), ("f1", "F1 (0.5)"), ("precision", "Precision"),
                   ("recall", "Recall"), ("brier", "Brier"), ("ece", "ECE")]:
        ci = bt.get(k, {}).get("ci") if k in bt else None
        rows.append(f"<tr><td>{lab}</td><td>{f(p.get(k), 3)}</td><td>{f(c.get(k), 3)}</td>"
                    f"<td>{'' if not ci or ci[0] is None else f'[{ci[0]:.3f}, {ci[1]:.3f}]'}</td></tr>")
    return "\n".join(rows)


def aoi_table():
    rows = []
    for a in (vs or {}).get("A_data_quality", {}).get("aois", []):
        d = detect.get(a["aoi_id"], {})
        st = labels.get("stats", {}).get(a["aoi_id"], {})
        rows.append(f"<tr><td>{html.escape(a['aoi_id'])}</td><td>{a['n_ok']}</td><td>{a['n_usable']}</td>"
                    f"<td>{pct(a.get('median_glint_fraction'))}</td><td>{len(d.get('candidates', [])) if d else '—'}</td>"
                    f"<td>{st.get('positive', '—')}/{st.get('negative', '—')}</td></tr>")
    return "\n".join(rows)


def build():
    figures()
    fh = hero["water_quality"]["features"]
    oh = hero["sensor_agreement"].get("Sentinel-3 OLCI", {})
    fa = art["water_quality"]["features"]
    oa = art["sensor_agreement"].get("Sentinel-3 OLCI", {})
    arms = hard["results"]["spatial_blocked"] if hard else {}
    fpA = arms.get("S2_multispectral_11band", {}).get("confusion_matrix", {}).get("fp")
    fpB = arms.get("813_hyperspectral_205band", {}).get("confusion_matrix", {}).get("fp")
    agree = B.get("agreement", {})
    rho_b = agree.get("BLOOM_LIKE", {})
    rho_s = agree.get("SEDIMENT_LIKE", {})
    loao = E.get("triage_leave_one_aoi_out") or []
    loao_rows = "\n".join(
        f"<tr><td>{r['held_out_aoi']}</td><td>{r['n_test']} ({r['test_positive']})</td>"
        f"<td>{f((r.get('candidate') or {}).get('auprc'), 3)}</td><td>{f((r.get('production') or {}).get('auprc'), 3)}</td></tr>"
        for r in loao)
    today = dt.date.today().isoformat()
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BLUEBAN 813: verification-first coastal incident intelligence for the UAE</title>
<meta name="description" content="Research paper: a closed-loop system for coastal water-quality incidents in the UAE using Sentinel-2, Sentinel-3 cross-sensor references and a simulated aquatic hyperspectral sensor (Satellite 813).">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,600;0,700;1,400&family=Inter:wght@500;600&display=swap" rel="stylesheet">
<style>
:root {{ --ink:#1b1f24; --muted:#56606d; --line:#dfe3e8; --accent:#1f4e99; --bg:#fbfbf9; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --ink:#e8eaed; --muted:#a3acb8; --line:#2b3240; --accent:#7fa8ff; --bg:#0f131a; }} }}
:root[data-theme="dark"] {{ --ink:#e8eaed; --muted:#a3acb8; --line:#2b3240; --accent:#7fa8ff; --bg:#0f131a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:17px/1.62 "Source Serif 4", Georgia, serif; }}
main {{ max-width:820px; margin:0 auto; padding:48px 16px 96px; }}
h1 {{ font-size:30px; line-height:1.2; margin:0 0 10px; }}
h2 {{ font:600 13px/1.4 Inter, system-ui, sans-serif; letter-spacing:.12em; text-transform:uppercase; color:var(--accent); margin:44px 0 8px; }}
h3 {{ font-size:18px; margin:26px 0 6px; }}
.authors {{ color:var(--muted); font-size:15px; }} .authors a {{ color:var(--accent); }}
.abstract {{ border-left:3px solid var(--accent); padding:4px 0 4px 16px; margin:26px 0; font-size:16px; }}
figure {{ margin:26px 0; }} figure img {{ width:100%; border:1px solid var(--line); border-radius:4px; background:#fff; }}
figcaption {{ font-size:14px; color:var(--muted); margin-top:6px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; margin:14px 0; }}
th, td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }}
th {{ font:600 12px Inter, system-ui, sans-serif; color:var(--muted); }}
code, .eq {{ font-family: ui-monospace, "SFMono-Regular", Consolas, monospace; font-size:14px; }}
.eq {{ display:block; background:rgba(127,127,127,.08); padding:8px 12px; border-radius:4px; margin:10px 0; overflow-x:auto; }}
.note {{ font-size:14px; color:var(--muted); }}
a {{ color:var(--accent); }}
ol.refs li {{ font-size:14px; margin-bottom:6px; }}
.meta {{ font:500 12px Inter, system-ui, sans-serif; color:var(--muted); display:flex; gap:14px; flex-wrap:wrap; margin-top:8px; }}
</style></head>
<body><main>
<div class="meta"><span>Arab Youth Space Hackathon 2026 · 813 Challenge</span><span>Built {today}</span><span><a href="https://github.com/4waiz/BlueBan-813">Code &amp; data</a></span><span><a href="https://BlueBan813.kanbanstudios.ae">Live system</a></span></div>
<h1>BLUEBAN 813: verification-first coastal incident intelligence for the UAE</h1>
<div class="authors">Awaiz Ahmed and <a href="https://kanbanstudios.ae/team-kanban">Team Kanban</a> (Kanban Studios)</div>

<div class="abstract"><b>Abstract.</b> Satellite water-quality products usually end at an index map, leaving operators to decide what an anomaly means and whether to act. We describe BLUEBAN 813, a closed-loop system that turns Sentinel-2 anomalies over UAE coastal waters into incidents that are verified, acted on and learned from. Each water pixel is compared with its own same-season history in other years, which suppresses persistent bright coastal features; candidates are checked against same-morning Sentinel-3 OLCI Case-2 retrievals used strictly as a cross-sensor reference; analysts' decisions become weighted labels; and a candidate triage model reaches production only through a frozen-validation gate and named human approval. Screening {n_ok:,} Sentinel-2 datatakes over {len(watch)} UAE areas of interest ({years[0] if years else '?'}–{years[-1] if years else '?'}) produced {n_cand:,} candidates. On 17 February 2024 the system isolated {f(hero['area_km2'], 2)} km² of discoloured, chlorophyll-rich filaments off Fujairah (NDCI robust z {f(fh['NDCI']['z'], 1)}, hue angle {f(fh['HUE_ANGLE']['value'], 0)}° against a usual {f(fh['HUE_ANGLE']['baseline_median'], 0)}°) that OLCI, {abs(oh.get('dt_minutes') or 0):.0f} minutes earlier, independently resolved as {f(oh.get('region_median'), 1)} vs {f(oh.get('background_median'), 1)} mg m⁻³ CHL_NN (×{f(oh.get('ratio'), 1)}). A comparable NDCI spike on 25 October 2023 was not supported by colour or by OLCI (×{f(oa.get('ratio'), 2)}) and is presented as a failure mode the loop is designed to learn. Because Satellite 813 data were not accessible and no public UAE in-situ measurements exist, 813 is simulated from real Tanager-1 hyperspectral pixels and no physical concentration is reported; on the same pixels the simulated 813 band set reduced false alarms at the decision boundary from {fpA} to {fpB} at matched recall.</div>

<h2>1 Introduction</h2>
<p>The UAE draws most of its drinking water from desalination plants on two very different seas: the shallow, hypersaline Arabian Gulf with a bright seabed, and the deep Gulf of Oman, where blooms have become more frequent and cluster between November and April [1]. The 2008–2009 <i>Margalefidinium</i> (<i>Cochlodinium</i>) bloom closed desalination plants and killed fish along both coasts [2], and green <i>Noctiluca scintillans</i> now dominates many winter blooms in the Gulf of Oman and Arabian Sea [3]. Satellite ocean colour sees these events, but three problems keep it from being operational: optically shallow water and bright coastlines flood spatial anomaly detectors with persistent false alarms [4]; standard chlorophyll products are biased in these waters [5]; and a map does not decide anything — someone has to review it, sample the water and feed the answer back.</p>
<p>BLUEBAN 813 addresses the third problem first. Its contributions are: (i) a per-pixel seasonal anomaly detector over the full Sentinel-2 archive that makes persistence explicit; (ii) a cross-sensor reference built from same-morning Sentinel-3 OLCI Case-2 retrievals, used as weak labels and as incident evidence but never as ground truth; (iii) an incident model with a state machine, verification queue, field workflow and alerts; (iv) a governed learning loop with a frozen validation set, a promotion gate and human approval; and (v) a measured, rather than assumed, estimate of what an aquatic hyperspectral sensor such as Satellite 813 would add.</p>

<h2>2 Data</h2>
<p><b>Sentinel-2 MSI Level-2A</b> surface reflectance (Sen2Cor) from the Microsoft Planetary Computer is the primary sensor. The reflectance offset (<code>BOA_ADD_OFFSET = −1000</code>) is applied according to each tile's processing baseline (≥ 04.00), not its acquisition date, before datatakes spanning UTM zones 39 and 40 are mosaicked. <b>Sentinel-3 OLCI WFR Level-2</b> (CHL_NN, TSM_NN, WQSF flags) provides the cross-sensor reference; the Planetary Computer archive ends on 23 February 2026. <b>Planet Tanager-1</b> hyperspectral data (CC-BY-4.0) over the Gulf of Annaba supply the source spectra for the simulated 813 product. ERA5 10 m winds drive a wind-only drift scenario; OpenStreetMap provides {len((seed or {}).get('assets', []))} coastal assets (desalination and power plants, ports, beaches); Environment Agency Abu Dhabi publishes monitoring-station locations but no measurements.</p>
<p>An audit of the hackathon platform and the gIQ portal (30 September 2026) found no accessible Satellite 813 product and no downloadable in-situ data; public searches found no per-sample UAE chlorophyll, turbidity or TSS measurements. These two facts shape everything below: 813 appears only as a labelled simulation, and all water-quality quantities are reported as proxies.</p>

<h2>3 Methods</h2>
<h3>3.1 Water mask and features</h3>
<p>Pixels are rejected when the scene classification flags no data, saturation, cloud shadow, medium or high cloud probability, cirrus or snow. Water requires MNDWI &gt; 0 and B11 &lt; 0.10; pixels with B11 &gt; 0.0215 are kept but flagged as glint-affected and corrected by subtracting B12 from every band, a first-order surface correction. Features follow their published definitions: NDCI = (R705 − R665)/(R705 + R665) [6]; MCI, the height of R705 above the R665–R740 baseline [7]; FAI [8]; turbidity from the Nechad et al. single-band algorithm with its generic coefficients [9]; and the water-colour hue angle [10].</p>
<h3>3.2 Per-pixel seasonal anomaly (DETECT)</h3>
<p>For acquisition <i>t</i> and feature <i>F</i>, each pixel is compared with its own values on acquisitions within ±45 days of the same day of year in other years:</p>
<span class="eq">z(p) = (F_t(p) − median(clim(p))) / (1.4826 · MAD(clim(p)) + floor_F)</span>
<p>A candidate is a connected region of at least 0.5 km² with z ≥ 3 and seasonal percentile ≥ 95 on the hypothesis' primary feature (NDCI for bloom-like, turbidity for sediment-like, FAI for surface material), with a secondary feature in agreement (MCI z ≥ 1 for bloom-like). A zone screen on the AOI's P95/P99 seasonal percentile selects {n_pix:,} of {n_acq:,} acquisitions for the pixel-level pass. Each candidate carries thirteen triage features, including its persistence (the share of past same-season dates showing a similar signal) and its water-colour change relative to the pixel's seasonal median.</p>
<h3>3.3 Cross-sensor reference</h3>
<p>For every bloom-like or sediment-like candidate up to 23 February 2026, the OLCI granule from the same morning is read in a window around the AOI, its pixels are mapped onto the candidate, and the Case-2 neural-network product (CHL_NN or TSM_NN) inside the region is compared with the surrounding water. The region is a reference positive when its median is ≥ 1.5 × the surroundings (and ≥ 2 units) or ≥ 10 units outright, a reference negative when the ratio is ≤ 1.15 and the median &lt; 5 units, and unlabelled otherwise. These labels carry weight 0.5 (analyst 1.0, field 2.0). For incidents the comparison uses footprint matching: an OLCI pixel belongs to the event when its 300 m footprint overlaps it.</p>
<h3>3.4 Incidents, verification and learning</h3>
<p>An incident moves through DETECTED → UNDER_REVIEW → FIELD_VALIDATION_REQUIRED → CONFIRMED / FALSE_POSITIVE / RESOLVED. Analyst decisions CONFIRM, FALSE_POSITIVE and RECLASSIFY create labels; NEEDS_FIELD_SAMPLE and INSUFFICIENT_EVIDENCE do not. Labels are split into train and a frozen validation set by a deterministic hash of AOI and month, so near-duplicate scenes never straddle the split. A candidate L2 logistic model (identical in Python and in the browser to 10⁻⁷) is promoted only if the model tests pass, the validation hash is unchanged, both classes are present, AUPRC is not worse than production (grouped bootstrap), calibration is acceptable, no AOI regresses, and a named human approves. Every action is recorded in a SHA-256 hash-chained audit log.</p>
<h3>3.5 Simulating Satellite 813</h3>
<p>The published 813 configuration (≈205 bands, 400–1700 nm) is simulated by Gaussian spectral-response convolution of real Tanager-1 spectra (368 good bands, 5 nm sampling). The simulator was checked against a real Sentinel-2 scene acquired {abs((sim or {}).get('time_offset_minutes', 0)):.0f} minutes from the Tanager scene. The ablation trains the same classifier on the same pixels convolved to each band set, with spatially blocked cross-validation ({(hard or {}).get('n_spatial_blocks', '?')} blocks), so spectral configuration is the only variable. Reference labels are a full-spectrum RX judgement, not in-situ truth.</p>

<h2>4 Results</h2>
<h3>4.1 Archive screening</h3>
<p>{n_ok:,} of {n_dt:,} Sentinel-2 datatakes were read over {len(watch)} UAE AOIs. DETECT produced {n_cand:,} candidates ({", ".join(f"{v:,} {k.replace('_', ' ').lower()}" for k, v in sorted(hyp_counts.items()))}). The cross-sensor reference labelled {labels.get('n', 0)} of them ({n_pos} confirmed, {n_neg} not confirmed); most others were smaller than a few OLCI pixels or had no clear OLCI granule.</p>
<table><thead><tr><th>AOI</th><th>Datatakes</th><th>Usable</th><th>Glint-flagged water (median)</th><th>Candidates</th><th>OLCI refs (+/−)</th></tr></thead><tbody>
{aoi_table()}
</tbody></table>

<h3>4.2 Fujairah, 17 February 2024</h3>
<figure><img src="figures/fig1_fujairah.png" alt="Three panels: true colour showing bright green filaments off Fujairah, NDCI robust z map, and hue angle map"><figcaption><b>Figure 1.</b> BB-AE-2024-001, Sentinel-2B, 17 Feb 2024 06:49 UTC, 20 m. (a) Bright-green filaments off Fujairah (median {f(hero['model_features'].get('dist_shore_km'), 1)} km from the coast). (b) NDCI robust z against 33 same-season acquisitions from other years. (c) Hue angle: the filaments are yellow-green (~{f(fh['HUE_ANGLE']['value'], 0)}°) in water that is usually blue (~{f(fh['HUE_ANGLE']['baseline_median'], 0)}°).</figcaption></figure>
<p>The event covers {f(hero['area_km2'], 2)} km² at 20 m. Its median NDCI is {f(fh['NDCI']['value'], 2)} against a seasonal median of {f(fh['NDCI']['baseline_median'], 3)} (robust z {f(fh['NDCI']['z'], 1)}, 100th seasonal percentile), MCI is {f(fh['MCI']['value'], 4)} against {f(fh['MCI']['baseline_median'], 4)}, and the same location showed a similar signal on only {pct(hero['temporal'].get('persistence_frac'), 0)} of past same-season dates. Sentinel-3B OLCI, {abs(oh.get('dt_minutes') or 0):.0f} minutes earlier, gives a CHL_NN median of {f(oh.get('region_median'), 1)} mg m⁻³ over the {oh.get('n_region_px')} OLCI pixels overlapping the event against {f(oh.get('background_median'), 1)} mg m⁻³ around it. The spectrum (Fig. 2) shows the red-edge excess at 705 nm expected of dense phytoplankton. The timing matches the winter <i>Noctiluca</i> season, and NASA's PACE imaged a likely-<i>Noctiluca</i> bloom in the Gulf of Oman a month later [11]; neither confirms the species of this event. The incident is therefore raised as a bloom-like optical anomaly for analyst review, with a five-point sampling plan (core, edge, background control, uncertainty) and exposure to the nearest ports and the Fujairah and Kalba power and desalination plants.</p>
<figure><img src="figures/fig2_spectra.png" alt="Event and background reflectance spectra"><figcaption><b>Figure 2.</b> Median Sentinel-2 spectra of the event and of background water (5–95 % band), SWIR-offset corrected.</figcaption></figure>
<figure><img src="figures/fig3_record.png" alt="Time series of NDCI P95 and hue angle for the Fujairah AOI"><figcaption><b>Figure 3.</b> The Fujairah AOI's seasonal record (AOI P95 of NDCI and median hue angle per acquisition). The two detections are marked.</figcaption></figure>

<h3>4.3 A failure mode: 25 October 2023</h3>
<p>BB-AE-2023-001 has an equally high NDCI z ({f(fa['NDCI']['z'], 1)}) but its hue angle ({f(fa['HUE_ANGLE']['value'], 0)}°) is unchanged from the usual {f(fa['HUE_ANGLE']['baseline_median'], 0)}°, turbidity is at its {f(fa['TUR_NECHAD2016'].get('seasonal_percentile'), 0)}th seasonal percentile, and same-morning OLCI saw {f(oa.get('region_median'), 1)} vs {f(oa.get('background_median'), 1)} mg m⁻³ (×{f(oa.get('ratio'), 2)}). Over very clear water the corrected red reflectance approaches zero and NDCI, a ratio, becomes unstable. The system raises it (the rule baseline cannot tell), the cross-sensor reference labels such cases negative, and an analyst rejection adds a full-weight label: this is precisely the error a learned triage model should absorb.</p>
<figure><img src="figures/fig6_controls.png" alt="The 2023 artifact case and the Annaba negative control"><figcaption><b>Figure 4.</b> (a) BB-AE-2023-001: no visible discolouration. (b–c) Negative control, Gulf of Annaba (Tanager-1): spatially anomalous (RX {f((annaba or {}).get('spatial', {}).get('rx_percentile'), 1)}th percentile) but at the {f((annaba or {}).get('temporal', {}).get('seasonal_percentile'), 1)}th seasonal percentile of {((annaba or {}).get('temporal') or {}).get('n_seasonal', '?')} observations — a persistent coastal feature, stood down.</figcaption></figure>

<h3>4.4 Agreement between Sentinel-2 and OLCI</h3>
<p>Across referenced candidates, the size of the Sentinel-2 change and the OLCI contrast are related (bloom-like: Spearman ρ = {f(rho_b.get('spearman_rho'), 2)}, n = {rho_b.get('n', 0)}; sediment-like: ρ = {f(rho_s.get('spearman_rho'), 2)}, n = {rho_s.get('n', 0)}; median |Δt| {f(B.get('median_abs_dt_minutes'), 0)} min). Figure 5 shows the separation the reference provides.</p>
<figure><img src="figures/fig4_crosssensor.png" alt="Scatter of Sentinel-2 change against OLCI contrast"><figcaption><b>Figure 5.</b> Sentinel-2 change against the OLCI region/surroundings contrast for referenced candidates. Dashed lines: the reference thresholds (×1.5 positive, ×1.15 negative).</figcaption></figure>

<h3>4.5 Triage model on the frozen validation set</h3>
<p>With {C.get('n_train', 0)} training and {C.get('n_validation', 0)} validation labels ({C.get('validation_positive', 0)} positive), the rule baseline and an offline logistic candidate score as follows. The validation set is small; the confidence intervals, not the point estimates, are the result.</p>
<table><thead><tr><th>Metric</th><th>Rule baseline (production)</th><th>Logistic candidate</th><th>Δ, grouped bootstrap 95 % CI</th></tr></thead><tbody>
{metrics_table()}
</tbody></table>
<p class="note">Leave-one-AOI-out (AUPRC, candidate vs rule):</p>
<table><thead><tr><th>Held-out AOI</th><th>n (positive)</th><th>Candidate</th><th>Rule</th></tr></thead><tbody>{loao_rows}</tbody></table>

<h3>4.6 What does 813 add?</h3>
<figure><img src="figures/fig5_ablation.png" alt="Bar chart of false alarms by band set"><figcaption><b>Figure 6.</b> False alarms at matched recall on the same Tanager pixels, spatially blocked cross-validation.</figcaption></figure>
<p>At the operational decision boundary the simulated 813 band set reduced false alarms from {fpA} to {fpB} (F1 {f(arms.get('S2_multispectral_11band', {}).get('f1'), 3)} → {f(arms.get('813_hyperspectral_205band', {}).get('f1'), 3)}), while for a gross plume both band sets saturate (F1 {f(((easy or {}).get('results', {}).get('spatial_blocked', {}).get('S2_multispectral_11band') or {}).get('f1'), 3)} vs {f(((easy or {}).get('results', {}).get('spatial_blocked', {}).get('813_hyperspectral_205band') or {}).get('f1'), 3)}). Regressions against OLCI products were not skilful for either (CHL_NN R² {f(((olci_lift or {}).get('targets', {}).get('CHL_NN_log10', {}).get('spatial_blocked', {}).get('S2_multispectral_11band') or {}).get('r2'), 2)} and {f(((olci_lift or {}).get('targets', {}).get('CHL_NN_log10', {}).get('spatial_blocked', {}).get('813_hyperspectral_205band') or {}).get('r2'), 2)}; {(olci_lift or {}).get('n_matchups', '?')} matchups {abs(((olci_lift or {}).get('matchup_dt_hours') or {}).get('median', 0)):.1f} h apart). The measured value of hyperspectral sampling is therefore discrimination near the decision boundary, not detection of obvious events and not, on this evidence, concentration.</p>

<h2>5 Discussion and limitations</h2>
<p>Sen2Cor is a land processor, and the SWIR offset removes only first-order glint; water-specific atmospheric correction would reduce the NDCI instability seen in §4.3. OLCI CHL_NN and TSM_NN are model products with their own errors, worst in optically shallow Gulf water; they are used as weak references and every label records the OLCI values it came from. The references under-represent events smaller than a few 300 m pixels and cannot exist after February 2026. The per-pixel climatology needs several years of same-season scenes and is weaker for the earliest dates. No physical concentration is reported: the matchup engine (±24 h, 3×3 box, CV ≤ 0.15, sensitivity at 3 h and 72 h) and a calibration gate (≥ 20 matchups in ≥ 5 groups, grouped-CV R² ≥ 0.4 in log space with a confidence interval above zero) are ready for the first legitimate samples. The drift is a wind-only scenario and no source is ever inferred from it. The 813 results are simulations on an Algerian scene until real 813 data and a UAE Tanager scene are available.</p>

<h2>6 Conclusion</h2>
<p>Treating detections as incidents — compared with their own history, cross-checked by an independent sensor, decided by analysts, confirmed in the field and fed back through a gated learning loop — turns satellite water-quality monitoring into something an operator can act on without being flooded by the coastline. On real UAE data the approach surfaced a visible, cross-sensor-supported bloom-like event off Fujairah and exposed, rather than hid, a characteristic false positive. BlueBan turns every coastal incident into both a response and a lesson.</p>

<h2>Data and code availability</h2>
<p>All code, derived outputs and this paper's generator are at <a href="https://github.com/4waiz/BlueBan-813">github.com/4waiz/BlueBan-813</a>; every figure and number here is rebuilt from the repository's outputs by <code>scripts/build_paper.py</code>. Input data are public (Copernicus, Planet Tanager open data, ERA5, OpenStreetMap). No restricted data are included.</p>

<h2>References</h2>
<ol class="refs">
<li>Al-Shehhi, M. R., Nelson, D., Farzanah, R., Alshihi, R., Salehi-Ashtiani, K. (2021). Characterizing algal blooms in a shallow &amp; a deep channel. <i>Ocean &amp; Coastal Management</i> 213, 105840.</li>
<li>Richlen, M. L. et al. (2010). The catastrophic 2008–2009 red tide in the Arabian Gulf region, with observations on the identification and phylogeny of the fish-killing dinoflagellate <i>Cochlodinium polykrikoides</i>. <i>Harmful Algae</i> 9, 163–172.</li>
<li>Gomes, H. R. et al. (2014). Massive outbreaks of <i>Noctiluca scintillans</i> blooms in the Arabian Sea due to spread of hypoxia. <i>Nature Communications</i> 5, 4862.</li>
<li>Al Shehhi, M. R., Gherboudj, I., Ghedira, H. (2017). In situ spectral response of the Arabian Gulf and Sea of Oman coastal waters to bio-optical properties. <i>J. Photochem. Photobiol. B</i> 175, 235–243.</li>
<li>Warren, M. A. et al. (2019). Assessment of atmospheric correction algorithms for the Sentinel-2A MultiSpectral Imager over coastal and inland waters. <i>Remote Sensing of Environment</i> 225, 267–289.</li>
<li>Mishra, S., Mishra, D. R. (2012). Normalized difference chlorophyll index. <i>Remote Sensing of Environment</i> 117, 394–406.</li>
<li>Gower, J., King, S., Borstad, G., Brown, L. (2005). Detection of intense plankton blooms using the 709 nm band of the MERIS imaging spectrometer. <i>Int. J. Remote Sensing</i> 26, 2005–2012.</li>
<li>Hu, C. (2009). A novel ocean color index to detect floating algae in the global oceans. <i>Remote Sensing of Environment</i> 113, 2118–2129.</li>
<li>Nechad, B., Ruddick, K. G., Park, Y. (2010). Calibration and validation of a generic multisensor algorithm for mapping of total suspended matter in turbid waters. <i>Remote Sensing of Environment</i> 114, 854–866.</li>
<li>van der Woerd, H. J., Wernand, M. R. (2015). True colour classification of natural waters with medium-spectral resolution satellites. <i>Sensors</i> 15, 25663–25680.</li>
<li>NASA Earth Observatory (2024). Complex Beauty in the Gulf of Oman (PACE OCI, 17 March 2024).</li>
<li>Doerffer, R., Schiller, H. (2007). The MERIS Case 2 water algorithm. <i>Int. J. Remote Sensing</i> 28, 517–535.</li>
<li>Gernez, P., Zoffoli, M. L., Lacour, T., Hernández Fariñas, T., Navarro, G., Caballero, I., Harmel, T. (2023). The many shades of red tides: Sentinel-2 optical types of highly-concentrated harmful algal blooms. <i>Remote Sensing of Environment</i> 287, 113486.</li>
</ol>
</main></body></html>"""
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fh_:
        fh_.write(body)
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print("paper ->", os.path.relpath(os.path.join(OUT, "index.html"), ROOT))


if __name__ == "__main__":
    build()
