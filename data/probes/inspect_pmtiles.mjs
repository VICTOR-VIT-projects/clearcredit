import { PMTiles } from './tooling/node_modules/pmtiles/dist/esm/index.js'

const url =
  'https://carbonplan-offsets-db.s3.us-west-2.amazonaws.com/miscellaneous/project-boundaries.pmtiles'

const archive = new PMTiles(url)
const [header, metadata] = await Promise.all([
  archive.getHeader(),
  archive.getMetadata(),
])

console.log(JSON.stringify({ header, metadata }, null, 2))
