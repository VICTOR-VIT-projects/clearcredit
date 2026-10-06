"""web3 client for ClearCreditRegistry: pre-checks, resumable relay, attestations, reads.

The relay is idempotent by construction: every step first reads on-chain state and only
does what is missing, so a retry after a crash or timeout resumes instead of duplicating.
"""
from __future__ import annotations

import json
import os
import threading
from functools import wraps
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from web3.exceptions import TimeExhausted, TransactionNotFound

from .store import Store

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


def _serialized(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return run


class Chain:
    def __init__(self, rpc_url: str, private_key: str, address: str, batch: int = 200, journal: Store | None = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
        self.account = Account.from_key(private_key)
        self.address = Web3.to_checksum_address(address)
        self.c = self.w3.eth.contract(address=self.address, abi=ABI)
        self.chain_id = self.w3.eth.chain_id
        self.batch = batch
        self.explorer = EXPLORERS.get(self.chain_id)
        # One worker/Chain per relayer key. State checks and sends share this lock.
        self._lock = threading.RLock()
        self.journal = journal or Store()

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

    @property
    def _scope(self) -> str:
        return f"{self.chain_id}:{self.address.lower()}:{self.account.address.lower()}"

    def _complete(self, row: dict) -> str:
        h = _b32(row["tx_hash"])
        try:
            receipt = self.w3.eth.get_transaction_receipt(h)
        except (TransactionNotFound, TimeExhausted):
            try:
                self.w3.eth.send_raw_transaction(bytes.fromhex(row["raw_tx"]))
            except Exception as e:
                # A known mempool transaction needs waiting, not a new nonce. All other
                # RPC errors retain the journal and fail closed for operator recovery.
                if "already known" not in str(e).lower() and "known transaction" not in str(e).lower():
                    raise
            receipt = self.w3.eth.wait_for_transaction_receipt(h, timeout=180)
        self.journal.relay_clear(self._scope)
        if receipt["status"] != 1:
            raise RuntimeError(f"transaction reverted: {row['tx_hash']}")
        return row["tx_hash"]

    def _reconcile(self, project_key: str) -> list[dict]:
        row = self.journal.relay_pending(self._scope)
        if not row:
            return []
        tx = self._complete(row)
        return [{"step": row["step"], "tx": tx}] if row["project_key"] == project_key else []

    @_serialized
    def _send(self, fn) -> str:
        operation = fn._encode_transaction_data()
        row = self.journal.relay_pending(self._scope)
        if row:
            tx_hash = self._complete(row)
            if row["operation"] == operation:
                return tx_hash
        tx = fn.build_transaction({"from": self.account.address, "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"), "chainId": self.chain_id})
        signed = self.account.sign_transaction(tx)
        raw = bytes(signed.raw_transaction)
        tx_hash = _hex(Web3.keccak(raw))
        args = getattr(fn, "arguments", ())
        project_key = _hex(args[0]) if args else None
        self.journal.relay_save(self._scope, operation, project_key, fn.fn_name, tx_hash, raw.hex())
        return self._complete(self.journal.relay_pending(self._scope))

    @_serialized
    def relay_registration(self, project_key, claim_hash, developer, vintage, credits, cells, signature, txs: list) -> None:
        """Register → add remaining cell batches → finalize. Safe to call again after any failure.
        Appends each confirmed tx to `txs` as it lands, so partial progress survives an exception."""
        pk = _b32(project_key)
        txs.extend(t for t in self._reconcile(project_key) if t not in txs)
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

    @_serialized
    def post_attestation(self, project_key, score_bps, evidence_hash, model_version) -> dict | None:
        """Append an attestation unless the latest one already says exactly this (retry-safe)."""
        recovered = self._reconcile(project_key)
        latest = (self.attestations(project_key) or [None])[-1]
        if latest and (latest["scoreBps"], latest["evidenceHash"], latest["modelVersion"]) == (score_bps, evidence_hash, model_version):
            return next((t for t in recovered if t["step"] == "postAttestation"), None)
        return {"step": "postAttestation", "tx": self._send(self.c.functions.postAttestation(
            _b32(project_key), score_bps, _b32(evidence_hash), model_version))}
