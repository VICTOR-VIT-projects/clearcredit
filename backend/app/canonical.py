"""Canonical claim encoding and hashing (ClearCredit claim schema 1.0).

Standalone on purpose: a third party can recompute a claim hash with only this file and
`pip install eth-hash[pycryptodome]`:

    python canonical.py claim.json

Rules (mirrored in docs/CLAIM_SCHEMA.md and the browser verifier):
  1. Drop `submittedAt` (server metadata, not claim content) and any null-valued field.
  2. `developer` is lower-cased.
  3. Every boundary coordinate becomes integer micro-degrees: floor(x * 1e6 + 0.5).
     Integers serialize identically in every language; decimal formatting does not.
  4. Per polygon: drop the closing vertex and consecutive duplicates, orient the exterior
     ring counter-clockwise and holes clockwise (RFC 7946), rotate each ring to start at its
     lexicographically smallest vertex, then re-close it. Holes are sorted; MultiPolygon
     parts are sorted by their canonical JSON.
  5. Serialize as JSON with sorted keys, no whitespace, UTF-8.
  6. claimHash = keccak256(canonical bytes).
"""
from __future__ import annotations

import json
import math
import sys

try:
    from eth_hash.auto import keccak
except ImportError:  # pragma: no cover
    sys.exit("pip install eth-hash[pycryptodome]")

EXCLUDED_FIELDS = {"submittedAt"}


def _micro(x: float) -> int:
    return math.floor(x * 1e6 + 0.5)


def _signed_area2(ring: list[list[int]]) -> int:
    """Twice the signed area (shoelace) on integer coords: exact, so orientation is deterministic."""
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))


def _canonical_ring(ring: list, ccw: bool) -> list[list[int]]:
    pts = [[_micro(p[0]), _micro(p[1])] for p in ring]
    dedup = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(dedup) > 1 and dedup[0] == dedup[-1]:
        dedup.pop()
    closed = dedup + dedup[:1]
    if (_signed_area2(closed) > 0) != ccw:
        dedup.reverse()
    k = dedup.index(min(dedup))
    rotated = dedup[k:] + dedup[:k]
    return rotated + rotated[:1]


def _canonical_polygon(rings: list) -> list:
    exterior = _canonical_ring(rings[0], ccw=True)
    holes = sorted(_canonical_ring(r, ccw=False) for r in rings[1:])
    return [exterior, *holes]


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_boundary(boundary: dict) -> dict:
    kind = boundary["type"]
    if kind == "Polygon":
        coords = _canonical_polygon(boundary["coordinates"])
    elif kind == "MultiPolygon":
        coords = sorted((_canonical_polygon(p) for p in boundary["coordinates"]), key=_dumps)
    else:
        raise ValueError(f"unsupported boundary type: {kind}")
    return {"type": kind, "coordinates": coords}


def canonical_claim(claim: dict) -> dict:
    out = {k: v for k, v in claim.items() if k not in EXCLUDED_FIELDS and v is not None}
    out["developer"] = out["developer"].lower()
    out["boundary"] = canonical_boundary(out["boundary"])
    return out


def canonical_bytes(claim: dict) -> bytes:
    return _dumps(canonical_claim(claim)).encode("utf-8")


def claim_hash(claim: dict) -> str:
    return "0x" + keccak(canonical_bytes(claim)).hex()


def project_key(project_id: str) -> str:
    """On-chain projectId: keccak256(utf8(projectId))."""
    return "0x" + keccak(project_id.encode("utf-8")).hex()


def submission_key(claim_hash_hex: str, developer: str, vintage_year: int) -> str:
    """keccak256(claimHash ‖ developer ‖ uint16 vintageYear), i.e. Solidity abi.encodePacked."""
    packed = bytes.fromhex(claim_hash_hex[2:]) + bytes.fromhex(developer[2:].lower()) + vintage_year.to_bytes(2, "big")
    return "0x" + keccak(packed).hex()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python canonical.py claim.json")
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    data = data.get("claim", data)  # accept a bare claim or an API response wrapping one
    print(claim_hash(data))
