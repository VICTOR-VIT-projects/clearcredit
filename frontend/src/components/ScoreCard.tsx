import type { IntegrityScore } from '../lib/types'
import { CopyValue } from './Inline'
import { formatNumber } from '../lib/format'

export function ScoreCard({ score }: { score: IntegrityScore }) {
  return (
    <section className="card score-card" aria-labelledby="integrity-score-heading">
      <div className="section-heading score-heading">
        <div>
          <p className="eyebrow">Transparent rule-based check</p>
          <h2 id="integrity-score-heading">Integrity score</h2>
        </div>
        <div className={`score-orb band-${score.band}`}>
          <strong>{score.score}</strong><span>/100</span>
        </div>
      </div>
      <div className="score-track" aria-label={`Integrity score ${score.score} out of 100`}>
        <span className={`band-${score.band}`} style={{ width: `${score.score}%` }} />
      </div>
      <p className={`band-label band-${score.band}`}>{score.band} integrity band · {score.modelVersion}</p>
      <div className="reason-list">
        {score.reasons.map((reason, index) => (
          <article className={`reason severity-${reason.severity}`} key={`${reason.code}-${index}`}>
            <div className="reason-topline">
              <strong>{reason.code.replaceAll('_', ' ')}</strong>
              <span>{reason.deduction > 0 ? `−${reason.deduction}` : 'No deduction'}</span>
            </div>
            <p>{reason.text}</p>
          </article>
        ))}
      </div>
      {score.attestationEvidence && <details className="subsection">
        <summary>Attestation evidence and project issuance history</summary>
        <p>Evidence version: {score.attestationEvidence.evidenceVersion}. The attestation commits both the satellite evidence hash and the history below.</p>
        {score.evidenceHash && <CopyValue value={score.evidenceHash} />}
        <p>History for {score.attestationEvidence.issuanceHistory.projectId || 'this project'}: {score.attestationEvidence.issuanceHistory.status === 'available' ? `${score.attestationEvidence.issuanceHistory.vintageCount} earlier vintages` : 'no history baseline'}.</p>
        {Object.entries(score.attestationEvidence.issuanceHistory.priorVintages).length > 0 && <table><thead><tr><th>Prior vintage</th><th>Issued credits</th></tr></thead><tbody>{Object.entries(score.attestationEvidence.issuanceHistory.priorVintages).map(([year, credits]) => <tr key={year}><td>{year}</td><td>{formatNumber(credits, 0)}</td></tr>)}</tbody></table>}
        <p>{score.attestationEvidence.issuanceHistory.limitation}</p>
        <p>{score.attestationEvidence.issuanceHistory.source || 'No issuance source available.'}</p>
        {score.attestationEvidence.issuanceHistory.snapshotHash && <CopyValue value={score.attestationEvidence.issuanceHistory.snapshotHash} />}
      </details>}
    </section>
  )
}
