import { afterEach, expect, it, vi } from 'vitest'
import { getClaim, verifyClaim } from './api'

afterEach(() => vi.unstubAllGlobals())

it('requires the wallet receipt block for claim and verification refreshes', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetch)
  await getClaim('PROJECT A', 123)
  await verifyClaim('PROJECT A', 123)
  expect(fetch.mock.calls[0][0]).toContain('/claims/PROJECT%20A?minBlock=123')
  expect(fetch.mock.calls[1][0]).toContain('/claims/PROJECT%20A/verify?minBlock=123')
})

it('surfaces a lagging RPC as retryable unavailability', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    error: { code: 'CHAIN_READ_UNAVAILABLE', message: 'Retry shortly.', details: { retryable: true } },
  }), { status: 503 })))
  await expect(getClaim('A', 123)).rejects.toMatchObject({ code: 'CHAIN_READ_UNAVAILABLE', status: 503 })
})
