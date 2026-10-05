import { createConfig, http } from 'wagmi'
import { injected } from 'wagmi/connectors'
import { baseSepolia, hardhat } from 'wagmi/chains'

export const configuredChainId = Number(import.meta.env.VITE_CHAIN_ID || 84532)
export const supportedChains = [baseSepolia, hardhat] as const

export const wagmiConfig = createConfig({
  chains: supportedChains,
  connectors: [injected()],
  transports: {
    [baseSepolia.id]: http(),
    [hardhat.id]: http('http://127.0.0.1:8545'),
  },
})
