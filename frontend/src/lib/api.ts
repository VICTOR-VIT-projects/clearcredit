import type { ApiErrorBody, Claim, ClaimView, PreviewResponse, RegistryResponse, VerificationResponse } from './types'
import type { RetirementLookup } from './types'

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody) {
    const validation = body.detail?.map((item) => item.msg).join('; ')
    super(body.error?.message || validation || `Request failed with status ${status}.`)
    this.name = 'ApiError'
    this.status = status
    this.code = body.error?.code || (status === 422 ? 'VALIDATION_ERROR' : 'HTTP_ERROR')
    this.details = body.error?.details || {}
  }
}

async function request<T>(path: string, init?: RequestInit, meta?: { replayed?: boolean }): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (error) {
    throw new ApiError(0, { error: { code: 'NETWORK_ERROR', message: error instanceof Error ? error.message : 'The API could not be reached.' } })
  }
  if (meta) meta.replayed = response.headers.get('Idempotent-Replayed') === 'true'
  const body = (await response.json().catch(() => ({}))) as ApiErrorBody | T
  if (!response.ok) throw new ApiError(response.status, body as ApiErrorBody)
  return body as T
}

export function previewClaim(claim: Claim): Promise<PreviewResponse> {
  return request('/claims/preview', { method: 'POST', body: JSON.stringify(claim) })
}

/** `replayed` is true when the API returned the stored result for a repeated Idempotency-Key. */
export async function submitClaim(claim: Claim, signature: string, idempotencyKey: string): Promise<{ view: ClaimView; replayed: boolean }> {
  const meta: { replayed?: boolean } = {}
  const view = await request<ClaimView>('/claims', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ claim, signature }),
  }, meta)
  return { view, replayed: Boolean(meta.replayed) }
}

export function getClaim(ref: string, minBlock = 0): Promise<ClaimView> {
  return request(`/claims/${encodeURIComponent(ref)}?minBlock=${minBlock}`)
}

export function verifyClaim(ref: string, minBlock = 0): Promise<VerificationResponse> {
  return request(`/claims/${encodeURIComponent(ref)}/verify?minBlock=${minBlock}`)
}

export function getOverlaps(ref: string): Promise<{ projectId: string; vintageYear: number; overlaps: ClaimView['overlaps'] }> {
  return request(`/overlaps/${encodeURIComponent(ref)}`)
}

export function getRegistry(offset: number, limit: number): Promise<RegistryResponse> {
  return request(`/registry?offset=${offset}&limit=${limit}`)
}

export function getRetirement(ref: string, serial: string): Promise<RetirementLookup> {
  return request(`/claims/${encodeURIComponent(ref)}/retirements/${encodeURIComponent(serial)}`)
}

export async function getRegistryMap(): Promise<RegistryResponse> {
  const first = await request<RegistryResponse>('/registry?offset=0&limit=200&includeBoundary=true')
  const items = [...first.items]
  while (items.length < first.total) {
    const block = first.observedBlock == null ? '' : `&atBlock=${first.observedBlock}`
    const next = await request<RegistryResponse>(`/registry?offset=${items.length}&limit=200&includeBoundary=true${block}`)
    if (next.total !== first.total || next.items.length === 0) throw new Error('Registry changed while loading; refresh the map.')
    items.push(...next.items)
  }
  if (new Set(items.map(item => item.claimHash)).size !== first.total) throw new Error('Registry changed while loading; refresh the map.')
  return { ...first, items: items.filter(item => item.status === 'registered') }
}
