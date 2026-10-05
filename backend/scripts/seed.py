"""Register claim files through the public API, exactly as a client would.

Signs each claim with its DEMO developer key (derived from the project ID — publicly
derivable, holds nothing of value, and is not the real project proponent). The
Idempotency-Key is the claim's submissionKey, so re-running the seed is a no-op replay.

    python -m scripts.seed [data/claims/real ...] [--api http://localhost:8000]
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


def demo_account(project_id: str):
    return Account.from_key(keccak(text=f"clearcredit-demo-developer:{project_id}"))


def sign(typed: dict, account) -> str:
    msg = encode_typed_data(domain_data=typed["domain"], message_types=typed["types"], message_data=typed["message"])
    return "0x" + account.sign_message(msg).signature.hex().removeprefix("0x")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*", default=[str(ROOT / "data" / "claims" / "real")])
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()
    files = sorted(f for d in args.dirs for f in Path(d).glob("*.json"))
    report = []
    with httpx.Client(base_url=args.api, timeout=900) as http:
        for f in files:
            claim = json.loads(f.read_text(encoding="utf-8"))
            account = demo_account(claim["projectId"])
            if account.address != claim["developer"]:
                print(f"skip    {claim['projectId']}: developer is not this project's demo wallet")
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
