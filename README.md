# ClearCredit

**Carbon-credit integrity and double-counting checker.** IEEE ClimateChain Global Hackathon 2026, track: *Carbon Markets & Emissions Transparency*.

A project developer submits a carbon-credit claim: a boundary polygon, a vintage year and the credits claimed. ClearCredit then:

1. **Registers a tamper-evident claim** on an EVM chain (Base Sepolia). The developer signs it with their wallet; the canonical claim hash goes on-chain.
2. **Blocks double counting.** The same land in the same vintage cannot be claimed twice: exact polygon overlap is checked off-chain, and an H3 cell index is enforced on-chain. Credits cannot be retired twice.
3. **Cross-checks the claim against independent satellite data:** Hansen Global Forest Change tree-cover loss (to 2025) and the Sentinel-2 NDVI trend.
4. **Publishes a transparent integrity score** (0–100) with plain-language reasons, as an append-only on-chain attestation. The contract refuses to issue credits while the score is below the threshold.
5. **Offers public verification and retirement lookup.** Anyone, with no wallet, can inspect a claim, recompute its hash in the browser, and see evidence and on-chain records. Retirement lookup resolves a serial to its beneficiary, range and matching transaction. Registry boundaries have an on-demand map; a bounded history API exposes project events. See `docs/PUBLIC_LOOKUPS.md` for snapshot and range limits.

> **What this proves, and what it doesn't.** The chain proves a record was **not altered** and **enforces uniqueness**. It does **not** prove physical truth. Satellite data is evidence, not certification. Outputs are an *integrity score* and a *verified integrity attestation*, never a "certified emission reduction". A low score means *flagged as suspicious*, not proven fraud.

## Why it matters

The same forest can back credits in two registries, or two projects can claim overlapping land for the same year. Retired credits can be counted again. Weak verification lets claims stand even when satellite imagery shows the forest was cleared. ClearCredit offers a shared uniqueness check for participating registries, published as an open schema and API that buyers and auditors can inspect.

## Demo flow

| Step | What you see |
|---|---|
| Legitimate project | Passes the overlap check; satellite evidence is consistent; high score; registered on-chain. |
| Duplicate claim on the same land and vintage | **Blocked**, naming the conflicting project and the overlap fraction. |
| Bypass the backend (second operator, empty database) | **Still blocked by the contract's cell index.** |
| Avoided-deforestation claim where Hansen shows clearing | Low score with reasons; the contract **refuses issuance**. |
| Retry the same submission | Same saved claim/result, refreshed chain observations, **zero new transactions** for a completed registration. If chain state is unavailable, retry fails closed. |
| Retire more credits than were issued | **Reverts on-chain** (`ExceedsIssued`); serial ranges never overlap. |
| Edit the stored claim off-chain | Verifier recomputes the hash → **mismatch** with the on-chain hash. |

## Data

Multi-registry local demo: `cd contracts` then
`npx hardhat run scripts/multi-registry-demo.ts`. Two distinct registrars share an
ephemeral local contract: A registers, B's same-cell/same-vintage attempt is blocked.
The script labels its synthetic indices; a backend integration test also covers real
H3-derived cells with separate registrar accounts and no API prechecks.

- **30 real projects** (Verra and Gold Standard) in 15 countries. Boundaries are from the open Karnik et al. 2024 dataset (CC BY 4.0, via CarbonPlan); credits are each project's **real issued quantity** for its latest vintage covered by forest-loss data (OffsetsDB issuance records). Repairs and simplifications are recorded in each claim's `boundarySource`. See `data/probes/POLYGON_SOURCES.md`.
- **Synthetic test cases** are labelled `synthetic` everywhere, including on-chain-hashed claims and the UI.
- Seed claims use **demo developer wallets**, not the real proponents. Scores on real projects reflect our processed boundary and public data; they are **not findings about those projects**.

## Evaluation

Faults are injected into the 30 real claims: duplicates, shifted overlaps, ×5 credit inflation, and claims relocated onto frontier land with recorded clearing. The rule-based score is compared with a uniqueness-only baseline (overlap check, no evidence layer). Thresholds were frozen before running.

| | ClearCredit | Uniqueness-only baseline |
|---|---|---|
| Recall (102 injected faults) | **0.843** | 0.578 |
| Relocated onto cleared land | **11/12** | 0/12 |
| False alarms on the 30 real projects | **4/30** | 0/30 |

`rules-v4` adds a project-history jump check using the frozen local issuance snapshot:
more than 3× a median of at least three earlier vintages deducts 50 points; absent or
insufficient history is visible with no deduction. Inflation detection rises from 3/30
to **16/30**, but false alarms rise from 2/30 to **4/30** and precision falls from .973
to **.956**. The new alarms require historical boundary/methodology context. The existing
dryland canopy alarm and unattributed disturbance alarm remain. Light clearing below
~2% of remaining forest per year still passes. Details: `docs/EVALUATION.md`. Metrics
measure injected faults on this dataset, **not real-world fraud prevalence**.

## Architecture

```
React UI (wagmi) ──► FastAPI backend ──► SQLite (claims, idempotency)
     │                 │  geometry · exact overlap · H3 cover
     │                 │  Hansen GFC + Sentinel-2 evidence (cached)
     │                 │  rule-based score + reasons
     │                 └─► ClearCreditRegistry (Base Sepolia): signed registration,
     └── EIP-712 signature      cell uniqueness, attestations, issuance gate, retirements
```

Details: `docs/ARCHITECTURE.md` · Threat model: `docs/THREAT_MODEL.md` · Claim schema and hashing: `docs/CLAIM_SCHEMA.md` · Decisions: `DECISIONS.md`.

## Quickstart

Requirements: Node 20.19+ (or 22.12+), Python 3.11, Git and three terminals. Commands
below are PowerShell on Windows, each starting in the repository root. On macOS/Linux
use `export NAME=value` and `.venv/bin/python`. Installation needs internet; the demo
and evaluation use committed evidence/history with no satellite fetches.

Run the API with **one worker** and one relayer instance per key. Admission checks and
relay state transitions are serialized in that worker; multi-worker deployment needs
cross-process admission and nonce coordination. Uncertain transactions are journaled
before broadcast and reconciled before a new nonce is allocated.

The current contract uses **EIP-712 v2** with a signed cell-list commitment. A fresh
local deployment is required; this backend rejects v1 deployments. Schema 1.0 claim
hashes and existing hash vectors remain unchanged. The documented public deployment is
separate from this local setup. Never reuse its address or a previous local database
after resetting Hardhat. `.env.example` is a configuration reference; these commands
use process variables and disable automatic environment-file reads.

```powershell
# One-time installation, from repo root
npm --prefix contracts ci
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -c backend/requirements-lock.txt -e './backend[dev]'
npm --prefix frontend ci

# Terminal 1, from repo root: tests, then leave the local node running
$env:CLEARCREDIT_NO_ENV='1'
Set-Location contracts
npx hardhat test
npx hardhat node --hostname 127.0.0.1 --port 8545
```

```powershell
# Terminal 2, from repo root: fresh v2 deployment, then leave the API running
$env:CLEARCREDIT_NO_ENV='1'
Set-Location contracts
npx hardhat run scripts/deploy.ts --network localhost
$localRegistry = (Get-Content deployments/localhost.json -Raw | ConvertFrom-Json).address
Set-Location ../backend
$env:CHAIN_RPC_URL='http://127.0.0.1:8545'
$env:REGISTRY_ADDRESS=$localRegistry
# Public Hardhat account #0; use only on this disposable local chain.
$env:DEPLOYER_PRIVATE_KEY='0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'
$env:CLEARCREDIT_DB=Join-Path $env:TEMP ('clearcredit-local-' + [guid]::NewGuid() + '.sqlite3')
$env:CLEARCREDIT_OFFLINE_EVIDENCE='1'
$env:ADMIN_TOKEN='local-demo-only'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 3, from repo root: seed through the API, then leave the UI running
$env:CLEARCREDIT_NO_ENV='1'
Set-Location backend
.venv/Scripts/python.exe -m scripts.seed --api http://127.0.0.1:8000
Set-Location ../frontend
$env:VITE_API_URL='http://127.0.0.1:8000'
$env:VITE_CHAIN_ID='31337'
npm test
npm run build
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

API/OpenAPI: `http://127.0.0.1:8000/docs`; UI: `http://127.0.0.1:5173`.
After the one-time installation, the same fresh local flow can be started with
`backend/.venv/Scripts/python.exe scripts/demo.py`; `--smoke` validates and stops it.
Stop all servers with Ctrl+C. Ports must be free; stop only processes you own.
Recompute a downloaded claim from repo root with
`backend/.venv/Scripts/python.exe backend/app/canonical.py claim.json`.
The rehearsal and public-key wallet setup are in `docs/DEMO_SCRIPT.md`;
acceptance evidence is in `docs/ACCEPTANCE.md`.

## Deployed contract

**Base Sepolia (chain ID 84532):** [`0x889BD5e5462139D7AA8384d520f00403De8CB2b4`](https://sepolia.basescan.org/address/0x889BD5e5462139D7AA8384d520f00403De8CB2b4). Also on [Blockscout](https://base-sepolia.blockscout.com/address/0x889BD5e5462139D7AA8384d520f00403De8CB2b4).

- EIP-712 domain `ClearCredit` v2, H3 resolution 8, issuance threshold 6000 bps (60/100).
- One demo key holds both registrar and verifier roles; production would separate them.
- The 30 real seed projects are registered on it through the public API, each with its signed claim, cell commitment and integrity attestation.
- Deployment details: `contracts/deployments/baseSepolia.json`. The whole deployment and seeding cost about 0.0015 **test** ETH, from a free faucet (no real money).

## Limitations

- The chain enforces uniqueness and tamper evidence; it **cannot prove a project is real or effective**. A fabricated project on land nobody else claims can only be flagged through satellite inconsistencies.
- Exact geometry is checked off-chain. The on-chain H3 cell index (resolution 8, ~74 ha) is a conservative backstop, so slivers smaller than a cell can pass it.
- Tiny disjoint boundaries can share the representative-point fallback cell and require manual boundary review. No on-chain exception exists.
- Pending registrations can be cancelled by the developer/admin after 7,200 blocks,
  releasing cells in bounded batches while preserving claim identity. Worker crashes
  use timestamp leases: after a stopped worker, expired requests resume safely. Requests
  still active in the single supported worker are never reclaimed merely due to age.
  Multi-process admission, fencing and relayer coordination remain unsupported.
- EIP-712 v2 commits the declared cell list and blocks mismatched finalization. A compromised
  registrar can still hold arbitrary cells while Pending until the recovery path is used;
  signing the list does not independently prove its geometry-to-cell derivation.
- A compromised verifier key could post inflated scores until it is rotated. Attestations are append-only and carry a reproducible `evidenceHash`.
- History is context, with no authenticated registry affiliation or historical-boundary
  comparison. The attestation commits its snapshot, prior vintages and satellite hash;
  the verifier displays these separately from the satellite-only evidence hash.
- Satellite evidence has limits: clouds, 30 m resolution, loss data lagging about a year, and sensor processing changes. One such change, the Sentinel-2 2022 baseline offset, is corrected and documented.
- Sybil developers and legal identity are out of scope; production needs registry-verified identities.
- Evaluation measures injected faults, not real-world fraud prevalence.
- Transparent rules can be gamed by claims chosen just inside thresholds; production
  needs human review and independently justified rule updates. There is no learned model
  or project hold-out split in this evaluation.
- RPC snapshots are labeled with their block height. Read-after-write uses a persisted
  receipt floor and fails with a retryable error if that height is unavailable. This can
  reduce availability on lagging providers; it cannot establish unseen future state.
- Stored claims can be altered off-chain; recomputation exposes changes to hashed fields.
  Raw satellite scene/mask provenance remains incomplete despite committed summaries.

## License

Code: MIT. Data: see `data/` provenance (Karnik et al. 2024 CC BY 4.0; Hansen GFC CC BY 4.0; Copernicus Sentinel data terms).
