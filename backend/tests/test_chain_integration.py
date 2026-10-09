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


def test_stale_rpc_read_after_register_cannot_fake_a_registration(chain, db_path):
    # Public RPCs are load-balanced: a read right after a confirmed write can hit a node that
    # is a block behind. Seen on Base Sepolia: the relay read status "none" after registerProject,
    # skipped addCells/finalize, and the API reported "registered" while the chain said "pending".
    client = client_for(chain, db_path)
    real_project, stale = chain.project, {"left": 1}

    def lagging(project_key):
        state = real_project(project_key)
        if state["status"] == "pending" and stale["left"]:
            stale["left"] -= 1
            return {**state, "status": "none"}  # what a lagging node returns
        return state

    chain.project = lagging
    try:
        r = submit(client, make_claim(), "k1")  # ~42 cells, batch=40: needs addCells + finalize
    finally:
        chain.project = real_project
    p = chain.project(canonical.project_key("TEST-A"))
    if r.status_code == 201:
        assert p["status"] == "registered" and p["cellCount"] == r.json()["cellCount"]
    else:  # failing closed is acceptable; claiming success is not
        assert r.json()["error"]["code"] == "RELAY_FAILED"
        assert client.get("/claims/TEST-A").json()["status"] != "registered"


def test_stale_attestation_read_cannot_append_duplicate(chain, db_path, monkeypatch):
    assert submit(client_for(chain, db_path), make_claim(), "att-lag").status_code == 201
    pk = canonical.project_key("TEST-A")
    real = chain.attestations
    before = real(pk)
    chain.post_attestation(pk, 7100, "0x" + "44" * 32, "new-model")
    nonce = chain.w3.eth.get_transaction_count(chain.account.address)
    calls = []
    def lagging(key):
        calls.append(key)
        return before if len(calls) == 1 else real(key)
    monkeypatch.setattr(chain, "attestations", lagging)
    chain.read_retry_delay = 0
    assert chain.post_attestation(pk, 7100, "0x" + "44" * 32, "new-model") is None
    assert len(calls) >= 2
    assert chain.w3.eth.get_transaction_count(chain.account.address) == nonce


def test_gas_estimates_and_reads_are_pinned_after_receipts(chain, db_path, monkeypatch):
    estimates, reads, failures = [], [], []
    send = chain._send
    def traced_send(fn):
        try:
            return send(fn)
        except Exception as e:
            failures.append(repr(e))
            raise
    monkeypatch.setattr(chain, "_send", traced_send)
    estimate = chain.w3.eth.estimate_gas
    call = chain.w3.eth.call
    def gas(tx, block_identifier=None, *args, **kwargs):
        estimates.append(block_identifier)
        assert isinstance(block_identifier, int)
        assert block_identifier >= chain.journal.chain_head(chain._read_scope)
        return estimate(tx, block_identifier, *args, **kwargs)
    def read(tx, block_identifier=None, *args, **kwargs):
        reads.append(block_identifier)
        assert isinstance(block_identifier, int)
        return call(tx, block_identifier, *args, **kwargs)
    monkeypatch.setattr(chain.w3.eth, "estimate_gas", gas)
    monkeypatch.setattr(chain.w3.eth, "call", read)
    response = submit(client_for(chain, db_path), make_claim(), "pinned")
    assert response.status_code == 201, (response.text, failures)
    assert len(estimates) == 4 and reads
    floor = chain.journal.chain_head(chain._read_scope)
    # A different RPC node's latest may lag; our next read must still demand the floor.
    monkeypatch.setattr(type(chain.w3.eth), "block_number", property(lambda _: 0))
    assert chain.snapshot(canonical.project_key("TEST-A"))["observedBlock"] == floor


def test_unavailable_receipt_block_fails_closed_after_restart(chain, db_path, monkeypatch):
    from app.chain import ChainReadUnavailable
    client = client_for(chain, db_path)
    assert submit(client, make_claim(), "floor").status_code == 201
    restarted = Chain(chain.w3.provider.endpoint_uri, HH_KEY, chain.address, journal=chain.journal)
    monkeypatch.setattr(restarted.w3.eth, "get_block", lambda *_: (_ for _ in ()).throw(ConnectionError("lag")))
    with pytest.raises(ChainReadUnavailable):
        restarted.snapshot(canonical.project_key("TEST-A"))
    response = client_for(restarted, db_path).get("/claims/TEST-A")
    assert response.status_code == 503 and response.json()["error"]["code"] == "CHAIN_READ_UNAVAILABLE"


def test_claim_response_stale_after_relay_never_stores_success(chain, db_path, monkeypatch):
    client = client_for(chain, db_path)
    real = chain.snapshot
    def lagging(key, minimum=0):
        value = real(key, minimum)
        value["project"]["status"] = "pending"
        return value
    monkeypatch.setattr(chain, "snapshot", lagging)
    response = submit(client, make_claim(), "view-lag")
    assert response.status_code == 502
    assert Store(db_path).get("TEST-A")["status"] == "relay_failed"


def test_wallet_receipt_minimum_block_is_required(chain, db_path):
    client = client_for(chain, db_path)
    assert submit(client, make_claim(), "min-block").status_code == 201
    block = chain.w3.eth.block_number
    assert client.get(f"/claims/TEST-A?minBlock={block}").json()["onChain"]["observedBlock"] >= block
    response = client.get(f"/claims/TEST-A?minBlock={block + 100}")
    assert response.status_code == 503
    assert client.get(f"/claims/TEST-A/verify?minBlock={block + 100}").status_code == 503


def test_reconcile_compares_latest_attestation_and_fails_closed(chain, db_path, monkeypatch):
    from scripts.reconcile import reconcile_claim
    from app.chain import ChainReadUnavailable
    assert submit(client_for(chain, db_path), make_claim(), "reconcile").status_code == 201
    store = Store(db_path)
    row = store.get("TEST-A")
    chain.post_attestation(row["project_key"], 100, "0x" + "55" * 32, "different")
    assert reconcile_claim(chain, store, row, dry_run=True) == "mismatch"
    assert reconcile_claim(chain, store, row) == "repaired"
    assert chain.attestations(row["project_key"])[-1]["modelVersion"] == row["result"]["score"]["modelVersion"]
    monkeypatch.setattr(chain, "snapshot", lambda *_: (_ for _ in ()).throw(ChainReadUnavailable("lag")))
    store.update_claim("TEST-A", status="relay_failed")
    with pytest.raises(ChainReadUnavailable):
        reconcile_claim(chain, store, store.get("TEST-A"))
    assert store.get("TEST-A")["status"] == "relay_failed"


def test_cached_success_is_revalidated_then_recovery_sends_nothing(chain, db_path, monkeypatch):
    client = client_for(chain, db_path)
    assert submit(client, make_claim(), "cache-truth").status_code == 201
    nonce = chain.w3.eth.get_transaction_count(chain.account.address)
    real = chain.snapshot
    calls = []
    def prewrite_once(key, minimum=0):
        value = real(key, minimum)
        calls.append(key)
        if len(calls) == 1:
            value["project"]["status"] = "pending"
        return value
    monkeypatch.setattr(chain, "snapshot", prewrite_once)
    replay = submit(client, make_claim(), "cache-truth")
    assert replay.status_code == 503
    assert Store(db_path).get("TEST-A")["status"] == "relay_failed"
    assert submit(client, make_claim(credits=999), "cache-truth").status_code == 422
    recovered = submit(client, make_claim(), "cache-truth")
    assert recovered.status_code == 201, recovered.text
    assert chain.w3.eth.get_transaction_count(chain.account.address) == nonce


def test_cached_replay_refreshes_totals_at_receipt_block(chain, db_path):
    client = client_for(chain, db_path)
    assert submit(client, make_claim(), "fresh-replay").status_code == 201
    from web3 import Web3
    chain.w3.provider.make_request("hardhat_setBalance", [DEV.address, hex(10**18)])
    fn = chain.c.functions.issueCredits(bytes.fromhex(canonical.project_key("TEST-A")[2:]), 100)
    tx = fn.build_transaction({"from": DEV.address, "nonce": chain.w3.eth.get_transaction_count(DEV.address)})
    receipt = chain.w3.eth.wait_for_transaction_receipt(chain.w3.eth.send_raw_transaction(DEV.sign_transaction(tx).raw_transaction))
    replay = submit(client, make_claim(), "fresh-replay")
    assert replay.status_code == 201 and replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["onChain"]["project"]["issued"] == 100
    assert replay.json()["onChain"]["observedBlock"] >= receipt.blockNumber


def retire_for_lookup(chain, client):
    assert submit(client, make_claim(), "retirement-lookup").status_code == 201
    chain.w3.provider.make_request("hardhat_setBalance", [DEV.address, hex(10**18)])
    pk = bytes.fromhex(canonical.project_key("TEST-A")[2:])
    receipts = []
    for fn in (chain.c.functions.issueCredits(pk, 100), chain.c.functions.retireCredits(pk, 40, "Buyer <A>"),
               chain.c.functions.retireCredits(pk, 20, "Buyer B")):
        tx = fn.build_transaction({"from": DEV.address, "nonce": chain.w3.eth.get_transaction_count(DEV.address)})
        receipts.append(chain.w3.eth.wait_for_transaction_receipt(chain.w3.eth.send_raw_transaction(DEV.sign_transaction(tx).raw_transaction)))
    return receipts


def test_public_retirement_serial_ranges_and_transaction_links(chain, db_path):
    client = client_for(chain, db_path)
    receipts = retire_for_lookup(chain, client)
    for serial, start, end, receipt in ((0, 0, 40, receipts[1]), (39, 0, 40, receipts[1]), (40, 40, 60, receipts[2]), (59, 40, 60, receipts[2])):
        response = client.get(f"/claims/TEST-A/retirements/{serial}?minBlock={receipts[-1].blockNumber}")
        assert response.status_code == 200, response.text
        record = response.json()
        assert (record["serialStart"], record["serialEndExclusive"]) == (str(start), str(end))
        assert record["transactionHash"] == "0x" + bytes(receipt.transactionHash).hex()
        assert record["dataLabel"] == "synthetic" and record["transactionUrl"] is None
    assert client.get("/claims/TEST-A/retirements/60").status_code == 404
    assert client.get("/claims/TEST-A/retirements/-1").status_code == 422
    assert client.get(f"/claims/TEST-A/retirements/{2**64}").status_code == 422


def test_retirement_missing_event_fails_closed_not_fake_not_found(chain, db_path, monkeypatch):
    client = client_for(chain, db_path)
    retire_for_lookup(chain, client)
    monkeypatch.setattr(chain.w3.eth, "get_logs", lambda *_: [])
    response = client.get("/claims/TEST-A/retirements/0")
    assert response.status_code == 503 and response.json()["error"]["code"] == "CHAIN_READ_UNAVAILABLE"


def test_bounded_history_splits_rpc_ranges_and_never_returns_partial_failure(chain, db_path, monkeypatch):
    client = client_for(chain, db_path)
    retire_for_lookup(chain, client)
    real = chain.w3.eth.get_logs
    attempts = []
    def limited(params):
        attempts.append(params)
        if params["toBlock"] > params["fromBlock"]:
            raise ValueError("provider range limit")
        values = real(params)
        return list(values) + list(values)  # duplicate transport rows are deduplicated
    monkeypatch.setattr(chain.w3.eth, "get_logs", limited)
    response = client.get("/claims/TEST-A/history")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dataLabel"] == "synthetic" and body["earlierHistoryOmitted"] is False
    assert [e["event"] for e in body["events"]].count("Retired") == 2
    assert any(e["event"] == "ProjectRegistered" for e in body["events"])
    assert len(attempts) > 1
    monkeypatch.setattr(chain.w3.eth, "get_logs", lambda *_: (_ for _ in ()).throw(ConnectionError("offline")))
    assert client.get("/claims/TEST-A/history").status_code == 503
    assert client.get("/claims/TEST-A/history?fromBlock=0&toBlock=10000").status_code == 422


def test_registry_map_optional_boundaries_and_explicit_historical_block(chain, db_path):
    client = client_for(chain, db_path)
    assert submit(client, make_claim(), "map").status_code == 201
    normal = client.get("/registry").json()
    assert "boundary" not in normal["items"][0]
    mapped = client.get("/registry?includeBoundary=true").json()
    assert mapped["items"][0]["boundary"] == make_claim()["boundary"]
    assert mapped["items"][0]["dataLabel"] == "synthetic" and mapped["observedBlock"] is not None
    registration_block = chain.project(canonical.project_key("TEST-A"))["registeredBlock"]
    past = client.get(f"/registry?includeBoundary=true&atBlock={registration_block}").json()
    assert past["observedBlock"] == registration_block
    assert past["items"][0]["status"] == "pending"  # DB success cannot override the chosen chain snapshot
