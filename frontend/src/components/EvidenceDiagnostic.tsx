import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getEvidenceDiagnostic } from '../lib/api'
import { LabelBadge } from './LabelBadge'
import { ErrorNotice, LoadingBlock } from './Inline'

export function EvidenceDiagnostic() {
  const [enabled, setEnabled] = useState(false)
  const query = useQuery({ queryKey: ['evidence-diagnostic'], queryFn: getEvidenceDiagnostic, enabled })
  return <section className="card">
    <h2>Cross-project evidence consistency</h2>
    <p>Check for shared NDVI step changes in cached observations. This diagnostic never changes integrity scores.</p>
    <button className="button button-secondary" onClick={() => { setEnabled(true); if (enabled) void query.refetch() }}>Check cached evidence</button>
    {query.isLoading && <LoadingBlock>Comparing cached observations…</LoadingBlock>}
    {query.error && <ErrorNotice>{query.error.message}</ErrorNotice>}
    {query.data && !query.error && <>
      <p>{query.data.uniqueCachedBoundaries} independent cached boundaries; {query.data.missingEvidenceProjects} projects without cached evidence.</p>
      <p className="fine-print">{query.data.note}</p>
      {query.data.warnings.length === 0 && <p>No common step met this diagnostic's review trigger.</p>}
      {query.data.warnings.map(warning => <article className="notice notice-warning" key={`${warning.dataset}-${warning.method}-${warning.fromYear}-${warning.toYear}`}>
        <strong>Evidence anomaly warning: {warning.fromYear} → {warning.toYear}</strong>
        <p>{warning.message}</p>
        <p>{warning.affectedCount}/{warning.comparisonCount} boundaries; median NDVI change {warning.medianDelta.toFixed(3)}.</p>
        <ul>{warning.projects.map(project => <li key={project.projectId}>{project.projectId} <LabelBadge label={project.dataLabel} /> · Δ {project.delta.toFixed(3)}</li>)}</ul>
      </article>)}
    </>}
  </section>
}
