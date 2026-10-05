import type { IntegrityScore } from '../lib/types'

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
    </section>
  )
}
