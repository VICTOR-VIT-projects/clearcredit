import { createReadStream } from 'node:fs'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { VectorTile } from './tooling/node_modules/@mapbox/vector-tile/index.js'
import { parse } from './tooling/node_modules/csv-parse/lib/index.js'
import { PbfReader } from './tooling/node_modules/pbf/index.js'
import polygonClipping from './tooling/node_modules/polygon-clipping/dist/polygon-clipping.esm.js'
import { PMTiles } from './tooling/node_modules/pmtiles/dist/esm/index.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const seedDirectory = path.resolve(here, '../seed')
const projectMetadataPath = path.join(
  here,
  'carbonplan-geographic-forest-projects.json',
)
const creditsPath = path.join(here, 'offsets-db-csv', 'credits.csv')

const RETRIEVED_AT = '2026-10-05'
const ZOOM = 12
const SOURCE_URL = 'https://zenodo.org/records/11459391'
const RETRIEVAL_URL =
  'https://carbonplan-offsets-db.s3.us-west-2.amazonaws.com/miscellaneous/project-boundaries.pmtiles'
const LICENSE =
  'CC BY 4.0 (Karnik et al. dataset); CarbonPlan Terms of Use also apply to the PMTiles derivative'

// Balanced across tropical regions while keeping the seed compact enough for a
// hackathon repo: 24 avoided-deforestation projects and 16 ARR projects.
const SELECTED_PROJECT_IDS = [
  // Avoided deforestation / REDD+
  'VCS647',
  'VCS812',
  'VCS1326',
  'VCS852',
  'VCS818',
  'VCS999',
  'VCS1133',
  'VCS1218',
  'VCS1799',
  'VCS856',
  'VCS1391',
  'VCS1392',
  'VCS1329',
  'VCS1115',
  'VCS1382',
  'VCS1112',
  'VCS562',
  'VCS2363',
  'VCS1498',
  'VCS1899',
  'VCS1202',
  'VCS2293',
  'VCS934',
  'VCS1748',
  // Afforestation / reforestation / revegetation
  'GLD3025',
  'VCS1429',
  'VCS1233',
  'VCS665',
  'VCS1663',
  'VCS2079',
  'VCS1351',
  'VCS1397',
  'VCS658',
  'VCS1327',
  'VCS2085',
  'VCS799',
  'VCS1684',
  'VCS2619',
  'VCS1085',
  'VCS142',
]

const registryLabels = {
  'american-carbon-registry': 'American Carbon Registry',
  'art-trees': 'ART TREES',
  cercarbono: 'Cercarbono',
  'climate-action-reserve': 'Climate Action Reserve',
  'gold-standard': 'Gold Standard',
  isometric: 'Isometric',
  verra: 'Verra VCS',
}

function lonToTile(lon, zoom) {
  return Math.floor(((lon + 180) / 360) * 2 ** zoom)
}

function latToTile(lat, zoom) {
  const clamped = Math.max(-85.05112878, Math.min(85.05112878, lat))
  const radians = (clamped * Math.PI) / 180
  return Math.floor(
    ((1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2) * 2 ** zoom,
  )
}

function tileCoordinatesForBbox(bbox, zoom) {
  const limit = 2 ** zoom - 1
  const minX = Math.max(0, lonToTile(bbox.xmin, zoom) - 1)
  const maxX = Math.min(limit, lonToTile(bbox.xmax, zoom) + 1)
  const minY = Math.max(0, latToTile(bbox.ymax, zoom) - 1)
  const maxY = Math.min(limit, latToTile(bbox.ymin, zoom) + 1)
  const result = []
  for (let x = minX; x <= maxX; x += 1) {
    for (let y = minY; y <= maxY; y += 1) result.push({ x, y })
  }
  return result
}

function asMultiPolygonCoordinates(geometry) {
  if (geometry.type === 'Polygon') return [geometry.coordinates]
  if (geometry.type === 'MultiPolygon') return geometry.coordinates
  throw new Error(`Unexpected boundary geometry: ${geometry.type}`)
}

function countPositions(value) {
  if (!Array.isArray(value)) return 0
  if (
    value.length >= 2 &&
    typeof value[0] === 'number' &&
    typeof value[1] === 'number'
  ) {
    return 1
  }
  return value.reduce((sum, child) => sum + countPositions(child), 0)
}

function geometryBbox(geometry) {
  const bbox = [Infinity, Infinity, -Infinity, -Infinity]
  function visit(value) {
    if (!Array.isArray(value)) return
    if (
      value.length >= 2 &&
      typeof value[0] === 'number' &&
      typeof value[1] === 'number'
    ) {
      bbox[0] = Math.min(bbox[0], value[0])
      bbox[1] = Math.min(bbox[1], value[1])
      bbox[2] = Math.max(bbox[2], value[0])
      bbox[3] = Math.max(bbox[3], value[1])
      return
    }
    for (const child of value) visit(child)
  }
  visit(geometry.coordinates)
  return bbox
}

async function readVintages(selectedIds) {
  const selected = new Set(selectedIds)
  const result = new Map(selectedIds.map((id) => [id, new Set()]))
  const parser = createReadStream(creditsPath).pipe(
    parse({ columns: true, bom: true, relax_quotes: true }),
  )
  for await (const record of parser) {
    if (!selected.has(record.project_id) || !record.vintage) continue
    const vintage = Number.parseInt(record.vintage, 10)
    if (Number.isInteger(vintage)) result.get(record.project_id).add(vintage)
  }
  return new Map(
    [...result].map(([id, years]) => [id, [...years].sort((a, b) => a - b)]),
  )
}

const allProjects = JSON.parse(await fs.readFile(projectMetadataPath, 'utf8'))
const projectById = new Map(allProjects.map((project) => [project.project_id, project]))
for (const id of SELECTED_PROJECT_IDS) {
  if (!projectById.has(id)) throw new Error(`Missing project metadata for ${id}`)
}

const vintagesById = await readVintages(SELECTED_PROJECT_IDS)
const archive = new PMTiles(RETRIEVAL_URL)
const tileCache = new Map()

async function loadTile(x, y) {
  const key = `${ZOOM}/${x}/${y}`
  if (!tileCache.has(key)) {
    tileCache.set(
      key,
      archive.getZxy(ZOOM, x, y).then((result) => {
        if (!result) return null
        return new VectorTile(new PbfReader(new Uint8Array(result.data)))
      }),
    )
  }
  return tileCache.get(key)
}

async function extractProjectGeometry(project) {
  const coordinates = tileCoordinatesForBbox(project.bbox, ZOOM)
  const fragments = []
  for (let offset = 0; offset < coordinates.length; offset += 16) {
    const batch = coordinates.slice(offset, offset + 16)
    const tiles = await Promise.all(
      batch.map(async ({ x, y }) => ({ x, y, tile: await loadTile(x, y) })),
    )
    for (const { x, y, tile } of tiles) {
      const layer = tile?.layers?.boundaries
      if (!layer) continue
      for (let index = 0; index < layer.length; index += 1) {
        const feature = layer.feature(index)
        if (feature.properties.project_id !== project.project_id) continue
        const geojson = feature.toGeoJSON(x, y, ZOOM)
        fragments.push(asMultiPolygonCoordinates(geojson.geometry))
      }
    }
  }
  if (fragments.length === 0) {
    throw new Error(`No PMTiles geometry found for ${project.project_id}`)
  }
  const coordinatesUnion = polygonClipping.union(...fragments)
  if (!coordinatesUnion?.length) {
    throw new Error(`Union produced an empty geometry for ${project.project_id}`)
  }
  return {
    geometry:
      coordinatesUnion.length === 1
        ? { type: 'Polygon', coordinates: coordinatesUnion[0] }
        : { type: 'MultiPolygon', coordinates: coordinatesUnion },
    fragments: fragments.length,
    requestedTiles: coordinates.length,
  }
}

await fs.mkdir(seedDirectory, { recursive: true })
const manifest = []

for (const id of SELECTED_PROJECT_IDS) {
  const project = projectById.get(id)
  const { geometry, fragments, requestedTiles } =
    await extractProjectGeometry(project)
  const featureCollection = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {
          projectId: project.project_id,
          name: project.name,
          sourceRegistry: registryLabels[project.registry] ?? project.registry,
          externalId: project.project_id,
          projectType:
            project.project_type === 'REDD+'
              ? 'avoided_deforestation'
              : project.project_type === 'Afforestation + Reforestation'
                ? 'afforestation'
                : 'other',
          country: project.country,
          vintageYears: vintagesById.get(project.project_id) ?? [],
          sourceUrl: SOURCE_URL,
          license: LICENSE,
          retrievedAt: RETRIEVED_AT,
          illustrative: false,
        },
        geometry,
      },
    ],
  }
  const outputPath = path.join(seedDirectory, `${project.project_id}.geojson`)
  await fs.writeFile(outputPath, `${JSON.stringify(featureCollection)}\n`)
  manifest.push({
    projectId: project.project_id,
    name: project.name,
    registry: project.registry,
    registryUrl: project.project_url,
    country: project.country,
    projectType: featureCollection.features[0].properties.projectType,
    vintageYears: featureCollection.features[0].properties.vintageYears,
    geometryType: geometry.type,
    positionCount: countPositions(geometry.coordinates),
    bbox: geometryBbox(geometry),
    pmtilesZoom: ZOOM,
    pmtilesFragments: fragments,
    requestedTiles,
    sourceDataset: SOURCE_URL,
    retrievalUrl: RETRIEVAL_URL,
  })
  console.log(
    `${project.project_id}: ${geometry.type}, ${countPositions(geometry.coordinates)} positions, ${fragments} fragments`,
  )
}

await fs.writeFile(
  path.join(here, 'SEED_MANIFEST.json'),
  `${JSON.stringify(
    {
      generatedAt: `${RETRIEVED_AT}T00:00:00+05:30`,
      sourceDataset: SOURCE_URL,
      retrievalUrl: RETRIEVAL_URL,
      pmtilesZoom: ZOOM,
      projects: manifest,
    },
    null,
    2,
  )}\n`,
)

console.log(`Wrote ${manifest.length} project GeoJSON files to ${seedDirectory}`)
