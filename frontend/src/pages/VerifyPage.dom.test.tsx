// @vitest-environment jsdom
import sampleJson from '../../../docs/sample-claim-response.json'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { VerifyPage } from './VerifyPage'
import { ApiError, getClaim, getOverlaps, verifyClaim } from '../lib/api'
import type { ClaimView } from '../lib/types'

vi.mock('../components/BoundaryMap', () => ({ BoundaryMap: () => <div>Boundary map</div> }))
vi.mock('../components/MetricChart', () => ({ MetricChart: () => <div>Evidence chart</div> }))
vi.mock('../components/DeveloperActions', () => ({ DeveloperActions: ({ onConfirmed }: { onConfirmed: (block: number) => void }) => <button onClick={() => onConfirmed(100)}>Simulate receipt</button> }))
vi.mock('../lib/api', async importOriginal => {
  const original = await importOriginal<typeof import('../lib/api')>()
  return { ...original, getClaim: vi.fn(), getOverlaps: vi.fn(), verifyClaim: vi.fn() }
})

const sample = sampleJson as unknown as ClaimView
let container: HTMLDivElement, root: Root, client: QueryClient

beforeEach(async () => {
  vi.clearAllMocks()
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.mocked(getClaim).mockResolvedValue(structuredClone(sample))
  vi.mocked(getOverlaps).mockResolvedValue({ projectId: sample.projectId, vintageYear: sample.claim.vintageYear, overlaps: [] })
  vi.mocked(verifyClaim).mockResolvedValue({ projectId: sample.projectId, recomputedHash: sample.claimHash, onChainHash: sample.claimHash, match: true, note: null })
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/verify/' + sample.projectId]}><Routes><Route path="/verify/:ref" element={<VerifyPage />} /></Routes></MemoryRouter></QueryClientProvider>))
  await settle()
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
})

async function settle() {
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}

function button(text: string) {
  const result = [...container.querySelectorAll('button')].find(element => element.textContent === text)
  if (!result) throw new Error('Missing button: ' + text)
  return result
}

it('renders the sample without a wallet and recomputes its hash in the mounted page', async () => {
  expect(container.textContent).toContain(sample.projectId)
  expect(container.textContent).toContain('SYNTHETIC')
  await act(async () => button('Recompute hash in your browser').click())
  expect(container.querySelector('.hash-result')?.textContent).toContain('✓ Match')
  expect(container.querySelector('.hash-result')?.textContent).toContain(sample.claimHash)
})

it('hides old totals and Match content when the receipt-block refresh is unavailable', async () => {
  await act(async () => button('Recompute hash in your browser').click())
  vi.mocked(getClaim).mockRejectedValue(new ApiError(503, { error: { code: 'CHAIN_READ_UNAVAILABLE', message: 'Required block unavailable; retry.' } }))
  vi.mocked(verifyClaim).mockRejectedValue(new ApiError(503, { error: { code: 'CHAIN_READ_UNAVAILABLE', message: 'Required block unavailable; retry.' } }))
  await act(async () => button('Simulate receipt').click())
  await settle()
  expect(getClaim).toHaveBeenLastCalledWith(sample.projectId, 100)
  expect(verifyClaim).toHaveBeenLastCalledWith(sample.projectId, 100)
  expect(container.textContent).toContain('Required block unavailable')
  expect(container.querySelector('.hash-result')).toBeNull()
  expect(container.querySelector('.chain-card')).toBeNull()
})

it('clears an old browser Match when refreshed claim content changes', async () => {
  await act(async () => button('Recompute hash in your browser').click())
  const changed = structuredClone(sample)
  changed.claim.claimedCredits += 1
  vi.mocked(getClaim).mockResolvedValue(changed)
  await act(async () => { await client.invalidateQueries({ queryKey: ['claim'] }) })
  await settle()
  expect(container.querySelector('.hash-result')).toBeNull()
  await act(async () => button('Recompute hash in your browser').click())
  expect(container.querySelector('.hash-result')?.textContent).toContain('✗ Mismatch')
})
