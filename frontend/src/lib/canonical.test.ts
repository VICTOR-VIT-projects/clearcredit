import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { canonicalString, claimHash, projectKey } from './canonical'

interface Vector {
  name: string
  claim: Record<string, unknown>
  canonical: string
  claimHash: string
  projectKey: string
}

const source = JSON.parse(
  readFileSync(new URL('../../../docs/claim-hash-vectors.json', import.meta.url), 'utf8'),
) as { vectors: Vector[] }

describe('ClearCredit cross-language claim hash vectors', () => {
  it.each(source.vectors)('$name', (vector) => {
    expect(canonicalString(vector.claim)).toBe(vector.canonical)
    expect(claimHash(vector.claim)).toBe(vector.claimHash)
    expect(projectKey(vector.claim.projectId as string)).toBe(vector.projectKey)
  })
})
