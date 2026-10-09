import { useEffect, useRef, useState } from 'react'
import { useAccount, useWaitForTransactionReceipt, useWriteContract } from 'wagmi'
import { BaseError, ContractFunctionRevertedError, decodeErrorResult, type Abi, type Hex } from 'viem'
import abiJson from '../abi.json'
import type { ClaimView } from '../lib/types'
import { formatNumber, shorten } from '../lib/format'

const abi = abiJson as Abi

function findHexData(value: unknown, seen = new Set<unknown>()): Hex | null {
  if (typeof value === 'string' && /^0x[0-9a-fA-F]{8,}$/.test(value)) return value as Hex
  if (!value || typeof value !== 'object' || seen.has(value)) return null
  seen.add(value)
  const record = value as Record<string, unknown>
  for (const key of ['data', 'cause', 'error', 'details']) {
    const found = findHexData(record[key], seen)
    if (found) return found
  }
  return null
}

function decodedErrorMessage(errorName: string, args?: readonly unknown[]): string {
  switch (errorName) {
        case 'ExceedsIssued':
          return `Blocked by the contract: you tried to retire beyond the ${String(args?.[1] ?? '?')} credits issued — credits cannot be retired twice.`
        case 'ScoreBelowThreshold':
          return 'Blocked: latest integrity score is below the issuance threshold.'
        case 'NoAttestation':
          return 'Blocked: no verified integrity attestation has been posted for this project.'
        case 'ExceedsClaimed':
          return `Blocked by the contract: total issuance would exceed the ${String(args?.[1] ?? '?')} credits claimed.`
        case 'NotDeveloper':
          return 'Blocked: only the developer wallet registered for this project can perform this action.'
        case 'ZeroValue':
          return 'Blocked: the amount must be greater than zero.'
        default:
          return `Contract rejected the transaction: ${errorName}.`
  }
}

function contractErrorMessage(error: unknown): string {
  if (error instanceof BaseError) {
    const reverted = error.walk((candidate) => candidate instanceof ContractFunctionRevertedError)
    if (reverted instanceof ContractFunctionRevertedError && reverted.data) {
      return decodedErrorMessage(reverted.data.errorName, reverted.data.args as readonly unknown[] | undefined)
    }
  }
  const data = findHexData(error)
  if (data) {
    try {
      const decoded = decodeErrorResult({ abi, data })
      return decodedErrorMessage(decoded.errorName, decoded.args as readonly unknown[] | undefined)
    } catch {
      // Some wallets omit revert data. Fall through to their plain-language error.
    }
  }
  return error instanceof Error ? error.message : 'The transaction was rejected.'
}

function explorerTransactionUrl(view: ClaimView, hash: string): string | null {
  const explorer = view.onChain?.explorer
  if (!explorer || !view.onChain) return null
  const suffix = `/address/${view.onChain.contract}`
  const base = explorer.endsWith(suffix) ? explorer.slice(0, -suffix.length) : explorer.replace(/\/address\/[^/]+\/?$/, '')
  return `${base}/tx/${hash}`
}

export function DeveloperActions({ view, onConfirmed }: { view: ClaimView; onConfirmed: (block: number) => void }) {
  const { address, chainId } = useAccount()
  const [issueAmount, setIssueAmount] = useState('')
  const [retireAmount, setRetireAmount] = useState('')
  const [beneficiary, setBeneficiary] = useState('')
  const [action, setAction] = useState<'issue' | 'retire' | null>(null)
  const [hash, setHash] = useState<Hex | undefined>()
  const [error, setError] = useState('')
  const notifiedHash = useRef<Hex | undefined>(undefined)
  const { writeContractAsync, isPending: isWalletPending } = useWriteContract()
  const receipt = useWaitForTransactionReceipt({ hash, chainId: view.onChain?.chainId })
  const isDeveloper = Boolean(address && view.claim.developer.toLowerCase() === address.toLowerCase())

  useEffect(() => {
    if (receipt.isSuccess && receipt.data?.status === 'success' && hash && notifiedHash.current !== hash) {
      notifiedHash.current = hash
      onConfirmed(Number(receipt.data.blockNumber))
    }
  }, [hash, onConfirmed, receipt.isSuccess, receipt.data])

  if (!isDeveloper || !view.onChain) return null
  const project = view.onChain.project
  const wrongNetwork = chainId !== view.onChain.chainId
  const pending = isWalletPending || receipt.isLoading
  const txUrl = hash ? explorerTransactionUrl(view, hash) : null

  const send = async (nextAction: 'issue' | 'retire') => {
    const amountText = nextAction === 'issue' ? issueAmount : retireAmount
    if (!/^\d+$/.test(amountText) || BigInt(amountText) <= 0n) {
      setError('Enter a whole-number amount greater than zero.')
      return
    }
    if (nextAction === 'retire' && !beneficiary.trim()) {
      setError('Enter the retirement beneficiary.')
      return
    }
    setError('')
    setHash(undefined)
    setAction(nextAction)
    try {
      const txHash = await writeContractAsync({
        abi,
        address: view.onChain!.contract,
        chainId: view.onChain!.chainId,
        functionName: nextAction === 'issue' ? 'issueCredits' : 'retireCredits',
        args: nextAction === 'issue'
          ? [view.projectKey, BigInt(amountText)]
          : [view.projectKey, BigInt(amountText), beneficiary.trim()],
      })
      setHash(txHash)
    } catch (transactionError) {
      setError(contractErrorMessage(transactionError))
      setAction(null)
    }
  }

  return (
    <section className="card developer-panel">
      <div className="section-heading"><div><p className="eyebrow">Developer controls</p><h2>Issue or retire credits</h2></div><span className="status-pill">Your project</span></div>
      <div className="totals-grid">
        <div><span>Claimed</span><strong>{formatNumber(project.claimedCredits, 0)}</strong></div>
        <div><span>Issued</span><strong>{formatNumber(project.issued, 0)}</strong></div>
        <div><span>Retired</span><strong>{formatNumber(project.retired, 0)}</strong></div>
        <div><span>Available</span><strong>{formatNumber(project.issued - project.retired, 0)}</strong></div>
      </div>
      {wrongNetwork && <div className="notice notice-warning"><strong>Wrong network</strong><p>Switch your wallet to chain {view.onChain.chainId} before sending a transaction.</p></div>}
      <div className="action-grid">
        <form onSubmit={(event) => { event.preventDefault(); void send('issue') }}>
          <h3>Issue credits</h3>
          <label className="field"><span>Amount</span><input type="number" min="1" step="1" value={issueAmount} onChange={(event) => setIssueAmount(event.target.value)} /></label>
          <button className="button button-primary" disabled={pending || wrongNetwork} type="submit">{pending && action === 'issue' ? 'Confirming…' : 'Issue credits'}</button>
        </form>
        <form onSubmit={(event) => { event.preventDefault(); void send('retire') }}>
          <h3>Retire credits</h3>
          <label className="field"><span>Amount</span><input type="number" min="1" step="1" value={retireAmount} onChange={(event) => setRetireAmount(event.target.value)} /></label>
          <label className="field"><span>Beneficiary</span><input maxLength={200} placeholder="Name or purpose" value={beneficiary} onChange={(event) => setBeneficiary(event.target.value)} /></label>
          <button className="button button-primary" disabled={pending || wrongNetwork} type="submit">{pending && action === 'retire' ? 'Confirming…' : 'Retire credits'}</button>
        </form>
      </div>
      {isWalletPending && <div className="progress-row"><span className="spinner" /><div><strong>Waiting for wallet</strong><span>Review and confirm the transaction.</span></div></div>}
      {hash && receipt.isLoading && <div className="progress-row"><span className="spinner" /><div><strong>Transaction pending</strong><span>{shorten(hash)} is waiting for confirmation.</span></div></div>}
      {hash && receipt.isSuccess && receipt.data?.status === 'success' && <div className="notice notice-success"><strong>Transaction confirmed</strong><p>{txUrl ? <a href={txUrl} target="_blank" rel="noreferrer">View transaction ↗</a> : `Transaction ${shorten(hash)} confirmed on local chain.`} Totals refresh at or after its receipt block.</p></div>}
      {hash && receipt.data?.status === 'reverted' && <div className="notice notice-error" role="alert">Transaction reverted; no successful outcome is reported.</div>}
      {(error || receipt.error) && <div className="notice notice-error" role="alert"><strong>Contract action failed</strong><p>{error || contractErrorMessage(receipt.error)}</p></div>}
    </section>
  )
}
