"""End-to-end against a real local Hardhat node + the real contract (skipped if Node is missing).

Covers the trust-model claims that matter most to a reviewer: signed registration, hash
verification and tamper detection, on-chain uniqueness when the backend is bypassed, and
relay resumption after a mid-flight failure.
"""
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import canonical, geo, scoring
from app.chain import Chain, cells_root
from app.main import create_app
from app.store import Store
from conftest import DEV, DEV2, box, make_claim, sign

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
PORT = 8555
# Hardhat's well-known default account #0 (public test key, local node only).
HH_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

pytestmark = pytest.mark.skipif(shutil.which("npx") is None, reason="needs Node/npx for a local Hardhat node")


def _wait_port(port, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.5)
    raise RuntimeError("hardhat node did not start")


@pytest.fixture(scope="module")
def node():
    proc = subprocess.Popen(f"npx hardhat node --port {PORT}", cwd=CONTRACTS, shell=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_port(PORT)
        yield f"http://127.0.0.1:{PORT}"
    finally:
        subprocess.run(f"taskkill /PID {proc.pid} /T /F", shell=True, capture_output=True) if shutil.which("taskkill") else proc.kill()


@pytest.fixture
def chain(node, tmp_path):
    """Fresh contract per test (cheap on a local node)."""
    abi = json.loads((Path(__file__).resolve().parents[1] / "app" / "abi.json").read_text())
    bytecode = json.loads((CONTRACTS / "artifacts/contracts/ClearCreditRegistry.sol/ClearCreditRegistry.json").read_text())["bytecode"]
    from eth_account import Account
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(node))
    acct = Account.from_key(HH_KEY)
    factory = w3.eth.contract(abi=abi, bytecode=bytecode)

    def send(tx):
        tx = tx.build_transaction({"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address, "pending")})
        h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
        return w3.eth.wait_for_transaction_receipt(h)

    addr = send(factory.constructor(acct.address, geo.CELL_RESOLUTION, 6000)).contractAddress
    c = w3.eth.contract(address=addr, abi=abi)
    for role in (c.functions.REGISTRAR_ROLE().call(), c.functions.VERIFIER_ROLE().call()):
        send(c.functions.grantRole(role, acct.address))
    return Chain(node, HH_KEY, addr, batch=40, journal=Store(str(tmp_path / "relay.sqlite3")))


def client_for(chain, db_path):
    return TestClient(create_app(store=Store(db_path), chain=chain, live_evidence=False))


def submit(client, claim, key, account=DEV):
    td = client.post("/claims/preview", json=claim).json()["typedData"]
    return client.post("/claims", json={"claim": claim, "signature": sign(td, account)}, headers={"Idempotency-Key": key})


def test_register_attest_and_verify(chain, db_path):
    client = client_for(chain, db_path)
    r = submit(client, make_claim(), "k1")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "registered"
    oc = body["onChain"]
    assert oc["project"]["status"] == "registered" and oc["project"]["developer"] == DEV.address
    assert oc["project"]["cellCount"] == body["cellCount"]
    assert oc["project"]["cellsRoot"] == oc["project"]["cellsHash"] == cells_root(geo.h3_cover(body["claim"]["boundary"]))
    assert len(oc["attestations"]) == 1 and oc["attestations"][0]["modelVersion"] == scoring.MODEL_VERSION
    assert [t["step"] for t in body["transactions"]][0] == "registerProject"
    assert client.get("/claims/TEST-A/verify").json()["match"] is True


def test_retry_after_success_sends_no_new_transactions(chain, db_path):
    client = client_for(chain, db_path)
    c = make_claim()
    submit(client, c, "k1")
    nonce = chain.w3.eth.get_transaction_count(chain.account.address)
    td = client.post("/claims/preview", json=c).json()["typedData"]
    again = client.post("/claims", json={"claim": c, "signature": sign(td)}, headers={"Idempotency-Key": "k1"})
    assert again.status_code == 201 and again.headers["Idempotent-Replayed"] == "true"
    assert chain.w3.eth.get_transaction_count(chain.account.address) == nonce


def test_tampered_offchain_record_is_detected(chain, db_path):
    client = client_for(chain, db_path)
    submit(client, make_claim(), "k1")
    store = Store(db_path)
    row = store.get("TEST-A")
    row["claim"]["claimedCredits"] = 99_999  # someone edits the database after registration
    store.db.execute("UPDATE claims SET claim_json = ? WHERE project_id = ?", (json.dumps(row["claim"]), "TEST-A"))
    v = client.get("/claims/TEST-A/verify").json()
    assert v["match"] is False and v["recomputedHash"] != v["onChainHash"]


def test_bad_signature_rejected(chain, db_path):
    client = client_for(chain, db_path)
    r = submit(client, make_claim(), "k1", account=DEV2)  # DEV2 signs a claim naming DEV
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_SIGNATURE"


def test_preview_signs_v2_cell_commitment_and_tampered_root_is_rejected(chain, db_path):
    client = client_for(chain, db_path)
    c = make_claim()
    preview = client.post("/claims/preview", json=c).json()
    td = preview["typedData"]
    assert td["domain"]["version"] == "2"
    assert td["message"]["cellsRoot"] == preview["cellsRoot"] == cells_root([int(x, 16) for x in preview["cellIds"]])
    td["message"]["cellsRoot"] = "0x" + "33" * 32
    r = client.post("/claims", json={"claim": c, "signature": sign(td)}, headers={"Idempotency-Key": "tampered-root"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_SIGNATURE"


def test_onchain_uniqueness_holds_even_if_backend_db_is_bypassed(chain, db_path, tmp_path):
    submit(client_for(chain, db_path), make_claim("A"), "k1")
    # A second backend with an EMPTY database knows nothing about A off-chain...
    other = client_for(chain, str(tmp_path / "other.sqlite3"))
    r = submit(other, make_claim("B", boundary=box(-63.08, -9.90, -63.03, -9.85), developer=DEV2), "k2", account=DEV2)
    err = r.json()["error"]
    # ...but the contract's cell registry still blocks the double claim.
    assert r.status_code == 409 and err["code"] == "OVERLAP_DETECTED"
    assert err["details"]["overlaps"] == [] and err["details"]["onChainCellConflicts"][0]["count"] > 0


def test_relay_resumes_after_mid_flight_failure(chain, db_path):
    client = client_for(chain, db_path)
    c = make_claim()  # ~42 cells with batch=40 -> register + addCells + finalize + attest
    real_send, calls = chain._send, {"n": 0}

    def flaky(fn):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("simulated RPC outage")
        return real_send(fn)

    chain._send = flaky
    try:
        first = submit(client, c, "k1")
        assert first.status_code == 502 and first.json()["error"]["code"] == "RELAY_FAILED"
        assert chain.project(canonical.project_key("TEST-A"))["status"] == "pending"
        second = submit(client, c, "k1")  # same key: key was released, relay resumes
    finally:
        chain._send = real_send
    assert second.status_code == 201, second.text
    p = second.json()["onChain"]["project"]
    assert p["status"] == "registered" and p["cellCount"] == second.json()["cellCount"]
    assert [t["step"] for t in second.json()["transactions"]].count("registerProject") == 1


def test_pending_attestation_timeout_then_late_mine_does_not_append_twice(chain, db_path, monkeypatch):
    from web3.exceptions import TimeExhausted
    client = client_for(chain, db_path)
    assert submit(client, make_claim(), "k1").status_code == 201
    pk = canonical.project_key("TEST-A")
    nonce = chain.w3.eth.get_transaction_count(chain.account.address)
    real_wait = chain.w3.eth.wait_for_transaction_receipt
    monkeypatch.setattr(chain.w3.eth, "wait_for_transaction_receipt",
                        lambda h, **_: real_wait(h, timeout=0.05, poll_latency=0.01))
    chain.w3.provider.make_request("evm_setAutomine", [False])
    try:
        with pytest.raises(TimeExhausted):
            chain.post_attestation(pk, 7000, "0x" + "33" * 32, "timeout-test")
        with pytest.raises(TimeExhausted):
            chain.post_attestation(pk, 7000, "0x" + "33" * 32, "timeout-test")
        assert chain.w3.eth.get_transaction_count(chain.account.address, "pending") == nonce + 1
        chain.w3.provider.make_request("evm_mine", [])
        recovered = chain.post_attestation(pk, 7000, "0x" + "33" * 32, "timeout-test")
        assert recovered["step"] == "postAttestation"
        assert len(chain.attestations(pk)) == 2  # initial score + precisely one new attestation
        assert chain.w3.eth.get_transaction_count(chain.account.address) == nonce + 1
        assert chain.post_attestation(pk, 7000, "0x" + "33" * 32, "timeout-test") is None
    finally:
        chain.w3.provider.make_request("evm_setAutomine", [True])


def test_expired_pending_cancellation_is_terminal_to_the_api(chain, db_path, monkeypatch):
    client = client_for(chain, db_path)
    real_send, calls = chain._send, {"n": 0}
    def fail_after_register(fn):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("pause after registration")
        return real_send(fn)
    monkeypatch.setattr(chain, "_send", fail_after_register)
    assert submit(client, make_claim(), "cancel-key").status_code == 502
    monkeypatch.setattr(chain, "_send", real_send)
    pk = canonical.project_key("TEST-A")
    cells = geo.h3_cover(make_claim()["boundary"])
    chain.w3.provider.make_request("hardhat_mine", [hex(chain.c.functions.PENDING_EXPIRY_BLOCKS().call())])
    chain._send(chain.c.functions.cancelPendingRegistration(bytes.fromhex(pk[2:]), cells))
    assert chain.project(pk)["status"] == "cancelled"
    retry = submit(client, make_claim(), "cancel-key")
    assert retry.status_code == 409 and retry.json()["error"]["code"] == "REGISTRATION_CANCELLED"
    assert client.get("/claims/TEST-A").json()["status"] == "cancelled"
    assert chain.check_cells(cells, 2023) == {}


def test_two_distinct_registrar_accounts_share_contract_uniqueness(chain, db_path, tmp_path):
    from web3.exceptions import ContractLogicError
    # Registry A's operator is the fixture's registrar. Registry B receives its own
    # registrar role/account and database, then bypasses ALL API overlap prechecks.
    assert submit(client_for(chain, db_path), make_claim("REGISTRY-A"), "registry-a").status_code == 201
    role = chain.c.functions.REGISTRAR_ROLE().call()
    chain._send(chain.c.functions.grantRole(role, DEV2.address))
    chain.w3.provider.make_request("hardhat_setBalance", [DEV2.address, hex(10**18)])
    other = Chain(chain.w3.provider.endpoint_uri, DEV2.key, chain.address,
                  journal=Store(str(tmp_path / "registry-b.sqlite3")))
    b = make_claim("REGISTRY-B", developer=DEV2)
    from app.models import Claim
    b = Claim(**b).model_dump()
    cells = geo.h3_cover(b["boundary"])
    pk, ch = canonical.project_key(b["projectId"]), canonical.claim_hash(b)
    td = other.typed_data(pk, ch, b["vintageYear"], b["claimedCredits"], cells_root(cells))
    with pytest.raises(ContractLogicError) as error:
        other.relay_registration(pk, ch, b["developer"], b["vintageYear"], b["claimedCredits"], cells, sign(td, DEV2), [])
    selector = chain.w3.keccak(text="CellAlreadyClaimed(uint64,uint16,bytes32)")[:4].hex().removeprefix("0x")
    assert selector in str(error.value)
    assert other.account.address != chain.account.address
    assert other.project(pk)["status"] == "none"
    assert set(other.check_cells(cells, 2023).values()) == {canonical.project_key("REGISTRY-A")}
