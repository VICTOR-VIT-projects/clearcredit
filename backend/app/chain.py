"""web3 client for ClearCreditRegistry: pre-checks, resumable relay, attestations, reads.

The relay is idempotent by construction: every step first reads on-chain state and only
does what is missing, so a retry after a crash or timeout resumes instead of duplicating.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

ABI = json.loads((Path(__file__).parent / "abi.json").read_text())
STATUS = {0: "none", 1: "pending", 2: "registered"}
ZERO32 = "0x" + "00" * 32
EXPLORERS = {84532: "https://sepolia.basescan.org", 31337: None}

CLAIM_TYPES = {
    "Claim": [
        {"name": "projectId", "type": "bytes32"},
        {"name": "claimHash", "type": "bytes32"},
        {"name": "vintageYear", "type": "uint16"},
        {"name": "claimedCredits", "type": "uint64"},
    ]
}


def typed_data(chain_id: int, contract: str, project_key: str, claim_hash: str, vintage: int, credits: int) -> dict:
    """EIP-712 payload the developer's wallet signs (eth_signTypedData_v4 shape)."""
    return {
        "domain": {"name": "ClearCredit", "version": "1", "chainId": chain_id, "verifyingContract": contract},
        "types": CLAIM_TYPES,
        "primaryType": "Claim",
        "message": {"projectId": project_key, "claimHash": claim_hash, "vintageYear": vintage, "claimedCredits": credits},
    }


def recover_signer(td: dict, signature: str) -> str:
    msg = encode_typed_data(domain_data=td["domain"], message_types=td["types"], message_data=td["message"])
    return Account.recover_message(msg, signature=signature)


def _b32(h: str) -> bytes:
    return bytes.fromhex(h[2:])


def _hex(b: bytes) -> str:
    return "0x" + bytes(b).hex()


class Chain:
    def __init__(self, rpc_url: str, private_key: str, address: str, batch: int = 300):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
        self.account = Account.from_key(private_key)
        self.address = Web3.to_checksum_address(address)
        self.c = self.w3.eth.contract(address=self.address, abi=ABI)
        self.chain_id = self.w3.eth.chain_id
        self.batch = batch
        self.explorer = EXPLORERS.get(self.chain_id)
        # ponytail: one process-wide lock serializes nonces for the single relayer key;
        # use a nonce manager or a key per worker if relay throughput ever matters.
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "Chain | None":
        addr, key = os.environ.get("REGISTRY_ADDRESS"), os.environ.get("DEPLOYER_PRIVATE_KEY")
        if not (addr and key):
            return None
        return cls(os.environ.get("CHAIN_RPC_URL") or os.environ.get("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org"), key, addr)

    def typed_data(self, project_key: str, claim_hash: str, vintage: int, credits: int) -> dict:
        return typed_data(self.chain_id, self.address, project_key, claim_hash, vintage, credits)

    # ------------------------------------------------------------ reads

    def project(self, project_key: str) -> dict:
        p = self.c.functions.getProject(_b32(project_key)).call()
        return {
            "developer": p[0], "claimHash": _hex(p[1]), "vintageYear": p[2], "status": STATUS[p[3]],
            "claimedCredits": p[4], "issued": p[5], "retired": p[6], "cellCount": p[7], "registeredAt": p[8],
        }

    def check_cells(self, cells: list[int], vintage: int) -> dict[int, str]:
        """Cells already held by another project for this vintage → owner projectKey."""
        out = {}
        for i in range(0, len(cells), 2000):
            chunk = cells[i : i + 2000]
            owners = self.c.functions.checkCells(chunk, vintage).call()
            out.update({c: _hex(o) for c, o in zip(chunk, owners) if _hex(o) != ZERO32})
        return out

    def attestations(self, project_key: str) -> list[dict]:
        return [
            {"scoreBps": a[0], "evidenceHash": _hex(a[1]), "modelVersion": a[2], "verifier": a[3], "timestamp": a[4]}
            for a in self.c.functions.getAttestations(_b32(project_key)).call()
        ]

    def retirements(self, project_key: str) -> list[dict]:
        return [
            {"serialStart": r[0], "amount": r[1], "from": r[2], "beneficiary": r[3], "timestamp": r[4]}
            for r in self.c.functions.getRetirements(_b32(project_key)).call()
        ]

    def tx_url(self, tx: str) -> str | None:
        return f"{self.explorer}/tx/{tx}" if self.explorer else None

    # ------------------------------------------------------------ writes

    def _send(self, fn) -> str:
        with self._lock:
            tx = fn.build_transaction({"from": self.account.address, "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"), "chainId": self.chain_id})
            signed = self.account.sign_transaction(tx)
            h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(h, timeout=180)
        if receipt["status"] != 1:
            raise RuntimeError(f"transaction reverted: {_hex(h)}")
        return _hex(h)

    def relay_registration(self, project_key, claim_hash, developer, vintage, credits, cells, signature, txs: list) -> None:
        """Register → add remaining cell batches → finalize. Safe to call again after any failure.
        Appends each confirmed tx to `txs` as it lands, so partial progress survives an exception."""
        pk = _b32(project_key)
        state = self.project(project_key)
        if state["status"] == "none":
            first = cells[: self.batch]
            txs.append({"step": "registerProject", "tx": self._send(self.c.functions.registerProject(
                pk, _b32(claim_hash), Web3.to_checksum_address(developer), vintage, credits, first, signature))})
            state = self.project(project_key)
        if state["status"] == "pending":
            owners = self.c.functions.checkCells(cells, vintage).call() if len(cells) <= 2000 else None
            todo = [c for c, o in zip(cells, owners) if bytes(o) != pk] if owners is not None else cells
            for i in range(0, len(todo), self.batch):  # re-adding owned cells is a no-op on-chain
                txs.append({"step": "addCells", "tx": self._send(self.c.functions.addCells(pk, todo[i : i + self.batch]))})
            txs.append({"step": "finalizeRegistration", "tx": self._send(self.c.functions.finalizeRegistration(pk))})

    def post_attestation(self, project_key, score_bps, evidence_hash, model_version) -> dict | None:
        """Append an attestation unless the latest one already says exactly this (retry-safe)."""
        latest = (self.attestations(project_key) or [None])[-1]
        if latest and (latest["scoreBps"], latest["evidenceHash"], latest["modelVersion"]) == (score_bps, evidence_hash, model_version):
            return None
        return {"step": "postAttestation", "tx": self._send(self.c.functions.postAttestation(
            _b32(project_key), score_bps, _b32(evidence_hash), model_version))}
