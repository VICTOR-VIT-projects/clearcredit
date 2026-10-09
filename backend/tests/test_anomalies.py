import copy
import pytest

from fastapi.testclient import TestClient

from app.anomalies import diagnose
from app.main import create_app
from app.store import Store


def project(index, delta=-0.3, boundary=None, method="same", label="synthetic"):
    return {"projectId": f"P{index}", "dataLabel": label, "evidence": {
        "boundaryKey": boundary or f"B{index}", "ndvi": {"dataset": "Sentinel-2", "method": method,
        "meanNdviByYear": {"2019": 0.8, "2020": 0.8, "2021": 0.8 + delta, "2022": 0.8 + delta + 0.01}}}}


def test_shared_offset_is_warning_only_with_labels_and_no_mutation():
    projects = [project(i) for i in range(10)]
    original = copy.deepcopy(projects)
    result = diagnose(projects)
    assert result["scoringAffected"] is False and projects == original
    (warning,) = result["warnings"]
    assert (warning["fromYear"], warning["toYear"], warning["medianDelta"]) == (2020, 2021, -0.3)
    assert warning["affectedCount"] == warning["comparisonCount"] == 10
    assert all(p["dataLabel"] == "synthetic" for p in warning["projects"])


def test_no_warning_for_small_mixed_or_insufficient_changes():
    assert diagnose([project(i, -0.1) for i in range(10)])["warnings"] == []
    assert diagnose([project(i, -0.3 if i < 5 else 0.19) for i in range(10)])["warnings"] == []
    assert diagnose([project(i) for i in range(9)])["warnings"] == []
    assert len(diagnose([project(i, -0.3 if i < 8 else 0) for i in range(10)])["warnings"]) == 1
    assert diagnose([project(i, -0.3 if i < 7 else 0) for i in range(10)])["warnings"] == []


def test_methods_and_duplicate_boundaries_cannot_fake_consensus():
    assert diagnose([project(i, method=str(i % 2)) for i in range(10)])["warnings"] == []
    result = diagnose([project(i, boundary="same-land") for i in range(10)])
    assert result["uniqueCachedBoundaries"] == 1 and not result["warnings"]


@pytest.mark.parametrize("before,after,warns", [(0.8, 0.65, True), (0.65, 0.8, True), (0.8, 0.651, False)])
def test_step_threshold_uses_decimal_observations_without_subtraction_roundoff(before, after, warns):
    projects = [project(i) for i in range(10)]
    for item in projects:
        item["evidence"]["ndvi"]["meanNdviByYear"] = {"2020": before, "2021": after}
    assert bool(diagnose(projects)["warnings"]) is warns


def test_missing_and_nonfinite_observations_do_not_pass_silently():
    projects = [project(i) for i in range(10)]
    projects[0]["evidence"] = None
    projects[1]["evidence"]["ndvi"]["meanNdviByYear"]["2021"] = float("nan")
    result = diagnose(projects)
    assert result["missingEvidenceProjects"] == 1 and result["warnings"] == []
    assert "absence of a warning does not validate" in result["note"]


def test_empty_registry_diagnostic_is_explicit_and_does_not_fetch(db_path, monkeypatch):
    from app import satellite
    monkeypatch.setattr(satellite, "get_evidence", lambda *_, **__: (_ for _ in ()).throw(AssertionError("Unexpected fetch")))
    response = TestClient(create_app(Store(db_path), chain=None)).get("/evidence/anomalies")
    assert response.status_code == 200
    assert response.json()["uniqueCachedBoundaries"] == 0
    assert response.json()["scoringAffected"] is False


def test_diagnostic_rejects_oversized_registry_before_reading_any_cache(db_path, monkeypatch):
    from app import satellite
    store = Store(db_path)
    monkeypatch.setattr(store, "page", lambda *_: (1001, []))
    monkeypatch.setattr(satellite, "get_evidence", lambda *_, **__: (_ for _ in ()).throw(AssertionError("Unexpected fetch")))
    response = TestClient(create_app(store, chain=None)).get("/evidence/anomalies")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EVIDENCE_ANALYSIS_LIMIT"
