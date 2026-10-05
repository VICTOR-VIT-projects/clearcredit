import type { Boundary } from './canonical'

export type DataLabel = 'real' | 'illustrative' | 'synthetic'
export type ProjectType = 'avoided_deforestation' | 'afforestation' | 'other'
export type Hash = `0x${string}`
export type Address = `0x${string}`

export interface Claim {
  schemaVersion: '1.0'
  projectId: string
  developer: Address
  projectType: ProjectType
  vintageYear: number
  claimedCredits: number
  creditUnit: 'tCO2e'
  boundary: Boundary
  boundaryCrs: 'EPSG:4326'
  sourceRegistry?: string | null
  boundarySource?: string | null
  dataLabel: DataLabel
  submittedAt?: string | null
}

export interface Overlap {
  project_id: string
  intersection_ha: number
  fraction_of_new: number
  fraction_of_existing: number
}

export interface CellConflict {
  projectId: string
  cells: string[]
  count: number
}

export interface ScoreReason {
  code: string
  severity: 'high' | 'medium' | 'low' | 'ok'
  deduction: number
  text: string
}

export interface IntegrityScore {
  score: number
  scoreBps: number
  band: 'high' | 'medium' | 'low'
  reasons: ScoreReason[]
  features: Record<string, number | string | null>
  modelVersion: string
  evidenceHash: Hash | null
}

export interface TypedDataPayload {
  domain: {
    name: string
    version: string
    chainId: number
    verifyingContract: Address
  }
  types: Record<string, readonly { name: string; type: string }[]>
  primaryType: string
  message: Record<string, string | number>
}

export interface PreviewResponse {
  claimHash: Hash
  projectKey: Hash
  submissionKey: Hash
  areaHa: number
  overlaps: Overlap[]
  onChainCellConflicts: CellConflict[]
  cellResolution: number
  cellCount: number
  score: IntegrityScore
  blocked: boolean
  canonicalClaim: Record<string, unknown>
  typedData?: TypedDataPayload
}

export interface Evidence {
  boundaryKey: string
  queriedAt: string
  forestLoss: {
    dataset: string
    license: string
    canopyThresholdPct: number
    forest2000Ha: number
    lossHaByYear: Record<string, number>
    lastCoveredYear: number
  }
  ndvi: {
    dataset: string
    license: string
    method: string
    meanNdviByYear: Record<string, number>
    slopePerYear: number | null
  }
  computeSeconds: number
  evidenceHash: Hash
}

export interface Transaction {
  step: string
  tx: Hash
  url: string | null
}

export interface ChainProject {
  developer: Address
  claimHash: Hash
  vintageYear: number
  status: string
  claimedCredits: number
  issued: number
  retired: number
  cellCount: number
  registeredAt: number
}

export interface Attestation {
  scoreBps: number
  evidenceHash: Hash
  modelVersion: string
  verifier: Address
  timestamp: number
}

export interface Retirement {
  serialStart: number
  amount: number
  from: Address
  beneficiary: string
  timestamp: number
}

export interface ClaimView {
  projectId: string
  projectKey: Hash
  claimHash: Hash
  dataLabel: DataLabel
  status: string
  claim: Claim
  areaHa: number
  overlaps: Overlap[]
  cellResolution: number
  cellCount: number
  score: IntegrityScore
  evidence: Evidence | null
  transactions: Transaction[]
  onChain: {
    contract: Address
    chainId: number
    explorer: string | null
    project: ChainProject
    attestations: Attestation[]
    retirements: Retirement[]
  } | null
  createdAt: string
  submissionKey?: Hash
  warnings?: { code: string; message: string }[]
}

export interface VerificationResponse {
  projectId: string
  recomputedHash: Hash
  onChainHash: Hash | null
  match: boolean | null
  note: string | null
}

export interface RegistryItem {
  projectId: string
  claimHash: Hash
  dataLabel: DataLabel
  projectType: ProjectType
  vintageYear: number
  claimedCredits: number
  areaHa: number
  score: number
  band: IntegrityScore['band']
  status: string
  sourceRegistry: string | null
}

export interface RegistryResponse {
  total: number
  items: RegistryItem[]
}

export interface ApiErrorBody {
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
  }
  detail?: { loc: (string | number)[]; msg: string; type: string }[]
}
