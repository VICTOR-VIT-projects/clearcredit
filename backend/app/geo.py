"""Boundary validation, geodesic areas, exact overlap and the H3 cover registered on-chain."""
from __future__ import annotations

from dataclasses import dataclass
import math

import h3
from pyproj import Geod
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.validation import explain_validity

CELL_RESOLUTION = 8  # must match the deployed contract's cellResolution
MIN_AREA_HA = 1.0
MAX_AREA_HA = 3_000_000.0  # larger than the biggest known single REDD+ projects
MAX_VERTICES = 20_000

_GEOD = Geod(ellps="WGS84")


class GeometryError(ValueError):
    """Raised with a human-readable reason; the API maps it to INVALID_GEOMETRY."""


def _rings(boundary: dict):
    coords = boundary.get("coordinates")
    if not isinstance(coords, (list, tuple)) or not coords:
        raise GeometryError("boundary coordinates must be a non-empty array")
    polys = coords if boundary["type"] == "MultiPolygon" else [coords]
    for poly in polys:
        if not isinstance(poly, (list, tuple)) or not poly:
            raise GeometryError("each polygon needs an exterior ring")
        for ring in poly:
            if not isinstance(ring, (list, tuple)):
                raise GeometryError("each ring must be an array of positions")
            yield ring


def validate_boundary(boundary: dict) -> BaseGeometry:
    if boundary.get("type") not in ("Polygon", "MultiPolygon"):
        raise GeometryError("boundary must be a GeoJSON Polygon or MultiPolygon")
    n = 0
    for ring in _rings(boundary):
        n += len(ring)
        if n > MAX_VERTICES:
            raise GeometryError(f"too many vertices ({n} > {MAX_VERTICES}); simplify the boundary")
        if len(ring) < 4:
            raise GeometryError("each ring needs at least 4 positions (3 corners + closing point)")
        for position in ring:
            if not isinstance(position, (list, tuple)) or len(position) not in (2, 3):
                raise GeometryError("positions need longitude, latitude and optional altitude")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in position):
                raise GeometryError("coordinates must be finite numbers")
            lon, lat = position[:2]
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise GeometryError(f"coordinate out of range: [{lon}, {lat}] (expected [lon, lat] in EPSG:4326)")
        if list(ring[0]) != list(ring[-1]):
            raise GeometryError("ring is not closed: first and last positions differ")
    try:
        geom = shape(boundary)
    except (ValueError, TypeError) as e:
        raise GeometryError("invalid coordinate structure") from e
    if not geom.is_valid:
        # No silent make_valid: a repaired boundary is a different claim.
        raise GeometryError(f"invalid geometry: {explain_validity(geom)}")
    minx, _, maxx, _ = geom.bounds
    if maxx - minx > 180:
        raise GeometryError("boundaries crossing the antimeridian are not supported")
    area = area_ha(geom)
    if not MIN_AREA_HA <= area <= MAX_AREA_HA:
        raise GeometryError(f"implausible area {area:,.1f} ha (allowed {MIN_AREA_HA:g}–{MAX_AREA_HA:,.0f} ha)")
    return geom


def area_ha(geom: BaseGeometry) -> float:
    """WGS84 geodesic area; winding cannot cancel parts or add holes."""
    if geom.is_empty:
        return 0.0
    if geom.geom_type == "Polygon":
        area, _ = _GEOD.geometry_area_perimeter(orient(geom, sign=1))
        return abs(area) / 10_000
    return sum(area_ha(part) for part in getattr(geom, "geoms", ()))


@dataclass
class Overlap:
    project_id: str
    intersection_ha: float
    fraction_of_new: float
    fraction_of_existing: float


def find_overlaps(geom: BaseGeometry, others: dict[str, BaseGeometry]) -> list[Overlap]:
    """Exact overlap of `geom` against same-vintage claims. Shared edges (zero area) don't count."""
    own = area_ha(geom)
    out = []
    for pid, other in others.items():
        if not geom.intersects(other):
            continue
        inter = area_ha(geom.intersection(other))
        if inter <= 0.01:  # < 100 m²: numerical noise along a shared border
            continue
        out.append(Overlap(pid, round(inter, 2), round(inter / own, 4), round(inter / area_ha(other), 4)))
    return sorted(out, key=lambda o: -o.intersection_ha)


def h3_cover(boundary: dict, res: int = CELL_RESOLUTION) -> list[int]:
    """Cells whose CENTER lies inside the boundary.

    Center containment partitions space: two non-overlapping boundaries can never both
    contain the same cell center, so adjacent projects never collide on-chain. A boundary
    too small to contain any center falls back to the cell holding its representative point.
    """
    cells = h3.h3shape_to_cells(h3.geo_to_h3shape(boundary), res)
    if not cells:
        p = shape(boundary).representative_point()
        cells = [h3.latlng_to_cell(p.y, p.x, res)]
    return sorted(h3.str_to_int(c) for c in cells)
