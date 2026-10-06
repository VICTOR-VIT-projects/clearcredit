"""API behaviour without a chain (offline mode): validation, idempotency, duplicates, overlap."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from conftest import DEV2, box, make_claim, sign


@pytest.fixture
def client(db_path):
    return TestClient(create_app(store=Store(db_path), chain=None, live_evidence=False))


def submit(client, claim, key):
    return client.post("/claims", json={"claim": claim, "signature": sign(None)}, headers={"Idempotency-Key": key})


def test_preview_returns_hashes_score_and_reasons(client):
    r = client.post("/claims/preview", json=make_claim())
    assert r.status_code == 200
    body = r.json()
    assert body["claimHash"].startswith("0x") and len(body["claimHash"]) == 66
    assert body["blocked"] is False and body["cellCount"] > 30
    assert any(x["code"] == "NO_EVIDENCE" for x in body["score"]["reasons"])
    assert "typedData" not in body  # no chain configured


def test_invalid_geometry_has_machine_readable_code(client):
    bad = make_claim(boundary={"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]]})
    r = client.post("/claims/preview", json=bad)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_GEOMETRY"


def test_schema_rejects_unknown_fields(client):
    r = client.post("/claims/preview", json={**make_claim(), "certified": True})
    assert r.status_code == 422


def test_idempotency_key_required(client):
    r = client.post("/claims", json={"claim": make_claim(), "signature": sign(None)})
    assert r.status_code == 400 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_retry_with_same_key_returns_original_and_creates_nothing(client):
    c = make_claim()
    first = submit(client, c, "k1")
    assert first.status_code == 201 and first.json()["status"] == "offline"
    again = submit(client, c, "k1")
    assert again.status_code == 201
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json() == first.json()
    assert client.get("/registry").json()["total"] == 1


def test_same_key_different_body_is_rejected(client):
    submit(client, make_claim(), "k1")
    r = submit(client, make_claim(credits=999), "k1")
    assert r.status_code == 422 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_same_claim_new_key_is_a_duplicate(client):
    submit(client, make_claim(), "k1")
    r = submit(client, make_claim(), "k2")
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_CLAIM"


def test_overlap_same_vintage_blocked_with_fraction(client):
    submit(client, make_claim("A"), "k1")
    r = submit(client, make_claim("B", boundary=box(-63.08, -9.90, -63.03, -9.85), developer=DEV2), "k2")
    err = r.json()["error"]
    assert r.status_code == 409 and err["code"] == "OVERLAP_DETECTED"
    (o,) = err["details"]["overlaps"]
    assert o["project_id"] == "A" and o["fraction_of_new"] == pytest.approx(0.6, abs=0.02)
    assert client.get("/registry").json()["total"] == 1


def test_same_land_different_vintage_allowed(client):
    submit(client, make_claim("A", vintage=2023), "k1")
    r = submit(client, make_claim("A-2024", vintage=2024), "k2")
    assert r.status_code == 201


def test_lookup_by_hash_and_verify_offline(client):
    created = submit(client, make_claim(), "k1").json()
    assert client.get(f"/claims/{created['claimHash']}").json()["projectId"] == "TEST-A"
    v = client.get("/claims/TEST-A/verify").json()
    assert v["recomputedHash"] == created["claimHash"] and v["match"] is None
    assert client.get("/claims/nope").json()["error"]["code"] == "NOT_FOUND"


def test_schema_endpoint(client):
    s = client.get("/schema").json()
    assert s["schemaVersion"] == "1.0" and "dataLabel" in s["jsonSchema"]["properties"]


def test_replay_header_is_visible_to_browsers(client):
    # Without Access-Control-Expose-Headers, cross-origin JS cannot read Idempotent-Replayed.
    origin = {"Origin": "http://localhost:5173"}
    c = make_claim()
    client.post("/claims", json={"claim": c, "signature": sign(None)}, headers={"Idempotency-Key": "k1", **origin})
    r = client.post("/claims", json={"claim": c, "signature": sign(None)}, headers={"Idempotency-Key": "k1", **origin})
    assert r.headers["Idempotent-Replayed"] == "true"
    assert "idempotent-replayed" in r.headers["access-control-expose-headers"].lower()


def test_concurrent_different_keys_cannot_bypass_overlap_admission(client, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from app import satellite
    entered, release = threading.Event(), threading.Event()
    original = satellite.get_evidence

    def pause_boundary(boundary, **kwargs):
        if boundary == make_claim("A")["boundary"] and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original(boundary, **kwargs)

    monkeypatch.setattr(satellite, "get_evidence", pause_boundary)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(submit, client, make_claim("A"), "concurrent-A")
        assert entered.wait(5)
        second = pool.submit(submit, client, make_claim("B", boundary=box(-63.08, -9.90, -63.03, -9.85)), "concurrent-B")
        try:
            second.result(timeout=0.2)
        except TimeoutError:
            pass
        finally:
            release.set()
        assert first.result().status_code == 201
        result = second.result()
        assert result.status_code == 409 and result.json()["error"]["code"] == "OVERLAP_DETECTED"
        assert client.get("/registry").json()["total"] == 1


@pytest.mark.parametrize("coordinates", [[None], [1], [[[0], [1], [2], [0]]], [[]], []])
def test_malformed_boundary_returns_structured_error(client, coordinates):
    r = client.post("/claims/preview", json=make_claim(boundary={"type": "Polygon", "coordinates": coordinates}))
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_GEOMETRY"


def test_oversized_body_is_rejected_before_json_parsing(client):
    r = client.post("/claims/preview", content=" " * (2 * 1024 * 1024 + 1), headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "REQUEST_TOO_LARGE"
