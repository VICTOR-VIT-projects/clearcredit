"""Register claim files through the public API, exactly as a client would.

Signs each claim with its DEMO developer key (derived from the project ID — publicly
derivable, holds nothing of value, and is not the real project proponent). The
Idempotency-Key is the claim's submissionKey, so re-running the seed is a no-op replay.

    python -m scripts.seed [data/claims/real data/synthetic/cases.json ...] [--api http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

ROOT = Path(__file__).resolve().parents[2]


# Public test keys used by the synthetic cases (data/synthetic/cases.json) — worthless by design.
TEST_ACCOUNTS = {a.address: a for a in (Account.from_key("0x" + "11" * 32), Account.from_key("0x" + "22" * 32))}


def demo_account(project_id: str):
    return Account.from_key(keccak(text=f"clearcredit-demo-developer:{project_id}"))


def signer_for(claim: dict):
    acct = demo_account(claim["projectId"])
    return acct if acct.address == claim["developer"] else TEST_ACCOUNTS.get(claim["developer"])


def load_claims(paths: list[str]) -> list[dict]:
    """Claim files from directories, plus data/synthetic/cases.json (only cases expected to register)."""
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += [json.loads(f.read_text(encoding="utf-8")) for f in sorted(p.glob("*.json"))]
        else:
            cases = json.loads(p.read_text(encoding="utf-8"))["cases"]
            out += [c["claim"] for c in cases if "claim" in c and c["expect"].get("status") == 201]
    return out


def sign(typed: dict, account) -> str:
    msg = encode_typed_data(domain_data=typed["domain"], message_types=typed["types"], message_data=typed["message"])
    return "0x" + account.sign_message(msg).signature.hex().removeprefix("0x")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=[str(ROOT / "data" / "claims" / "real"), str(ROOT / "data" / "synthetic" / "cases.json")])
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()
    report = []
    with httpx.Client(base_url=args.api, timeout=900) as http:
        for claim in load_claims(args.paths):
            account = signer_for(claim)
            if account is None:
                print(f"skip    {claim['projectId']}: no demo/test key for developer {claim['developer']}")
                continue
            pre = http.post("/claims/preview", json=claim)
            if pre.status_code != 200:
                report.append({"projectId": claim["projectId"], "result": pre.json()["error"]["code"], "details": pre.json()})
                print(f"invalid {claim['projectId']}: {pre.text[:200]}")
                continue
            pre = pre.json()
            r = http.post("/claims", json={"claim": claim, "signature": sign(pre["typedData"], account)},
                          headers={"Idempotency-Key": pre["submissionKey"]})
            body = r.json()
            if r.status_code == 201:
                s = body["score"]
                tag = "replay " if r.headers.get("Idempotent-Replayed") else "created"
                print(f"{tag} {claim['projectId']}: score {s['score']} ({s['band']}), {body['cellCount']} cells, {len(body['transactions'])} txs")
                report.append({"projectId": claim["projectId"], "result": "registered", "score": s["score"], "band": s["band"]})
            else:
                err = body["error"]
                print(f"{err['code'].lower():8s}{claim['projectId']}: {err['message']}")
                report.append({"projectId": claim["projectId"], "result": err["code"], "details": err.get("details")})
    out = ROOT / "data" / "claims" / "SEED_REPORT.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
