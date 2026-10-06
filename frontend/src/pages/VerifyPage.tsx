import { useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { BoundaryMap } from '../components/BoundaryMap'
import { DeveloperActions } from '../components/DeveloperActions'
import { CopyValue, ErrorNotice, LoadingBlock } from '../components/Inline'
import { LabelBadge } from '../components/LabelBadge'
import { MetricChart } from '../components/MetricChart'
import { ScoreCard } from '../components/ScoreCard'
import { getClaim, getOverlaps, verifyClaim } from '../lib/api'
import { currentVerification, verifyInBrowser, type BrowserVerification } from '../lib/verification'
import { formatDate, formatNumber, humanize, percent } from '../lib/format'
import type { ClaimView } from '../lib/types'

function downloadClaim(view: ClaimView) {
  const blob = new Blob([JSON.stringify(view.claim, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${view.projectId}-claim.json`
  link.click()
  URL.revokeObjectURL(url)
}

function VerifySearch({ initial = '' }: { initial?: string }) {
  const [search, setSearch] = useState(initial)
  const navigate = useNavigate()
  return (
    <form className="verify-search" onSubmit={(event) => { event.preventDefault(); const value = search.trim(); if (value) navigate(`/verify/${encodeURIComponent(value)}`) }}>
      <label htmlFor="claim-search">Project ID or claim hash</label>
      <div><input id="claim-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="VCS1115 or 0x…" /><button className="button button-primary" type="submit">Verify claim</button></div>
    </form>
  )
}

function OverlapsPanel({ view }: { view: ClaimView }) {
  const query = useQuery({ queryKey: ['overlaps', view.projectId], queryFn: () => getOverlaps(view.projectId) })
  const overlaps = query.data?.overlaps ?? view.overlaps
  return (
    <section className="card">
      <div className="section-heading"><div><p className="eyebrow">Double-counting check</p><h2>Boundary overlaps</h2></div><span className={`status-pill ${overlaps.length ? 'status-danger' : 'status-ok'}`}>{overlaps.length ? `${overlaps.length} found` : 'None found'}</span></div>
      {query.isLoading && <p className="muted">Refreshing exact overlap results…</p>}
      {query.error && <p className="muted">Live overlap refresh failed; showing the stored result.</p>}
      {overlaps.length === 0 ? <p>No exact polygon overlap with another claim for vintage {view.claim.vintageYear}.</p> : <div className="overlap-list">{overlaps.map((overlap) => <article key={overlap.project_id}><strong>{overlap.project_id}</strong><p>{formatNumber(overlap.intersection_ha)} ha intersects · {percent(overlap.fraction_of_new)} of this claim · {percent(overlap.fraction_of_existing)} of the existing claim</p></article>)}</div>}
      <p className="fine-print">Exact polygon overlap is checked off-chain. The on-chain H3 cell index is a conservative backstop.</p>
    </section>
  )
}

function EvidencePanel({ view }: { view: ClaimView }) {
  const evidence = view.evidence
  if (!evidence) return <section className="card"><p className="eyebrow">Satellite evidence</p><h2>Evidence not yet computed</h2><p>The claim remains visible, but independent satellite evidence is not available for this boundary yet.</p></section>
  return (
    <section className="card evidence-card">
      <div className="section-heading"><div><p className="eyebrow">Independent evidence</p><h2>Satellite evidence</h2></div><span className="query-time">Queried {formatDate(evidence.queriedAt)}</span></div>
      <div className="evidence-summary"><div><span>Forest cover in 2000</span><strong>{formatNumber(evidence.forestLoss.forest2000Ha)} ha</strong><small>{evidence.forestLoss.canopyThresholdPct}% canopy threshold</small></div><div><span>NDVI slope</span><strong>{evidence.ndvi.slopePerYear === null ? 'Unavailable' : `${evidence.ndvi.slopePerYear >= 0 ? '+' : ''}${evidence.ndvi.slopePerYear.toFixed(5)} /yr`}</strong><small>vegetation greenness trend</small></div><div><span>Satellite evidence hash</span><CopyValue value={evidence.evidenceHash} /></div></div>
      <div className="chart-section"><h3>Forest loss by year</h3><p>Hectares lost inside the project boundary. The vintage year is highlighted.</p><MetricChart title="Forest loss in hectares per year" values={evidence.forestLoss.lossHaByYear} highlightYear={view.claim.vintageYear} unit="ha" color="var(--danger)" /></div>
      <div className="chart-section"><h3>Mean NDVI by year</h3><p>{evidence.ndvi.method}</p><MetricChart title="Mean NDVI per year" values={evidence.ndvi.meanNdviByYear} highlightYear={view.claim.vintageYear} unit="NDVI" /></div>
      <div className="dataset-grid"><article><strong>{evidence.forestLoss.dataset}</strong><span>License: {evidence.forestLoss.license}</span><span>Coverage through {evidence.forestLoss.lastCoveredYear}</span></article><article><strong>{evidence.ndvi.dataset}</strong><span>License: {evidence.ndvi.license}</span></article></div>
    </section>
  )
}

function OnChainPanel({ view }: { view: ClaimView }) {
  if (!view.onChain) return <section className="card"><p className="eyebrow">On-chain</p><h2>No chain configured</h2><p>This API is running in offline mode, so there is no public contract state to compare.</p></section>
  const { project } = view.onChain
  return (
    <section className="card chain-card">
      <div className="section-heading"><div><p className="eyebrow">Chain {view.onChain.chainId}</p><h2>On-chain record</h2></div><span className={`status-pill status-${project.status}`}>{project.status}</span></div>
      <div className="detail-grid"><div><span>Developer</span><CopyValue value={project.developer} /></div><div><span>Land cells</span><strong>{project.cellCount} <small>H3 resolution {view.cellResolution}</small></strong></div><div><span>Claimed</span><strong>{formatNumber(project.claimedCredits, 0)} tCO2e</strong></div><div><span>Issued</span><strong>{formatNumber(project.issued, 0)} tCO2e</strong></div><div><span>Retired</span><strong>{formatNumber(project.retired, 0)} tCO2e</strong></div><div><span>Registered</span><strong>{formatDate(project.registeredAt)}</strong></div></div>
      <div className="subsection"><h3>Verified integrity attestations</h3>{view.onChain.attestations.length === 0 ? <p className="muted">No attestations posted.</p> : <div className="record-list">{view.onChain.attestations.map((attestation, index) => <article key={`${attestation.evidenceHash}-${index}`}><div><strong>{(attestation.scoreBps / 100).toFixed(0)}/100</strong><span>{attestation.modelVersion}</span></div><div><span>Evidence</span><CopyValue value={attestation.evidenceHash} /></div><div><span>Verifier</span><CopyValue value={attestation.verifier} /></div><time>{formatDate(attestation.timestamp)}</time></article>)}</div>}</div>
      <div className="subsection"><h3>Retirements</h3>{view.onChain.retirements.length === 0 ? <p className="muted">No credits retired.</p> : <div className="record-list">{view.onChain.retirements.map((retirement, index) => <article key={`${retirement.serialStart}-${index}`}><div><strong>{formatNumber(retirement.amount, 0)} tCO2e</strong><span>{retirement.beneficiary}</span></div><div><span>Serial range</span><code>[{retirement.serialStart}, {retirement.serialStart + retirement.amount})</code></div><div><span>Retired by</span><CopyValue value={retirement.from} /></div><time>{formatDate(retirement.timestamp)}</time></article>)}</div>}</div>
      <div className="subsection"><h3>Transactions</h3><div className="transaction-list">{view.transactions.map((transaction) => transaction.url ? <a key={transaction.tx} href={transaction.url} target="_blank" rel="noreferrer"><span>{transaction.step}</span><code>{transaction.tx.slice(0, 12)}…</code><strong>View ↗</strong></a> : <div key={transaction.tx}><span>{transaction.step}</span><code>{transaction.tx.slice(0, 12)}…</code><em>Local chain</em></div>)}</div></div>
      <div className="contract-link"><span>Registry contract</span>{view.onChain.explorer ? <a href={view.onChain.explorer} target="_blank" rel="noreferrer">{view.onChain.contract} ↗</a> : <code>{view.onChain.contract} · local chain</code>}</div>
    </section>
  )
}

export function VerifyPage() {
  const { ref = '' } = useParams()
  const decodedRef = decodeURIComponent(ref)
  const query = useQuery({ queryKey: ['claim', decodedRef], queryFn: () => getClaim(decodedRef), enabled: Boolean(decodedRef) })
  const serverVerification = useQuery({ queryKey: ['verify', decodedRef], queryFn: () => verifyClaim(decodedRef), enabled: Boolean(decodedRef) })
  const [browserResult, setLocalResult] = useState<BrowserVerification | null>(null)
  const refresh = useCallback(() => { void query.refetch(); void serverVerification.refetch() }, [query, serverVerification])

  if (!decodedRef) {
    return <div className="page verify-empty"><div className="hero"><p className="eyebrow">Independent verification</p><h1>Verify any ClearCredit claim.</h1><p>No wallet required. Search a project ID or claim hash to inspect the signed claim, recompute its hash, and compare it with the on-chain record.</p></div><VerifySearch /><div className="verify-promises"><div><strong>01</strong><span>Inspect the original claim and boundary</span></div><div><strong>02</strong><span>Recompute its tamper-evident hash locally</span></div><div><strong>03</strong><span>Review evidence, scoring, and chain activity</span></div></div></div>
  }

  return (
    <div className="page verify-page">
      <VerifySearch initial={decodedRef} />
      {query.isLoading && <LoadingBlock>Loading claim and chain state…</LoadingBlock>}
      {query.error && <ErrorNotice title="Claim not found">{query.error.message}</ErrorNotice>}
      {query.data && (() => {
        const view = query.data
        const localResult = currentVerification(browserResult, view)
        return <>
          <header className="claim-header"><div><LabelBadge label={view.dataLabel} detailed /><h1>{view.projectId}</h1><p>{humanize(view.claim.projectType)} · vintage {view.claim.vintageYear} · {formatNumber(view.claim.claimedCredits, 0)} tCO2e</p></div><span className={`status-pill status-${view.status}`}>{view.status}</span></header>
          <section className="card hash-card">
            <div><p className="eyebrow">Canonical claim hash</p><CopyValue value={view.claimHash} /></div>
            <div className="hash-actions"><button className="button button-primary" type="button" onClick={() => setLocalResult(verifyInBrowser(view))}>Recompute hash in your browser</button><button className="button button-secondary" type="button" onClick={() => downloadClaim(view)}>Download claim JSON</button></div>
            <p className="fine-print">Recompute independently: <code>python canonical.py claim.json</code></p>
            {localResult?.error && <ErrorNotice title="Recomputation unavailable">{localResult.error}</ErrorNotice>}
            {localResult?.hash && <div className={`hash-result ${localResult.match === false ? 'hash-mismatch' : localResult.match === true ? 'hash-match' : ''}`}><strong>{localResult.match === true ? '✓ Match' : localResult.match === false ? '✗ Mismatch' : 'Chain comparison unavailable'}</strong><span>Browser result: <code>{localResult.hash}</code></span>{localResult.match === false && <p>The stored claim differs from the on-chain claim hash. Treat this record as altered.</p>}</div>}
            <div className="server-check"><span>API recomputation</span>{serverVerification.isLoading ? <em>Checking…</em> : serverVerification.data ? <strong className={serverVerification.data.match === false ? 'text-danger' : 'text-success'}>{serverVerification.data.match === true ? '✓ Match' : serverVerification.data.match === false ? '✗ Mismatch' : 'No on-chain comparison'}</strong> : <em>Unavailable</em>}</div>
            {serverVerification.data && <div className="server-result"><div><span>Recomputed</span><code>{serverVerification.data.recomputedHash}</code></div><div><span>On-chain</span><code>{serverVerification.data.onChainHash || 'Not available'}</code></div>{serverVerification.data.note && <p>{serverVerification.data.note}</p>}</div>}
          </section>
          <div className="verify-grid">
            <section className="card claim-details"><div className="section-heading"><div><p className="eyebrow">Claim record</p><h2>Project details</h2></div></div><dl><div><dt>Developer</dt><dd><CopyValue value={view.claim.developer} /></dd></div><div><dt>Project type</dt><dd>{humanize(view.claim.projectType)}</dd></div><div><dt>Vintage year</dt><dd>{view.claim.vintageYear}</dd></div><div><dt>Claimed credits</dt><dd>{formatNumber(view.claim.claimedCredits, 0)} {view.claim.creditUnit}</dd></div><div><dt>Area</dt><dd>{formatNumber(view.areaHa)} ha</dd></div><div><dt>Source registry</dt><dd>{view.claim.sourceRegistry || 'Not provided'}</dd></div><div><dt>Boundary source</dt><dd>{view.claim.boundarySource || 'Not provided'}</dd></div><div><dt>Created</dt><dd>{formatDate(view.createdAt)}</dd></div></dl></section>
            <BoundaryMap boundary={view.claim.boundary} />
          </div>
          <OverlapsPanel view={view} />
          <EvidencePanel view={view} />
          <ScoreCard score={view.score} />
          <OnChainPanel view={view} />
          <DeveloperActions view={view} onConfirmed={refresh} />
        </>
      })()}
    </div>
  )
}
