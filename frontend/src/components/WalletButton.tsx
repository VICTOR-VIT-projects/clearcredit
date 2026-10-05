import { useAccount, useConnect, useDisconnect, useSwitchChain } from 'wagmi'
import { configuredChainId } from '../lib/wagmi'
import { shorten } from '../lib/format'

export function WalletButton() {
  const { address, chainId, isConnected } = useAccount()
  const { connectors, connect, isPending, error } = useConnect()
  const { disconnect } = useDisconnect()
  const { switchChain, isPending: isSwitching } = useSwitchChain()
  const connector = connectors[0]

  if (!isConnected) {
    return (
      <div className="wallet-control">
        <button className="button button-compact button-secondary" type="button" disabled={!connector || isPending} onClick={() => connector && connect({ connector })}>
          {isPending ? 'Connecting…' : 'Connect wallet'}
        </button>
        {error && <span className="wallet-error" title={error.message}>Wallet connection failed</span>}
      </div>
    )
  }

  if (chainId !== configuredChainId) {
    return (
      <button className="button button-compact button-warning" type="button" disabled={isSwitching} onClick={() => switchChain({ chainId: configuredChainId })}>
        {isSwitching ? 'Switching…' : `Switch to chain ${configuredChainId}`}
      </button>
    )
  }

  return (
    <button className="wallet-address" type="button" title="Disconnect wallet" onClick={() => disconnect()}>
      <span className="status-dot" aria-hidden="true" />
      {shorten(address || '')}
    </button>
  )
}
