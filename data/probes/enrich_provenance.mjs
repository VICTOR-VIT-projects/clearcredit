import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parse } from "./tooling/node_modules/csv-parse/dist/esm/sync.js";

const probesDir = path.resolve("data/probes");
const indexUrl =
  "https://zenodo.org/api/records/11459391/files/carbon_projects_database_index.csv/content";
const response = await fetch(indexUrl, {
  headers: { "user-agent": "ClearCredit academic data probe" },
});
if (!response.ok) throw new Error(`Karnik index download failed: HTTP ${response.status}`);
const csv = await response.text();
await writeFile(path.join(probesDir, "KARNIK_PROJECT_INDEX.csv"), csv, "utf8");

const rows = parse(csv, { columns: true, skip_empty_lines: true });
const byId = new Map(rows.map((row) => [row.ProjectID, row]));
const manifest = JSON.parse(
  await readFile(path.join(probesDir, "SEED_MANIFEST.json"), "utf8"),
);
const records = manifest.projects.map((project) => {
  const sourceProjectId = project.projectId.startsWith("GLD")
    ? `GS${project.projectId.slice(3)}`
    : project.projectId;
  const row = byId.get(sourceProjectId);
  if (!row) throw new Error(`${project.projectId} is missing from the Karnik index`);
  const normalizedProjectType = {
    AD: "avoided_deforestation",
    ARR: "afforestation",
    IFM: "other",
  }[row["Project Type"]];
  if (!normalizedProjectType) {
    throw new Error(`${project.projectId} has unsupported source project type ${row["Project Type"]}`);
  }
  return {
    projectId: project.projectId,
    sourceProjectId,
    sourceRegistryName: row["Registry Name"],
    sourceProjectType: row["Project Type"],
    offsetsDbProjectType: project.projectType,
    normalizedProjectType,
    processingApproach: row["Processing Approach"],
    projectDocumentDeclinedToProvide: row["PD Declined to Provide"],
    sourceGeometryType: row["Geometry Type"],
    includesProjectArea: row["Project Area"] === "1",
    includesProjectAccountingArea: row["Project Accounting Area"] === "1",
    includesProjectReferenceRegion: row["Project Reference Region"] === "1",
    methodology: row.Methodology,
    projectStartDate: row["Project Start Date"],
    projectEndDate: row["Project End Date"],
    datasetEntryDate: row["Date of Entry"],
  };
});

const approachCounts = Object.fromEntries(
  [...new Set(records.map((record) => record.processingApproach))]
    .sort()
    .map((approach) => [
      approach,
      records.filter((record) => record.processingApproach === approach).length,
    ]),
);
const typeCorrections = records
  .filter((record) => record.offsetsDbProjectType !== record.normalizedProjectType)
  .map((record) => ({
    projectId: record.projectId,
    offsetsDbProjectType: record.offsetsDbProjectType,
    normalizedProjectType: record.normalizedProjectType,
  }));

for (const project of manifest.projects) {
  const record = records.find((candidate) => candidate.projectId === project.projectId);
  project.projectType = record.normalizedProjectType;
}
await writeFile(
  path.join(probesDir, "SEED_MANIFEST.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

const provenance = {
  generatedAt: "2026-10-05",
  source: "https://zenodo.org/records/11459391",
  sourceIndexDownload: indexUrl,
  sourceDatasetProjectCount: rows.length,
  seedProjectCount: records.length,
  approachCounts,
  typeCorrections,
  records,
};

// Keep projectId aligned with OffsetsDB while preserving each registry's native ID.
for (const record of records) {
  const seedPath = path.resolve("data/seed", `${record.projectId}.geojson`);
  const collection = JSON.parse(await readFile(seedPath, "utf8"));
  collection.features[0].properties.externalId = record.sourceProjectId;
  collection.features[0].properties.projectType = record.normalizedProjectType;
  await writeFile(seedPath, `${JSON.stringify(collection)}\n`, "utf8");
}

await writeFile(
  path.join(probesDir, "SEED_PROVENANCE.json"),
  `${JSON.stringify(provenance, null, 2)}\n`,
  "utf8",
);
console.log(JSON.stringify({ sourceDatasetProjectCount: rows.length, seedProjectCount: records.length, approachCounts, typeCorrections }, null, 2));
