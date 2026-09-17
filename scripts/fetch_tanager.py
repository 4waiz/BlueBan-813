"""Download a Tanager-1 scene's ortho surface-reflectance HDF5 + sidecar metadata.

Source : Planet open STAC catalog (no authentication required)
Licence: CC-BY-4.0 (c) Planet Labs PBC
Usage  : python scripts/fetch_tanager.py <item_id> [--collection coastal-water-bodies]
"""
import argparse, hashlib, json, os, sys, time, urllib.request

STAC_BASE = "https://www.planet.com/data/stac/tanager-core-imagery"
OUT_DIR = os.path.join("data", "raw", "tanager")
META_DIR = os.path.join("data", "metadata")


def _get_json(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "bluepulse813/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def download(url, dest, chunk=8 * 1024 * 1024):
    """Stream to disk with a resume-safe temp file and a running SHA-256."""
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "bluepulse813/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        total = int(r.headers.get("Content-Length", 0))
        h = hashlib.sha256()
        done = 0
        t0 = time.time()
        with open(tmp, "wb") as f:
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                f.write(buf)
                h.update(buf)
                done += len(buf)
                pct = 100.0 * done / total if total else 0.0
                mbs = done / 1e6 / max(time.time() - t0, 1e-9)
                print(f"\r  {done/1e9:.3f}/{total/1e9:.3f} GB ({pct:5.1f}%) {mbs:6.1f} MB/s",
                      end="", flush=True)
    print()
    os.replace(tmp, dest)
    return h.hexdigest(), total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("item_id")
    ap.add_argument("--collection", default="coastal-water-bodies")
    ap.add_argument("--asset", default="ortho_sr_hdf5")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(META_DIR, exist_ok=True)

    iid = args.item_id
    url = f"{STAC_BASE}/{args.collection}/{iid}/{iid}.json"
    print(f"STAC item: {url}")
    item = _get_json(url)

    meta_path = os.path.join(META_DIR, f"tanager_{iid}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(item, f, indent=1)
    print(f"Saved STAC metadata -> {meta_path}")

    asset = item["assets"][args.asset]
    href = asset["href"]
    dest = os.path.join(OUT_DIR, os.path.basename(href))
    if os.path.exists(dest):
        print(f"Already present: {dest} ({os.path.getsize(dest)/1e9:.3f} GB)")
        return 0

    print(f"Downloading {args.asset}\n  {href}")
    sha, size = download(href, dest)
    prov = {
        "item_id": iid,
        "collection": args.collection,
        "asset_key": args.asset,
        "source_url": href,
        "stac_item_url": url,
        "local_path": dest.replace("\\", "/"),
        "bytes": size,
        "sha256": sha,
        "downloaded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "licence": item["properties"].get("license"),
        "datetime": item["properties"].get("datetime"),
        "platform": item["properties"].get("platform"),
        "constellation": item["properties"].get("constellation"),
        "gsd": item["properties"].get("gsd"),
        "attribution": "Tanager STAC Data, available at www.planet.com/data/stac "
                       "(c) 2025 Planet Labs PBC. All Rights Reserved.",
    }
    pp = os.path.join(META_DIR, f"tanager_{iid}_download.json")
    with open(pp, "w", encoding="utf-8") as f:
        json.dump(prov, f, indent=1)
    print(f"Saved download provenance -> {pp}\n  sha256={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
