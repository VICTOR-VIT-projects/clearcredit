# Public retirement, history and registry-map reads

All endpoints are wallet-free and use numbered chain blocks. `observedBlock` identifies
the observation; it does not claim to include transactions mined afterward. If the
required block or contract read is unavailable, the API returns retryable 503
`CHAIN_READ_UNAVAILABLE`, with no partial chain outcome. Offline mode returns 503
`CHAIN_UNAVAILABLE` for retirement/history queries.

## Retirement by serial

`GET /claims/{projectId-or-claimHash}/retirements/{serial}?minBlock=0`

The serial is a nonnegative uint64 decimal integer. A retirement covers the half-open
range `[serialStart, serialEndExclusive)`: the start belongs to the range and the end
does not. A serial outside all records returns 404 `RETIREMENT_NOT_FOUND`, including
the observed block in error details. Invalid serials return 422.

The response includes `projectId`, `claimHash`, visible `dataLabel`, `beneficiary`,
`from`, `timestamp`, `transactionHash`, `transactionUrl`, `blockNumber`, `observedBlock`,
and decimal **strings** for `serial`, `serialStart`, `serialEndExclusive` and `amount`.
Strings prevent uint64 precision loss in browser JavaScript. A local chain has no
explorer URL; the transaction hash is still shown.

The record comes from `getRetirements` at one pinned snapshot. Binary search over numbered
block timestamps locates its event window; the API requires exactly one matching `Retired`
event (range, amount, sender and beneficiary). Missing event data is retryable unavailability,
not an invented link or a false not-found result. Claim metadata must hash to the chain
record before a retirement result is presented. The public UI is `/retirements`, linked
from the navigation, with shareable `/retirements/{projectId}/{serial}` routes.

## Bounded project history

`GET /claims/{ref}/history?fromBlock=...&toBlock=...`

The default window is the last 10,000 observed blocks, starting no earlier than the
project's registration block. A caller may select an ordered historical window of at
most 10,000 blocks. Future/reversed/oversized ranges return 422 `INVALID_BLOCK_RANGE`.
The response includes the requested bounds, observed block, project/data label,
`earlierHistoryOmitted`, and ordered events with transaction URLs/hashes, block/log
positions, names and decoded arguments. Integers beyond JavaScript's safe range are
decimal strings. Request successive windows to inspect earlier history; the endpoint
does not claim that one bounded response is a complete lifetime timeline.

Queries start in 2,000-block chunks, bisect provider-rejected ranges, deduplicate logs
and stop at 128 RPC range attempts or 1,000 returned events. Failure at a single block
or exhaustion fails the whole request; partial results are not returned. This is a read
of the contract's project events, not full reconstruction of cell IDs (which are absent
from CellsAdded). Provider compliance with numbered-block log semantics is assumed;
deep reorgs and providers silently lying about data need independent verification.

## Registry map

`GET /registry?offset=0&limit=200&includeBoundary=true&atBlock=...`

Boundary inclusion is opt-in. The response adds `observedBlock`; subsequent map pages
use the first page's explicit `atBlock`. The frontend loads every page on demand,
rejects detected pagination changes, and displays only projects Registered at that
snapshot. It shows all registered boundaries **known to this API**, not an enumeration
of undisclosed projects in other databases. Colors follow the saved integrity score band;
permanent labels include project ID, real/illustrative/synthetic category and score.
Labels are assigned with DOM textContent, not interpolated HTML. Map tiles use the existing
OpenStreetMap layer; satellite/evidence measurements are not fetched by these reads.

The prototype has no spatial database/index or map simplification layer. Loading a
large registry can be expensive; future work needs server-side spatial windows/tiles.
Boundary geometry and score metadata remain off-chain; use each claim's verifier to
compare its hash. An explicit historical block can correctly show Pending even when
the convenience DB currently says registered.

## Non-scoring evidence diagnostic

`GET /evidence/anomalies` checks committed cache summaries for all stored projects
(prototype cap 1,000, otherwise explicit `EVIDENCE_ANALYSIS_LIMIT`). The Registry page
has an on-demand **Check cached evidence** control. No satellite fetches occur.

Within a shared dataset/method and adjacent-year pair, at least ten independent boundary
observations are needed. A warning requires a median absolute NDVI step of at least 0.15,
with at least 80% of boundaries changing by at least 0.15 in that same direction.
Identical boundary keys across different vintages count once. Missing caches and inadequate
sample sizes are explicit; absence of a warning does not validate evidence. Each affected
project keeps its real/illustrative/synthetic label visible.

This is a review heuristic for common processing, scene-sampling or regional effects;
it does not attribute a sensor bug. The trigger was frozen before inspecting aggregate
cache results and is not calibrated for diagnostic accuracy. It is separate from scores,
attestation commitments and cached measurement values: rules-v4 and ev3 are unchanged.

After freezing that rule, the committed real-project caches yielded 30 independent
boundaries, zero missing caches and zero warnings. This is an observed cache result,
not diagnostic-accuracy validation. Tests exercise shared changes, mixed signs,
insufficient samples, method separation, boundary deduplication, missing/nonfinite values,
the inclusive step threshold and the API project limit. Decimal subtraction of serialized
observations prevents binary floating-point rounding from excluding an exact 0.15 step.

## Frontend regression coverage

Mounted component tests load `docs/sample-claim-response.json` into the actual Verify
page without wallet hooks, recompute its hash, require the confirmed receipt's minimum
block on refresh, and hide old totals/Match results when that refresh fails. A changed
claim clears the previous browser Match. Structured submission error tests cover overlap,
retryable chain-read 503, invalid evidence and unknown-code fallback. jsdom is a development
dependency for these DOM interactions. Real wallet extensions, maps, keyboard navigation
and visual browser acceptance still require the checks in `docs/ACCEPTANCE.md`.
