// Deploys ClearCreditRegistry and grants REGISTRAR + VERIFIER to the deployer (demo setup:
// one backend key holds both roles; production would use separate keys).
// Usage: npx hardhat run scripts/deploy.ts --network baseSepolia
import { ethers, network } from "hardhat";
import * as fs from "fs";

const CELL_RESOLUTION = Number(process.env.CELL_RESOLUTION || 8);
const ISSUE_THRESHOLD_BPS = Number(process.env.ISSUE_THRESHOLD_BPS || 6000);

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log(`network=${network.name} deployer=${deployer.address} balance=${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH`);

  const reg = await ethers.deployContract("ClearCreditRegistry", [deployer.address, CELL_RESOLUTION, ISSUE_THRESHOLD_BPS]);
  await reg.waitForDeployment();
  const address = await reg.getAddress();
  await (await reg.grantRole(await reg.REGISTRAR_ROLE(), deployer.address)).wait();
  await (await reg.grantRole(await reg.VERIFIER_ROLE(), deployer.address)).wait();

  const out = { network: network.name, chainId: Number((await ethers.provider.getNetwork()).chainId), address,
    deployTx: reg.deploymentTransaction()?.hash, cellResolution: CELL_RESOLUTION, issueThresholdBps: ISSUE_THRESHOLD_BPS,
    deployedAt: new Date().toISOString() };
  fs.mkdirSync("deployments", { recursive: true });
  fs.writeFileSync(`deployments/${network.name}.json`, JSON.stringify(out, null, 2));
  console.log(out);
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
