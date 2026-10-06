import copy
import json

from app import canonical, history, scoring, satellite
from test_scoring import claim, evidence


def snapshot(records):
    return {"source": "test snapshot", "snapshotHash": "0x" + "12" * 32, "records": {"VCS1": records}}


def test_issuance_aggregates_by_vintage_and_excludes_retirements_and_invalid_numbers(tmp_path):
    path = tmp_path / "credits.csv"
    path.write_text("project_id,quantity,transaction_type,vintage\nVCS1,20,issuance,2020\nVCS1,30.0,issuance,2020\nVCS1,100,retirement,2020\nVCS1,NaN,issuance,2021\nVCS1,-3,issuance,2021\nVCS2,90,issuance,2020\nVCS1,1.2,issuance,2020\n", encoding="utf-8")
    assert history.read_issuance(path, {"VCS1"}) == {"VCS1": {2020: 50}}


def test_history_excludes_current_and_future_vintages_and_uses_project_reference():
    c = {**claim(vintage=2023), "projectId": "new-submission", "sourceRegistry": "Verra VCS VCS1"}
    h = history.for_claim(c, snapshot({"2019": 100, "2020": 200, "2021": 300, "2023": 9999, "2024": 8888}))
    assert h["projectId"] == "VCS1" and h["medianCredits"] == 200 and h["vintageCount"] == 3
    assert set(h["priorVintages"]) == {"2019", "2020", "2021"}


def test_no_or_insufficient_history_is_explicit_without_a_deduction():
    c = {**claim(), "projectId": "VCS1"}
    for snap in ({}, snapshot({"2020": 100, "2021": 100})):
        h = history.for_claim(c, snap)
        result = scoring.score_claim(c, 1000, [], evidence(), h)
        reason = next(r for r in result["reasons"] if r["code"] == "NO_HISTORY")
        assert reason["deduction"] == 0 and "No history" in reason["text"]


def test_frozen_jump_rule_boundaries_and_first_principles_invariance():
    c = {**claim(credits=300), "projectId": "VCS1"}
    h = history.for_claim(c, snapshot({"2018": 100, "2019": 100, "2020": 100}))
    at_limit = scoring.score_claim(c, 1000, [], evidence(), h)
    assert "HISTORY_CREDITS_JUMP" not in {r["code"] for r in at_limit["reasons"]}
    for area in (1000, 2000):
        above = scoring.score_claim({**c, "claimedCredits": 301}, area, [], evidence(), h)
        assert above["score"] < 60
        assert next(r for r in above["reasons"] if r["code"] == "HISTORY_CREDITS_JUMP")["deduction"] == 50


def test_history_numbers_are_in_the_attestation_commitment():
    c = {**claim(), "projectId": "VCS1"}
    h = history.for_claim(c, snapshot({"2018": 100, "2019": 100, "2020": 100}))
    s = scoring.score_claim(c, 1000, [], evidence(), h)
    assert s["evidenceHash"] == satellite.evidence_hash(s["attestationEvidence"])
    changed = copy.deepcopy(h)
    changed["priorVintages"]["2018"] = 101
    assert scoring.score_claim(c, 1000, [], evidence(), changed)["evidenceHash"] != s["evidenceHash"]


def test_missing_and_tampered_snapshot_fail_explicitly(tmp_path):
    path = tmp_path / "snapshot.json"
    assert history.load_snapshot(path) is None
    path.write_text(json.dumps({"snapshotHash": "0xwrong", "source": "test", "records": {}}))
    import pytest
    with pytest.raises(ValueError, match="hash mismatch"):
        history.load_snapshot(path)
