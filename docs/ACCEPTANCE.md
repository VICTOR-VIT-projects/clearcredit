# Acceptance evidence — 2026-10-09

Original checklist: `../CLEARCREDIT_HANDOFF.md` §12.3. Automated checks below were run
on a separate local clone with a fresh Python 3.11 venv, installed npm lockfiles and
the validated Python dependency constraints. No public network was contacted for chain
testing, and no environment-file contents were read. Dependency installation used the
package registries; satellite data came only from committed caches.

| Original item | Status | Evidence / remaining action |
|---|---|---|
| All 8 synthetic cases behave as specified | Done | `backend/tests/test_synthetic_cases.py::test_synthetic_cases`, included in the 91-test clean-clone backend run. Replays retain claim/results and refresh chain observations, with no new transactions. |
| Verifier page works with no wallet and no login | Human-only for full browser flow | Public GET claim/verify endpoints and downloaded hash work without authentication; local UI HTTP smoke passes. Verify page sample/component tests supplement this; real-browser rendering/navigation and wallet-disconnected behavior must be checked. |
| Hash recomputation from a downloaded claim matches on-chain | Done for independent CLI; browser human-only | Downloaded `VCS1115` claim JSON from local API; `backend/.venv/Scripts/python.exe backend/app/canonical.py downloaded-claim.json` matched the returned/on-chain hash. Original cross-language hash vectors and browser verification unit tests pass. Click/download flow remains manual. |
| README Quickstart works from a clean clone | Done for commands and HTTP flow | Fresh clone, fresh venv, npm ci, constrained editable backend install; 36 contracts / 91 backend / 17 frontend tests and build passed. Fresh v2 deployment and cached seed gave 30/30 registered, API health chainId 31337, UI and its local-chain configuration served successfully. |
| Deployed contract address and explorer link documented | Done in repo; human must refresh external evidence | README and `contracts/deployments/baseSepolia.json` record the owner's existing deployment. This run did not query or transact on it; current external state is not independently asserted. |
| No secrets committed; .env.example provided | Done for this change set; historical audit human-only | Only public Hardhat/synthetic demo keys used. Environment files disabled by process flag; `.env.example` documents settings. A comprehensive historical secret scan is not claimed. |
| Every limitation in original spec appears in public README | Done for documented residual scope | README covers coarse/sliver/fallback coverage, shared-contract adoption, compromised verifier and rotation, fabricated mitigation, upstream/cloud/coverage limits, off-chain alteration, identities/Sybil, rule gaming and injected-fault evaluation. Additional snapshot/provenance/single-worker limits are explicit. |
| Demo video recorded against cached data, 3–5 minutes | Not done | Human recording/submission task. Rehearsal script: `docs/DEMO_SCRIPT.md`. |

## Reproduction evidence

Local clone command (no remote fetch):

```powershell
git clone --no-hardlinks . $acceptClone
backend/.venv/Scripts/python.exe -m venv "$acceptClone/backend/.venv"
```

The retained clone is `C:/Users/amith/AppData/Local/Temp/clearcredit-acceptance-20261009-140159`.
It started from `24a062f`; candidate T3 README/config/test/constraint changes were copied
into this owned clone before verification. Installation initially selected newer Python
dependencies; the constrained install then selected the already-tested versions.
No alternate interpreter was used. The local probe logs (`node.log`, `api.log`, `ui.log`),
downloaded JSON and `data/claims/SEED_REPORT.json` remain there as disposable evidence.
The probe asserted all 30 report entries registered and stopped its own process trees.
No wallet extension or visual browser acceptance is inferred from those HTTP checks.

The T5 one-command runner was also exercised with `--smoke`, both on default ports and
`--node-port 18545 --api-port 18000 --ui-port 15173`. Both registered 30/30 examples,
matched a downloaded hash, served API/UI and stopped owned processes; all six ports
were free afterward. Logs remain in `clearcredit-demo-wr0etx6b` and
`clearcredit-demo-2zrgqt8x` under the system temp directory. The post-T5 suites passed
36 contracts / 96 backend / 17 frontend and production build. Actual interactive
Ctrl+C with a browser/wallet remains a manual rehearsal; injected interrupt cleanup
and real child-process termination are automated tests.

The final T6 checkout passed **36 contract / 109 backend / 29 frontend tests**, plus
production build with zero type errors. Public retirement tests verify exact half-open
serial bounds and matching transaction events; history tests exercise adaptive RPC
splitting, limits and no partial success. Registry tests pin map pagination and preserve
data labels. Mounted Verify tests use the committed sample to recompute the hash without
wallet hooks and hide stale results on failed receipt-block refresh. These supplement
the original acceptance items; they do not replace real-browser/wallet acceptance.
The cache diagnostic found 30 distinct real-project boundaries, zero missing caches
and zero warnings after its review trigger was frozen; diagnostic accuracy is unvalidated.
Frozen canonicalization/vectors, scoring, satellite measurements, real claims, Solidity
and evaluation outputs were compared with main and remain unchanged. OpenAPI matches
the current application. No command was blocked by the sandbox.

After installation, from each relevant directory with `CLEARCREDIT_NO_ENV=1`:

```powershell
npx hardhat test
.venv/Scripts/python.exe -m pytest -q
npm test
npm run build
```

The backend emitted one upstream Starlette/TestClient deprecation warning. Fresh
contract npm installation reported 47 dependency advisories (14 low, 9 moderate,
23 high, 1 critical); frontend installation reported zero. These are installer audit
counts, not a traced exploit of the deployed contract. Toolchain dependency remediation
needs a separate compatibility/security review; no blind `npm audit fix --force` was run.

## Human checks before submission

- Browser with no wallet: search, download/recompute, tampered JSON, reload/navigation,
  light/dark labels and keyboard focus; public retirement serial lookup and shareable URL;
  registry map labels/colors and cached-evidence diagnostic, including failures.
- MetaMask on local 31337: reject signing; switch account/network during preparation;
  register/retry; issue/retire; verify totals refresh only at/after the receipt block;
  over-issue/over-retire rejection; cancelled Pending cleanup in multiple batches.
- Stop the relevant API before any owner-managed public reconciliation; use its existing
  configured environment and matching DB. From backend, run
  `.venv/Scripts/python.exe -m scripts.reconcile --dry-run`, inspect, then
  `.venv/Scripts/python.exe -m scripts.reconcile` only under the owner's separate
  authorization. The latter sends transactions; it was not run on a public network here.
- Owner supplies repo/video URLs, verifies the external deployment record, records the
  cached-data video, publishes the repository and submits. No push/publish was performed.
