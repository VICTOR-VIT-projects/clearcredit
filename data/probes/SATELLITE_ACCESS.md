# Satellite Data Access — Phase 0 Probe (2026-10-05)

Test polygon: ~5×5 km box in Rondônia, Brazil — bbox `(-63.10, -9.90, -63.05, -9.85)`, EPSG:4326.

## 1. Tree-cover loss — Hansen Global Forest Change

| Item | Result |
|---|---|
| Latest version | **GFC-2025-v1.13** (HTTP 200). GFC-2024-v1.12 also available. |
| Last covered loss year | **2025** (`lossyear` values 1–25 = 2001–2025) |
| URL pattern | `https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_{layer}_{lat}_{lon}.tif`, layers `lossyear`, `treecover2000`; 10°×10° tiles named by top-left corner (e.g. `00N_070W`) |
| Access | Public HTTPS, no key. Read with rasterio `/vsicurl/` windowed reads (no full-tile download). |
| Latency | ~5 s for the test window (tiles are striped, not internally tiled, so reads pull whole rows of a 40000-px strip — larger polygons cost more) |
| Sample output (GFC-2024 lossyear, test box) | 39,909 pixels; 3,003 loss pixels across 2001–2024, peaks in 2005 (440 px) and 2009 (516 px) |
| License | CC BY 4.0. Cite: Hansen, M. C. et al. 2013. "High-Resolution Global Maps of 21st-Century Forest Cover Change." *Science* 342: 850–53. |

Pixel area must be computed per row (≈30 m at the equator, shrinking with cos(latitude)); never sum raw degree pixels.

## 2. NDVI trend — Sentinel-2 L2A via Microsoft Planetary Computer STAC

| Item | Result |
|---|---|
| Endpoint | `https://planetarycomputer.microsoft.com/api/stac/v1`, collection `sentinel-2-l2a` |
| Access | No key; assets signed with `planetary_computer.sign_inplace` |
| Query | Jun–Aug of each year, `eo:cloud_cover < 20`, lowest-cloud 4 scenes |
| Cloud mask | SCL classes 0,1,3,8,9,10 masked |
| Latency | ~10–12 s per year (4 scenes × 3 bands, decimated window read) |
| Sample output | Mean dry-season NDVI **2019: 0.527 → 2024: 0.318** |
| License | Copernicus Sentinel data terms (free, attribution: "Contains modified Copernicus Sentinel data [year]") |

## Recommendation

- Both sources work from the dev machine without keys. (A sandboxed build environment could not reach them — TLS/filesystem restrictions there, not a real outage.)
- Precompute: ~5 s Hansen + ~6 years × 10 s NDVI ≈ 65 s per polygon → ~1 h for 50 polygons. Run once, cache JSON per polygon under `data/cache/evidence/`, store dataset version + query date + `evidenceHash`.
- Use decimated reads (`out_shape`) for NDVI on large polygons; Hansen loss needs full resolution (30 m) but is a single read per tile.
- The demo reads only the cache; live fetch is a fallback path, never used during recording.
