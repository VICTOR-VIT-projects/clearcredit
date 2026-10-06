import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAccount, useSignTypedData } from 'wagmi'
import { ApiError, previewClaim, submitClaim } from '../lib/api'
import type { Boundary } from '../lib/canonical'
import type { Claim, ClaimView, DataLabel, PreviewResponse, ProjectType } from '../lib/types'
import { BoundaryMap } from '../components/BoundaryMap'
import { ErrorNotice, CopyValue } from '../components/Inline'
import { LabelBadge } from '../components/LabelBadge'
import { ScoreCard } from '../components/ScoreCard'
import { formatNumber, percent } from '../lib/format'

const ERROR_EXPLANATIONS: Record<string, string> = {
  OVERLAP_DETECTED: 'Registration is blocked because the same land and vintage are already claimed. Resolve the boundary conflict before trying again.',
  DUPLICATE_CLAIM: 'This project ID or identical claim is already registered. Search the registry instead of submitting it again.',
  INVALID_GEOMETRY: 'The boundary is invalid. Check that rings do not cross, use longitude/latitude, and contain enough distinct points.',
  BAD_SIGNATURE: 'The wallet signature does not match the developer address in this claim. Reconnect the correct wallet and prepare the claim again.',
  RELAY_FAILED: 'The claim was saved, but the on-chain relay failed. Retry with the same prepared claim; the idempotency key will be reused safely.',
  IDEMPOTENCY_KEY_REUSED: 'This retry key was used with a different request. Prepare the claim again before resubmitting.',
  REQUEST_IN_PROGRESS: 'The relay is still processing. Wait a moment, then retry; the same request key will be reused.',
  NETWORK_ERROR: 'The API could not be reached. Check that the backend is running, then retry.',
  VALIDATION_ERROR: 'The backend rejected one or more fields. Review the form and boundary data.',
  REQUEST_TOO_LARGE: 'The request exceeds the 2 MiB limit. Simplify the boundary before submitting.',
}

type SubmitStage = 'editing' | 'checking' | 'ready' | 'signing' | 'relaying' | 'registered'

function asObject(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function geometryFromGeoJson(input: unknown): Boundary {
  const root = asObject(input)
  if (!root) throw new Error('GeoJSON must be a JSON object.')

  let candidates: unknown[] = []
  if (root.type === 'FeatureCollection') {
    if (!Array.isArray(root.features)) throw new Error('FeatureCollection.features must be an array.')
    candidates = root.features
      .map((feature) => asObject(feature)?.geometry)
      .filter((geometry) => {
        const object = asObject(geometry)
        return object?.type === 'Polygon' || object?.type === 'MultiPolygon'
      })
    if (candidates.length !== 1) throw new Error('FeatureCollection must contain exactly one Polygon or MultiPolygon feature.')
  } else if (root.type === 'Feature') {
    candidates = [root.geometry]
  } else {
    candidates = [root]
  }

  const geometry = asObject(candidates[0])
  if (!geometry || (geometry.type !== 'Polygon' && geometry.type !== 'MultiPolygon') || !Array.isArray(geometry.coordinates)) {
    throw new Error('Boundary must be a Polygon or MultiPolygon geometry.')
  }
  return { type: geometry.type, coordinates: geometry.coordinates } as Boundary
}

function errorInfo(error: unknown): { code: string; message: string; retryable: boolean } {
  if (error instanceof ApiError) {
    return {
      code: error.code,
      message: ERROR_EXPLANATIONS[error.code] || error.message,
      retryable: error.status === 0 || error.status === 502 || error.code === 'REQUEST_IN_PROGRESS',
    }
  }
  const message = error instanceof Error ? error.message : 'An unexpected error occurred.'
  return { code: 'CLIENT_ERROR', message, retryable: false }
}

export function SubmitPage() {
  const { address, chainId, isConnected } = useAccount()
  const { signTypedDataAsync } = useSignTypedData()
  const [projectId, setProjectId] = useState('')
  const [projectType, setProjectType] = useState<ProjectType>('avoided_deforestation')
  const [vintageYear, setVintageYear] = useState(String(new Date().getFullYear() - 1))
  const [claimedCredits, setClaimedCredits] = useState('')
  const [sourceRegistry, setSourceRegistry] = useState('')
  const [dataLabel, setDataLabel] = useState<DataLabel>('synthetic')
  const [boundaryText, setBoundaryText] = useState('')
  const [boundary, setBoundary] = useState<Boundary | null>(null)
  const [boundaryError, setBoundaryError] = useState('')
  const [stage, setStage] = useState<SubmitStage>('editing')
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [preparedClaim, setPreparedClaim] = useState<Claim | null>(null)
  const [idempotencyKey, setIdempotencyKey] = useState('')
  const [signature, setSignature] = useState('')
  const [result, setResult] = useState<ClaimView | null>(null)
  const [replays, setReplays] = useState(0)
  const [error, setError] = useState<ReturnType<typeof errorInfo> | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const invalidate = () => {
    setPreview(null)
    setPreparedClaim(null)
    setIdempotencyKey('')
    setSignature('')
    setResult(null)
    setError(null)
    setStage('editing')
  }

  const updateBoundaryText = (value: string) => {
    setBoundaryText(value)
    invalidate()
    if (!value.trim()) {
      setBoundary(null)
      setBoundaryError('')
      return
    }
    try {
      setBoundary(geometryFromGeoJson(JSON.parse(value)))
      setBoundaryError('')
    } catch (parseError) {
      setBoundary(null)
      setBoundaryError(parseError instanceof Error ? parseError.message : 'Could not read this GeoJSON.')
    }
  }

  const claim = useMemo<Claim | null>(() => {
    const year = Number(vintageYear)
    const credits = Number(claimedCredits)
    if (!address || !boundary || !projectId || !Number.isInteger(year) || !Number.isSafeInteger(credits) || credits <= 0) return null
    return {
      schemaVersion: '1.0',
      projectId,
      developer: address,
      projectType,
      vintageYear: year,
      claimedCredits: credits,
      creditUnit: 'tCO2e',
      boundary,
      boundaryCrs: 'EPSG:4326',
      sourceRegistry: sourceRegistry.trim() || null,
      dataLabel,
    }
  }, [address, boundary, claimedCredits, dataLabel, projectId, projectType, sourceRegistry, vintageYear])

  const updateField = (setter: (value: string) => void) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setter(event.target.value)
    invalidate()
  }

  const checkClaim = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!claim) return
    setError(null)
    setStage('checking')
    try {
      const nextPreview = await previewClaim(claim)
      setPreparedClaim(claim)
      setPreview(nextPreview)
      setIdempotencyKey(crypto.randomUUID())
      setStage('ready')
    } catch (requestError) {
      setError(errorInfo(requestError))
      setStage('editing')
    }
  }

  const relay = async (nextSignature: string) => {
    if (!preparedClaim || !idempotencyKey) return
    setError(null)
    setStage('relaying')
    try {
      const { view, replayed } = await submitClaim(preparedClaim, nextSignature, idempotencyKey)
      setResult(view)
      setReplays((count) => (replayed ? count + 1 : 0))
      setStage('registered')
    } catch (requestError) {
      setError(errorInfo(requestError))
      setStage('ready')
    }
  }

  const signAndRegister = async () => {
    if (!preview?.typedData || !preparedClaim) return
    setError(null)
    setStage('signing')
    const typed = preview.typedData
    const message = { ...typed.message }
    for (const field of typed.types[typed.primaryType] || []) {
      if (field.type.startsWith('uint') || field.type.startsWith('int')) message[field.name] = BigInt(message[field.name] as string | number) as unknown as number
    }
    try {
      const signed = await signTypedDataAsync({
        domain: typed.domain,
        types: typed.types,
        primaryType: typed.primaryType,
        message,
      })
      setSignature(signed)
      await relay(signed)
    } catch (signError) {
      setError(errorInfo(signError))
      setStage('ready')
    }
  }

  const chainMismatch = preview?.typedData && chainId !== preview.typedData.domain.chainId

  return (
    <div className="page page-submit">
      <div className="hero compact-hero">
        <p className="eyebrow">Register with evidence</p>
        <h1>Check a carbon-credit claim before it reaches the chain.</h1>
        <p>We check exact boundary overlap, independent satellite evidence, and the conservative on-chain land-cell index. The result is an integrity score—not proof of physical truth.</p>
      </div>

      <div className="submit-layout">
        <form className="card form-card" onSubmit={checkClaim}>
          <div className="section-heading"><div><p className="step-label">01</p><h2>Claim details</h2></div></div>
          {!isConnected && <div className="notice notice-info"><strong>Connect a wallet to begin.</strong><p>The connected address becomes the claim developer and signs the prepared claim.</p></div>}
          <div className="form-grid">
            <label className="field field-wide"><span>Project ID</span><input required maxLength={64} pattern="[A-Za-z0-9._:-]{1,64}" placeholder="e.g. VCS1115" value={projectId} onChange={updateField(setProjectId)} /></label>
            <label className="field"><span>Project type</span><select value={projectType} onChange={updateField((value) => setProjectType(value as ProjectType))}><option value="avoided_deforestation">Avoided deforestation</option><option value="afforestation">Afforestation</option><option value="other">Other</option></select></label>
            <label className="field"><span>Vintage year</span><input required type="number" min="2000" max="2100" value={vintageYear} onChange={updateField(setVintageYear)} /></label>
            <label className="field"><span>Claimed credits (tCO2e)</span><input required type="number" min="1" step="1" value={claimedCredits} onChange={updateField(setClaimedCredits)} /></label>
            <label className="field"><span>Data label</span><select value={dataLabel} onChange={updateField((value) => setDataLabel(value as DataLabel))}><option value="synthetic">Synthetic</option><option value="illustrative">Illustrative</option><option value="real">Real</option></select></label>
            <label className="field field-wide"><span>Source registry <em>optional</em></span><input maxLength={200} placeholder="Registry name and external ID" value={sourceRegistry} onChange={updateField(setSourceRegistry)} /></label>
          </div>

          <div className="boundary-input">
            <div className="field-label-row"><label htmlFor="boundary-geojson">Boundary GeoJSON</label><button className="text-button" type="button" onClick={() => fileRef.current?.click()}>Upload file</button></div>
            <input ref={fileRef} hidden type="file" accept=".json,.geojson,application/json,application/geo+json" onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void file.text().then(updateBoundaryText).catch(() => setBoundaryError('Could not read that file.'))
            }} />
            <textarea id="boundary-geojson" required rows={9} spellCheck={false} placeholder={'Paste a Polygon, MultiPolygon, Feature, or FeatureCollection…'} value={boundaryText} onChange={(event) => updateBoundaryText(event.target.value)} />
            {boundaryError && <p className="field-error">{boundaryError}</p>}
            {boundary && <p className="field-success">Boundary parsed: {boundary.type}</p>}
          </div>
          <button className="button button-primary button-full" disabled={!claim || stage === 'checking'} type="submit">
            {stage === 'checking' ? <><span className="spinner" /> Checking boundary and evidence…</> : 'Check claim'}
          </button>
        </form>

        <aside className="submit-aside">
          {boundary ? <BoundaryMap boundary={boundary} compact /> : <div className="map-placeholder"><span>Boundary preview</span><p>Paste or upload GeoJSON to inspect the project area.</p></div>}
          <div className="card mini-explainer"><strong>What the check can prove</strong><p>Registration makes the claim tamper-evident. It does not make the underlying claim true. Evidence and conflicts determine the integrity score.</p></div>
        </aside>
      </div>

      {error && <ErrorNotice title={error.code.replaceAll('_', ' ')}>{error.message}</ErrorNotice>}

      {preview && preparedClaim && (
        <div className="results-stack">
          <div className="results-header"><div><p className="step-label">02</p><h2>Prepared claim</h2></div><LabelBadge label={preparedClaim.dataLabel} /></div>
          {preview.blocked && (
            <div className="notice notice-blocked" role="alert">
              <strong>{preview.overlaps.length > 0 ? `Blocked: overlaps project ${preview.overlaps[0].project_id} by ${percent(Math.max(preview.overlaps[0].fraction_of_new, preview.overlaps[0].fraction_of_existing))} for vintage ${preparedClaim.vintageYear}` : `Blocked: land cells are already claimed for vintage ${preparedClaim.vintageYear}`}</strong>
              {preview.overlaps.map((overlap) => <p key={overlap.project_id}>{formatNumber(overlap.intersection_ha)} ha intersects {overlap.project_id} ({percent(overlap.fraction_of_new)} of this boundary).</p>)}
              {preview.onChainCellConflicts.map((conflict) => <p key={conflict.projectId}>On-chain cell conflict with {conflict.projectId}: {conflict.count} cells ({conflict.cells.join(', ')}{conflict.count > conflict.cells.length ? ', …' : ''}).</p>)}
            </div>
          )}
          {preview.score.band === 'low' && !preview.blocked && <div className="notice notice-warning"><strong>Low integrity score</strong><p>The claim is flagged as suspicious by the published rules. If registered, the contract will refuse issuance until a passing verified integrity attestation is posted.</p></div>}
          <div className="metrics-grid">
            <div className="metric"><span>Area</span><strong>{formatNumber(preview.areaHa)} ha</strong></div>
            <div className="metric"><span>H3 land cells</span><strong>{formatNumber(preview.cellCount)}</strong><small>resolution {preview.cellResolution}</small></div>
            <div className="metric metric-wide"><span>Claim hash</span><CopyValue value={preview.claimHash} /></div>
          </div>
          <ScoreCard score={preview.score} />

          {!preview.blocked && (
            <section className="card register-card">
              <div className="section-heading"><div><p className="step-label">03</p><h2>Sign &amp; register</h2></div></div>
              <p>Your wallet signs the exact claim hash. The API relays registration and posts the verified integrity attestation.</p>
              {!preview.typedData && <div className="notice notice-warning"><strong>Signing unavailable</strong><p>The API did not return EIP-712 typed data. It may be running without a configured chain.</p></div>}
              {chainMismatch && <div className="notice notice-warning"><strong>Wrong network</strong><p>The prepared signature targets chain {preview.typedData?.domain.chainId}, but your wallet is on chain {chainId}. Switch networks before signing.</p></div>}
              {stage === 'signing' && <div className="progress-row"><span className="spinner" /><div><strong>Waiting for signature</strong><span>Confirm the EIP-712 message in your wallet.</span></div></div>}
              {stage === 'relaying' && <div className="progress-row"><span className="spinner" /><div><strong>Relaying on-chain</strong><span>This normally takes 10–60 seconds. Keep this page open.</span></div></div>}
              {stage !== 'registered' && (
                <div className="button-row">
                  <button className="button button-primary" type="button" disabled={!preview.typedData || Boolean(chainMismatch) || stage === 'signing' || stage === 'relaying'} onClick={() => void signAndRegister()}>{signature ? 'Sign again' : 'Sign & register'}</button>
                  {error?.retryable && signature && <button className="button button-secondary" type="button" disabled={stage === 'relaying'} onClick={() => void relay(signature)}>Retry same request</button>}
                </div>
              )}
            </section>
          )}
        </div>
      )}

      {stage === 'registered' && result && (
        <section className="card success-card">
          <span className="success-icon">✓</span>
          <div><p className="eyebrow">Registered</p><h2>{result.projectId} is on the registry.</h2><p>The record is now tamper-evident. Review the evidence and on-chain state on the public Verify page.</p>
            {result.warnings?.map((warning) => <div className="notice notice-warning" key={warning.code}><strong>{warning.code.replaceAll('_', ' ')}</strong><p>{warning.message}</p></div>)}
            {replays > 0 && <div className="notice notice-success"><strong>Same request replayed{replays > 1 ? ` ×${replays}` : ''}</strong><p>The API recognised the Idempotency-Key and returned the original result. No new record and no new transaction were created.</p></div>}
            <div className="button-row"><Link className="button button-primary" to={`/verify/${encodeURIComponent(result.projectId)}`}>Open Verify page</Link>{signature && <button className="button button-secondary" type="button" onClick={() => void relay(signature)}>Send the same request again</button>}{result.transactions.map((transaction) => transaction.url ? <a key={transaction.tx} className="button button-secondary" href={transaction.url} target="_blank" rel="noreferrer">{transaction.step} ↗</a> : null)}</div>
          </div>
        </section>
      )}
    </div>
  )
}
