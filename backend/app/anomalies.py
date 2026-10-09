"""Cross-project cache diagnostics, separate from scoring and hashed evidence."""
import math
from collections import defaultdict
from decimal import Decimal
from statistics import median

MIN_BOUNDARIES = 10
MIN_SHARE = 0.8
STEP_SIZE = 0.15


def diagnose(projects: list[dict]) -> dict:
    """Look for a common adjacent-year step within the same dataset/method.

    A large change shared by most independent boundaries is a processing/sampling
    review trigger, not proof of a sensor error. No score or evidence value is modified.
    """
    comparisons, seen = defaultdict(list), set()
    missing = 0
    for project in projects:
        evidence = project["evidence"]
        if not evidence:
            missing += 1
            continue
        boundary = evidence["boundaryKey"]
        if boundary in seen:
            continue  # different vintages of the same land are not independent samples
        seen.add(boundary)
        ndvi = evidence["ndvi"]
        values = {}
        for year, value in ndvi["meanNdviByYear"].items():
            if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and -1 <= value <= 1:
                values[int(year)] = value
        for year in sorted(values):
            if year - 1 in values:
                key = (ndvi["dataset"], ndvi["method"], year - 1, year)
                comparisons[key].append({"projectId": project["projectId"], "dataLabel": project["dataLabel"],
                                         "delta": float(Decimal(str(values[year])) - Decimal(str(values[year - 1])))})
    warnings = []
    for (dataset, method, before, after), records in sorted(comparisons.items()):
        if len(records) < MIN_BOUNDARIES:
            continue
        typical = median(r["delta"] for r in records)
        affected = [r for r in records if abs(r["delta"]) >= STEP_SIZE and r["delta"] * typical > 0]
        if abs(typical) >= STEP_SIZE and len(affected) / len(records) >= MIN_SHARE:
            warnings.append({"code": "EVIDENCE_ANOMALY", "dataset": dataset, "method": method,
                             "fromYear": before, "toYear": after, "medianDelta": round(typical, 5),
                             "comparisonCount": len(records), "affectedCount": len(affected),
                             "projects": affected,
                             "message": "A large NDVI step is shared by most cached boundaries. Review processing, scene sampling and regional conditions; this does not establish a sensor error or change integrity scores."})
    return {"scoringAffected": False, "totalProjects": len(projects), "uniqueCachedBoundaries": len(seen),
            "missingEvidenceProjects": missing, "warnings": warnings,
            "note": "Diagnostic only; absence of a warning does not validate evidence. At least ten independent boundaries with the same method and adjacent-year observations are required."}
