"""Injected-fault evaluation of the integrity score (handoff §8.4).

Negatives: the real seed claims as published ("presumed legitimate", not guaranteed).
Positives: faults injected into copies of those claims:
  DUPLICATE  same boundary, new project ID, same vintage
  SHIFTED    boundary translated by 30% of its width, same vintage (partial overlap)
  INFLATED   claimed credits x5 on the same land
  RELOCATED  claim moved onto a box where Hansen data shows heavy forest loss in the vintage year
             (boxes found by scanning the Rondônia frontier, stratified by loss severity 1–2%, 2–5%, 5–15%, >15%)

Detected = blocked by the overlap check, or integrity score < 60 (the contract's issuance threshold).
Baseline = uniqueness-only: what a registry with an overlap check but no evidence layer catches.

This measures detection of INJECTED faults on a seeded dataset, not real-world fraud prevalence.

    python -m scripts.evaluate find-boxes     # once: pick frontier boxes + compute their evidence
    python -m scripts.evaluate run            # metrics -> data/eval/results.json
"""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import rasterio
from shapely.affinity import translate
from shapely.geometry import mapping, shape

from app import geo, satellite, scoring

ROOT = Path(__file__).resolve().parents[2]
CLAIMS = ROOT / "data" / "claims" / "real"
EVAL = ROOT / "data" / "eval"
BOXES = EVAL / "frontier_boxes.json"
ISSUE_THRESHOLD = 60
FRONTIER = (-64.0, -10.0, -62.0, -8.0)  # Rondônia, inside Hansen tile 00N_070W
BOX = 0.05  # degrees (~5.5 km)
LOSS_BANDS = [(0.01, 0.02), (0.02, 0.05), (0.05, 0.15), (0.15, 1.01)]  # share of 2000 forest lost in one year


def box(x0, y0, size=BOX):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]]}


def find_frontier_boxes(per_band: int = 3):
    """Scan the frontier at 30 m and pick boxes across bands of single-year loss rate (2021–2024)."""
    url = "/vsicurl/" + satellite.GFC_URL.format(v=satellite.GFC_VERSION, layer="{}", tile="00N_070W")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(url.format("lossyear")) as ly, rasterio.open(url.format("treecover2000")) as tc:
            win = rasterio.windows.from_bounds(*FRONTIER, ly.transform).round_offsets().round_lengths()
            loss, cover = ly.read(1, window=win), tc.read(1, window=win)
    step = round(BOX / 0.00025)  # pixels per box (GFC pixel = 0.00025 deg)
    cands = []
    for r in range(0, loss.shape[0] - step + 1, step):
        for c in range(0, loss.shape[1] - step + 1, step):
            lb, cb = loss[r : r + step, c : c + step], cover[r : r + step, c : c + step] > satellite.CANOPY_THRESHOLD
            forest = cb.sum()
            if forest < 0.3 * cb.size:  # need real forest to "protect"
                continue
            for year in range(2021, 2025):
                rate = ((lb == year - 2000) & cb).sum() / forest
                cands.append((rate, year, FRONTIER[0] + c * 0.00025, FRONTIER[3] - (r + step) * 0.00025))
    # Stratify by severity so the test includes subtle clearing, not only near-total clear-cuts.
    # Within each band take the 25th/50th/75th percentile candidates (one box per location), so
    # picks are not biased toward the band's severe edge. Deterministic.
    cands.sort()
    chosen, used = [], set()
    for lo, hi in LOSS_BANDS:
        best_per_loc = {}
        for rate, year, x0, y0 in cands:  # ascending: keep each location's most severe in-band year
            if lo <= rate < hi:
                best_per_loc[(x0, y0)] = (rate, year, x0, y0)
        inband = sorted(best_per_loc.values())
        for q in [(k + 1) / (per_band + 1) for k in range(per_band)]:
            rate, year, x0, y0 = inband[int(q * (len(inband) - 1))]
            if (x0, y0) in used:
                continue
            used.add((x0, y0))
            chosen.append({"vintageYear": year, "lossRate": round(float(rate), 4), "band": f"{lo:.0%}-{hi:.0%}" if hi <= 1 else f">{lo:.0%}",
                           "boundary": box(round(x0, 5), round(y0, 5))})
    EVAL.mkdir(parents=True, exist_ok=True)
    BOXES.write_text(json.dumps(chosen, indent=1), encoding="utf-8")
    for b in chosen:
        e = satellite.get_evidence(b["boundary"])
        print(f"box {b['boundary']['coordinates'][0][0]} vintage {b['vintageYear']} loss {b['lossRate']:.1%} -> evidence {e['evidenceHash'][:10]}", flush=True)


def evaluate(claim: dict, boundary: dict, others: dict, evidence: dict | None) -> dict:
    g = shape(boundary)
    overlaps = [o.__dict__ for o in geo.find_overlaps(g, others)]
    s = scoring.score_claim({**claim, "boundary": boundary}, geo.area_ha(g), overlaps, evidence)
    blocked = any(r["code"] == "OVERLAP" for r in s["reasons"])
    return {"blocked": blocked, "score": s["score"], "codes": [r["code"] for r in s["reasons"] if r["deduction"] > 0]}


def run():
    claims = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(CLAIMS.glob("*.json"))]
    geoms = {c["projectId"]: shape(c["boundary"]) for c in claims}
    evid = {c["projectId"]: satellite.get_evidence(c["boundary"], live=False) for c in claims}
    missing = [p for p, e in evid.items() if e is None]
    if missing:
        sys.exit(f"evidence missing for {missing}; run scripts.precompute_evidence first")
    boxes = json.loads(BOXES.read_text(encoding="utf-8")) if BOXES.exists() else []

    def same_vintage(c, exclude):
        return {p: geoms[p] for p in geoms if p != exclude and next(x for x in claims if x["projectId"] == p)["vintageYear"] == c["vintageYear"]}

    rows = []
    for c in claims:
        pid = c["projectId"]
        others = same_vintage(c, pid)
        rows.append({"case": pid, "fault": "NONE", **evaluate(c, c["boundary"], others, evid[pid])})
        # Faulted copies compete against the original too.
        with_orig = {**others, pid: geoms[pid]}
        rows.append({"case": pid, "fault": "DUPLICATE", **evaluate(c, c["boundary"], with_orig, evid[pid])})
        minx, _, maxx, _ = geoms[pid].bounds
        shifted = json.loads(json.dumps(mapping(translate(geoms[pid], xoff=0.3 * (maxx - minx)))))
        # ponytail: shifted copy reuses the original's evidence (overlap is what's tested);
        # compute evidence for shifted boundaries if this fault ever needs the evidence rules.
        rows.append({"case": pid, "fault": "SHIFTED", **evaluate(c, shifted, with_orig, evid[pid])})
        rows.append({"case": pid, "fault": "INFLATED", **evaluate({**c, "claimedCredits": c["claimedCredits"] * 5}, c["boundary"], others, evid[pid])})
    # RELOCATED: each frontier box gets a claim modelled on a real avoided-deforestation project
    # (same credits per hectare), with the box's high-loss year as vintage.
    redd = [c for c in claims if c["projectType"] == "avoided_deforestation"]
    for i, b in enumerate(boxes):
        base = redd[i % len(redd)]
        cph = base["claimedCredits"] / geo.area_ha(geoms[base["projectId"]])
        fake = {**copy.deepcopy(base), "projectId": f"RELOC-{i}", "vintageYear": b["vintageYear"],
                "claimedCredits": max(1, round(cph * geo.area_ha(shape(b["boundary"]))))}
        rows.append({"case": f"RELOC-{i} (from {base['projectId']})", "fault": "RELOCATED", "stratum": b.get("band"),
                     **evaluate(fake, b["boundary"], {}, satellite.get_evidence(b["boundary"], live=False))})

    for r in rows:
        r["detected"] = r["blocked"] or r["score"] < ISSUE_THRESHOLD
        r["baselineDetected"] = r["blocked"]

    def metrics(key):
        pos = [r for r in rows if r["fault"] != "NONE"]
        neg = [r for r in rows if r["fault"] == "NONE"]
        tp = sum(r[key] for r in pos)
        fp = sum(r[key] for r in neg)
        per = {f: f"{sum(r[key] for r in rs)}/{len(rs)}" for f, rs in _group(pos).items()}
        strata = defaultdict(list)
        for r in pos:
            if r["fault"] == "RELOCATED":
                strata[r["stratum"]].append(r[key])
        per_stratum = {k: f"{sum(v)}/{len(v)}" for k, v in sorted(strata.items())}
        return {
            "recall": round(tp / len(pos), 3) if pos else None,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "falseAlarmRate": round(fp / len(neg), 3),
            "falseAlarms": f"{fp}/{len(neg)}",
            "perFault": per,
            "relocatedByLossStratum": per_stratum,
        }

    result = {
        "note": "Detection of injected faults on a seeded dataset of 30 real published projects; not real-world fraud prevalence.",
        "detectionRule": f"blocked by overlap OR score < {ISSUE_THRESHOLD}",
        "thresholdsFrozen": "rules-v2 thresholds retained in rules-v3; orientation-independent area correction, no threshold tuning",
        "scoringModel": scoring.MODEL_VERSION,
        "evidenceVersion": satellite.EVIDENCE_VERSION,
        "clearcredit": metrics("detected"),
        "baselineUniquenessOnly": metrics("baselineDetected"),
        "falseAlarmReasons": dict(Counter(code for r in rows if r["fault"] == "NONE" and r["detected"] for code in r["codes"])),
        "rows": rows,
    }
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "results.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1))


def _group(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["fault"]].append(r)
    return g


if __name__ == "__main__":
    {"find-boxes": find_frontier_boxes, "run": run}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
