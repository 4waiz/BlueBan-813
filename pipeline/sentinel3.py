"""Sentinel-3 OLCI Water Full Resolution Level-2 access.

Stage A of the cascade, and our independent reference.

OLCI WFR L2 is an ESA *operational* ocean-colour product: chlorophyll-a from
both the OC4Me band-ratio algorithm and a neural-network algorithm tuned for
Case-2 (coastal, optically complex) water, plus total suspended matter and
inherent optical properties. We do not re-derive these. Re-implementing an
operationally validated retrieval badly and then calling the result a product
is a common own goal; using ESA's and citing it is better science and a better
reference against which to test a hyperspectral retrieval.

Data source: Microsoft Planetary Computer, ``sentinel-3-olci-wfr-l2-netcdf``.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

# Level-2 variables and their units, per the Sentinel-3 OLCI Level-2 Water
# Product Data Format specification.
L2_VARIABLES = {
    "chl-oc4me": {
        "variable": "CHL_OC4ME",
        "units": "log10(mg m^-3)",
        "algorithm": "OC4Me maximum band ratio, Case-1 water",
        "reference": "Morel et al. (2007); S3 OLCI ATBD ATBD_OC4Me",
        "note": "Stored as log10. Valid for clear open-ocean water; "
                "unreliable in Case-2 coastal water.",
    },
    "chl-nn": {
        "variable": "CHL_NN",
        "units": "log10(mg m^-3)",
        "algorithm": "Neural network, Case-2 water",
        "reference": "Doerffer & Schiller (2007); S3 OLCI ATBD ATBD_C2RCC",
        "note": "Stored as log10. Designed for optically complex coastal "
                "water; the appropriate choice for the Gulf of Annaba.",
    },
    "tsm-nn": {
        "variable": "TSM_NN",
        "units": "log10(g m^-3)",
        "algorithm": "Neural network total suspended matter",
        "reference": "Doerffer & Schiller (2007)",
        "note": "Stored as log10.",
    },
    "iop-nn": {
        "variable": "ADG443_NN / KD490_M07",
        "units": "log10(m^-1)",
        "algorithm": "Neural network inherent optical properties",
        "reference": "S3 OLCI ATBD",
        "note": "Contains CDOM+detrital absorption at 443 nm and diffuse "
                "attenuation at 490 nm.",
    },
}

# WQSF (Water Quality and Science Flags) bits that invalidate a water pixel.
# Names follow the OLCI L2 product specification.
WQSF_REJECT = [
    "INVALID", "LAND", "CLOUD", "CLOUD_AMBIGUOUS", "CLOUD_MARGIN",
    "SNOW_ICE", "SUSPECT", "HISOLZEN", "SATURATED", "HIGHGLINT",
    "WHITECAPS", "AC_FAIL", "OC4ME_FAIL", "ANNOT_TAU06", "RWNEG_O2",
    "RWNEG_O3", "RWNEG_O4", "RWNEG_O5", "RWNEG_O6", "RWNEG_O7", "RWNEG_O8",
]

# OLCI band centres (nm), bands Oa01-Oa21.
OLCI_BANDS_NM = [400, 412.5, 442.5, 490, 510, 560, 620, 665, 673.75, 681.25,
                 708.75, 753.75, 761.25, 764.375, 767.5, 778.75, 865, 885,
                 900, 940, 1020]


@dataclass
class OlciScene:
    item_id: str
    datetime: str
    cloud_cover: float
    variables: dict          # name -> 2D array
    valid: np.ndarray        # boolean, True = usable water
    lon: np.ndarray
    lat: np.ndarray


def search(bbox, datetime_range: str, limit: int = 2000):
    """Search Planetary Computer for OLCI WFR L2 items."""
    from pystac_client import Client
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    items = list(cat.search(collections=["sentinel-3-olci-wfr-l2-netcdf"],
                            bbox=bbox, datetime=datetime_range,
                            max_items=limit).items())
    items.sort(key=lambda i: i.properties["datetime"])
    return items


def _open_asset(item, key):
    import planetary_computer as pc
    import xarray as xr
    import fsspec
    href = pc.sign(item).assets[key].href
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f = fsspec.open(href).open()
        return xr.open_dataset(f, engine="h5netcdf", chunks=None)


def load(item, variables=("chl-nn", "tsm-nn"), with_geo: bool = True,
         apply_flags: bool = True) -> OlciScene:
    """Load selected L2 variables plus geolocation and the WQSF quality mask.

    Values are returned in their NATIVE storage form. CHL_NN and TSM_NN are
    stored as log10; callers that want linear units must exponentiate
    explicitly. Doing that silently is how a chlorophyll value ends up wrong by
    orders of magnitude.
    """
    out: dict = {}
    valid = None

    for key in variables:
        ds = _open_asset(item, key)
        for v in ds.data_vars:
            if v.upper().startswith(("CHL", "TSM", "ADG", "KD")):
                out[v] = np.asarray(ds[v].values, dtype="float32")
        ds.close()

    lon = lat = None
    if with_geo:
        ds = _open_asset(item, "geo-coordinates")
        lon = np.asarray(ds["longitude"].values, dtype="float64")
        lat = np.asarray(ds["latitude"].values, dtype="float64")
        ds.close()

    if apply_flags:
        try:
            ds = _open_asset(item, "wqsf")
            wq = ds["WQSF"]
            masks = {n: int(v) for n, v in zip(
                wq.attrs.get("flag_meanings", "").split(),
                np.atleast_1d(wq.attrs.get("flag_masks", [])))}
            bits = 0
            for name in WQSF_REJECT:
                if name in masks:
                    bits |= masks[name]
            valid = (np.asarray(wq.values).astype("uint64") & np.uint64(bits)) == 0
            ds.close()
        except Exception:
            valid = None

    if valid is None:
        ref = next(iter(out.values())) if out else np.zeros((1, 1))
        valid = np.isfinite(ref)

    return OlciScene(
        item_id=item.id,
        datetime=item.properties["datetime"],
        cloud_cover=float(item.properties.get("eo:cloud_cover") or -1),
        variables=out, valid=valid, lon=lon, lat=lat,
    )


def to_linear(values: np.ndarray) -> np.ndarray:
    """Convert a log10-stored OLCI L2 variable to linear units."""
    return np.power(10.0, values)


def subset_bbox(scene: OlciScene, bbox) -> dict:
    """Extract pixels inside ``bbox`` with their coordinates and values.

    OLCI L2 is on an irregular instrument grid, so this is a point selection,
    not an array window. Returns a dict of flat arrays.
    """
    lo_x, lo_y, hi_x, hi_y = bbox
    inside = (
        (scene.lon >= lo_x) & (scene.lon <= hi_x)
        & (scene.lat >= lo_y) & (scene.lat <= hi_y)
        & scene.valid
    )
    out = {"lon": scene.lon[inside], "lat": scene.lat[inside],
           "n": int(inside.sum())}
    for k, v in scene.variables.items():
        if v.shape == inside.shape:
            out[k] = v[inside]
    return out


def load_window(item, bbox, pad_deg: float = 0.25,
                variables=("chl-nn", "tsm-nn")) -> dict | None:
    """Read only the part of an OLCI granule around ``bbox``.

    A WFR granule is ~4000 x 4800 pixels; a coastal AOI needs a few hundred.
    The tie-point grid (subsampled 64 x 64) locates the window, and only that
    hyperslab is read from each variable, so a cross-check costs megabytes
    instead of the full granule. Returns flat arrays of the window (lon, lat,
    valid and each variable in its native log10 form), or None when the AOI
    is outside the granule.
    """
    tie = _open_asset(item, "tie-geo-coordinates")
    tlon = np.asarray(tie["longitude"].values, dtype="float64")
    tlat = np.asarray(tie["latitude"].values, dtype="float64")
    al = int(tie.attrs.get("al_subsampling_factor", 64))
    ac = int(tie.attrs.get("ac_subsampling_factor", 64))
    tie.close()
    lo_x, lo_y, hi_x, hi_y = bbox
    near = ((tlon >= lo_x - pad_deg) & (tlon <= hi_x + pad_deg)
            & (tlat >= lo_y - pad_deg) & (tlat <= hi_y + pad_deg))
    if not near.any():
        return None
    rr, cc = np.where(near)
    win = {"rows": slice(max(rr.min() - 1, 0) * al, (rr.max() + 2) * al),
           "columns": slice(max(cc.min() - 1, 0) * ac, (cc.max() + 2) * ac)}

    def read(key, names):
        ds = _open_asset(item, key)
        sub = ds.isel({k: v for k, v in win.items() if k in ds.dims})
        got = {n: np.asarray(sub[n].values) for n in names if n in sub}
        ds.close()
        return got

    geo = read("geo-coordinates", ("longitude", "latitude"))
    out = {"lon": geo["longitude"].astype("float64"), "lat": geo["latitude"].astype("float64")}
    for key in variables:
        var = L2_VARIABLES.get(key, {}).get("variable", "").split(" ")[0]
        got = read(key, (var,))
        if var in got:
            out[var] = got[var].astype("float32")
    ds = _open_asset(item, "wqsf")
    wq = ds["WQSF"]
    masks = {n: int(v) for n, v in zip(wq.attrs.get("flag_meanings", "").split(),
                                       np.atleast_1d(wq.attrs.get("flag_masks", [])))}
    bits = 0
    for name in WQSF_REJECT:
        bits |= masks.get(name, 0)
    wv = np.asarray(ds.isel({k: v for k, v in win.items() if k in ds.dims})["WQSF"].values)
    ds.close()
    out["valid"] = (wv.astype("uint64") & np.uint64(bits)) == 0
    for k in list(out):
        out[k] = out[k].ravel()
    out["item_id"] = item.id
    out["datetime"] = item.properties["datetime"]
    return out


#: Which OLCI Case-2 product answers which event hypothesis.
REFERENCE_VARIABLE = {"BLOOM_LIKE": ("CHL_NN", "mg m^-3"), "SEDIMENT_LIKE": ("TSM_NN", "g m^-3")}
#: Last OLCI WFR granule on the Planetary Computer (checked 2026-09-30).
PC_OLCI_END = "2026-02-23"


def reference_contrast(region_vals, bg_vals):
    """Cross-sensor reference rule on linear values -> (y, region, background, ratio).

    y = 1 when the region is >= 1.5 x its surroundings (and >= 2 units) or
    >= 10 units outright; y = 0 when the ratio is <= 1.15 and the region is
    < 5 units; otherwise None (ambiguous). One rule for seed labels and for
    the incident evidence, so the two can never disagree.
    """
    reg = float(np.median(region_vals))
    bg = float(np.median(bg_vals))
    ratio = reg / bg if bg > 0 else float("inf")
    if (ratio >= 1.5 and reg >= 2.0) or reg >= 10.0:
        return 1, reg, bg, ratio
    if ratio <= 1.15 and reg < 5.0:
        return 0, reg, bg, ratio
    return None, reg, bg, ratio


def crosscheck(bbox, date: str, s2_datetime: str, locate, hypothesis: str,
               pad_deg: float = 0.2, min_region_px: int = 8, min_bg_px: int = 30) -> dict:
    """Compare an S2 event with the same-morning OLCI Case-2 product.

    ``locate(lon, lat) -> (in_region, near_region)`` maps OLCI pixel centres
    onto the event mask. Returns a JSON-ready record; never raises.
    """
    import datetime as _dt
    var, units = REFERENCE_VARIABLE.get(hypothesis, (None, None))
    if var is None:
        return {"available": False, "note": f"no OLCI counterpart for {hypothesis}"}
    if date > PC_OLCI_END:
        return {"available": False, "note": f"OLCI on the Planetary Computer ends {PC_OLCI_END}"}
    try:
        items = search(bbox, f"{date}T03:30:00Z/{date}T10:00:00Z")
    except Exception as e:
        return {"available": False, "note": f"OLCI search failed: {e!r}"[:200]}
    t_s2 = _dt.datetime.fromisoformat(s2_datetime.replace("Z", "+00:00"))
    best = None
    for it in items[:3]:
        try:
            w = load_window(it, bbox, pad_deg, variables=("chl-nn", "tsm-nn"))
        except Exception:
            continue
        if not w or var not in w:
            continue
        inr, near = locate(w["lon"], w["lat"])
        v = np.power(10.0, w[var].astype("float64"))
        ok = w["valid"] & np.isfinite(v)
        rp, bp = ok & inr, ok & ~near
        if best is None or rp.sum() > best[0]:
            best = (int(rp.sum()), w, v, rp, bp)
    if best is None:
        return {"available": False, "note": "no OLCI granule with valid water that morning"}
    n, w, v, rp, bp = best
    t_o = _dt.datetime.fromisoformat(str(w["datetime"]).replace("Z", "+00:00"))
    rec = {"available": True, "item_id": w["item_id"], "datetime": str(w["datetime"])[:19] + "Z",
           "dt_minutes": round((t_o - t_s2).total_seconds() / 60.0, 1), "variable": var, "units": units,
           "n_region_px": int(rp.sum()), "n_background_px": int(bp.sum()),
           "product": "ESA OLCI WFR L2 Case-2 neural net (a model product, not in situ)"}
    if rp.sum() < min_region_px or bp.sum() < min_bg_px:
        rec.update({"agrees": None, "note": "too few valid OLCI pixels over the event"})
        return rec
    y, reg, bg, ratio = reference_contrast(v[rp], v[bp])
    rec.update({"agrees": None if y is None else bool(y), "region_median": round(reg, 3),
                "background_median": round(bg, 3), "ratio": round(ratio, 3)})
    return rec
