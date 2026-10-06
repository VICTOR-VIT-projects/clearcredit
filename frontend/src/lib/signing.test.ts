import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { claimHash, projectKey } from './canonical'
import { cellsRoot } from './cells'
import { validateSigningPayload } from './signing'
import type { ClaimView, PreviewResponse } from './types'

const sample = JSON.parse(readFileSync(new URL('../../../docs/sample-claim-response.json', import.meta.url), 'utf8')) as ClaimView
const claim = sample.claim
const cellIds = ['0x880000000000001', '0x880000000000002']
function preview(): PreviewResponse {
  const hash = claimHash(claim as unknown as Record<string, unknown>)
  const pk = projectKey(claim.projectId)
  const root = cellsRoot(cellIds)
  return {
    claimHash: hash, projectKey: pk, cellsRoot: root, cellIds, cellCount: 2,
    submissionKey: hash, areaHa: sample.areaHa, overlaps: [], onChainCellConflicts: [], cellResolution: 8,
    score: sample.score, blocked: false, canonicalClaim: {},
    typedData: {
      domain: { name: 'ClearCredit', version: '2', chainId: 31337, verifyingContract: `0x${'11'.repeat(20)}` }, primaryType: 'Claim',
      types: { Claim: [{ name: 'projectId', type: 'bytes32' }, { name: 'claimHash', type: 'bytes32' }, { name: 'vintageYear', type: 'uint16' }, { name: 'claimedCredits', type: 'uint64' }, { name: 'cellsRoot', type: 'bytes32' }] },
      message: { projectId: pk, claimHash: hash, vintageYear: claim.vintageYear, claimedCredits: claim.claimedCredits, cellsRoot: root },
    },
  }
}

describe('prepared wallet consent', () => {
  it('accepts the exact v2 payload and rejects account/network changes', () => {
    expect(() => validateSigningPayload(claim, preview(), claim.developer, 31337)).not.toThrow()
    expect(() => validateSigningPayload(claim, preview(), `0x${'22'.repeat(20)}`, 31337)).toThrow('wallet account changed')
    expect(() => validateSigningPayload(claim, preview(), claim.developer, 84532)).toThrow('network')
  })
  it('rejects changed claim fields, signature fields and a substituted cell list', () => {
    const p = preview()
    p.typedData!.message.claimedCredits = claim.claimedCredits + 1
    expect(() => validateSigningPayload(claim, p, claim.developer, 31337)).toThrow('does not match')
    const changed = preview()
    changed.cellIds = ['0x880000000000001', '0x880000000000003']
    expect(() => validateSigningPayload(claim, changed, claim.developer, 31337)).toThrow('does not match')
    const old = preview()
    old.typedData!.domain.version = '1'
    expect(() => validateSigningPayload(claim, old, claim.developer, 31337)).toThrow('Unsupported')
  })
})
