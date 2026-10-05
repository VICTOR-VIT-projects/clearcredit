import copy
import json

import pytest

from app import canonical, geo

BOX = [[-63.10, -9.90], [-63.05, -9.90], [-63.05, -9.85], [-63.10, -9.85], [-63.10, -9.90]]


def claim(**over):
    c = {
        "schemaVersion": "1.0",
        "projectId": "TEST-001",
        "developer": "0x6958d2152447CCDbC42466B6b8AE5e379B3C95e8",
        "projectType": "avoided_deforestation",
        "vintageYear": 2023,
        "claimedCredits": 12000,
        "creditUnit": "tCO2e",
        "boundary": {"type": "Polygon", "coordinates": [BOX]},
        "boundaryCrs": "EPSG:4326",
        "dataLabel": "synthetic",
        "submittedAt": "2026-10-05T12:00:00Z",
    }
    c.update(over)
    return c


def box(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


# ---------------------------------------------------------------- canonical hashing

def test_hash_ignores_key_order_and_whitespace():
    c = claim()
    shuffled = json.loads(json.dumps(dict(reversed(list(c.items()))), indent=4))
    assert canonical.claim_hash(c) == canonical.claim_hash(shuffled)


def test_hash_ignores_ring_start_orientation_and_submitted_at():
    rotated = BOX[2:-1] + BOX[:2] + [BOX[2]]
    reversed_ring = list(reversed(BOX))
    base = canonical.claim_hash(claim())
    assert canonical.claim_hash(claim(boundary={"type": "Polygon", "coordinates": [rotated]})) == base
    assert canonical.claim_hash(claim(boundary={"type": "Polygon", "coordinates": [reversed_ring]})) == base
    assert canonical.claim_hash(claim(submittedAt="2030-01-01T00:00:00Z")) == base
    assert canonical.claim_hash(claim(developer=claim()["developer"].lower())) == base


def test_hash_ignores_sub_micro_degree_noise_but_not_real_changes():
    noisy = copy.deepcopy(BOX)
    noisy[1][0] += 1e-9
    base = canonical.claim_hash(claim())
    assert canonical.claim_hash(claim(boundary={"type": "Polygon", "coordinates": [noisy]})) == base
    assert canonical.claim_hash(claim(claimedCredits=12001)) != base
    assert canonical.claim_hash(claim(vintageYear=2024)) != base
    assert canonical.claim_hash(claim(dataLabel="real")) != base  # honesty label is tamper-evident


def test_micro_rounding_is_half_up_at_binary_ties():
    # 0.0078125 is exactly representable; Python's round-half-even would give 7812, JS toFixed 7813.
    assert canonical._micro(0.0078125) == 7813
    assert canonical._micro(-63.1) == -63100000


def test_multipolygon_part_order_does_not_matter():
    a, b = box(0, 0, 1, 1)["coordinates"], box(2, 2, 3, 3)["coordinates"]
    h1 = canonical.claim_hash(claim(boundary={"type": "MultiPolygon", "coordinates": [a, b]}))
    h2 = canonical.claim_hash(claim(boundary={"type": "MultiPolygon", "coordinates": [b, a]}))
    assert h1 == h2


def test_submission_key_matches_solidity_encode_packed():
    # keccak256(abi.encodePacked(bytes32(0x11..), address(0x22..), uint16(2023)))
    from eth_utils import keccak
    h, dev = "0x" + "11" * 32, "0x" + "22" * 20
    expected = "0x" + keccak(bytes.fromhex("11" * 32) + bytes.fromhex("22" * 20) + (2023).to_bytes(2, "big")).hex()
    assert canonical.submission_key(h, dev, 2023) == expected


def test_project_key_matches_ethers_id():
    # ethers.id("P1") == keccak256(utf8("P1"))
    assert canonical.project_key("P1") == "0x" + __import__("eth_utils").keccak(text="P1").hex()


# ---------------------------------------------------------------- geometry

def test_valid_box_area_is_geodesic():
    g = geo.validate_boundary(box(-63.10, -9.90, -63.05, -9.85))
    assert 3000 < geo.area_ha(g) < 3100  # ~5.48 km x 5.53 km


@pytest.mark.parametrize(
    "boundary, msg",
    [
        ({"type": "Point", "coordinates": [0, 0]}, "Polygon or MultiPolygon"),
        ({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}, "not closed"),
        ({"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]]}, "invalid geometry"),
        ({"type": "Polygon", "coordinates": [[[0, 0], [0, 95], [1, 95], [0, 0]]]}, "out of range"),
        (box(0, 0, 0.0001, 0.0001), "implausible area"),
        (box(0, 0, 40, 40), "implausible area"),
    ],
)
def test_invalid_boundaries_are_rejected_with_reasons(boundary, msg):
    with pytest.raises(geo.GeometryError, match=msg):
        geo.validate_boundary(boundary)


def test_overlap_fractions():
    a = geo.validate_boundary(box(0, 0, 0.1, 0.1))
    b = geo.validate_boundary(box(0.05, 0, 0.15, 0.1))  # half of each overlaps
    (o,) = geo.find_overlaps(b, {"A": a})
    assert o.project_id == "A"
    assert o.fraction_of_new == pytest.approx(0.5, abs=0.01)
    assert o.fraction_of_existing == pytest.approx(0.5, abs=0.01)


def test_shared_edge_is_not_an_overlap():
    a = geo.validate_boundary(box(0, 0, 0.1, 0.1))
    b = geo.validate_boundary(box(0.1, 0, 0.2, 0.1))
    assert geo.find_overlaps(b, {"A": a}) == []


def test_h3_cover_has_contract_resolution_and_adjacent_projects_never_share_cells():
    left, right = box(-63.10, -9.90, -63.05, -9.85), box(-63.05, -9.90, -63.00, -9.85)
    cl, cr = geo.h3_cover(left), geo.h3_cover(right)
    assert 35 < len(cl) < 50
    assert all(((c >> 52) & 0xF) == geo.CELL_RESOLUTION for c in cl)
    assert set(cl).isdisjoint(cr)  # center containment: shared border, zero shared cells
    assert set(cl) & set(geo.h3_cover(box(-63.08, -9.90, -63.03, -9.85)))  # real overlap collides


def test_tiny_polygon_still_gets_one_cell():
    assert len(geo.h3_cover(box(10.0, 10.0, 10.002, 10.002))) == 1
