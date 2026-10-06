import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { currentVerification, verifyInBrowser } from './verification'
import type { ClaimView } from './types'

const sample = JSON.parse(readFileSync(new URL('../../../docs/sample-claim-response.json', import.meta.url), 'utf8')) as ClaimView

describe('browser verification trust result', () => {
  it('recomputes the sample and hides the result on navigation or record refresh', () => {
    const result = verifyInBrowser(sample)
    expect(result.hash).toBe(sample.claimHash)
    expect(currentVerification(result, sample)).toBe(result)
    const changed = structuredClone(sample)
    changed.claim.claimedCredits += 1
    expect(currentVerification(result, changed)).toBeNull()
    const next = structuredClone(sample)
    next.claim.projectId = 'another-project'
    expect(currentVerification(result, next)).toBeNull()
  })

  it('renders malformed stored content as unavailable and offline content without a match', () => {
    const bad = structuredClone(sample)
    bad.claim.boundary.coordinates = []
    expect(verifyInBrowser(bad).error).toBeTruthy()
    expect(verifyInBrowser({ ...sample, onChain: null }).match).toBeNull()
  })
})
