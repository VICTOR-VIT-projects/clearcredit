import { keccak256, toBytes } from 'viem'

export type Position = [number, number, ...number[]]
export type LinearRing = Position[]
export type PolygonCoordinates = LinearRing[]
export type MultiPolygonCoordinates = PolygonCoordinates[]

export type Boundary =
  | { type: 'Polygon'; coordinates: PolygonCoordinates }
  | { type: 'MultiPolygon'; coordinates: MultiPolygonCoordinates }

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }
type IntegerPoint = [number, number]
type IntegerRing = IntegerPoint[]
type IntegerPolygon = IntegerRing[]

const EXCLUDED_FIELDS = new Set(['submittedAt'])

function codePointCompare(a: string, b: string): number {
  const aa = Array.from(a, (character) => character.codePointAt(0)!)
  const bb = Array.from(b, (character) => character.codePointAt(0)!)
  const length = Math.min(aa.length, bb.length)
  for (let index = 0; index < length; index += 1) {
    if (aa[index] !== bb[index]) return aa[index] - bb[index]
  }
  return aa.length - bb.length
}

/** Python-compatible json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False). */
export function stableStringify(value: unknown): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') {
    return JSON.stringify(value)
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError('Canonical JSON cannot contain a non-finite number.')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const keys = Object.keys(record).sort(codePointCompare)
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(',')}}`
  }
  throw new TypeError(`Unsupported canonical JSON value: ${typeof value}`)
}

function micro(value: number): number {
  return Math.floor(value * 1e6 + 0.5)
}

function comparePoints(a: IntegerPoint, b: IntegerPoint): number {
  return a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]
}

function compareNestedIntegerLists(a: unknown, b: unknown): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (Array.isArray(a) && Array.isArray(b)) {
    const length = Math.min(a.length, b.length)
    for (let index = 0; index < length; index += 1) {
      const result = compareNestedIntegerLists(a[index], b[index])
      if (result !== 0) return result
    }
    return a.length - b.length
  }
  throw new TypeError('Expected nested integer lists.')
}

function signedArea2(ring: IntegerRing): bigint {
  let area = 0n
  for (let index = 0; index < ring.length - 1; index += 1) {
    const current = ring[index]
    const next = ring[index + 1]
    area += BigInt(current[0]) * BigInt(next[1]) - BigInt(next[0]) * BigInt(current[1])
  }
  return area
}

function canonicalRing(ring: LinearRing, ccw: boolean): IntegerRing {
  const points = ring.map((position): IntegerPoint => [micro(position[0]), micro(position[1])])
  const deduplicated = points.filter(
    (point, index) => index === 0 || point[0] !== points[index - 1][0] || point[1] !== points[index - 1][1],
  )
  if (
    deduplicated.length > 1 &&
    comparePoints(deduplicated[0], deduplicated[deduplicated.length - 1]) === 0
  ) {
    deduplicated.pop()
  }
  if (deduplicated.length === 0) throw new TypeError('A boundary ring cannot be empty.')

  const initiallyClosed = [...deduplicated, deduplicated[0]]
  if ((signedArea2(initiallyClosed) > 0n) !== ccw) deduplicated.reverse()

  let smallestIndex = 0
  for (let index = 1; index < deduplicated.length; index += 1) {
    if (comparePoints(deduplicated[index], deduplicated[smallestIndex]) < 0) smallestIndex = index
  }
  const rotated = [...deduplicated.slice(smallestIndex), ...deduplicated.slice(0, smallestIndex)]
  return [...rotated, rotated[0]]
}

function canonicalPolygon(rings: PolygonCoordinates): IntegerPolygon {
  if (rings.length === 0) throw new TypeError('A polygon must have an exterior ring.')
  const exterior = canonicalRing(rings[0], true)
  const holes = rings.slice(1).map((ring) => canonicalRing(ring, false))
  holes.sort(compareNestedIntegerLists)
  return [exterior, ...holes]
}

export function canonicalBoundary(boundary: Boundary): { type: Boundary['type']; coordinates: unknown } {
  if (boundary.type === 'Polygon') {
    return { type: boundary.type, coordinates: canonicalPolygon(boundary.coordinates) }
  }
  if (boundary.type === 'MultiPolygon') {
    const coordinates = boundary.coordinates.map(canonicalPolygon)
    coordinates.sort((a, b) => codePointCompare(stableStringify(a), stableStringify(b)))
    return { type: boundary.type, coordinates }
  }
  throw new TypeError(`Unsupported boundary type: ${(boundary as { type?: string }).type ?? 'missing'}`)
}

export function canonicalClaim(claim: Record<string, unknown>): Record<string, unknown> {
  const output: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(claim)) {
    if (!EXCLUDED_FIELDS.has(key) && value !== null) output[key] = value
  }
  if (typeof output.developer !== 'string') throw new TypeError('Claim developer must be a string.')
  output.developer = output.developer.toLowerCase()
  output.boundary = canonicalBoundary(output.boundary as Boundary)
  return output
}

export function canonicalString(claim: Record<string, unknown>): string {
  return stableStringify(canonicalClaim(claim) as JsonValue)
}

export function claimHash(claim: Record<string, unknown>): `0x${string}` {
  return keccak256(toBytes(canonicalString(claim)))
}

export function projectKey(projectId: string): `0x${string}` {
  return keccak256(toBytes(projectId))
}
