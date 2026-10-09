import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";

if (process.env.CLEARCREDIT_NO_ENV !== "1") dotenv.config({ path: "../.env" });

const key = process.env.DEPLOYER_PRIVATE_KEY;

const config: HardhatUserConfig = {
  solidity: { version: "0.8.28", settings: { evmVersion: "cancun", optimizer: { enabled: true, runs: 200 } } },
  networks: {
    localhost: { url: process.env.CLEARCREDIT_LOCAL_RPC_URL || "http://127.0.0.1:8545", chainId: 31337 },
    baseSepolia: {
      url: process.env.BASE_SEPOLIA_RPC_URL || "https://sepolia.base.org",
      chainId: 84532,
      accounts: key ? [key] : [],
    },
  },
  etherscan: { apiKey: process.env.BASESCAN_API_KEY || "" },
};

export default config;
