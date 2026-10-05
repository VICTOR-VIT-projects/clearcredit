# Decision Log

Format: date — decision — rationale. Deviations from `CLEARCREDIT_HANDOFF.md` are marked **[deviation]**.

| Date | Decision | Rationale |
|---|---|---|
| 2026-10-05 | Testnet: **Base Sepolia** (chainId 84532) | Reliable public RPC and BaseScan explorer; multiple faucets. |
| 2026-10-05 | Issuance: **attestation-gated self-issue**, no `ISSUER_ROLE` | Handoff §7.1 option. Developer issues up to `claimedCredits` only when the latest attestation score ≥ `issueThresholdBps` (default 6000 = 60/100, admin-settable). One less role to secure. |
| 2026-10-05 | DB: **SQLite + in-memory shapely** instead of PostGIS **[deviation, allowed fallback]** | Docker is not installed on the dev machine; handoff §4 permits this fallback. Exact overlap is computed with shapely in an equal-area projection. |
| 2026-10-05 | Polygons: try public registry geometry first, fall back to clearly labelled **illustrative** polygons | Handoff §10.1. Outcome recorded in `data/probes/POLYGON_SOURCES.md`. |
| 2026-10-05 | H3 cell resolution: **8** (≈0.74 km² per cell), enforced on-chain | Handoff §7.4 start point. The contract rejects cells of any other resolution (resolution is encoded in H3 index bits 52–55) because mixing resolutions would silently break uniqueness. Revisit once seed polygon sizes are known; resolution is a constructor parameter, so changing it means redeploying. |
| 2026-10-05 | Registration is **relayed by the backend with the developer's EIP-712 signature** **[clarification]** | Handoff wants both a backend relay (§8.1) and wallet connection (§9). The developer signs `Claim(projectId, claimHash, vintageYear, claimedCredits)` gas-free; the backend (`REGISTRAR_ROLE`) submits it; the contract verifies the signer equals `developer`. Domain separator binds chainId + contract address (no cross-chain replay); unique `claimHash`/`projectId` prevents same-chain replay. Standard ECDSA via OpenZeppelin, no custom crypto. |
| 2026-10-05 | Roles: `DEFAULT_ADMIN_ROLE`, `REGISTRAR_ROLE`, `VERIFIER_ROLE` | Separation of duties. In the demo one backend key holds registrar + verifier; production would split them. Residual risk documented in the threat model. |
| 2026-10-05 | `projectId` on-chain = `keccak256(utf8(projectId string))` | Fixed-size key, cheap storage; the human-readable ID lives in the claim JSON whose hash is on-chain. |
| 2026-10-05 | Cell batch cap: **300 cells/tx** (~7M gas measured) | Bounded loops (handoff §7.5). Large projects register in batches via `addCells`, then `finalizeRegistration`. Re-adding a cell the project already owns is a no-op so a retried batch cannot fail or double count. |
| 2026-10-05 | Tooling: **Hardhat 2** (`hh2` tag) + toolbox, **TypeScript 5**, Solidity 0.8.28, `evmVersion: cancun` | Hardhat 2 has the stable, widely documented test/matcher stack. TypeScript 7 (native compiler) has no JS API, which breaks ts-node, so TS is pinned to 5. OpenZeppelin 5.6 uses `mcopy`, so the EVM target is Cancun (supported on Base). |
