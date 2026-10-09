import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getRetirement } from '../lib/api'
import type { RetirementLookup } from '../lib/types'
import { LabelBadge } from '../components/LabelBadge'
import { CopyValue, ErrorNotice, LoadingBlock } from '../components/Inline'
import { formatDate } from '../lib/format'

export function RetirementRecord({ record }: { record: RetirementLookup }) {
  return <section className="card">
    <LabelBadge label={record.dataLabel} detailed />
    <h2>Retirement for {record.projectId}</h2>
    <dl className="detail-grid">
      <div><dt>Beneficiary</dt><dd>{record.beneficiary}</dd></div>
      <div><dt>Amount</dt><dd>{record.amount} tCO2e</dd></div>
      <div><dt>Serial range (end excluded)</dt><dd><code>[{record.serialStart}, {record.serialEndExclusive})</code></dd></div>
      <div><dt>Retired by</dt><dd><CopyValue value={record.from} /></dd></div>
      <div><dt>Retired at</dt><dd>{formatDate(record.timestamp)}</dd></div>
      <div><dt>Observed block</dt><dd>{record.observedBlock}</dd></div>
    </dl>
    <p>{record.transactionUrl ? <a href={record.transactionUrl} target="_blank" rel="noreferrer">View retirement transaction ↗</a> : <>Local transaction: <code>{record.transactionHash}</code></>}</p>
    <Link to={`/verify/${encodeURIComponent(record.projectId)}`}>Inspect the claim and integrity evidence</Link>
    <p className="fine-print">This is a recorded retirement in the shared contract. It does not establish physical mitigation or retirement in another registry.</p>
  </section>
}

export function RetirementPage() {
  const { ref = '', serial = '' } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(ref)
  const [input, setInput] = useState(serial)
  const [error, setError] = useState('')
  const query = useQuery({ queryKey: ['retirement', ref, serial], queryFn: () => getRetirement(ref, serial), enabled: Boolean(ref && /^\d+$/.test(serial)) })
  return <div className="page">
    <div className="hero compact-hero"><p className="eyebrow">Public retirement lookup</p><h1>Inspect a retirement serial.</h1><p>No wallet or login required. Search a project and any serial inside its retirement range.</p></div>
    <form className="card" onSubmit={event => {
      event.preventDefault()
      if (!project.trim() || !/^\d+$/.test(input) || BigInt(input) > 18446744073709551615n) { setError('Enter a project and a nonnegative uint64 serial.'); return }
      setError('')
      navigate(`/retirements/${encodeURIComponent(project.trim())}/${input}`)
    }}>
      <label className="field"><span>Project ID or claim hash</span><input value={project} onChange={event => setProject(event.target.value)} required /></label>
      <label className="field"><span>Serial</span><input inputMode="numeric" value={input} onChange={event => setInput(event.target.value)} required /></label>
      <button className="button button-primary" type="submit">Look up retirement</button>
    </form>
    {error && <ErrorNotice>{error}</ErrorNotice>}
    {query.isLoading && <LoadingBlock>Reading retirement and transaction…</LoadingBlock>}
    {query.error && <ErrorNotice title="Retirement unavailable">{query.error.message}</ErrorNotice>}
    {query.data && !query.error && <RetirementRecord record={query.data} />}
  </div>
}
