import { afterEach, expect, it, vi } from 'vitest'
import { getClaim, verifyClaim, getRegistryMap } from './api'

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

it('loads every registry page at the first observed block and includes only Registered projects', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ total: 3, observedBlock: 50, items: [{ claimHash: 'a', status: 'registered' }, { claimHash: 'b', status: 'pending' }] })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ total: 3, observedBlock: 50, items: [{ claimHash: 'c', status: 'registered' }] })))
  vi.stubGlobal('fetch', fetch)
  const map = await getRegistryMap()
  expect(map.items.map(item => item.claimHash)).toEqual(['a', 'c'])
  expect(fetch.mock.calls[1][0]).toContain('offset=2&limit=200&includeBoundary=true&atBlock=50')
})

it('fails rather than showing an incomplete map if registry pagination changes', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ total: 2, items: [{ claimHash: 'a' }] })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ total: 3, items: [{ claimHash: 'b' }] }))))
  await expect(getRegistryMap()).rejects.toThrow('Registry changed')
})
