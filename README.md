# ClearCredit

Carbon-credit integrity and double-counting checker — IEEE ClimateChain Global Hackathon 2026, track: Carbon Markets & Emissions Transparency.

> Work in progress. Full README (problem, quickstart, honest limits) lands in Phase 6.

ClearCredit produces a **verified integrity attestation** for a carbon-credit claim: it enforces on-chain that the same land and vintage cannot be claimed twice, blocks double retirement, cross-checks the claim against public satellite data, and publishes a transparent integrity score with reasons. The chain proves a record was not altered; it does **not** prove physical truth.

## Layout
- `contracts/` — `ClearCreditRegistry.sol` (Hardhat). `npx hardhat test`
- `backend/` — FastAPI service (geometry, overlap, evidence, scoring, chain relay)
- `frontend/` — React UI (Submit, Verify, Registry, About)
- `data/` — seed projects (real, with provenance) and synthetic test cases (labelled)
- `docs/` — architecture, threat model, claim schema, evaluation
- `DECISIONS.md` — design decisions and deviations

## Contracts quickstart
```bash
cp .env.example .env            # then set DEPLOYER_PRIVATE_KEY (or: cd contracts && npx ts-node scripts/new-wallet.ts)
cd contracts && npm install
npx hardhat test
npx hardhat run scripts/deploy.ts --network baseSepolia
```
