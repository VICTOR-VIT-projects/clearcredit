import fs from 'node:fs/promises'

const endpoint =
  'https://carbonplan.org/research/offsets-db/api/query?path=projects%2F&category=forest&geography=true'

const records = []
for (let page = 1; page <= 6; page += 1) {
  const response = await fetch(`${endpoint}&current_page=${page}`)
  if (!response.ok) throw new Error(`OffsetsDB page ${page}: HTTP ${response.status}`)
  const body = await response.json()
  records.push(...body.data)
  if (page >= body.pagination.total_pages) break
}

await fs.writeFile(
  new URL('./carbonplan-geographic-forest-projects.json', import.meta.url),
  `${JSON.stringify(records, null, 2)}\n`,
)

const tropical = new Set([
  'Belize',
  'Bolivia',
  'Brazil',
  'Cambodia',
  'Colombia',
  'Costa Rica',
  'DR Congo',
  'Ecuador',
  'Guatemala',
  'Guyana',
  'India',
  'Indonesia',
  'Kenya',
  'Laos',
  'Madagascar',
  'Malaysia',
  'Mozambique',
  'Nicaragua',
  'Panama',
  'Papua New Guinea',
  'Peru',
  'Sri Lanka',
  'Tanzania',
  'Thailand',
  'Uganda',
  'Vietnam',
  'Zambia',
  'Zimbabwe',
])

function lonToTile(lon, z) {
  return Math.floor(((lon + 180) / 360) * 2 ** z)
}

function latToTile(lat, z) {
  const radians = (Math.max(-85.05112878, Math.min(85.05112878, lat)) * Math.PI) / 180
  return Math.floor(
    ((1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2) * 2 ** z,
  )
}

function tileCount(bbox, z = 12) {
  const minX = lonToTile(bbox.xmin, z)
  const maxX = lonToTile(bbox.xmax, z)
  const minY = latToTile(bbox.ymax, z)
  const maxY = latToTile(bbox.ymin, z)
  return (maxX - minX + 1) * (maxY - minY + 1)
}

const candidates = records
  .filter(
    (record) =>
      tropical.has(record.country) &&
      ['REDD+', 'Afforestation + Reforestation'].includes(record.project_type),
  )
  .map((record) => ({
    project_id: record.project_id,
    name: record.name,
    registry: record.registry,
    country: record.country,
    project_type: record.project_type,
    tiles_z12: tileCount(record.bbox),
    bbox: record.bbox,
  }))
  .sort((a, b) => a.tiles_z12 - b.tiles_z12 || a.project_id.localeCompare(b.project_id))

console.log(JSON.stringify({ total: records.length, candidates }, null, 2))
