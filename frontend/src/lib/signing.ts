import { claimHash, projectKey } from './canonical'
import { cellsRoot } from './cells'
import type { Claim, PreviewResponse } from './types'

export function validateSigningPayload(claim: Claim, preview: PreviewResponse, walletAddress: string | undefined, chainId: number | undefined): void {
  const td = preview.typedData
  if (!walletAddress || walletAddress.toLowerCase() !== claim.developer.toLowerCase()) throw new Error('The wallet account changed. Reconnect the prepared developer wallet or check a new claim.')
  if (!td || chainId !== td.domain.chainId) throw new Error('Switch to the prepared claim network before signing.')
  const expectedTypes = [
    { name: 'projectId', type: 'bytes32' }, { name: 'claimHash', type: 'bytes32' },
    { name: 'vintageYear', type: 'uint16' }, { name: 'claimedCredits', type: 'uint64' },
    { name: 'cellsRoot', type: 'bytes32' },
  ]
  if (td.domain.name !== 'ClearCredit' || td.domain.version !== '2' || td.primaryType !== 'Claim' || JSON.stringify(td.types.Claim) !== JSON.stringify(expectedTypes)) throw new Error('Unsupported claim signing format.')
  if (preview.claimHash !== claimHash(claim as unknown as Record<string, unknown>) || preview.projectKey !== projectKey(claim.projectId) ||
      preview.cellIds.length !== preview.cellCount || cellsRoot(preview.cellIds) !== preview.cellsRoot ||
      td.message.claimHash !== preview.claimHash || td.message.projectId !== preview.projectKey ||
      Number(td.message.vintageYear) !== claim.vintageYear || Number(td.message.claimedCredits) !== claim.claimedCredits || td.message.cellsRoot !== preview.cellsRoot) {
    throw new Error('The signature does not match the prepared claim and committed cell list.')
  }
}
