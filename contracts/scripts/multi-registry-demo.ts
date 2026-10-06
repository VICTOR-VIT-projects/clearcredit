import assert from "node:assert/strict";
import { ethers, network } from "hardhat";

async function main() {
  assert(["hardhat", "localhost"].includes(network.name), "Use a local Hardhat network only.");
  const [admin, registryA, registryB, developerA, developerB] = await ethers.getSigners();
  const reg = await ethers.deployContract("ClearCreditRegistry", [admin.address, 8, 6000]);
  for (const registrar of [registryA, registryB]) {
    await reg.grantRole(await reg.REGISTRAR_ROLE(), registrar.address);
  }
  // Synthetic resolution-8 shaped cell indices; this scenario tests the shared
  // registry rule, not geometry or satellite evidence. Real H3 cells are exercised
  // separately by the backend integration test.
  const cells = [1n, 2n].map(n => (1n << 59n) | (8n << 52n) | n);
  const root = cells.reduce((h, c) => ethers.solidityPackedKeccak256(["bytes32", "uint64"], [h, c]), ethers.ZeroHash);
  const domain = { name: "ClearCredit", version: "2", chainId: (await ethers.provider.getNetwork()).chainId, verifyingContract: await reg.getAddress() };
  const types = { Claim: [
    { name: "projectId", type: "bytes32" }, { name: "claimHash", type: "bytes32" },
    { name: "vintageYear", type: "uint16" }, { name: "claimedCredits", type: "uint64" },
    { name: "cellsRoot", type: "bytes32" },
  ] };
  const a = { projectId: ethers.id("SYN-REGISTRY-A"), claimHash: ethers.id("synthetic A"), vintageYear: 2023, claimedCredits: 100n, cellsRoot: root };
  const b = { ...a, projectId: ethers.id("SYN-REGISTRY-B"), claimHash: ethers.id("synthetic B") };
  await reg.connect(registryA).registerProject(a.projectId, a.claimHash, developerA.address, a.vintageYear, a.claimedCredits, root, cells, await developerA.signTypedData(domain, types, a));
  await reg.connect(registryA).finalizeRegistration(a.projectId);
  const signatureB = await developerB.signTypedData(domain, types, b);
  let blocked = false;
  try {
    await reg.connect(registryB).registerProject(b.projectId, b.claimHash, developerB.address, b.vintageYear, b.claimedCredits, root, cells, signatureB);
  } catch (error) {
    const data = (error as { data?: string }).data;
    blocked = Boolean(data && reg.interface.parseError(data)?.name === "CellAlreadyClaimed");
  }
  assert(blocked, "Registry B must be rejected by the shared contract's cell index.");
  assert.equal((await reg.getProject(b.projectId)).status, 0n);
  assert.equal(await reg.cellClaim(cells[0], 2023), a.projectId);
  console.log("dataLabel=synthetic: Registry A registered; distinct Registry B blocked by CellAlreadyClaimed on the same contract.");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
