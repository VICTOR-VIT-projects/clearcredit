"""Independent satellite evidence per boundary, cached to disk.

Two signals (see data/probes/SATELLITE_ACCESS.md):
  * Tree-cover loss — Hansen Global Forest Change (CC BY 4.0), 30 m, loss years 2001–2025.
  * NDVI trend      — Sentinel-2 L2A via Microsoft Planetary Computer STAC, cloud-masked.

Evidence is precomputed for every seed/synthetic boundary; the demo reads only the cache.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import rasterio.errors
import rasterio.transform
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

from .canonical import _dumps, canonical_boundary, keccak

GFC_VERSION = "GFC-2025-v1.13"
GFC_LAST_YEAR = 2025
GFC_URL = "https://storage.googleapis.com/earthenginepartners-hansen/{v}/Hansen_{v}_{layer}_{tile}.tif"
CANOPY_THRESHOLD = 30  # % canopy cover in 2000 counted as forest (GFW convention)
ROW_BLOCK = 2048
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
NDVI_YEARS = range(2019, 2026)
NDVI_SCENES_PER_YEAR = 4
NDVI_MAX_PX = 256
SCL_MASK = [0, 1, 3, 8, 9, 10]  # no-data, saturated, cloud shadow, cloud med/high, cirrus
EARTH_R = 6_371_007.2  # authalic radius (m)

EVIDENCE_VERSION = "ev2"  # bump whenever evidence numbers change; part of the cache key and the hashed bundle
CACHE_DIR = Path(os.environ.get("EVIDENCE_CACHE", Path(__file__).resolve().parents[2] / "data" / "cache" / "evidence"))
_GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2")


def boundary_key(boundary: dict) -> str:
    return keccak(_dumps(canonical_boundary(boundary)).encode()).hex()


def evidence_hash(bundle: dict) -> str:
    return "0x" + keccak(_dumps(bundle).encode()).hex()


# ---------------------------------------------------------------- Hansen tree-cover loss

def _gfc_tiles(bounds):
    minx, miny, maxx, maxy = bounds
    for top in range(math.floor(miny / 10) * 10 + 10, math.ceil(maxy / 10) * 10 + 1, 10):
        for left in range(math.floor(minx / 10) * 10, math.floor(maxx / 10) * 10 + 1, 10):
            name = f"{abs(top):02d}{'N' if top >= 0 else 'S'}_{abs(left):03d}{'E' if left >= 0 else 'W'}"
            yield name, (left, top - 10, left + 10, top)


def _pixel_area_ha(transform, rows: int, row0: float) -> np.ndarray:
    """Spherical (authalic) area of each pixel row in a lat/lon grid, in hectares."""
    dlon = math.radians(transform.a)
    lat_top = transform.f + transform.e * (row0 + np.arange(rows))
    lat_bot = lat_top + transform.e
    return (EARTH_R**2 * dlon * np.abs(np.sin(np.radians(lat_top)) - np.sin(np.radians(lat_bot)))) / 10_000


def forest_loss(geom) -> dict:
    forest_ha = 0.0
    loss = np.zeros(GFC_LAST_YEAR - 2000 + 1)
    with rasterio.Env(**_GDAL_ENV):
        for tile, tb in _gfc_tiles(geom.bounds):
            part = geom.intersection(shape({"type": "Polygon", "coordinates": [[(tb[0], tb[1]), (tb[2], tb[1]), (tb[2], tb[3]), (tb[0], tb[3]), (tb[0], tb[1])]]}))
            if part.area == 0:  # missing or only touching this tile's edge
                continue
            urls = {l: "/vsicurl/" + GFC_URL.format(v=GFC_VERSION, layer=l, tile=tile) for l in ("lossyear", "treecover2000")}
            with rasterio.open(urls["lossyear"]) as ly, rasterio.open(urls["treecover2000"]) as tc:
                win = from_bounds(*part.bounds, ly.transform).round_offsets().round_lengths()
                win = win.intersection(Window(0, 0, ly.width, ly.height))
                # Row blocks keep memory bounded for multi-degree projects (~30 m pixels).
                for r0 in range(0, int(win.height), ROW_BLOCK):
                    sub = Window(win.col_off, win.row_off + r0, win.width, min(ROW_BLOCK, win.height - r0))
                    lossyear, cover = ly.read(1, window=sub), tc.read(1, window=sub)
                    wt = ly.window_transform(sub)
                    inside = ~geometry_mask([mapping(part)], out_shape=lossyear.shape, transform=wt, all_touched=False)
                    forest = inside & (cover > CANOPY_THRESHOLD)
                    row_area = _pixel_area_ha(wt, lossyear.shape[0], 0)
                    forest_ha += float(forest.sum(axis=1) @ row_area)
                    rows, _ = np.nonzero(forest)
                    loss += np.bincount(lossyear[forest], weights=row_area[rows], minlength=loss.size)[: loss.size]
    by_year = {str(2000 + i): round(float(v), 2) for i, v in enumerate(loss) if i > 0}
    return {
        "dataset": f"Hansen/UMD/Google/USGS/NASA Global Forest Change {GFC_VERSION}",
        "license": "CC BY 4.0",
        "canopyThresholdPct": CANOPY_THRESHOLD,
        "forest2000Ha": round(forest_ha, 2),
        "lossHaByYear": by_year,
        "lastCoveredYear": GFC_LAST_YEAR,
    }


# ---------------------------------------------------------------- Sentinel-2 NDVI

def _scene_ndvi(item, geom) -> float | None:
    """Mean NDVI inside `geom` for one scene. All bands are resampled onto the SCL (20 m)
    window grid so pixels align; large boundaries are decimated to <= NDVI_MAX_PX."""
    with rasterio.open(item.assets["SCL"].href) as ds:
        g = shp_transform(Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform, geom)
        try:
            win = from_bounds(*g.bounds, ds.transform).intersection(Window(0, 0, ds.width, ds.height))
        except rasterio.errors.WindowError:
            return None  # boundary is outside this scene's tile
        scale = max(1.0, max(win.width, win.height) / NDVI_MAX_PX)
        out = (max(1, round(win.height / scale)), max(1, round(win.width / scale)))
        bounds = ds.window_bounds(win)
        wt = rasterio.transform.from_bounds(*bounds, out[1], out[0])
        scl = ds.read(1, window=win, out_shape=out)
    arrays = {}
    for band in ("B04", "B08"):
        with rasterio.open(item.assets[band].href) as ds:
            arrays[band] = ds.read(1, window=from_bounds(*bounds, ds.transform), out_shape=out).astype("float32")
    inside = ~geometry_mask([mapping(g)], out_shape=out, transform=wt)
    ok = inside & ~np.isin(scl, SCL_MASK) & (arrays["B04"] > 0) & (arrays["B08"] > 0)  # DN 0 = no data
    offset = boa_offset(item.properties["s2:processing_baseline"])
    red, nir = (np.clip(arrays[b][ok] - offset, 0, None) for b in ("B04", "B08"))
    keep = (nir + red) > 0
    if keep.sum() < 10:
        return None
    return float(np.mean((nir[keep] - red[keep]) / (nir[keep] + red[keep])))


def boa_offset(processing_baseline: str) -> int:
    """DN offset to subtract before computing reflectance ratios. Since processing baseline
    04.00 (Jan 2022) L2A DNs carry BOA_ADD_OFFSET = -1000: reflectance = (DN - 1000) / 10000.
    Ignoring it pushes NDVI down by ~0.3 from 2022 onward and fakes a declining trend."""
    return 1000 if float(processing_baseline) >= 4.0 else 0


def ndvi_trend(geom) -> dict:
    import planetary_computer as pc
    from pystac_client import Client

    cat = Client.open(STAC_URL, modifier=pc.sign_inplace)
    per_year = {}
    with rasterio.Env(**_GDAL_ENV):
        for year in NDVI_YEARS:
            items = cat.search(
                collections=["sentinel-2-l2a"], intersects=mapping(geom), datetime=f"{year}-01-01/{year}-12-31",
                query={"eo:cloud_cover": {"lt": 20}}, sortby=[{"field": "eo:cloud_cover", "direction": "asc"}],
                max_items=NDVI_SCENES_PER_YEAR,
            ).items()
            vals = [v for it in items if (v := _scene_ndvi(it, geom)) is not None]
            if vals:
                per_year[str(year)] = round(float(np.median(vals)), 4)
    slope = None
    if len(per_year) >= 3:
        xs = np.array([int(y) for y in per_year]); ys = np.array(list(per_year.values()))
        slope = round(float(np.polyfit(xs, ys, 1)[0]), 5)
    return {
        "dataset": "Copernicus Sentinel-2 L2A (Microsoft Planetary Computer)",
        "license": "Copernicus Sentinel data terms; contains modified Copernicus Sentinel data",
        "method": f"per year: {NDVI_SCENES_PER_YEAR} least-cloudy scenes (<20%), BOA offset removed for processing baseline >= 04.00, SCL-masked mean NDVI inside boundary, median across scenes",
        "meanNdviByYear": per_year,
        "slopePerYear": slope,
    }


# ---------------------------------------------------------------- bundle + cache

def get_evidence(boundary: dict, *, live: bool = True) -> dict | None:
    """Cached evidence bundle for a boundary; computes and caches it when `live` is True."""
    path = CACHE_DIR / f"{EVIDENCE_VERSION}-{boundary_key(boundary)}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        return None
    geom = shape(boundary)
    t = time.time()
    bundle = {
        "evidenceVersion": EVIDENCE_VERSION,
        "boundaryKey": boundary_key(boundary),
        "queriedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "forestLoss": forest_loss(geom),
        "ndvi": ndvi_trend(geom),
    }
    bundle["computeSeconds"] = round(time.time() - t, 1)
    bundle["evidenceHash"] = evidence_hash({k: v for k, v in bundle.items() if k != "computeSeconds"})
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle
