import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const seedDir = path.resolve("data/seed");
const probesDir = path.resolve("data/probes");
const manifest = JSON.parse(
  await readFile(path.join(probesDir, "SEED_MANIFEST.json"), "utf8"),
);
const manifestById = new Map(manifest.projects.map((project) => [project.projectId, project]));
const requiredProperties = [
  "projectId",
  "name",
  "sourceRegistry",
  "externalId",
  "projectType",
  "country",
  "vintageYears",
  "sourceUrl",
  "license",
  "retrievedAt",
  "illustrative",
];
const allowedProjectTypes = new Set([
  "avoided_deforestation",
  "afforestation",
  "other",
]);

function increment(object, key) {
  object[key] = (object[key] ?? 0) + 1;
}

function walkPositions(coordinates, visit) {
  if (
    Array.isArray(coordinates) &&
    coordinates.length >= 2 &&
    typeof coordinates[0] === "number" &&
    typeof coordinates[1] === "number"
  ) {
    visit(coordinates);
    return;
  }
  if (Array.isArray(coordinates)) {
    for (const child of coordinates) walkPositions(child, visit);
  }
}

function allRings(geometry) {
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

function samePosition(a, b) {
  return a.length >= 2 && b.length >= 2 && a[0] === b[0] && a[1] === b[1];
}

function bboxFromGeometry(geometry) {
  const bbox = [Infinity, Infinity, -Infinity, -Infinity];
  let positionCount = 0;
  walkPositions(geometry.coordinates, ([longitude, latitude]) => {
    bbox[0] = Math.min(bbox[0], longitude);
    bbox[1] = Math.min(bbox[1], latitude);
    bbox[2] = Math.max(bbox[2], longitude);
    bbox[3] = Math.max(bbox[3], latitude);
    positionCount += 1;
  });
  return { bbox, positionCount };
}

const files = (await readdir(seedDir))
  .filter((filename) => filename.endsWith(".geojson"))
  .sort();
const errors = [];
const warnings = [];
const checksums = [];
const seenProjectIds = new Set();
const counts = {
  byProjectType: {},
  byRegistry: {},
  byCountry: {},
  byGeometryType: {},
};
let totalPositions = 0;
let totalRings = 0;
let totalBytes = 0;

for (const filename of files) {
  const filePath = path.join(seedDir, filename);
  const raw = await readFile(filePath);
  totalBytes += raw.byteLength;
  checksums.push(
    `${createHash("sha256").update(raw).digest("hex")}  data/seed/${filename}`,
  );

  let collection;
  try {
    collection = JSON.parse(raw.toString("utf8"));
  } catch (error) {
    errors.push(`${filename}: invalid JSON (${error.message})`);
    continue;
  }

  if (collection.type !== "FeatureCollection") {
    errors.push(`${filename}: top-level type is not FeatureCollection`);
  }
  if (!Array.isArray(collection.features) || collection.features.length !== 1) {
    errors.push(`${filename}: expected exactly one feature`);
    continue;
  }

  const feature = collection.features[0];
  if (feature.type !== "Feature") errors.push(`${filename}: item is not a Feature`);
  const properties = feature.properties ?? {};
  const propertyKeys = Object.keys(properties).sort();
  const expectedKeys = [...requiredProperties].sort();
  if (JSON.stringify(propertyKeys) !== JSON.stringify(expectedKeys)) {
    errors.push(`${filename}: properties do not exactly match the required schema`);
  }
  for (const property of requiredProperties) {
    if (!(property in properties)) errors.push(`${filename}: missing property ${property}`);
  }

  const expectedId = path.basename(filename, ".geojson");
  if (properties.projectId !== expectedId) {
    errors.push(`${filename}: projectId does not match filename`);
  }
  if (typeof properties.externalId !== "string" || properties.externalId.length === 0) {
    errors.push(`${filename}: externalId must be a non-empty string`);
  }
  if (seenProjectIds.has(properties.projectId)) {
    errors.push(`${filename}: duplicate projectId ${properties.projectId}`);
  }
  seenProjectIds.add(properties.projectId);
  if (!allowedProjectTypes.has(properties.projectType)) {
    errors.push(`${filename}: invalid projectType ${properties.projectType}`);
  }
  if (!Array.isArray(properties.vintageYears)) {
    errors.push(`${filename}: vintageYears is not an array`);
  } else if (
    properties.vintageYears.some((year) => !Number.isInteger(year)) ||
    properties.vintageYears.some((year, index, years) => index > 0 && year <= years[index - 1])
  ) {
    errors.push(`${filename}: vintageYears must contain strictly ascending integers`);
  }
  if (properties.illustrative !== false) {
    errors.push(`${filename}: illustrative must be false`);
  }
  if (properties.retrievedAt !== "2026-10-05") {
    errors.push(`${filename}: unexpected retrievedAt value`);
  }

  const geometry = feature.geometry;
  if (!geometry || !["Polygon", "MultiPolygon"].includes(geometry.type)) {
    errors.push(`${filename}: geometry must be Polygon or MultiPolygon`);
    continue;
  }

  const rings = allRings(geometry);
  totalRings += rings.length;
  for (const [index, ring] of rings.entries()) {
    if (!Array.isArray(ring) || ring.length < 4) {
      errors.push(`${filename}: ring ${index} has fewer than four positions`);
    } else if (!samePosition(ring[0], ring.at(-1))) {
      errors.push(`${filename}: ring ${index} is not closed`);
    }
  }

  let coordinateError = false;
  walkPositions(geometry.coordinates, ([longitude, latitude]) => {
    if (
      !Number.isFinite(longitude) ||
      !Number.isFinite(latitude) ||
      longitude < -180 ||
      longitude > 180 ||
      latitude < -90 ||
      latitude > 90
    ) {
      coordinateError = true;
    }
  });
  if (coordinateError) errors.push(`${filename}: invalid EPSG:4326 coordinate found`);

  const { bbox, positionCount } = bboxFromGeometry(geometry);
  totalPositions += positionCount;
  const manifestProject = manifestById.get(properties.projectId);
  if (!manifestProject) {
    errors.push(`${filename}: project missing from SEED_MANIFEST.json`);
  } else {
    const bboxDifference = bbox.map((value, index) => Math.abs(value - manifestProject.bbox[index]));
    if (bboxDifference.some((difference) => difference > 1e-10)) {
      errors.push(`${filename}: geometry bbox differs from manifest`);
    }
    if (positionCount !== manifestProject.positionCount) {
      errors.push(`${filename}: position count differs from manifest`);
    }
  }

  increment(counts.byProjectType, properties.projectType);
  increment(counts.byRegistry, properties.sourceRegistry);
  increment(counts.byCountry, properties.country);
  increment(counts.byGeometryType, geometry.type);
}

if (files.length !== 40) errors.push(`Expected 40 GeoJSON files, found ${files.length}`);
if (manifest.projects.length !== files.length) {
  errors.push(`Manifest has ${manifest.projects.length} projects but seed has ${files.length} files`);
}
for (const projectId of manifestById.keys()) {
  if (!seenProjectIds.has(projectId)) errors.push(`Manifest project ${projectId} has no seed file`);
}
if (warnings.length === 0) {
  warnings.push(
    "Structural validation cannot prove registry authority, currentness, or survey-grade positional accuracy.",
  );
  warnings.push(
    "The seed was extracted from a zoom-12 vector-tile derivative and is suitable for prototype analysis, not cadastral or issuance decisions.",
  );
}

for (const object of Object.values(counts)) {
  const sorted = Object.entries(object).sort(([a], [b]) => a.localeCompare(b));
  for (const key of Object.keys(object)) delete object[key];
  for (const [key, value] of sorted) object[key] = value;
}

const report = {
  validatedAt: "2026-10-05",
  status: errors.length === 0 ? "PASS" : "FAIL",
  filesChecked: files.length,
  uniqueProjectIds: seenProjectIds.size,
  totalBytes,
  totalPositions,
  totalRings,
  counts,
  checks: {
    validJson: errors.every((error) => !error.includes("invalid JSON")),
    oneFeaturePerCollection: errors.every((error) => !error.includes("expected exactly one feature")),
    exactRequiredProperties: errors.every((error) => !error.includes("required schema") && !error.includes("missing property")),
    epsg4326CoordinateRanges: errors.every((error) => !error.includes("EPSG:4326")),
    polygonalGeometryOnly: errors.every((error) => !error.includes("geometry must")),
    ringsClosed: errors.every((error) => !error.includes("not closed")),
    uniqueIds: errors.every((error) => !error.includes("duplicate projectId")),
    manifestAgreement: errors.every((error) => !error.includes("manifest") && !error.includes("Manifest")),
    illustrativeFalse: errors.every((error) => !error.includes("illustrative must")),
  },
  errors,
  warnings,
};

await writeFile(
  path.join(probesDir, "VALIDATION_REPORT.json"),
  `${JSON.stringify(report, null, 2)}\n`,
);
await writeFile(
  path.join(probesDir, "SEED_SHA256.txt"),
  `${checksums.join("\n")}\n`,
);

console.log(JSON.stringify(report, null, 2));
if (errors.length > 0) process.exitCode = 1;
