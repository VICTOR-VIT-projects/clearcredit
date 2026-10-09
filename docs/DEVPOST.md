# ClearCredit

**Tagline:** A shared carbon-credit integrity check that anchors signed claims, blocks
duplicate land claims and makes evidence inspectable.

**Short description:** ClearCredit lets a developer submit a boundary, vintage and credit
quantity, then checks exact overlap, shared on-chain land-cell ownership, satellite signals
and issuance history. It publishes a transparent integrity score and a public verifier
where anyone can recompute the claim hash. The chain enforces recorded uniqueness and
retirement limits; it does not establish physical mitigation. Synthetic examples are
labeled, and real-project examples use demo wallets rather than the actual proponents.

## Track alignment

Carbon Markets & Emissions Transparency: smart contracts to prevent double counting,
and blockchain-based carbon credit verification. Participating registries share a cell
index; buyers and auditors inspect signed claims and verified integrity attestations.
Source: [README](../README.md), [architecture](ARCHITECTURE.md).

## Inspiration and problem

The same land can support competing claims across registries. A tidy registry record
does not show whether the claimed land overlaps another project or whether independent
observations contradict the claim. ClearCredit connects those checks while making their
limits visible. Source: [README](../README.md).

## What it does

Developers sign a canonical claim hash and cell-list commitment. Exact polygon overlap
is checked off-chain; the contract enforces cell/vintage uniqueness. Satellite forest
loss, vegetation trend and prior issuance inform an integrity score with readable reasons.
Low scores restrict issuance. Retirement amounts are capped by issued credits and receive
sequential serial ranges. Public retirement lookup links a serial to its beneficiary
and transaction; the registry map labels each boundary's data category and score.
Anyone can inspect the public verifier without a wallet.
Source: [claim schema](CLAIM_SCHEMA.md), [threat model](THREAT_MODEL.md).

## How it was built

The system combines a Solidity registry with role-controlled registration and attestations,
EIP-712 wallet consent, and standard keccak/ECDSA primitives. A FastAPI service validates
geometry, computes H3 coverage, scores cached evidence and relays transactions. SQLite
persists claims, request leases and signed transaction journals. React presents submission,
verification and developer controls. Browser and Python canonicalization share test vectors.
Source: [architecture](ARCHITECTURE.md), [claim schema](CLAIM_SCHEMA.md).

## Challenges

Sentinel-2's processing baseline introduced an apparent vegetation step change until the
reflectance offset was handled. The EIP-7825 transaction gas cap required smaller relay
batches. Public RPC reads lagged confirmed writes, including simulations used for gas
estimation; reads and estimates now require explicit block heights, and unavailable state
fails closed. Valid floating-point polygons could become invalid at hash precision, so
validation checks that representation too. Source: [decisions](../DECISIONS.md).

## Accomplishments

The local demonstration exercises separate registrars against the same contract. Developer
consent binds the declared cell list, expired Pending registrations have bounded cleanup,
and uncertain broadcasts retain their transaction identity across retries. A clean-clone
rehearsal registered all 30 seed projects using cached evidence and independently matched
a downloaded claim hash. Source: [decisions](../DECISIONS.md), [acceptance](ACCEPTANCE.md).

## Evaluation

On 102 injected faults built from 30 published projects, rules-v4 recalls 86/102 (0.843),
versus 59/102 (0.578) for uniqueness alone; precision is 0.956. Duplicates: 30/30; shifted
copies: 29/30; inflation: 16/30; relocated claims: 11/12. False alarms are 4/30, up from
2/30 before history screening. These include issuance changes that may need legitimate
historical context; no cause is attributed to the projects. The system still misses
14/30 inflated claims and light clearing below roughly 2% of remaining forest per year.
The shifted-copy miss contains no actual shared land. Thresholds were frozen before
evaluation; there is no learned model or project hold-out split. These are injected-fault
results, not real-world prevalence estimates. Source: [evaluation](EVALUATION.md).

## Who adopts it and what it costs

Registries operate authorized relayers against a shared contract; buyers and auditors use
the schema, API and verifier. Operators pay for hosting, evidence processing and chain
transactions. The owner's recorded Base Sepolia deployment/seeding spent about 0.0015
test ETH; this is neither real money nor a production cost estimate. Current external
state was not reverified during this local hardening pass. Source: [README](../README.md),
[decisions](../DECISIONS.md).

## Scalability

Writes are batched; cached summaries avoid repeated satellite processing. The prototype
supports one API worker/relayer per key. Production needs cross-process admission and nonce
coordination, indexed spatial search, bounded event/history queries and independent
operators. Source: [architecture](ARCHITECTURE.md), [threat model](THREAT_MODEL.md).

## Limitations

Cell coverage is coarse: sliver overlaps can evade it and tiny neighbours can conflict.
Geometry checking still trusts participating backends. Satellite coverage, clouds, woodland
definitions and incomplete raw-scene provenance limit evidence. History does not authenticate
registry affiliation or methodology changes. A compromised verifier can post misleading
scores until rotated. Fabricated mitigation, identities and rule gaming remain unresolved.
Source: [README](../README.md), [threat model](THREAT_MODEL.md).

## What's next

Record the cached-data demo, complete browser/wallet acceptance, expand independently
justified evidence coverage and expand buyer-facing audit integration. Assess operational
coordination and registry partnerships before production use. Source: [acceptance](ACCEPTANCE.md).

## Built with

Solidity, OpenZeppelin, EIP-712, EVM/Base Sepolia, Python, FastAPI, SQLite, Shapely, pyproj,
H3, Rasterio, Hansen Global Forest Change, Sentinel-2, OffsetsDB, React, TypeScript, Vite,
wagmi, viem and Leaflet. Source: [architecture](ARCHITECTURE.md), dependency manifests.

## Links

- Repository: `REPO_URL`
- Demo video: `VIDEO_URL`
- Deployment/explorer: see [README deployment record](../README.md#deployed-contract).
