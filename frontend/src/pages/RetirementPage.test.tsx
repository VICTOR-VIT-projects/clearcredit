import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { RetirementRecord } from './RetirementPage'
import type { RetirementLookup } from '../lib/types'

const record: RetirementLookup = {
  projectId: 'DEMO', claimHash: `0x${'11'.repeat(32)}`, dataLabel: 'synthetic', serial: '9007199254740993',
  serialStart: '9007199254740993', serialEndExclusive: '9007199254740995', amount: '2', beneficiary: '<script>buyer</script>',
  from: `0x${'22'.repeat(20)}`, timestamp: 1700000000, transactionHash: `0x${'33'.repeat(32)}`, transactionUrl: null,
  blockNumber: 10, observedBlock: 12,
}

it('shows the data label and exact large serial strings and escapes the beneficiary', () => {
  const html = renderToStaticMarkup(<MemoryRouter><RetirementRecord record={record} /></MemoryRouter>)
  expect(html).toContain('SYNTHETIC')
  expect(html).toContain('9007199254740993')
  expect(html).toContain('9007199254740995')
  expect(html).toContain('&lt;script&gt;buyer&lt;/script&gt;')
  expect(html).toContain('Local transaction')
})

it('links the matching transaction when an explorer is configured', () => {
  const html = renderToStaticMarkup(<MemoryRouter><RetirementRecord record={{ ...record, transactionUrl: 'https://example.invalid/tx/record' }} /></MemoryRouter>)
  expect(html).toContain('https://example.invalid/tx/record')
  expect(html).toContain('end excluded')
})
