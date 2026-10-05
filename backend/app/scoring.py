"""Transparent rule-based integrity score (0–100) with plain-language reasons.

This is an integrity score, not a certification: it flags claims that are inconsistent with
independent evidence. Thresholds are deliberately simple and published so they can be audited.
"""
from __future__ import annotations

MODEL_VERSION = "rules-v2"  # v2: FOREST_LOSS_HIGH 40 -> 60 (a contradicted claim must fall below the 60 issuance threshold)
BLOCKING_OVERLAP = 0.01  # >= 1% of either boundary overlapping a same-vintage claim

# Plausible issuance ranges, tCO2e per hectare per vintage year (broad literature ranges).
CREDITS_PER_HA = {"avoided_deforestation": (15, 30), "afforestation": (25, 40), "other": (25, 50)}


def _reason(code: str, deduction: int, text: str) -> dict:
    severity = "high" if deduction >= 30 else "medium" if deduction >= 10 else "low" if deduction > 0 else "ok"
    return {"code": code, "severity": severity, "deduction": deduction, "text": text}


def band(score: int) -> str:
    return "high" if score >= 75 else "medium" if score >= 50 else "low"


def score_claim(claim: dict, area_ha: float, overlaps: list[dict], evidence: dict | None) -> dict:
    vintage, ptype = claim["vintageYear"], claim["projectType"]
    reasons, features = [], {"areaHa": round(area_ha, 2)}

    # 1. Overlap with other claims for the same vintage
    worst = max((max(o["fraction_of_new"], o["fraction_of_existing"]) for o in overlaps), default=0.0)
    features["maxOverlapFraction"] = worst
    if worst >= BLOCKING_OVERLAP:
        o = max(overlaps, key=lambda o: max(o["fraction_of_new"], o["fraction_of_existing"]))
        reasons.append(_reason("OVERLAP", 60, f"{worst:.1%} overlap with project {o['project_id']} for the same vintage ({vintage}): the same land would be counted twice."))
    elif worst > 0:
        reasons.append(_reason("OVERLAP_MINOR", 10, f"A sliver ({worst:.2%}) overlaps another same-vintage claim; boundaries should be reconciled."))
    else:
        reasons.append(_reason("NO_OVERLAP", 0, f"No overlap with any other claim for vintage {vintage}."))

    # 2. Credits per hectare
    cph = claim["claimedCredits"] / area_ha
    features["creditsPerHa"] = round(cph, 2)
    warn, high = CREDITS_PER_HA[ptype]
    if cph > high:
        reasons.append(_reason("CREDITS_IMPLAUSIBLE", 30, f"{cph:.1f} tCO2e/ha claimed for one year is far above the plausible range for this project type (≤{warn})."))
    elif cph > warn:
        reasons.append(_reason("CREDITS_HIGH", 10, f"{cph:.1f} tCO2e/ha claimed for one year is unusually high for this project type (typical ≤{warn})."))
    else:
        reasons.append(_reason("CREDITS_PLAUSIBLE", 0, f"{cph:.1f} tCO2e/ha is within the plausible range for this project type."))

    # 3. Satellite evidence
    if evidence is None:
        reasons.append(_reason("NO_EVIDENCE", 15, "Satellite evidence is not yet available for this boundary; the claim cannot be cross-checked."))
    else:
        fl, nd = evidence["forestLoss"], evidence["ndvi"]
        forest = fl["forest2000Ha"]
        loss = {int(y): v for y, v in fl["lossHaByYear"].items()}
        features["forestCover2000Fraction"] = round(forest / area_ha, 4) if area_ha else 0.0
        if ptype == "avoided_deforestation":
            if forest / area_ha < 0.3:
                reasons.append(_reason("LITTLE_FOREST", 30, f"Only {forest / area_ha:.0%} of the area had tree cover in 2000, which is little forest to protect."))
            if vintage > fl["lastCoveredYear"]:
                reasons.append(_reason("LOSS_DATA_PENDING", 0, f"Forest-loss data covers up to {fl['lastCoveredYear']}; vintage {vintage} cannot be checked yet."))
            elif forest > 0:
                remaining = forest - sum(v for y, v in loss.items() if y < vintage)
                rate = loss.get(vintage, 0.0) / remaining if remaining > 0 else 1.0
                features["vintageLossRate"] = round(rate, 4)
                text = f"{loss.get(vintage, 0.0):,.0f} ha of forest ({rate:.1%} of remaining forest) was lost inside the boundary in {vintage}"
                if rate > 0.02:
                    reasons.append(_reason("FOREST_LOSS_HIGH", 60, f"{text}, which contradicts an avoided-deforestation claim."))
                elif rate > 0.005:
                    reasons.append(_reason("FOREST_LOSS_MODERATE", 20, f"{text}, above what a protected forest would show."))
                else:
                    reasons.append(_reason("FOREST_LOSS_LOW", 0, f"{text}, consistent with protection."))
        slope = nd.get("slopePerYear")
        features["ndviSlopePerYear"] = slope
        if slope is None:
            reasons.append(_reason("NDVI_UNAVAILABLE", 5, "Too few cloud-free Sentinel-2 years to estimate a vegetation trend."))
        elif slope < -0.02:
            reasons.append(_reason("NDVI_DECLINING", 20, f"Vegetation greenness (NDVI) fell by {abs(slope):.3f} per year since 2019, inconsistent with a protection or planting claim."))
        elif ptype == "afforestation" and slope <= 0:
            reasons.append(_reason("NDVI_NO_GREENING", 10, "No greening trend detected since 2019, which is unexpected for a planting project."))
        else:
            reasons.append(_reason("NDVI_STABLE", 0, f"Vegetation greenness trend ({slope:+.3f}/yr) is consistent with the claim."))

    score = max(0, 100 - sum(r["deduction"] for r in reasons))
    return {
        "score": score,
        "scoreBps": score * 100,
        "band": band(score),
        "reasons": sorted(reasons, key=lambda r: -r["deduction"]),
        "features": features,
        "modelVersion": MODEL_VERSION,
        "evidenceHash": evidence["evidenceHash"] if evidence else None,
    }
