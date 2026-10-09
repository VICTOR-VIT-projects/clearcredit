"""All 8 synthetic cases (data/synthetic/cases.json) end to end: API -> real contract on a local
Hardhat node, scored from the committed evidence cache (no network)."""
import json
from pathlib import Path

import pytest
from web3 import Web3
from web3.exceptions import ContractLogicError

from app import canonical, satellite
from app.store import Store
from conftest import DEV, DEV2
from test_chain_integration import chain, client_for, node, pytestmark, submit  # noqa: F401 (fixtures)

ROOT = Path(__file__).resolve().parents[2]
CASES = {c["case"]: c for c in json.loads((ROOT / "data/synthetic/cases.json").read_text(encoding="utf-8"))["cases"]}
SIGNERS = {"DEV": DEV, "DEV2": DEV2}


def selector(sig: str) -> str:
    return Web3.keccak(text=sig)[:4].hex().removeprefix("0x")


def reverts_with(call, error_sig: str):
    with pytest.raises(ContractLogicError) as e:
        call()
    assert selector(error_sig) in str(e.value)


def test_synthetic_cases(chain, db_path, monkeypatch):
    monkeypatch.setattr(satellite, "CACHE_DIR", ROOT / "data/cache/evidence")
    client = client_for(chain, db_path)
    w3, reg = chain.w3, chain.c
    for acct in (DEV, DEV2):
        w3.provider.make_request("hardhat_setBalance", [acct.address, hex(10**18)])

    def dev_send(fn):
        tx = fn.build_transaction({"from": DEV.address, "nonce": w3.eth.get_transaction_count(DEV.address)})
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(DEV.sign_transaction(tx).raw_transaction))

    responses = {}
    for n in range(1, 6):  # claim-submission cases, in order (2-4 depend on 1)
        case = CASES[n]
        claim, exp = case["claim"], case["expect"]
        r = submit(client, claim, f"key-{n}", account=SIGNERS[case.get("signer", "DEV")])
        assert r.status_code == exp["status"], f"case {n}: {r.text}"
        body = responses[n] = r.json()
        if "error" in exp:
            err = body["error"]
            assert err["code"] == exp["error"]
            (o,) = err["details"]["overlaps"]
            assert o["project_id"] == exp["overlapWith"]
            assert o["fraction_of_new"] == pytest.approx(exp["overlapFraction"], abs=0.02)
            assert err["details"]["onChainCellConflicts"], f"case {n}: contract cell registry should also conflict"
            continue
        assert body["dataLabel"] == "synthetic" and body["status"] == "registered"
        reasons = {x["code"] for x in body["score"]["reasons"]}
        assert "NO_EVIDENCE" not in reasons, f"case {n}: evidence cache miss"
        assert body["score"]["band"] == exp["band"], f"case {n}: {body['score']}"
        if "reason" in exp:
            assert exp["reason"] in reasons
        if "warning" in exp:
            assert exp["warning"] in {w["code"] for w in body["warnings"]}
        if exp.get("issuable") is False:
            key = canonical.project_key(claim["projectId"])
            reverts_with(lambda: reg.functions.issueCredits(key, 1).call({"from": DEV.address}),
                         "ScoreBelowThreshold(uint16,uint16)")
    assert client.get("/registry").json()["total"] == 3  # cases 1, 4, 5 registered; 2, 3 blocked

    # Case 6: same Idempotency-Key -> original response, no new record, no new transaction.
    nonce = w3.eth.get_transaction_count(chain.account.address)
    again = submit(client, CASES[1]["claim"], "key-1")
    assert again.status_code == 201 and again.headers["Idempotent-Replayed"] == "true"
    # Replay preserves the submitted result while refreshing chain observations (T2).
    assert {k: v for k, v in again.json().items() if k != "onChain"} == {k: v for k, v in responses[1].items() if k != "onChain"}
    assert again.json()["onChain"]["project"] == responses[1]["onChain"]["project"]
    assert again.json()["onChain"]["observedBlock"] >= responses[1]["onChain"]["observedBlock"]
    assert client.get("/registry").json()["total"] == 3
    assert w3.eth.get_transaction_count(chain.account.address) == nonce

    # Case 7: issue 100, retire 100, retiring 1 more reverts.
    key = canonical.project_key("SYN-01-CLEAN")
    dev_send(reg.functions.issueCredits(key, 100))
    dev_send(reg.functions.retireCredits(key, 100, "Synthetic buyer"))
    reverts_with(lambda: reg.functions.retireCredits(key, 1, "Synthetic buyer").call({"from": DEV.address}),
                 "ExceedsIssued(uint64,uint64)")
    assert [r["amount"] for r in client.get("/claims/SYN-01-CLEAN").json()["onChain"]["retirements"]] == [100]

    # Case 8: edit the stored claim after registration -> verify reports a mismatch.
    assert client.get("/claims/SYN-01-CLEAN/verify").json()["match"] is True
    store = Store(db_path)
    row = store.get("SYN-01-CLEAN")
    row["claim"]["claimedCredits"] = 300_000
    store.db.execute("UPDATE claims SET claim_json = ? WHERE project_id = ?", (json.dumps(row["claim"]), "SYN-01-CLEAN"))
    v = client.get("/claims/SYN-01-CLEAN/verify").json()
    assert v["match"] is False and v["onChainHash"] == responses[1]["claimHash"] != v["recomputedHash"]
