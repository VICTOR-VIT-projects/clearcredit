"""Reconcile the claim database with the chain (the chain is the source of truth).

For every stored claim: read its on-chain status; if it is not Registered, resume the relay
(missing cell batches + finalize, all idempotent), make sure its attestation is posted, and
correct the database status. Run with the API stopped (one process per relayer key).

    CLEARCREDIT_DB=... CHAIN_RPC_URL=... REGISTRY_ADDRESS=... python -m scripts.reconcile [--dry-run]
"""
from __future__ import annotations

import argparse

from app.chain import ZERO32, Chain, RegistrationCancelled
from app.main import load_env_file
from app.store import Store


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
        pid, claim = row["project_id"], row["claim"]
        onchain = chain.project(row["project_key"])["status"]
        if onchain == "registered" and row["status"] == "registered" and chain.attestations(row["project_key"]):
            ok += 1
            continue
        print(f"{pid}: db={row['status']} chain={onchain} cells={len(row['cells'])}", flush=True)
        if args.dry_run:
            continue
        txs = list(row["txs"])
        try:
            chain.relay_registration(row["project_key"], row["claim_hash"], claim["developer"], claim["vintageYear"],
                                     claim["claimedCredits"], row["cells"], row["signature"], txs)
            s = row["result"]["score"]
            att = chain.post_attestation(row["project_key"], s["scoreBps"], s["evidenceHash"] or ZERO32, s["modelVersion"])
            txs += [att] if att else []
            store.update_claim(pid, status="registered", txs=txs)
            fixed += 1
            print(f"  -> registered ({len(txs) - len(row['txs'])} new txs)", flush=True)
        except RegistrationCancelled:
            store.update_claim(pid, status="cancelled", txs=txs)
            print("  -> cancelled on-chain", flush=True)
        except Exception as e:  # keep going; rerun to retry
            store.update_claim(pid, status="relay_failed", txs=txs)
            failed += 1
            print(f"  -> FAILED: {type(e).__name__}: {e}", flush=True)
    print(f"done: {ok} already consistent, {fixed} repaired, {failed} failed")


if __name__ == "__main__":
    main()
