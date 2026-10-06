# ClearCredit review — 2026-10-06

Phase A snapshot: `main` before any review changes; work branch `review-and-features`.
Locations below refer to that snapshot. Confirmed means traced in code or reproduced;
suspected means additional measurement or external validation is needed. No production
code changed during Phase A. This is a review of a prototype, not a security audit.

## Conflicts and safe scope

- The supplied working directory is the parent; the actual Git root is `clearcredit/`.
- The brief's “process-wide” relay lock is actually per `Chain` instance. Its zero-new-
  transaction promise after timeouts is stronger than its implementation (H1).
- The documented no-neighbour-conflict guarantee contradicts the representative-point
  fallback (M3). Keep the existing cover algorithm and correct the guarantee.
- The Python venv works here. Run pytest **from backend/**: invocation at the parent
  mistakenly collects ignored upstream probe tests and cannot import `app`.
- Existing Hardhat/Vite configuration automatically loads environment files. The initial
  backend integration invocation reached that existing loader before it was guarded;
  this was a boundary mistake against the instruction not to read `.env`. No contents
  were deliberately inspected, displayed or modified. All subsequent Node commands used
  a temporary preload that substitutes empty contents for environment files, including
  inherited Hardhat integration subprocesses. Only local Hardhat integration and committed
  satellite evidence were used. Public deployment is outside authorization.

## Findings (most severe first)

### H1 — HIGH, confirmed: receipt timeout can allocate a second nonce

**Location:** `backend/app/chain.py:113-121,140-146`; `backend/app/main.py:170-178,213-215`.
`_send` broadcasts before waiting, but returns its hash only after confirmation. A timeout
loses the hash; the API releases the key and sets `relay_failed`. Retry reads *mined* state,
not pending state, and uses the next pending nonce. Scenario: attestation N broadcasts →
receipt timeout → no attestation yet visible → retry broadcasts identical attestation N+1
→ both mine → two append-only attestations. Registration's unique ID prevents a second
successful registration but does not prevent a second transaction/revert; cell batches
can duplicate successfully. The existing outage test fails *before* sending, so misses this.
**Fix:** journal the signed transaction/hash before broadcast, persist uncertainty across
restarts, reconcile/wait or rebroadcast the same bytes and nonce, and block allocation
behind an unresolved transaction. Serialize state checks with sends. Test automining-off
timeouts and process reconstruction, not only pre-send failures.

### H2 — HIGH, confirmed: geodesic area cancels across orientations

**Location:** `backend/app/geo.py:58-63,81-84`.
`Geod.geometry_area_perimeter` returns signed area. Taking one absolute value after adding
parts permits cancellation. Reproduced: two equal 0.1° squares, one clockwise and one
counter-clockwise, total approximately zero versus 24,618 ha separately. Holes with the
same winding as their exterior add area instead of subtracting it. Intersection results
also have independent orientation. Scenario: overlap intersections with mixed part
orientations shrink below the blocker; a larger boundary can evade the area cap.
**Fix:** orient each polygon exterior/holes consistently, sum absolute per-part areas,
including polygon parts in geometry collections. Test holes, mixed parts and overlaps.
Version the changed scoring inputs and rerun evaluation without changing thresholds.

### H3 — HIGH, confirmed: concurrent submissions bypass exact overlap admission

**Location:** `backend/app/main.py:185-203`; `backend/app/store.py:51-57,71-76`.
The idempotency lock protects only one key lookup/insert. Different keys can both analyze
before either claim is inserted. Scenario: two sliver-overlapping boundaries sharing no
H3 center simultaneously pass `same_vintage`, both insert and both register; exact ≥1%
overlap admission is bypassed. Same ID with different keys can instead produce an uncaught
SQLite unique violation. **Fix:** serialize admission through insertion (and same-project
resumption), returning a structured duplicate/conflict. Explicitly restrict deployment
to one worker until cross-process admission and relayer coordination exist. Test threads
with different keys, different IDs and conflicting boundaries.

### H4 — HIGH, confirmed: unbounded parsing and malformed geometry reach expensive code

**Location:** `backend/app/models.py:22-24`; `backend/app/geo.py:33-45`;
`backend/app/main.py:141-160`.
No byte limit precedes JSON/Pydantic parsing. Geometry iterates the complete vertex input
before checking its cap; arbitrary nested `Any` values can raise `TypeError`/unpacking
exceptions rather than `INVALID_GEOMETRY`. Scenario: very large JSON exhausts memory or
many malformed requests tie up workers; `coordinates=[null]` causes a 500.
**Fix:** stream-limit bodies before parsing, stop vertex traversal immediately at the cap,
validate nesting/finite numeric positions before shapely/H3, and return safe structured
errors. Test missing Content-Length, understated Content-Length and malformed nesting.

### M1 — MEDIUM, confirmed: signed claim does not commit the cell list

**Location:** `contracts/contracts/ClearCreditRegistry.sol:115-119,139-147`.
A registrar holding a valid signature can substitute or append unrelated cells and
finalize early. Scenario: signed boundary A, arbitrary cells B registered under its hash.
This requires a compromised/trusted registrar but contradicts broad consent language.
**Fix:** F2 end-to-end signed cell commitment, EIP-712 v2, sorted running commitment and
finalization equality; keep schema 1.0 claim hashing frozen. Until then disclose T5 residual.

### M2 — MEDIUM, confirmed: Pending projects hold cells indefinitely

**Location:** `contracts/contracts/ClearCreditRegistry.sol:121-149`.
There is no expiry/release path. A failed relay or malicious registrar can squat cells
forever. **Fix:** F3 bounded cancellation after a block delay, admin/developer authorization,
release only cells still owned, preserve audit events and prohibit cancel after issuance.

### M3 — MEDIUM, confirmed: tiny neighbouring boundaries can conflict

**Location:** `backend/app/geo.py:95-98`; `docs/CLAIM_SCHEMA.md:81`;
`docs/THREAT_MODEL.md:30`; `docs/ARCHITECTURE.md:85`.
Two disjoint small polygons in one cell contain no center, so both fallback to that cell.
The “never collide”/“no residual” language is false for these supported inputs.
**Fix:** retain the conservative fallback, disclose its false positives and manual boundary
dispute path; add a tiny-neighbour regression test. Avoid inventing an untested exception.

### M4 — MEDIUM, confirmed: raw geometry may become invalid at hash precision

**Location:** `backend/app/geo.py:45-55`; `backend/app/canonical.py:43-53`.
Only raw geometry is validated. A >1 ha long polygon less than half a micro-degree wide
can quantize to a line; narrow holes can touch their exterior after rounding. Its hash
then describes a degenerate boundary while evidence/H3 use the raw boundary.
**Fix:** reject geometry invalid at frozen micro-degree precision. Do not change ring
canonicalization or old vectors. Test collapsed rings and touching holes.

### M5 — MEDIUM, confirmed: evidence bundle lacks raw scene provenance

**Location:** `backend/app/satellite.py:153-179,185-206`.
The hash commits reported summaries/method/date, not scene IDs, individual masks, selected
assets or their versions. A future STAC query may select different least-cloudy scenes.
Cached hashes also are not recomputed on read. **Fix:** validate cache commitment before
use; future evidence version should record scene/item IDs and processing parameters.
Do not rewrite ev2 numbers or fetch new evidence in this task.

### M6 — MEDIUM, confirmed: verifier retains a result from another claim

**Location:** `frontend/src/pages/VerifyPage.tsx:83-86,104-107`.
`localResult` survives navigation/refetch. Recompute A → navigate to B in the same component
→ A's green Match can remain beneath B. Invalid/tampered geometry can also throw directly
inside the button handler. **Fix:** bind the result to exact claim content and chain hash,
hide it when either changes, and render recomputation errors without a page crash.

### M7 — MEDIUM, confirmed: wallet changes leave stale prepared submissions

**Location:** `frontend/src/pages/SubmitPage.tsx:91-100,181-209,278-281`.
Only field edits invalidate preparation. Account A checks, account changes to B, then B
signs A's claim → avoidable BAD_SIGNATURE; network/account can change during async preview.
**Fix:** capture/check wallet identity and chain at preview/sign completion, invalidate
stale preparation, and preserve an already signed retry payload deliberately.

### M8 — MEDIUM, confirmed: stale idempotency/relaying records after a crash

**Location:** `backend/app/store.py:60`; `backend/app/main.py:186-189`.
Crash after `idem_begin` leaves the same key REQUEST_IN_PROGRESS forever; after insertion,
a different key sees `relaying` as duplicate rather than resumable. **Fix:** durable worker
leases/recovery coordinated with the transaction journal. Do not expire keys blindly
while an original worker may still submit. Document restart recovery until implemented.

### M9 — MEDIUM, suspected: sparse/polar geometries can cause excessive H3 work

**Location:** `backend/app/geo.py:49-54,95`; `backend/app/satellite.py:111-145`.
Area/vertex caps do not bound span or H3 candidate enumeration. Thin, widely separated
MultiPolygon parts and near-pole shapes need resource measurements; raster data may not
cover them. **Fix:** benchmark offline, bound cover count/span with explicit domain
restrictions, and never silently reinterpret antimeridian or polar geometry.

### L1 — LOW, confirmed: token comparison and RPC error leakage

**Location:** `backend/app/main.py:215,253`.
Default-unset admin token fails closed (good); ordinary string comparison is not timing
safe. RELAY_FAILED includes arbitrary exception text that can expose RPC details.
**Fix:** `secrets.compare_digest` on bytes and generic client error with server-side logs.

### L2 — LOW, confirmed: events do not reconstruct the cell list; views grow unbounded

**Location:** `contracts/contracts/ClearCreditRegistry.sol:65,167-168,228-240`.
CellsAdded emits counts, not IDs. An event-only indexer cannot rebuild cell ownership;
it needs calldata. `checkCells`, getAttestations and getRetirements can exceed RPC limits.
Strings in attest/retire are unbounded (authorized callers pay gas). **Fix:** emit cell
IDs and paginate read history in a later contract revision; backend already chunks
checkCells at 2,000. Do not claim an event-only full reconstruction today.

### L3 — LOW, confirmed: documentation exceeds implemented acceptance evidence

**Location:** `README.md:11,26,102`; `docs/ARCHITECTURE.md:56,85,105`;
`docs/THREAT_MODEL.md:40`; `docs/EVALUATION.md:9`.
Verifier transaction list is backend relay metadata, not full event history (wallet
issue/retire tx links absent). Architecture still says 300-cell relay batches versus
actual 200. Evaluation has no project held-out split for this fixed rule model, despite
T13 saying held-out. Reproduction suggests find-boxes, which fetches new satellite data.
Deployed address remains a placeholder; clean-clone browser/wallet acceptance and video
are not evidenced. **Fix:** describe observed scope, cached-only run command, correct
batches/evaluation wording, and list deployment/video/browser checks as human acceptance.

### L4 — LOW, suspected: light-mode medium-band contrast and boundary textarea label

**Location:** `frontend/src/styles.css:20,175`; `frontend/src/pages/SubmitPage.tsx:248-257`.
Amber `#b87208` on white likely falls below small-text AA; visual “Boundary GeoJSON” is
not associated with the textarea. **Fix:** measure contrast; darken light-mode amber and
use htmlFor/id. Verify keyboard focus and both themes in a browser.

## Checks with no demonstrated vulnerability

- Contract mutations have role/developer checks; default role admin is DEFAULT_ADMIN_ROLE.
  Admin renunciation can permanently remove recovery if it was the last admin: operator
  risk, use multisig/rotation runbook. Constructor permits zero admin/invalid H3 resolution:
  deployment validation is desirable. No external calls in state transitions. Solidity
  checked arithmetic prevents uint64 issuance/retirement and uint32 cell-count wraparound.
- Installed OpenZeppelin ECDSA rejects high-s and zero recovery. EIP712 binds chainId and
  contract. Outsiders cannot front-run registrar-only registration; a registrar cannot
  redirect credits to itself without a matching developer signature. A legitimate signature
  replay under another contract/domain fails. Cell-resolution checks validate only those
  bits, not full H3 validity; registrar remains responsible for valid cell IDs.
- Bounded 300-cell writes are documented around 7M gas, below 2^24. Relay uses 200. Long
  strings and unlimited history views still need production RPC bounds (L2). No claim of
  newly measured worst-case gas here.
- Canonical Python/TS implement the same half-up quantization, integer shoelace (TS BigInt),
  ring rotations, numeric hole ordering, code-point MultiPolygon ordering, key sorting,
  UTF-8 and submittedAt exclusion. Safe credits cap is 2^53−1. Unrestricted 1e21 numbers
  could format differently but cannot enter accepted schema 1.0 claims. Pydantic rejects
  lone surrogates (probed); U+2028/non-BMP text and negative zero need more vectors. Empty,
  duplicate and touching rings are geometry validation concerns, not permission to change
  frozen hashing. No accepted-input cross-language divergence demonstrated.
- `Store.find` interpolates only one of two fixed column names; values are parameterized.
  No SQL injection found. SQLite CREATE IF NOT EXISTS is not a migration framework.
- Forest tile intersections skip touching-only edges; pixel windows are clipped. NDVI
  requires three years, otherwise slope=None. Mask drops clouds/shadow/no-data but keeps
  water/snow/unclassified; no minimum spatial coverage or same-season sampling. BOA offset
  is removed for baseline ≥04.00. These evidence semantics need a new evidence version
  for changes. No satellite data was requested for review probes.
- Scoring explicitly labels missing evidence/future loss coverage, but “consistent with
  protection” and NDVI text for `other` are stronger than the signals alone support. The
  50–59 medium band is still below issuance threshold: a band is not issuance eligibility.
  Retain frozen rules absent a versioned, evaluated change.
- UI labels real/illustrative/synthetic on claim and registry cards; React escapes text.
  Structured API errors generally render; unknown codes fall back to server text. Wallet
  rejection renders client error, wrong-network buttons are disabled; contract domain is
  the final replay protection. Component tests and real-browser checks remain necessary.

## Phase A validation

Contracts: 29 passed. Backend: 47 passed (one upstream TestClient deprecation warning).
Frontend: 5 passed; production build passed with zero type errors. The unrestricted
venv interpreter works; no substitute Python used. Baseline cached evaluation reproduced
rules-v2: recall .716, precision .973, false alarms 2/30, inflation 3/30; unchanged thresholds.

## Changes made

The initial review contains **0 critical, 4 high, 9 medium and 4 low** findings (no nits):
15 confirmed and 2 suspected. L4 was subsequently confirmed by contrast measurement;
M9 remains suspected. All four high findings have regression tests demonstrated failing
against the old implementation and passing after the corresponding fix.

| Commit | Finding / feature | Result |
|---|---|---|
| `7a8e477` | Phase A | Ranked review recorded before production changes. |
| `3830bec` | H1 | SQLite journal persists signed public transaction bytes/hash before broadcast. Retry reconciles or rebroadcasts the same nonce/bytes; unresolved transactions block nonce allocation. Tests cover reconstruction, late mining with automining disabled, and a different operation behind an unresolved send. |
| `83a426c` | H2 | Normalize each polygon's winding, subtract holes and sum polygon parts independently. Version rules-v3; cached evaluation unchanged. |
| `a340815` | H3 | Serialize admission through insertion/resumption within one worker. Different-key concurrent overlap test now blocks the second claim. |
| `6586ed1` | H4; L1 | Stream-limit requests to 2 MiB before JSON parsing, validate nesting/finite positions and stop at the vertex cap. Timing-safe admin token comparison and generic relay errors. |
| `555f0d0` | M3, M4 | Reject geometry invalid at frozen hash precision; add tiny-neighbour fallback regression and disclose conservative cell conflicts. Canonicalization and original vectors unchanged. |
| `b82fe80` | M6; L3, L4 | Bind browser recomputation to claim content plus chain hash and handle malformed content. Correct documentation scope; associate textarea label and improve light warning-text contrast from 3.85:1 to 5.29:1. Add three cross-language vectors without changing the original five. |
| `15fced9` | F1; partial M5 | Commit offline issuance-history snapshot and hash-bound ev3 attestation bundle, validate committed evidence on read, and add rules-v4 history screening. Tests, decision row and evaluation/documentation updates included. |
| `eac2a25` | F2, F3; M1, M2, M7 | EIP-712 v2 cell consent completed across contract/backend/frontend, with running commitment checked at finalization. Developer/admin can cancel expired Pending projects and release owned cells in bounded batches. Wallet account/network revisions invalidate stale preparation. Tests and migration/cancellation docs included. |
| `49f1dc8` | F4 | Two separate registrars share one contract; Registry B's same-vintage land claim is rejected on-chain. Local script and real-H3 backend integration pass; docs and decision row included. |

No dependencies were added. F2 deliberately supersedes brief invariant I2 as explicitly
authorized by F2: fresh local deployment is required, v1 contracts/signatures cannot be
reused, and schema 1.0 claim hashing remains unchanged. Contract ABIs and OpenAPI were
updated. `dataLabel` remains visible and demo wallets remain distinct from real proponents.

### Validation after each phase

| Phase | Contracts | Backend | Frontend tests | Production build |
|---|---|---|---|---|
| A | 29 passed | 47 passed | 5 passed | passed, zero type errors |
| B | 29 passed | 65 passed | 10 passed | passed, zero type errors |
| C, final F1–F4 | 36 passed | 76 passed | 15 passed | passed, zero type errors |

Commands, each from the named directory:

```powershell
# contracts/
npx hardhat test
# backend/
.venv/Scripts/python.exe -m pytest -q
# frontend/
npm test
npm run build
# backend/, cached-only evaluation
.venv/Scripts/python.exe -m scripts.evaluate run
# contracts/, ephemeral local F4 demonstration
npx hardhat run scripts/multi-registry-demo.ts
```

Node commands after the initial invocation inherited an environment-file guard via
`NODE_OPTIONS=--require=<temporary clearcredit-no-env.cjs>`. The existing backend venv
worked; no alternate interpreter or system installation was used and no commands remained
blocked. Backend emits one upstream Starlette/TestClient deprecation warning. The final
working tree has no failing tests. Real-browser wallet acceptance remains separate.

### Evaluation before / after

Rules-v2 → rules-v3 corrected area inputs without changing any threshold; metrics stayed
unchanged. Rules-v4 / ev3 then added the frozen history rule (>3× median of at least three
earlier positive issuance vintages, −50). Satellite measurements were preserved from ev2.

| Metric | rules-v2/v3 before | rules-v4 after |
|---|---|---|
| Recall | .716 (73/102) | .843 (86/102) |
| Precision | .973 | .956 |
| False alarms | 2/30 | 4/30 |
| Inflation flagged | 3/30 | 16/30 |
| Duplicate / shifted / relocated | 30/30 · 29/30 · 11/12 | unchanged |

The gain comes with two additional false alarms, VCS1233 and VCS142. History is sufficient
for 19/30 projects; the other 11 explicitly report no history with no deduction. Registry
affiliation, historical boundary changes and methodology changes are not authenticated.
These are screening results on injected faults, not findings about the real projects.
See `docs/EVALUATION.md` for the full before/after evidence and limitations.

## Not done / deferred

Feature work stops after **F4** to preserve completed, tested behavior. F5's woodland-aware
rule cannot be justified by simply lowering a threshold on cached >30% canopy aggregates:
those summaries cannot reconstruct ≥10% canopy area. New satellite measurements are
forbidden, and fitting a special case to VCS562 would violate the evaluation rule. F5 is
deferred pending suitable offline measurements and an independently justified rule.
F6–F10 are deferred at this quality cutoff: cross-project evidence anomaly checks, registry
map, retirement lookup, complete one-command demo/rate limits/on-chain history, and broad
frontend component coverage. Parts of F9/F10 landed with fixes (request-size limit and
focused frontend verification/signing/history tests); that does not make the whole features
complete. F3 cancellation is documented as a contract operation; there is no cancellation UI.

Remaining findings and limitations:

- **M5, partial:** cache commitments are checked and ev3 binds history, but raw scene/item
  IDs, masks and selected asset provenance remain absent. Future evidence work needs a
  separately versioned reproducible processing manifest.
- **M8:** a crash can still strand an in-flight idempotency key or `relaying` claim.
  Transaction uncertainty is durably journaled, but automatic worker leases/claim recovery
  remain unfinished. Never clear records blindly while a worker or transaction may be live.
- **M9, suspected:** sparse/polar cover-cost bounds and the 1,000-claim overlap benchmark
  remain unmeasured. Single-worker admission is supported; cross-process coordination is
  not. A stuck or externally replaced journaled transaction fails closed and needs operator
  recovery, rather than allocating another nonce.
- **L2:** event-only full cell/history reconstruction, paginated reads and bounded strings
  remain deferred. Cell commitments bind consent but do not emit the complete cell list.
- **M3:** conservative fallback can intentionally reject tiny disjoint neighbours sharing
  a cell. Documentation now states this; a manual boundary dispute path remains necessary.
- **L3/L4 acceptance:** real-browser accessibility and wallet flows remain unverified.
  Automated checks are useful but do not establish keyboard focus or wallet-extension UX.

Human acceptance must check: fresh local v2 deployment/configuration without reusing a v1
address; clean-clone setup using committed snapshots; account/network switches during
preview/signing; rejection and signed retries; wallet issue/retire and serial display;
verifier navigation/refetch and tampered claims; data labels in both themes; keyboard
focus/labels; and expired Pending cancellation across release batches. Public deployment,
address publication and submission video are separate human tasks outside this authorization.
No remote push or public deployment was performed.
