from app.satellite import boa_offset


def test_boa_offset_only_from_baseline_04():
    assert boa_offset("02.09") == 0 and boa_offset("03.01") == 0
    assert boa_offset("04.00") == 1000 and boa_offset("05.11") == 1000


def test_frozen_ev2_cache_is_verified_and_wrapped_without_new_satellite_numbers(tmp_path, monkeypatch):
    import copy
    import json
    import pytest
    from app import satellite
    from conftest import box
    b = box(0, 0, 0.1, 0.1)
    key = satellite.boundary_key(b)
    bundle = {"evidenceVersion": "ev2", "boundaryKey": key, "queriedAt": "2026-10-06",
              "forestLoss": {"forest2000Ha": 42}, "ndvi": {"slopePerYear": 0.003}}
    bundle["evidenceHash"] = satellite.evidence_hash(bundle)
    path = tmp_path / f"ev2-{key}.json"
    path.write_text(json.dumps(bundle))
    monkeypatch.setattr(satellite, "CACHE_DIR", tmp_path)
    def forbidden(*_):
        raise AssertionError("no new satellite data")
    monkeypatch.setattr(satellite, "forest_loss", forbidden)
    monkeypatch.setattr(satellite, "ndvi_trend", forbidden)
    wrapped = satellite.get_evidence(b, live=False)
    assert wrapped["evidenceVersion"] == "ev3"
    assert wrapped["sourceEvidenceHash"] == bundle["evidenceHash"]
    assert wrapped["forestLoss"] == bundle["forestLoss"] and wrapped["ndvi"] == bundle["ndvi"]
    assert json.loads(path.read_text()) == bundle  # committed source unchanged
    tampered = copy.deepcopy(bundle)
    tampered["forestLoss"]["forest2000Ha"] += 1
    path.write_text(json.dumps(tampered))
    with pytest.raises(satellite.EvidenceError):
        satellite.get_evidence(b, live=False)
