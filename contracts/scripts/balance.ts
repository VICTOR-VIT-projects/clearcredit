// Usage: npx hardhat run scripts/balance.ts --network baseSepolia
import { ethers, network } from "hardhat";
ethers.getSigners().then(async ([s]) =>
  console.log(`${network.name} ${s.address} ${ethers.formatEther(await ethers.provider.getBalance(s.address))} ETH`));
