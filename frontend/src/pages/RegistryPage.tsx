import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getRegistry } from '../lib/api'
import { LabelBadge } from '../components/LabelBadge'
import { ErrorNotice, LoadingBlock } from '../components/Inline'
import { formatNumber } from '../lib/format'

const PAGE_SIZE = 20

export function RegistryPage() {
  const [page, setPage] = useState(0)
  const query = useQuery({ queryKey: ['registry', page], queryFn: () => getRegistry(page * PAGE_SIZE, PAGE_SIZE) })
  const pages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1

  return (
    <div className="page">
      <div className="hero compact-hero"><p className="eyebrow">Public registry</p><h1>Inspect every registered claim.</h1><p>Project boundaries, evidence, integrity scores, and on-chain activity are public and independently verifiable.</p></div>
      {query.isLoading && <LoadingBlock>Loading registry…</LoadingBlock>}
      {query.error && <ErrorNotice>{query.error.message}</ErrorNotice>}
      {query.data && (
        <section className="card table-card">
          <div className="table-summary"><strong>{formatNumber(query.data.total, 0)} claims</strong><span>Page {page + 1} of {pages}</span></div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Project</th><th>Label</th><th>Type</th><th>Vintage</th><th>Credits</th><th>Area</th><th>Score</th><th>Status</th></tr></thead>
              <tbody>
                {query.data.items.map((item) => (
                  <tr key={item.claimHash}>
                    <td><Link className="table-link" to={`/verify/${encodeURIComponent(item.projectId)}`}>{item.projectId}</Link>{item.sourceRegistry && <small>{item.sourceRegistry}</small>}</td>
                    <td><LabelBadge label={item.dataLabel} /></td>
                    <td>{item.projectType.replaceAll('_', ' ')}</td>
                    <td>{item.vintageYear}</td>
                    <td>{formatNumber(item.claimedCredits, 0)}</td>
                    <td>{formatNumber(item.areaHa)} ha</td>
                    <td><span className={`table-score band-${item.band}`}>{item.score}</span></td>
                    <td><span className={`status-pill status-${item.status}`}>{item.status}</span></td>
                  </tr>
                ))}
                {query.data.items.length === 0 && <tr><td colSpan={8} className="empty-cell">No claims have been registered yet.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="pagination"><button className="button button-secondary" disabled={page === 0 || query.isFetching} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="button button-secondary" disabled={page + 1 >= pages || query.isFetching} onClick={() => setPage((value) => value + 1)}>Next</button></div>
        </section>
      )}
    </div>
  )
}
