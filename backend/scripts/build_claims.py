"""Build claim files for the seed dataset: data/seed/*.geojson + real issuance → data/claims/real/*.json.

Each claim uses a real published boundary (Karnik et al. 2024, CC BY 4.0) and the real issued
quantity for its latest vintage (Berkeley/CarbonPlan OffsetsDB issuance records). The developer
address is a DEMO wallet derived from the project ID — not the real project proponent.

    python -m scripts.build_claims
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from eth_account import Account
from eth_utils import keccak
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

from app import geo, satellite

ROOT = Path(__file__).resolve().parents[2]
SEED, OUT = ROOT / "data" / "seed", ROOT / "data" / "claims" / "real"
CREDITS = ROOT / "data" / "probes" / "offsets-db-csv" / "credits.csv"
PROVENANCE = ROOT / "data" / "probes" / "SEED_PROVENANCE.json"
MAX_VERTICES = 5000


def demo_developer(project_id: str) -> str:
    return Account.from_key(keccak(text=f"clearcredit-demo-developer:{project_id}")).address


def n_vertices(g) -> int:
    polys = g.geoms if isinstance(g, MultiPolygon) else [g]
    return sum(len(p.exterior.coords) + sum(len(i.coords) for i in p.interiors) for p in polys)


def polygonal(g):
    """Keep only polygon parts (make_valid can emit lines/points along repaired edges)."""
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    parts = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
    flat = [q for p in parts for q in (p.geoms if isinstance(p, MultiPolygon) else [p])]
    return MultiPolygon(flat) if len(flat) > 1 else flat[0]


def prepare_boundary(geom) -> tuple[dict, list[str]]:
    notes = []
    if not geom.is_valid:
        geom = polygonal(make_valid(geom))
        notes.append("repaired to valid geometry (shapely make_valid)")
    original, tol = n_vertices(geom), 0.0001  # ~11 m
    for _ in range(5):  # up to ~180 m; every part keeps >= 4 vertices, so this alone may not converge
        if n_vertices(geom) <= MAX_VERTICES:
            break
        geom = geom.simplify(tol, preserve_topology=True)
        tol *= 2
    if n_vertices(geom) < original:
        notes.append(f"simplified from {original} to {n_vertices(geom)} vertices (tolerance <= {tol / 2:.4f} deg)")
    if n_vertices(geom) > MAX_VERTICES and isinstance(geom, MultiPolygon):
        # Highly fragmented boundaries (thousands of patches): keep the largest parts.
        parts = sorted(geom.geoms, key=lambda p: -p.area)
        kept, total = [], 0
        for p in parts:
            if total + n_vertices(p) > MAX_VERTICES:
                break
            kept.append(p)
            total += n_vertices(p)
        dropped_share = 1 - sum(geo.area_ha(p) for p in kept) / geo.area_ha(geom)
        if dropped_share > 0.05:  # would misstate the project's area (and its credits per ha)
            raise geo.GeometryError(f"too fragmented ({len(parts)} parts) to register faithfully under {MAX_VERTICES} vertices")
        notes.append(f"kept largest {len(kept)} of {len(parts)} parts; dropped parts are {dropped_share:.1%} of area")
        geom = MultiPolygon(kept)
    boundary = json.loads(json.dumps(mapping(geom)))  # tuples -> lists
    geo.validate_boundary(boundary)
    return boundary, notes


def issuance_by_vintage(ids: set[str]) -> dict[str, dict[int, int]]:
    out: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    with open(CREDITS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["project_id"] in ids and r["transaction_type"] == "issuance" and r["vintage"]:
                out[r["project_id"]][int(float(r["vintage"]))] += int(float(r["quantity"]))
    return out


def main():
    prov = {r["projectId"]: r for r in json.loads(PROVENANCE.read_text(encoding="utf-8"))["records"]}
    features = {}
    for f in sorted(SEED.glob("*.geojson")):
        feat = json.loads(f.read_text(encoding="utf-8"))["features"][0]
        features[feat["properties"]["projectId"]] = feat
    issued = issuance_by_vintage(set(features))
    OUT.mkdir(parents=True, exist_ok=True)
    built, skipped = [], []
    for pid, feat in features.items():
        p = feat["properties"]
        vintages = {v: q for v, q in issued.get(pid, {}).items() if v <= satellite.GFC_LAST_YEAR and q > 0}
        if not vintages:
            skipped.append((pid, "no issuance with a vintage covered by forest-loss data"))
            continue
        vintage = max(vintages)
        try:
            boundary, notes = prepare_boundary(shape(feat["geometry"]))
        except geo.GeometryError as e:
            skipped.append((pid, str(e)))
            continue
        approach = prov.get(pid, {}).get("processingApproach", "unknown")
        claim = {
            "schemaVersion": "1.0",
            "projectId": pid,
            "developer": demo_developer(pid),
            "projectType": p["projectType"],
            "vintageYear": vintage,
            "claimedCredits": vintages[vintage],
            "creditUnit": "tCO2e",
            "boundary": boundary,
            "boundaryCrs": "EPSG:4326",
            "sourceRegistry": f"{p['sourceRegistry']} {p['externalId']}",
            "boundarySource": "; ".join([f"Karnik et al. 2024 (Zenodo 11459391, CC BY 4.0) via CarbonPlan; approach: {approach}", *notes])[:300],
            "dataLabel": "real",
        }
        (OUT / f"{pid}.json").write_text(json.dumps(claim, indent=1), encoding="utf-8")
        built.append((pid, vintage, vintages[vintage], round(geo.area_ha(shape(boundary))), "; ".join(notes)))
    for b in built:
        print("built  ", *b)
    for s in skipped:
        print("skipped", *s)
    print(f"{len(built)} claims written to {OUT}, {len(skipped)} skipped")


if __name__ == "__main__":
    main()
