from app.scoring import score_claim


def evidence(forest=900.0, loss_vintage=1.0, slope=0.001):
    by_year = {str(y): 0.5 for y in range(2001, 2026)}
    by_year["2023"] = loss_vintage
    return {
        "evidenceHash": "0xabc",
        "forestLoss": {"forest2000Ha": forest, "lossHaByYear": by_year, "lastCoveredYear": 2025},
        "ndvi": {"slopePerYear": slope, "meanNdviByYear": {}},
    }


def claim(ptype="avoided_deforestation", credits=5000, vintage=2023):
    return {"projectType": ptype, "claimedCredits": credits, "vintageYear": vintage}


def codes(result):
    return {r["code"] for r in result["reasons"]}


def test_clean_project_scores_high_with_reasons():
    r = score_claim(claim(), 1000.0, [], evidence())
    assert r["score"] == 100 and r["band"] == "high" and r["scoreBps"] == 10000
    assert {"NO_OVERLAP", "CREDITS_PLAUSIBLE", "FOREST_LOSS_LOW", "NDVI_STABLE"} <= codes(r)
    assert all(r["text"] for r in r["reasons"])
    assert r["evidenceHash"] == "0xabc" and r["modelVersion"] == "rules-v2"


def test_forest_loss_contradicts_avoided_deforestation():
    r = score_claim(claim(), 1000.0, [], evidence(loss_vintage=120.0, slope=-0.05))
    assert {"FOREST_LOSS_HIGH", "NDVI_DECLINING"} <= codes(r)
    assert r["band"] == "low"
    assert r["reasons"][0]["code"] == "FOREST_LOSS_HIGH"  # biggest deduction first


def test_forest_loss_alone_blocks_issuance():
    # Stable NDVI must not rescue a claim the loss data contradicts: score < 60 (contract issue threshold).
    r = score_claim(claim(), 1000.0, [], evidence(loss_vintage=120.0))
    assert r["band"] == "low" and r["scoreBps"] < 6000


def test_overlap_is_a_major_deduction():
    ov = [{"project_id": "VCS1", "fraction_of_new": 0.4, "fraction_of_existing": 0.1, "intersection_ha": 400}]
    r = score_claim(claim(), 1000.0, ov, evidence())
    assert "OVERLAP" in codes(r) and r["score"] == 40


def test_inflated_credits_flagged():
    r = score_claim(claim(credits=50_000), 1000.0, [], evidence())
    assert "CREDITS_IMPLAUSIBLE" in codes(r)


def test_little_forest_for_avoided_deforestation():
    r = score_claim(claim(), 1000.0, [], evidence(forest=100.0))
    assert "LITTLE_FOREST" in codes(r)


def test_afforestation_without_greening():
    r = score_claim(claim("afforestation"), 1000.0, [], evidence(slope=-0.001))
    assert "NDVI_NO_GREENING" in codes(r) and "FOREST_LOSS_LOW" not in codes(r)


def test_missing_evidence_and_future_vintage_are_explicit():
    assert "NO_EVIDENCE" in codes(score_claim(claim(), 1000.0, [], None))
    assert "LOSS_DATA_PENDING" in codes(score_claim(claim(vintage=2026), 1000.0, [], evidence()))
