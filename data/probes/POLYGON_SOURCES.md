# Carbon-project polygon source probe

Retrieved: **2026-10-05**

## Bottom line

Yes: real, machine-readable carbon-project geometries are publicly available in sufficient quantity for a ClearCredit prototype. This probe produced **40 non-fabricated project GeoJSON files**: 23 avoided-deforestation projects and 17 afforestation/reforestation projects across 17 tropical countries.

That does **not** make all 40 registry-official or survey-grade. The source dataset's own index classifies the underlying records as **25 Official, 12 Georeferenced, and 3 Method-derived**. In addition, this seed was reconstructed from CarbonPlan's zoom-12 vector-tile derivative, not copied byte-for-byte from the original registry attachments or full-resolution GeoPackages. It is appropriate for prototype overlap and satellite-loss experiments. It is not defensible as authoritative evidence for issuance, cancellation, ownership, cadastral, or legal decisions.

No illustrative fallback is needed for Phase 0. A production system still needs exact-source lineage, boundary-version dates, and a reliable distinction between project area, accounting area, leakage belt, and reference region.

## Sources checked

Counts below are not interchangeable. Some are whole-registry project counts; others are the nature-based subset for which the cited research dataset looked for geometry. Dates and scope are stated where they matter.

| Source | Machine-readable project geometry? | Format / download | License or terms found | Count | URL | Notes |
|---|---:|---|---|---:|---|---|
| Karnik et al., *An open-access database of nature-based carbon offset project boundaries* / Zenodo v1 | **Yes** | Six continental GeoPackages, index CSV, helper script | **CC BY 4.0** | **575 projects** in 55 countries; 533 polygons and 42 points | [Paper](https://www.nature.com/articles/s41597-025-04868-2); [Zenodo record and files](https://zenodo.org/records/11459391); [direct index CSV](https://zenodo.org/api/records/11459391/files/carbon_projects_database_index.csv/content) | Best open bulk source found. The record says 433 geometries came from registry/developer scraping and 127 from manual georeferencing/digitization; the remaining entries include method-derived/processed cases. It covers avoided deforestation, ARR, and improved forest management. EPSG:4326. Do not silently treat the manually georeferenced records as official. |
| CarbonPlan OffsetsDB | **Yes, for a forest subset** | Public vector PMTiles for polygons; project/credit metadata as zipped CSV or Parquet; public web API | CarbonPlan [Terms of Data Access](https://github.com/carbonplan/offsets-db-data/blob/main/docs/TERMS-OF-DATA-ACCESS.md): as-is; CarbonPlan claims no copyright in factual data, but underlying registries may claim rights. Boundary source is Karnik et al. | Docs say **500** polygon projects after filtering an earlier 537-record forest subset. The live probe returned **517** forest projects with geography; the current PMTiles contained **532 distinct IDs**. | [OffsetsDB](https://carbonplan.org/research/offsets-db); [data access](https://github.com/carbonplan/offsets-db-data/blob/main/docs/data-access.md); [processing notes](https://github.com/carbonplan/offsets-db-data/blob/main/docs/data-processing.md); [boundary PMTiles](https://carbonplan-offsets-db.s3.us-west-2.amazonaws.com/miscellaneous/project-boundaries.pmtiles); [CSV archive](https://carbonplan-offsets-db.s3.us-west-2.amazonaws.com/production/latest/offsets-db.csv.zip) | The 500/517/532 mismatch is real version drift between documentation, API, and map artifacts—not a count to hand-wave away. This probe used the PMTiles geometry and a CSV snapshot generated 2026-06-01. Tiles are a display derivative and quantize/simplify geometry. |
| Verra VCS registry and project documents | **Sometimes** | Per-project KML/KMZ or SHP attachments when supplied; many other projects expose only maps inside PDF/DOCX | [Verra Registry Terms of Use](https://verra.org/documents/verra-registry-terms-of-use/); no open bulk spatial-data license identified | Karnik v1 contains **294 Verra nature-based projects**, 92.9% polygon (~273); 26.5% required georeferencing. The 2026-06 OffsetsDB snapshot contains **4,983 Verra projects total**, but most do not have public geometry in OffsetsDB. | [Registry overview](https://verra.org/registry/overview/); [registry search](https://registry.verra.org/app/search/VCS); [example project page exposing a “Project Boundary (KML File)” attachment](https://registry.verra.org/verra/public/program/VCS/projects/4845) | Geometry exists, but not through a consistent open bulk endpoint. Availability is project-by-project and attachment URLs are not a stable API. The July 2026 registry transition also makes old URLs and automation brittle. |
| Gold Standard Impact Registry | **Sometimes, but not as a reliable bulk feed** | Project pages and documents; maps are common, KML/SHP inconsistent | [Gold Standard terms](https://www.goldstandard.org/terms-and-conditions). CarbonPlan records that Gold Standard requires downloads through interfaces Gold Standard provides; no open bulk boundary license identified. | Karnik v1 contains **17 Gold Standard nature-based projects**, 64.7% polygon (~11) and 64.7% georeferenced. The 2026-06 OffsetsDB snapshot contains **4,105 Gold Standard projects total**, not 4,105 polygons. | [Impact Registry](https://www.goldstandard.org/impact-registry); [project search](https://registry.goldstandard.org/projects?q=&page=1); [project-document mapping requirements](https://globalgoals.goldstandard.org/standards/101_V1.2_PAR_Principles-Requirements.pdf) | Public project documents are useful, but a map in a PDF is not a machine-readable polygon. Automated bulk scraping would be a bad licensing/terms bet. |
| Berkeley Carbon Trading Project — Voluntary Registry Offsets Database (VROD) | **No geometry** | XLSX/CSV-style tabular project and credit metadata | **CC BY 4.0** | The downloaded v2026-06 workbook states **11,468 offset projects** | [Official database page](https://gspp.berkeley.edu/berkeley-carbon-trading-project/offsets-database); [v2026-06 workbook](https://10edb8fc77.nxcli.io/assets/uploads/page/Voluntary-Registry-Offsets-Database--v2026-06.xlsx) | Excellent cross-registry identifiers, types, issuances, retirements, and vintages. There are no boundary coordinate/geometry columns, so this is an enrichment source, not a polygon source. |
| Global Forest Watch / WRI | **No carbon-project boundary corpus** | Raster/vector environmental datasets via API; formats include GeoTIFF, JSON, CSV, SHP, and GPKG depending on the dataset | Layer-specific. Check each dataset; do not assume one blanket license. The current GFW Hansen tree-cover-loss page exposes no license in its metadata. | **0 carbon-project polygons** | [GFW Data API](https://data-api.globalforestwatch.org/docs); [forest carbon gross removals](https://datasets.wri.org/datasets/gfw-forest-carbon-gross-removals); [Hansen tree-cover change](https://data.globalforestwatch.org/documents/gfw%3A%3Ahigh-resolution-global-maps-of-21st-century-forest-cover-change/about) | This is the right family of sources for forest-loss/carbon cross-checking after a project boundary is known. It does not solve the project-boundary acquisition problem. |
| Plan Vivo / S&P Global registry | **No open bulk geometry found** | Public project pages and PDF PDD/monitoring documents; no public boundary API or bulk KML/SHP collection found | Site/registry terms apply; no open reusable spatial-data license identified | Public portfolio exists, but no authoritative machine-readable boundary count is exposed; **0 bulk project polygons obtained** | [Plan Vivo registry](https://www.planvivo.org/buy-credits/pv-climate-registry); [Plan Vivo projects](https://www.planvivo.org/); [example project page](https://www.planvivo.org/projects/hieu-commune-vietnam-decertified) | Some documents may contain maps or coordinates. That is manual document research, not a dependable boundary feed. The current registry is managed through S&P Global infrastructure. |
| GitHub: `rhammell/forest-watch` | **Pipeline, not a maintained boundary release** | Python scraper converts qualifying Verra KML to GeoJSON/IPFS | Repository terms/license must be checked before reuse; no separate spatial-data license established by this probe | No fixed packaged project count stated | [Repository](https://github.com/rhammell/forest-watch) | Useful evidence that Verra KML attachments can be discovered and converted. It does not provide a versioned, quality-controlled, comprehensive boundary dataset. |
| GitHub: `carbonplan/bigcoast-project-boundary` | **Yes, one reconstructed example** | GeoJSON/reconstruction code | MIT for repository code; source geometry is explicitly approximate/reconstructed | **1 project** | [Repository](https://github.com/carbonplan/bigcoast-project-boundary) | This is not an official BigCoast boundary and is unsuitable as an “official” seed record. It was not included in `data/seed/`. |
| Google Earth Engine Community Catalog mirror of Karnik dataset | **Yes** | Earth Engine FeatureCollection asset | **CC BY 4.0** | **575 records** | [Catalog entry](https://gee-community-catalog.org/projects/carbon_projects/) | Convenient for cloud analysis. Asset: `projects/sat-io/open-datasets/CARBON-OFFSET-PROJECTS-GLOBAL`. It mirrors the Karnik corpus rather than adding independent provenance. |

## What was downloaded and created

### Seed set

- **40** files at `data/seed/<projectId>.geojson`, one GeoJSON `FeatureCollection` per project.
- **23** `avoided_deforestation`; **17** `afforestation`; **0** `other`.
- **39** Verra VCS projects; **1** Gold Standard project.
- **17 countries**: Belize, Bolivia, Brazil, Cambodia, Colombia, Democratic Republic of the Congo, Indonesia, Kenya, Laos, Madagascar, Mozambique, Nicaragua, Papua New Guinea, Peru, Tanzania, Uganda, and Zambia.
- Underlying Karnik processing approach: **25 Official**, **12 Georeferenced**, **3 Method-derived**. Every selected index record contains a project-area geometry; 12 also flag an accounting-area geometry. The PMTiles schema does not expose those roles, so the extracted map polygon must not be advertised as a verified accounting boundary.
- Polygon form: **18 Polygon**, **22 MultiPolygon**; 273,298 coordinate positions across 9,643 rings; total seed size 10,894,207 bytes.

Avoided-deforestation IDs:

`VCS562`, `VCS647`, `VCS812`, `VCS818`, `VCS852`, `VCS856`, `VCS934`, `VCS999`, `VCS1112`, `VCS1115`, `VCS1133`, `VCS1202`, `VCS1218`, `VCS1326`, `VCS1329`, `VCS1382`, `VCS1391`, `VCS1392`, `VCS1498`, `VCS1748`, `VCS1799`, `VCS2293`, `VCS2363`.

Afforestation/reforestation IDs:

`GLD3025`, `VCS142`, `VCS658`, `VCS665`, `VCS799`, `VCS1085`, `VCS1233`, `VCS1327`, `VCS1351`, `VCS1397`, `VCS1429`, `VCS1663`, `VCS1684`, `VCS1899`, `VCS2079`, `VCS2085`, `VCS2619`.

Supporting probe outputs:

- `SEED_MANIFEST.json`: project names, registry links, countries, vintages, source/retrieval URLs, bboxes, geometry types, position counts, and tile-fragment counts.
- `SEED_PROVENANCE.json`: per-project crosswalk to the Karnik index, including `Official` / `Georeferenced` / `Method`, methodology, source ID, component-role flags, and source dates.
- `KARNIK_PROJECT_INDEX.csv`: the open CC BY 4.0 index downloaded directly from Zenodo.
- `VALIDATION_REPORT.json`: machine-readable validation result.
- `SEED_SHA256.txt`: SHA-256 hashes for all 40 seed files.

Raw/reference downloads retained under `data/probes/`:

- `offsets-db.csv.zip` and `offsets-db-csv/`: the CarbonPlan snapshot generated 2026-06-01, used for registry metadata and vintage aggregation.
- `VROD-v2026-06.xlsx`: the Berkeley VROD workbook used to verify cross-registry coverage, CC BY 4.0 terms, and the absence of geometry columns.
- `offsets-db-data-source/` and `offsets-db-web-source/`: public CarbonPlan source checkouts used to verify data-access terms, boundary-processing notes, and the PMTiles endpoint.
- `carbonplan-geographic-forest-projects.json`: the live 517-record candidate response used for selection.
- `build_seed.mjs`, `probe_candidates.mjs`, `inspect_pmtiles.mjs`, `enrich_provenance.mjs`, and local `tooling/`: the reproducible probe/conversion code and its local JavaScript dependencies. These are working artifacts, not additional boundary sources.

### Selection and conversion method

1. Queried CarbonPlan's current OffsetsDB forest projects that report geography.
2. Prioritized tropical avoided-deforestation/REDD+ and ARR projects with polygon geometry, while retaining country diversity.
3. Read each project's bounding box and metadata from OffsetsDB.
4. Requested all intersecting zoom-12 tiles from CarbonPlan's public boundary PMTiles archive, decoded the `boundaries` vector layer, selected the matching `project_id`, and unioned tile fragments.
5. Wrote each result as EPSG:4326 GeoJSON with exactly the requested properties. `externalId` uses the native source ID (`GS3025` for the Gold Standard record); `projectId` retains the OffsetsDB identifier (`GLD3025`).
6. Added vintage years by aggregating the OffsetsDB credit rows in the 2026-06-01 snapshot.
7. Cross-checked every seed ID and type against the Karnik source index and recorded the source's processing approach separately. This caught one real metadata conflict: current OffsetsDB classified `VCS1899` as avoided deforestation, while the Karnik geometry index classified it as ARR. The [project developer's page](https://forestcarbon.com/projects/sumatra-merang-peatland-project) also explicitly lists ARR alongside Wetlands Conservation and Restoration, so the seed uses `afforestation`; `SEED_PROVENANCE.json` records both database values.

The per-feature `sourceUrl` points to the CC BY 4.0 Zenodo dataset. `SEED_MANIFEST.json` separately records the actual transformation input, CarbonPlan's PMTiles URL. `illustrative:false` means the geometry is a published representation of a named real project and was not fabricated for the demo. It does **not** mean “current registry-certified boundary.”

The six full Zenodo GeoPackages total 1,691,230,208 bytes (about 1.57 GiB), so they were not mirrored into this hackathon repository. That storage shortcut is why this starter set uses CarbonPlan's smaller public tile derivative and why replacing it with exact GeoPackage/direct-attachment geometry is the first production hardening step.

## Validation

`VALIDATION_REPORT.json` reports **PASS** for all 40 files:

- valid JSON and one feature per FeatureCollection;
- exactly the required property names;
- unique IDs and filename/ID agreement;
- only Polygon/MultiPolygon geometry;
- finite longitude/latitude values inside EPSG:4326 ranges;
- all rings have at least four positions and are closed;
- computed bboxes and position counts agree with `SEED_MANIFEST.json`;
- all `illustrative` values are the boolean `false`.

This is structural validation, not an independent survey or registry audit. It does not prove currentness, ownership, registry status, topological validity under every GIS engine, or that the polygon represents the accounting area rather than a broader project area.

## Gaps and risks

1. **No clean registry-wide spatial API exists.** Verra and Gold Standard sometimes publish machine-readable attachments, but coverage is inconsistent and terms do not support pretending there is a frictionless open bulk feed.
2. **“Boundary” is underspecified.** A project can have project areas, accounting areas, leakage belts, reference regions, nested parcels, and versioned expansions. Simple polygon overlap can generate false alarms unless each component's role and effective date are known.
3. **The seed is tile-derived.** Zoom-12 Mapbox vector tiles quantize coordinates and may simplify the source geometry. This is fine for hackathon-scale spatial screening, not fine for legal or credit-issuance conclusions.
4. **Provenance is mixed.** Only 25 of the 40 selected source records are marked `Official`; 12 were manually georeferenced and 3 were derived using a documented method. Present those categories visibly in the product.
5. **Artifacts drift independently.** CarbonPlan's documentation, live API, and PMTiles currently report different geography counts. Pin versions and hashes instead of silently consuming `latest` in production.
6. **Registry metadata can change.** Names, status, crediting periods, polygons, and registry URLs need refresh/version tracking. A polygon without an effective date is a future bug wearing a map costume.
7. **Satellite layers are a separate licensing problem.** GFW/WRI is useful for forest-loss evidence, but each layer's terms, temporal coverage, resolution, cloud masking, and uncertainty must be recorded independently.

## Recommendation

**Phase 0 verdict: enough real polygons; do not use illustrative fallback.** The 40-file seed is sufficient to build and demonstrate spatial indexing, overlap detection, bounding-box prefilters, map rendering, and satellite-loss joins.

For anything beyond a prototype, replace the zoom-12 tile reconstructions with the exact Zenodo GeoPackage features or direct registry KML/SHP attachments for the **25 Official** records first. Preserve the original files and hashes, store source component roles and effective dates, and show provenance quality (`official`, `georeferenced`, `method-derived`) in every match result. Until that is done, ClearCredit can honestly say “potential spatial overlap detected against a published research boundary”; it cannot honestly say “double counting proven.”
