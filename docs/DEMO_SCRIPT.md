# Demo Script (3–5 minutes)

Record against **cached evidence** and a **freshly seeded local chain**, so nothing depends on live satellite APIs or testnet latency. Rehearse twice.

## 0. Reset and seed (before recording, ~5 min)

Install dependencies once using **README → Quickstart**, then from repo root:

```powershell
backend/.venv/Scripts/python.exe scripts/demo.py
```

This starts a loopback Hardhat node, deploys a fresh v2 contract, starts a cached-only
API with a fresh temporary DB, seeds all real examples and starts the UI. It prints
URLs and the temporary log/database directory. Ctrl+C stops its process trees. It
refuses occupied ports and never deletes an existing database. For automatic HTTP,
seed and downloaded-hash checks followed by cleanup, add `--smoke`. If ports are busy,
use `--node-port 18545 --api-port 18000 --ui-port 15173`; configure the wallet's RPC
to that printed local port. There is no public/testnet mode.

Manual alternative:

Follow **README → Quickstart** literally for installation and the three PowerShell
terminals. It creates a fresh v2 local contract and a new temporary database, sets the
local wallet/network/API process variables explicitly, and disables automatic environment
file reads. Python commands use `backend/.venv`, not a globally installed pytest/uvicorn.
No existing database is deleted. Default local ports are 8545 / 8000 / 5173.
The cached-only API sets `CLEARCREDIT_OFFLINE_EVIDENCE=1`; uncached uploads report
unavailable evidence rather than contacting satellite services.

**Wallet (MetaMask):**
1. Add the network: RPC `http://127.0.0.1:8545`, chain ID `31337`.
2. Import Hardhat dev account #1 with key `0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d`. This is a public test key; never use it anywhere else.
3. Registration needs only a signature (gas-free). Issue and retire are normal transactions.

**Upload files** for the live submissions are in `data/demo/`. Their evidence is already cached, so previews are instant.

| File | Fields to enter |
|---|---|
| `SYN-01-CLEAN.geojson` | avoided deforestation · vintage 2023 · 30,000 credits |
| `SYN-02-DUPLICATE.geojson` | same as SYN-01, different project ID |
| `SYN-03-PARTIAL.geojson` | same fields |
| `SYN-05-CONTRADICTED.geojson` | avoided deforestation · vintage **2022** · 30,000 credits |

Set the data label to **Synthetic** for all of them.

## 1. Problem (30 s)

"The same forest can back credits twice: in two registries, or as overlapping projects in the same year. Credits can be retired twice. Verification often never checks the land. There is no shared uniqueness check across registries."

Show the **Registry** page: 30 real projects in 15 countries, with real issued credits on published boundaries.

## 2. Legitimate project (45 s)

**Submit** → upload `SYN-01-CLEAN` → **Check claim**. Point out:
- no overlap
- forest cover ~99%
- 0 ha loss in the vintage year
- stable NDVI
- score **100 (high)**, with every reason in plain language

**Sign & register**: the wallet signs typed data, with no gas. The relay registers it on-chain. Open the claim page and show the transactions.

## 3. Duplicate blocked (45 s)

Submit `SYN-02-DUPLICATE` with a different project ID and the same vintage. Result: **Blocked: overlaps SYN-01-CLEAN by 100% for vintage 2023**.

Then `SYN-03-PARTIAL`: **blocked at 60%** with the fraction shown.

One line: "Even if someone bypasses our backend, the contract's cell index rejects it. We test exactly that: a second backend with an empty database is still blocked on-chain."

## 4. Contradicted claim (45 s)

Submit `SYN-05-CONTRADICTED`: an avoided-deforestation claim on the Rondônia frontier, vintage 2022. It is **registered, but scores low**: Hansen shows about 8% of the remaining forest cleared inside the boundary that year. It gets a `LOW_INTEGRITY_SCORE` warning.

On its claim page, open **Developer actions** → **Issue 100** → the contract **refuses**: "latest integrity score is below the issuance threshold".

## 5. Retry safety (20 s)

On SYN-01's success card, press **Send the same request again**. This resends the identical request with the same `Idempotency-Key`. A green **"Same request replayed"** notice appears: the API returned the saved result with refreshed chain observations, with **no new record and no new transaction** (the API sends the response header `Idempotent-Replayed: true`).

## 6. Verifier page (45 s)

**Verify** → paste SYN-01's claim hash (no wallet needed) → **Recompute hash in your browser** → ✓ matches the on-chain hash. Show the satellite evidence, the score reasons, and the on-chain attestation.

**Retirement:** Developer actions → issue 100 → retire 100 to "Acme" → retire 1 more → **reverts `ExceedsIssued`**. Serial ranges are sequential, so credits cannot be retired twice.

**Tamper:** in a terminal, run `python -m scripts.tamper SYN-01-CLEAN`, which changes the credits in the database. Reload: verify shows **✗ mismatch**, because the off-chain record no longer matches the chain. Restore with `--restore`.

## 7. Limits and adoption (30 s)

Optional multi-registry insert (F4): from `contracts/`, run
`npx hardhat run scripts/multi-registry-demo.ts`. It creates a fresh **ephemeral local**
contract, grants separate registrar accounts to Registry A and Registry B, registers A,
and confirms B is blocked by `CellAlreadyClaimed` for the same cells/vintage. Output is
labelled synthetic; the indices demonstrate the contract rule, not project boundaries
or satellite evidence. `test_two_distinct_registrar_accounts_share_contract_uniqueness`
also exercises actual H3 covers with separate accounts and no API prechecks. The script
refuses public networks. This does not modify the running demo's registry.

"The chain proves a record wasn't altered and enforces uniqueness. It does **not** prove the forest exists. Satellite data is evidence, not certification. Scores flag claims as suspicious; they don't prove fraud. Our evaluation measures injected faults, not real-world fraud prevalence, and it shows where we miss subtle clearing."

Adoption: registries run a registrar against the shared contract; buyers and auditors use the open schema, the API, and the verifier page. Show `/docs` (OpenAPI) and `docs/CLAIM_SCHEMA.md`.
