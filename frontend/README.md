# ClearCredit frontend

Vite + React + TypeScript frontend for the ClearCredit carbon-credit integrity and double-counting checker.

## Run locally

Prerequisites: Node.js 20 or newer and a running ClearCredit API.

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

The app opens at `http://localhost:5173`. The API defaults to `http://localhost:8000`.

## Configuration

- `VITE_API_URL`: FastAPI base URL. Default: `http://localhost:8000`.
- `VITE_CHAIN_ID`: wallet network expected by the UI. Default: `84532` (Base Sepolia). Use `31337` for local Hardhat at `http://127.0.0.1:8545`.

When using local Hardhat, configure the backend for the same chain and contract, then set `VITE_CHAIN_ID=31337` before starting Vite.

## Checks

```bash
npm test
npm run build
```

`npm test` loads every vector from `../docs/claim-hash-vectors.json` and checks the browser canonical string, claim hash, and project key against the Python reference outputs.

## Main routes

- `/submit` — preview, score, sign, and register a claim.
- `/verify/:ref` — public verification by project ID or claim hash; no wallet required.
- `/registry` — paginated public claim registry.
- `/about` — precise statement of what ClearCredit does and does not prove.

The Verify page only exposes issue/retire controls when the connected wallet matches the registered developer.
