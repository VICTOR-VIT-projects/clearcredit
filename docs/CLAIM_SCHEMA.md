# ClearCredit Claim Schema — v1.0

An open, versioned format for a carbon-credit claim. Any registry, buyer or auditor can produce a claim, recompute its hash, and compare it with the value registered on-chain. The machine-readable JSON Schema is served at `GET /schema`.

## Fields

| Field | Type | Required | Hashed | Notes |
|---|---|---|---|---|
| `schemaVersion` | `"1.0"` | yes | yes | Bumped on any change to fields or canonicalization. |
| `projectId` | string `^[A-Za-z0-9._:-]{1,64}$` | yes | yes | Stable, unique (e.g. `VCS1115`). On-chain key = `keccak256(utf8(projectId))`. |
| `developer` | `0x` + 40 hex | yes | yes (lower-cased) | Wallet that signs the claim (EIP-712). |
| `projectType` | `avoided_deforestation` \| `afforestation` \| `other` | yes | yes | |
| `vintageYear` | integer 2000–2100 | yes | yes | Uniqueness is enforced per (land, vintage). |
| `claimedCredits` | integer > 0 | yes | yes | Credits claimed for this vintage. |
| `creditUnit` | `"tCO2e"` | yes | yes | |
| `boundary` | GeoJSON `Polygon` \| `MultiPolygon` | yes | yes (canonicalized) | `[lon, lat]`, closed rings, valid geometry, 1 ha – 3,000,000 ha, ≤ 20,000 vertices, no antimeridian crossing. |
| `boundaryCrs` | `"EPSG:4326"` | yes | yes | |
| `sourceRegistry` | string ≤ 200 | no | yes | Registry name + external ID. |
| `boundarySource` | string ≤ 300 | no | yes | Provenance of the boundary and any processing (repair, simplification). |
| `dataLabel` | `real` \| `illustrative` \| `synthetic` | yes | yes | Honesty label. Being hashed makes it tamper-evident. |
| `submittedAt` | ISO-8601 string | no | **no** | Server metadata. Excluded so a retried submission hashes identically. |

Unknown fields are rejected.

API request bodies are limited to **2 MiB**, measured before JSON parsing (including
chunked requests). Oversized input returns HTTP 413 `REQUEST_TOO_LARGE`. Geometry traversal
stops at 20,000 vertices before constructing shapely/H3 objects; malformed coordinate
nesting returns HTTP 422 `INVALID_GEOMETRY`.

## Canonicalization (claimHash)

1. Remove `submittedAt` and every field whose value is `null`.
2. Lower-case `developer`.
3. Convert every boundary coordinate to **integer micro-degrees**: `floor(x * 1e6 + 0.5)`.
   Integers serialize the same way in every language. Decimal formatting does not: at exact binary ties such as `0.0078125`, Python rounds half-to-even and JavaScript's `toFixed` rounds up.
4. For each polygon:
   - Drop the closing vertex and any consecutive duplicate vertices.
   - Orient the exterior ring **counter-clockwise** and holes **clockwise** (RFC 7946). Orientation uses the exact integer shoelace sum.
   - Rotate each ring to start at its lexicographically smallest `[x, y]` vertex, then re-close it.
   - Sort holes lexicographically.
5. For a `MultiPolygon`, sort the parts by their canonical JSON string.
6. Serialize as JSON with **keys sorted by code point**, no whitespace, UTF-8, non-ASCII characters left unescaped.
7. `claimHash = keccak256(canonical bytes)`.

Reference implementation: `backend/app/canonical.py`. It is a standalone file that needs only `pip install eth-hash[pycryptodome]`.

```bash
python backend/app/canonical.py claim.json      # prints 0x… claimHash
```

**Test vectors:** `docs/claim-hash-vectors.json`. Every implementation (including the browser verifier) must reproduce each vector's `canonical` string and `claimHash` exactly. The vectors cover:
- key order and whitespace
- ring rotation and orientation
- the rounding tie case
- holes and Unicode
- `MultiPolygon` part order
- developer address case

## Derived keys

| Key | Definition | Use |
|---|---|---|
| `projectKey` | `keccak256(utf8(projectId))` | On-chain project ID (`bytes32`). |
| `submissionKey` | `keccak256(claimHash ‖ developer(20 bytes) ‖ uint16 vintageYear)` (Solidity `abi.encodePacked`) | Default `Idempotency-Key` for clients. |

## Developer signature (EIP-712)

The developer's wallet signs this typed data (gas-free) before the backend relays the claim:

```
domain:  { name: "ClearCredit", version: "2", chainId, verifyingContract }
types:   Claim(bytes32 projectId, bytes32 claimHash, uint16 vintageYear, uint64 claimedCredits, bytes32 cellsRoot)
```

The contract recovers the signer and requires it to equal `developer`. The domain binds the signature to one chain and one contract, so it cannot be replayed elsewhere. Because `claimHash` and `projectId` are unique, it cannot be replayed on the same contract either. `POST /claims/preview` returns the exact `typedData` to sign, and the contract's `claimDigest(...)` view exposes the digest for independent checking.

**Cell commitment (F2):** sort unique cell IDs numerically. Start `h0 = bytes32(0)`;
for each cell, `hi = keccak256(hi-1 || uint64(cell))`, with the cell encoded as **8 bytes
big-endian**, equivalent to Solidity `abi.encodePacked(bytes32,uint64)`. `cellsRoot = hN`.
The contract adds only new owned cells to its running hash, requires new cells in ascending
order across batches, and refuses finalization unless that hash equals the signed root.
Re-adding an owned cell is still a no-op. Preview includes `cellIds` (hex strings) and
`cellsRoot`; the frontend recomputes both claim hash and root and shows the list before
signing. It validates exact typed-data fields and current wallet account/network. Geometry
to H3 derivation still uses the backend; a list commitment does not prove boundary truth.

**Migration:** domain v2 and the new ABI require a fresh local contract. Existing v1
signatures/registrations are not migrated or replayed. Claim schema 1.0 vectors are unchanged.

## On-chain cell cover

The backend registers the H3 cells at **resolution 8** (~74 ha each) whose **centers** lie inside the boundary. The contract rejects any other resolution.

With non-empty center covers, disjoint boundaries do not share cells. A boundary too
small to contain any cell center registers its representative-point cell; two disjoint
small neighbours can therefore conflict. This conservative false positive requires
manual boundary review and resubmission after agreement; there is no on-chain exception
mechanism. Geometry must also remain valid after micro-degree quantization. The normal
center cover (before the fallback) is:

```python
h3.h3shape_to_cells(h3.geo_to_h3shape(boundary), 8)
```

## Versioning

Claim schema 1.0 hashing is unchanged. Project-history scoring itself does not change
the signing domain; the separate cell-commitment feature moves EIP-712 to v2.
Scoring model `rules-v4` uses evidence version `ev3`; this is separate from the claim
schema. The score's `attestationEvidence` contains the satellite evidence hash and
the issuance history (source snapshot hash, reference project, earlier vintages, median
and limitations). `score.evidenceHash = keccak256(UTF8(canonical._dumps(attestationEvidence)))`.
The satellite-only hash displayed in the evidence panel is one component, not the whole
attestation commitment. Scores with no satellite evidence still commit the explicit
no-evidence/no-history context. A cache/hash mismatch returns HTTP 503 `EVIDENCE_INVALID`.

Any change to fields or canonicalization rules creates a new `schemaVersion`. Hashes are only comparable within one version.

## Pending-registration recovery (F3)

At block `registeredBlock + 7200` or later, the developer (sending a wallet transaction)
or an account with DEFAULT_ADMIN_ROLE can call `cancelPendingRegistration(projectKey,
cellIds)`, with at most 300 IDs per batch. This sets status `cancelled` permanently and
clears only cells still owned by this project. Repeat batches until `cellCount == 0`;
duplicates/already released/other-owned cells are skipped. Project ID and claim hash stay
reserved for audit. Registered projects cannot be cancelled by this path. The clock is
blocks, not hours. The API reports terminal HTTP 409 `REGISTRATION_CANCELLED` on relay retry.
Operators obtain the full cell list from stored claim data/preview; events still expose
counts rather than every cell ID. UI cancellation controls are not provided yet.
