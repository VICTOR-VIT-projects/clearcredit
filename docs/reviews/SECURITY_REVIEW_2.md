# ClearCredit continuation review — 2026-10-09

Baseline: `c5a4d53` on main. Work branch: `finish-and-harden`.
All findings below are confirmed by tracing unless a regression test is named.
No public RPC or environment-file contents were accessed for this review.

## Scope and conflicts

Brief 2 supersedes the old task list. EIP-712 remains v2 as already implemented by F2;
the older I2 v1 text is historical. R4's deployment prohibition is interpreted with
T3/T5's explicit local-deployment instructions: ephemeral local Hardhat deployments
are necessary tests; public deployment and publication remain prohibited.
Hardhat, Vite and the API have an explicit `CLEARCREDIT_NO_ENV=1` mode so test/demo
subprocesses need no environment-file access. Commits use the configured repository user.

## T1 — ranked findings and complete read inventory

Locations refer to baseline, before the fixes.

### S1 — HIGH: stale attestation reads can append duplicates

`backend/app/chain.py:216-225`: after `_reconcile` clears a confirmed transaction,
`attestations()` reads unpinned latest. A lagging node can omit that append, causing
another nonce and a second identical attestation. Fix: persist confirmed receipt heights
atomically with journal clearance, pin reads to at least that height, and maintain a
durable observed/confirmed attestation-count floor. Missing observations poll, then fail
closed. `test_stale_attestation_read_cannot_append_duplicate` injects pre-write state
once and asserts the nonce is unchanged; the receipt-timeout integration test also
exercises recovery after mining.

### S2 — HIGH: gas estimation and nonce reads can regress behind confirmed writes

`backend/app/chain.py:173-175`: `build_transaction` implicitly estimates against latest.
Polling project state does not ensure the *next RPC request* hits a caught-up node.
This affects register/add/finalize/attest/cancel and role grants using `_send`, not only
finalize. Fix: explicit `estimate_gas(block_identifier=known_height)`, then supply gas
to build_transaction; take the larger pending and pinned mined nonce. An unsupported
historical estimate fails closed before signing. Gas retains 20% headroom.
`test_gas_estimates_and_reads_are_pinned_after_receipts` asserts every contract call and
estimate is explicit, and forces latest below the persisted floor. Uncertain receipt
lookup followed by a nonce-too-low rebroadcast still fails closed with its journal intact.

### S3 — HIGH: API can store success before assembling a stale/incoherent response

`backend/app/main.py:110-136,237-238,259,304-320`: claim views mix independent latest reads;
success is stored before those reads; verification and registry statuses can regress or
come from the DB alone. A confirmed issue/retire followed by refetch can show old totals.
Fix: one pinned snapshot per claim view, observedBlock exposed, store registered only
after validation, and a retryable `CHAIN_READ_UNAVAILABLE` error for inaccessible blocks.
Registry reads one explicit height; verify uses a snapshot. Wallet refetch supplies
`minBlock` from a successful receipt; its query key changes, hiding old totals while the
required snapshot loads. A reverted receipt never triggers successful refresh.
Tests: `test_claim_response_stale_after_relay_never_stores_success`,
`test_wallet_receipt_minimum_block_is_required`,
`test_unavailable_receipt_block_fails_closed_after_restart`, frontend API tests.

### S4 — MEDIUM: reconciliation skips claims with the wrong latest attestation

`backend/scripts/reconcile.py:31-34`: any nonempty attestation list counts as consistent,
even if its latest score/model/hash differs from the saved intended result. Fix: one
pinned snapshot, exact latest-attestation comparison, and a final snapshot check before
storing registration. Per-claim read failures do not terminate the whole repair run.

### S5 — MEDIUM: cached successes and abandoned requests outlive the state they describe

`backend/app/main.py:181-182`; `backend/app/store.py:77-88`: cached 201 responses bypass
all chain reads, while an abandoned in-flight row has no expiry. T2 addresses both;
see the task resolution below.

### Inventory and classification

| Read / decision | Classification and treatment |
|---|---|
| Constructor `eip712Domain` | Harmless immutable version check; unavailable deployment fails construction. |
| Registration initial status, after-register state, batch completeness, final status | Needs receipt floor and pinned calls. Existing polling retained for defensive visibility checks. |
| `checkCells` admission / after register / chunked batches | Pin all chunks to one height. A stale admission precheck cannot authorize a conflict; the contract rechecks on write. Owned-cell retries remain no-ops. |
| `_complete` / `_reconcile` | Receipt is evidence of a write, not a state-read freshness promise. Atomically persist receipt height/count before clearing journal; next reads cannot go behind it. |
| Attestation latest / after append / retry | Pin and require observed count floor, including restart recovery. |
| Every `_send` gas estimate / pending nonce | Estimate pinned; nonce at least pinned mined count. Never fall back to latest on provider failure. |
| API claim / verify / registry | Pin; report observed snapshot, not DB chain outcomes. `minBlock` enforces wallet read-after-write. |
| Verifier re-score | Update saved result only after the chain post succeeds; evidence-only offline mode remains explicit. |
| Cancel | No backend cancel endpoint exists. Contract-authorized wallet cancellation is enforced on-chain; local `_send` cancellation uses the same estimate/receipt floor. Relay retries read cancelled at a pinned height and stop. |
| DeveloperActions receipt/refetch | Require receipt status success, propagate receipt block, and hide old query content during refresh/unavailability. Wallet simulation may reject on stale state; this is an availability failure and cannot report success. |
| Deploy role reads | Role identifiers already computed locally; receipt waits retained. Local-only execution here. Public role verification is a human task. |
| Fee estimates, chain ID, explorer URL | Do not assert a contract outcome; stale fees may delay/reject sends, retained journal handles uncertainty. |

Snapshots are observations at an explicit block, not a promise to know concurrent future
transactions. Latest may itself lag when no receipt/floor is known; this is labeled by
observedBlock. Previously observed heights are durable and never decrease. Deep reorgs,
provider lies about numbered-block semantics, multiple relayer processes and externally
replaced/stuck transactions require operator recovery; no blind nonce allocation follows.

## T2–T6 resolutions

Pending task execution; results and commit mapping will be recorded before completion.

## Validation and changes

| Task | Contracts | Backend | Frontend | Build |
|---|---|---|---|---|
| T1 | 36 | 83 | 17 | passed, zero type errors |

Commands run in their respective directories with `CLEARCREDIT_NO_ENV=1`:
`npx hardhat test`; `.venv/Scripts/python.exe -m pytest -q`; `npm test`; `npm run build`.
The existing venv works. One upstream Starlette/TestClient deprecation warning remains.

## Not done / deferred

Real-browser wallet flows, public reconciliation, submission video and publication are
human-only. No public transactions, pushes, accounts or new satellite fetches are allowed.
