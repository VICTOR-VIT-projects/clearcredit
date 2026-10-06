import { claimHash } from './canonical'
import type { ClaimView } from './types'

export interface BrowserVerification {
  source: string
  hash?: string
  match?: boolean | null
  error?: string
}

export function verificationSource(view: ClaimView): string {
  return JSON.stringify([view.claim, view.onChain?.project.claimHash ?? null])
}

export function verifyInBrowser(view: ClaimView): BrowserVerification {
  const source = verificationSource(view)
  try {
    const hash = claimHash(view.claim as unknown as Record<string, unknown>)
    const onChainHash = view.onChain?.project.claimHash ?? null
    return { source, hash, match: onChainHash === null ? null : hash.toLowerCase() === onChainHash.toLowerCase() }
  } catch {
    return { source, error: 'The stored claim cannot be hashed. Its content or boundary is malformed; verification is unavailable.' }
  }
}

export function currentVerification(result: BrowserVerification | null, view: ClaimView): BrowserVerification | null {
  return result?.source === verificationSource(view) ? result : null
}
