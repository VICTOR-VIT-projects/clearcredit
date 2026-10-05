# ClearCredit

**Carbon-credit integrity and double-counting checker.** IEEE ClimateChain Global Hackathon 2026, track: *Carbon Markets & Emissions Transparency*.

A project developer submits a carbon-credit claim: a boundary polygon, a vintage year and the credits claimed. ClearCredit then:

1. **Registers a tamper-evident claim** on an EVM chain (Base Sepolia). The developer signs it with their wallet; the canonical claim hash goes on-chain.
2. **Blocks double counting.** The same land in the same vintage cannot be claimed twice: exact polygon overlap is checked off-chain, and an H3 cell index is enforced on-chain. Credits cannot be retired twice.
3. **Cross-checks the claim against independent satellite data:** Hansen Global Forest Change tree-cover loss (to 2025) and the Sentinel-2 NDVI trend.
4. **Publishes a transparent integrity score** (0–100) with plain-language reasons, as an append-only on-chain attestation. The contract refuses to issue credits while the score is below the threshold.
5. **Offers a public verifier page.** Anyone, with no wallet, can inspect a claim, recompute its hash in the browser, and see its evidence and on-chain history.

> **What this proves, and what it doesn't.** The chain proves a record was **not altered** and **enforces uniqueness**. It does **not** prove physical truth. Satellite data is evidence, not certification. Outputs are an *integrity score* and a *verified integrity attestation*, never a "certified emission reduction". A low score means *flagged as suspicious*, not proven fraud.

## Why it matters

The same forest can back credits in two registries, or two projects can claim overlapping land for the same year. Retired credits can be counted again. Weak verification lets claims stand even when satellite imagery shows the forest was cleared. No shared, cross-registry uniqueness check exists. ClearCredit is that check, published as an open schema and API that any registry, buyer or auditor can run or verify independently.

## Demo flow

| Step | What you see |
|---|---|
| Legitimate project | Passes the overlap check; satellite evidence is consistent; high score; registered on-chain. |
| Duplicate claim on the same land and vintage | **Blocked**, naming the conflicting project and the overlap fraction. |
| Bypass the backend (second operator, empty database) | **Still blocked by the contract's cell index.** |
| Avoided-deforestation claim where Hansen shows clearing | Low score with reasons; the contract **refuses issuance**. |
| Retry the same submission | Same response, **zero new transactions** (idempotency key + resumable relay). |
| Retire more credits than were issued | **Reverts on-chain** (`ExceedsIssued`); serial ranges never overlap. |
| Edit the stored claim off-chain | Verifier recomputes the hash → **mismatch** with the on-chain hash. |

## Data

- **30 real projects** (Verra and Gold Standard) in 15 countries. Boundaries are from the open Karnik et al. 2024 dataset (CC BY 4.0, via CarbonPlan); credits are each project's **real issued quantity** for its latest vintage covered by forest-loss data (OffsetsDB issuance records). Repairs and simplifications are recorded in each claim's `boundarySource`. See `data/probes/POLYGON_SOURCES.md`.
- **Synthetic test cases** are labelled `synthetic` everywhere, including on-chain-hashed claims and the UI.
- Seed claims use **demo developer wallets**, not the real proponents. Scores on real projects reflect our processed boundary and public data; they are **not findings about those projects**.

## Evaluation

The rule-based score is evaluated against a uniqueness-only baseline on **injected faults**: duplicates, shifted overlaps, inflated credits, and claims relocated onto land with recorded clearing. False alarms are measured on the real projects as published. See `docs/EVALUATION.md`. These metrics measure detection of injected faults on a seeded dataset, **not real-world fraud prevalence**.

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

Requirements: Node 20+, Python 3.11.

```bash
cp .env.example .env

# Contracts: tests, local chain, deploy
cd contracts && npm install && npx hardhat test
npx hardhat node                                          # terminal 1
npx hardhat run scripts/deploy.ts --network localhost     # terminal 2 → contract address

# Backend
cd ../backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # (bin/ on macOS/Linux)
pytest                                                    # includes real-chain integration tests
# local chain: CHAIN_RPC_URL=http://127.0.0.1:8545, REGISTRY_ADDRESS=<address>,
# DEPLOYER_PRIVATE_KEY=<hardhat account #0>, set in .env
uvicorn app.main:create_app --factory --port 8000        # OpenAPI at http://localhost:8000/docs
python -m scripts.seed                                    # register the 30 real claims via the API

# Frontend
cd ../frontend && npm install && npm run dev              # http://localhost:5173
```

Recompute any claim hash independently: `python backend/app/canonical.py claim.json`.

## Deployed contract

Base Sepolia: *(address and BaseScan link added at deployment)*.

## Limitations

- The chain enforces uniqueness and tamper evidence; it **cannot prove a project is real or effective**. A fabricated project on land nobody else claims can only be flagged through satellite inconsistencies.
- Exact geometry is checked off-chain. The on-chain H3 cell index (resolution 8, ~74 ha) is a conservative backstop, so slivers smaller than a cell can pass it.
- A compromised verifier key could post inflated scores until it is rotated. Attestations are append-only and carry a reproducible `evidenceHash`.
- Satellite evidence has limits: clouds, 30 m resolution, loss data lagging about a year, and sensor processing changes. One such change, the Sentinel-2 2022 baseline offset, is corrected and documented.
- Sybil developers and legal identity are out of scope; production needs registry-verified identities.
- Evaluation measures injected faults, not real-world fraud prevalence.

## License

Code: MIT. Data: see `data/` provenance (Karnik et al. 2024 CC BY 4.0; Hansen GFC CC BY 4.0; Copernicus Sentinel data terms).
