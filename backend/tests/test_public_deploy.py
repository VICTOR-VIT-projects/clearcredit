"""Public read-only deployment: no writes, no real key, budgeted requests."""
import pytest
from eth_account import Account
from fastapi.testclient import TestClient

from app import chain as chain_module
from app.main import create_app
from app.store import Store
from conftest import make_claim, sign


@pytest.fixture
def ro_client(db_path, monkeypatch):
    monkeypatch.setenv("CLEARCREDIT_READ_ONLY", "1")
    return TestClient(create_app(store=Store(db_path), chain=None))


def test_read_only_refuses_writes_but_serves_reads(ro_client):
    r = ro_client.post("/claims", json={"claim": make_claim(), "signature": sign(None)}, headers={"Idempotency-Key": "k"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "READ_ONLY"
    a = ro_client.post("/claims/TEST-A/attest", headers={"X-Admin-Token": "anything"})
    assert a.status_code == 403 and a.json()["error"]["code"] == "READ_ONLY"
    assert ro_client.get("/registry").status_code == 200
    assert ro_client.get("/health").json()["readOnly"] is True
    assert ro_client.post("/claims/preview", json=make_claim()).status_code == 200  # cached evidence only


def test_read_only_never_uses_the_real_relayer_key(monkeypatch):
    real = Account.create()
    monkeypatch.setenv("CLEARCREDIT_READ_ONLY", "1")
    monkeypatch.setenv("REGISTRY_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setenv("DEPLOYER_PRIVATE_KEY", real.key.hex())
    seen = {}
    monkeypatch.setattr(chain_module.Chain, "__init__", lambda self, rpc, key, addr, **kw: seen.setdefault("key", key) and None)
    chain_module.Chain.from_env()
    assert Account.from_key(seen["key"]).address != real.address


def test_rate_limit_per_client(db_path, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    client = TestClient(create_app(store=Store(db_path), chain=None, live_evidence=False))
    codes = [client.get("/health", headers={"X-Forwarded-For": "203.0.113.7"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert client.get("/health", headers={"X-Forwarded-For": "198.51.100.9"}).status_code == 200  # other client unaffected
