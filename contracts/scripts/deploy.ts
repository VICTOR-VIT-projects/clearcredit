// Deploys ClearCreditRegistry and grants REGISTRAR + VERIFIER to the deployer (demo setup:
// one backend key holds both roles; production would use separate keys).
// Usage: npx hardhat run scripts/deploy.ts --network baseSepolia
// Resume a deployment whose role grants did not finish (no redeploy):
//   ATTACH_ADDRESS=0x... npx hardhat run scripts/deploy.ts --network baseSepolia
import { ethers, network } from "hardhat";
import * as fs from "fs";
import * as path from "path";

const CELL_RESOLUTION = Number(process.env.CELL_RESOLUTION || 8);
const ISSUE_THRESHOLD_BPS = Number(process.env.ISSUE_THRESHOLD_BPS || 6000);
// Public RPCs are load-balanced; reading right after a write can hit a node that is behind.
const CONFIRMATIONS = network.name === "hardhat" || network.name === "localhost" ? 1 : 2;

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log(`network=${network.name} deployer=${deployer.address} balance=${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH`);

  let deployTx: string | null = null;
  const attach = process.env.ATTACH_ADDRESS;
  const reg = attach
    ? await ethers.getContractAt("ClearCreditRegistry", attach)
    : await ethers.deployContract("ClearCreditRegistry", [deployer.address, CELL_RESOLUTION, ISSUE_THRESHOLD_BPS]);
  if (!attach) {
    deployTx = reg.deploymentTransaction()!.hash;
    await reg.deploymentTransaction()!.wait(CONFIRMATIONS);
  }
  const address = await reg.getAddress();

  // Role ids computed locally (keccak256 of the role name), so no read is needed before granting.
  for (const role of ["REGISTRAR_ROLE", "VERIFIER_ROLE"]) {
    const id = ethers.id(role);
    if (await reg.hasRole(id, deployer.address)) {
      console.log(`${role} already granted`);
      continue;
    }
    await (await reg.grantRole(id, deployer.address)).wait(CONFIRMATIONS);
    console.log(`${role} granted`);
  }

  const out = { network: network.name, chainId: Number((await ethers.provider.getNetwork()).chainId), address,
    deployTx, cellResolution: CELL_RESOLUTION, issueThresholdBps: ISSUE_THRESHOLD_BPS,
    deployedAt: new Date().toISOString() };
  const output = process.env.DEPLOYMENT_FILE || `deployments/${network.name}.json`;
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(out, null, 2));
  console.log(out);
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
