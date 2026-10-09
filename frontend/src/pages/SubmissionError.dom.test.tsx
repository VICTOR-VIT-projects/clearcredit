// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { errorInfo, SubmissionError } from './SubmitPage'

vi.mock('../components/BoundaryMap', () => ({ BoundaryMap: () => null }))

it.each([
  ['OVERLAP_DETECTED', 409, 'Registration is blocked', false],
  ['CHAIN_READ_UNAVAILABLE', 503, 'Retry the same signed request', true],
  ['EVIDENCE_INVALID', 503, 'failed its commitment', false],
  ['UNKNOWN_CODE', 400, 'Server fallback', false],
])('renders %s with the correct retry behavior', async (code, status, text, retryable) => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const error = errorInfo(new ApiError(status, { error: { code, message: 'Server fallback' } }))
  const container = document.createElement('div')
  const root = createRoot(container)
  try {
    await act(async () => root.render(<SubmissionError error={error} />))
    expect(container.querySelector('[role="alert"]')?.textContent).toContain(text)
    expect(error.retryable).toBe(retryable)
  } finally {
    await act(async () => root.unmount())
  }
})
