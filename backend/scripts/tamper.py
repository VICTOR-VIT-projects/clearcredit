"""Demo step: alter a stored claim OFF-CHAIN, then show the verifier detects it.

    python -m scripts.tamper SYN-01-CLEAN            # inflate claimedCredits x10 in the DB
    python -m scripts.tamper SYN-01-CLEAN --restore  # put the original back

This edits only the backend database — exactly what a malicious or careless operator could do.
The on-chain claimHash is untouched, so GET /claims/{id}/verify reports a mismatch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.store import Store

SIDECAR = Path(__file__).resolve().parents[1] / ".tamper-originals.json"  # kept outside the claim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_id")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()
    store = Store()
    row = store.get(args.project_id)
    if row is None:
        raise SystemExit(f"no claim {args.project_id!r} in {store.db.execute('PRAGMA database_list').fetchone()[2]}")
    claim = row["claim"]
    originals = json.loads(SIDECAR.read_text()) if SIDECAR.exists() else {}
    if args.restore:
        if args.project_id not in originals:
            raise SystemExit("nothing to restore")
        claim["claimedCredits"] = originals.pop(args.project_id)
    else:
        if args.project_id in originals:
            raise SystemExit("already tampered; use --restore first")
        originals[args.project_id] = claim["claimedCredits"]
        claim["claimedCredits"] *= 10
    SIDECAR.write_text(json.dumps(originals))
    store.db.execute("UPDATE claims SET claim_json = ? WHERE project_id = ?", (json.dumps(claim), args.project_id))
    print(f"{args.project_id}: claimedCredits is now {claim['claimedCredits']:,} in the database "
          f"({'restored' if args.restore else 'tampered'}). Check /claims/{args.project_id}/verify.")


if __name__ == "__main__":
    main()
