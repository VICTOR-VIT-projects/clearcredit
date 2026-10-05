// Generates a fresh testnet key, appends it to ../.env, and prints only the address.
import { Wallet } from "ethers";
import * as fs from "fs";

const envPath = "../.env";
const env = fs.existsSync(envPath) ? fs.readFileSync(envPath, "utf8") : fs.readFileSync("../.env.example", "utf8");
if (/^DEPLOYER_PRIVATE_KEY=0x[0-9a-fA-F]{64}/m.test(env)) {
  console.log("DEPLOYER_PRIVATE_KEY already set; not overwriting.");
  process.exit(0);
}
const w = Wallet.createRandom();
fs.writeFileSync(envPath, env.replace(/^DEPLOYER_PRIVATE_KEY=.*$/m, `DEPLOYER_PRIVATE_KEY=${w.privateKey}`));
console.log(`Deployer address: ${w.address}`);
