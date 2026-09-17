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
