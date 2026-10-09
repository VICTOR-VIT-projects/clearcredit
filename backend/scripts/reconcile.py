"""Reconcile the claim database with the chain (the chain is the source of truth).

For every stored claim: read its on-chain status; if it is not Registered, resume the relay
(missing cell batches + finalize, all idempotent), make sure its attestation is posted, and
correct the database status. Run with the API stopped (one process per relayer key).

    CLEARCREDIT_DB=... CHAIN_RPC_URL=... REGISTRY_ADDRESS=... python -m scripts.reconcile [--dry-run]
"""
from __future__ import annotations

import argparse

from app.chain import ZERO32, Chain, ChainReadUnavailable, RegistrationCancelled
from app.main import load_env_file
from app.store import Store


def reconcile_claim(chain: Chain, store: Store, row: dict, dry_run: bool = False) -> str:
    """Use one pinned snapshot for each decision; never treat any old attestation as current."""
    pid, claim, key = row["project_id"], row["claim"], row["project_key"]
    snapshot = chain.snapshot(key)
    expected = row["result"]["score"]
    latest = (snapshot["attestations"] or [{}])[-1]
    matches = all(latest.get(k) == v for k, v in {
        "scoreBps": expected["scoreBps"], "evidenceHash": expected["evidenceHash"] or ZERO32,
        "modelVersion": expected["modelVersion"],
    }.items())
    if snapshot["project"]["status"] == "registered" and row["status"] == "registered" and matches:
        return "consistent"
    if dry_run:
        return "mismatch"
    txs = list(row["txs"])
    try:
        chain.relay_registration(key, row["claim_hash"], claim["developer"], claim["vintageYear"],
                                 claim["claimedCredits"], row["cells"], row["signature"], txs)
        att = chain.post_attestation(key, expected["scoreBps"], expected["evidenceHash"] or ZERO32, expected["modelVersion"])
        txs += [att] if att else []
        if chain.snapshot(key)["project"]["status"] != "registered":
            raise ChainReadUnavailable("Confirmed registration is not visible")
        store.update_claim(pid, status="registered", txs=txs)
        return "repaired"
    except RegistrationCancelled:
        store.update_claim(pid, status="cancelled", txs=txs)
        return "cancelled"
    except Exception:
        store.update_claim(pid, status="relay_failed", txs=txs)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report mismatches without sending transactions")
    args = ap.parse_args()
    load_env_file()
    chain = Chain.from_env()
    if chain is None:
        raise SystemExit("set REGISTRY_ADDRESS (and DEPLOYER_PRIVATE_KEY in .env)")
    store = Store()
    _, rows = store.page(0, 10_000)
    fixed = ok = failed = 0
    for row in sorted(rows, key=lambda r: r["project_id"]):
        pid = row["project_id"]
        try:
            outcome = reconcile_claim(chain, store, row, args.dry_run)
            ok += outcome == "consistent"
            fixed += outcome == "repaired"
            print(f"{pid}: {outcome}", flush=True)
        except Exception as e:  # keep going; rerun to retry
            failed += 1
            print(f"  -> FAILED: {type(e).__name__}: {e}", flush=True)
    print(f"done: {ok} already consistent, {fixed} repaired, {failed} failed")


if __name__ == "__main__":
    main()
