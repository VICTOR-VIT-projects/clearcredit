import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ScoreCard } from './ScoreCard'
import type { IntegrityScore } from '../lib/types'

describe('issuance-history disclosure', () => {
  it('shows missing history and the separate attestation commitment', () => {
    const score: IntegrityScore = {
      score: 85, scoreBps: 8500, band: 'high', modelVersion: 'rules-v4',
      evidenceHash: `0x${'11'.repeat(32)}`, features: {},
      reasons: [{ code: 'NO_HISTORY', deduction: 0, severity: 'ok', text: 'No history baseline: earlier vintages unavailable.' }],
      attestationEvidence: {
        evidenceVersion: 'ev3', satelliteEvidenceHash: null,
        issuanceHistory: { status: 'no_history', projectId: 'SYN-1', priorVintages: {}, vintageCount: 0,
          medianCredits: null, snapshotHash: null, source: null, limitation: 'Historical boundaries are unavailable.' },
      },
    }
    const html = renderToStaticMarkup(<ScoreCard score={score} />)
    expect(html).toContain('no history baseline')
    expect(html).toContain('Historical boundaries are unavailable.')
    expect(html).toContain(score.evidenceHash)
    expect(html).toContain('ev3')
  })
})
