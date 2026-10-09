"""web3 client for ClearCreditRegistry: pre-checks, resumable relay, attestations, reads.

The relay is idempotent by construction: every step first reads on-chain state and only
does what is missing, so a retry after a crash or timeout resumes instead of duplicating.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from functools import wraps
from contextlib import contextmanager
from pathlib import Path

from eth_account import Account
from eth_utils.abi import get_abi_output_types
from eth_account.messages import encode_typed_data
from web3 import Web3
from web3.exceptions import TimeExhausted, TransactionNotFound

from .store import Store

ABI = json.loads((Path(__file__).parent / "abi.json").read_text())
STATUS = {0: "none", 1: "pending", 2: "registered", 3: "cancelled"}
ZERO32 = "0x" + "00" * 32
EXPLORERS = {84532: "https://sepolia.basescan.org", 31337: None}


class RegistrationCancelled(RuntimeError):
    pass


class ChainReadUnavailable(RuntimeError):
    """The RPC cannot provide the required coherent chain snapshot; retry later."""

CLAIM_TYPES = {
    "Claim": [
        {"name": "projectId", "type": "bytes32"},
        {"name": "claimHash", "type": "bytes32"},
        {"name": "vintageYear", "type": "uint16"},
        {"name": "claimedCredits", "type": "uint64"},
        {"name": "cellsRoot", "type": "bytes32"},
    ]
}


def cells_root(cells: list[int]) -> str:
    """Sorted unique uint64 cells: h0=0; hi=keccak(hi-1 || uint64(cell))."""
    if cells != sorted(set(cells)):
        raise ValueError("cell commitment requires a sorted unique list")
    h = bytes(32)
    for cell in cells:
        h = Web3.keccak(h + cell.to_bytes(8, "big"))
    return _hex(h)


def typed_data(chain_id: int, contract: str, project_key: str, claim_hash: str, vintage: int, credits: int, cell_commitment: str) -> dict:
    """EIP-712 payload the developer's wallet signs (eth_signTypedData_v4 shape)."""
    return {
        "domain": {"name": "ClearCredit", "version": "2", "chainId": chain_id, "verifyingContract": contract},
        "types": CLAIM_TYPES,
        "primaryType": "Claim",
        "message": {"projectId": project_key, "claimHash": claim_hash, "vintageYear": vintage, "claimedCredits": credits, "cellsRoot": cell_commitment},
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
    BATCH_SIZE = 10          # calls per JSON-RPC batch; public RPCs count each call against a per-second budget
    RATE_LIMIT_RETRIES = 4
    block_reuse_seconds = 0.0      # immutable defaults; __init__ sets per-instance values
    _latest_cache = (0.0, -1)

    def __init__(self, rpc_url: str, private_key: str, address: str, batch: int = 200, journal: Store | None = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
        self.account = Account.from_key(private_key)
        self.address = Web3.to_checksum_address(address)
        self.c = self.w3.eth.contract(address=self.address, abi=ABI)
        self.chain_id = self.w3.eth.chain_id
        if self.c.functions.eip712Domain().call()[2] != "2":
            raise RuntimeError("This backend requires ClearCredit EIP-712 v2; use a fresh local contract, not a v1 deployment.")
        self.batch = batch
        self.explorer = EXPLORERS.get(self.chain_id)
        # One worker/Chain per relayer key. State checks and sends share this lock.
        self._lock = threading.RLock()
        self.read_attempts, self.read_retry_delay = 15, 2.0  # ~30 s for a lagging RPC node to catch up
        self.journal = journal or Store()
        self._reads = threading.local()
        # Read-side load control for rate-limited public RPCs (sepolia.base.org: 25 requests/s,
        # counting every call inside a batch). Contract state at a fixed block never changes, so
        # results are cached by (call, block); optionally the latest block is reused for a few
        # seconds so bursts of visitors share reads (CHAIN_BLOCK_REUSE_SECONDS, off by default).
        self.block_reuse_seconds = float(os.environ.get("CHAIN_BLOCK_REUSE_SECONDS") or 0)
        self._latest_cache = (0.0, -1)
        self._call_cache: dict[tuple[str, int], str] = {}
        self._cache_lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "Chain | None":
        addr, key = os.environ.get("REGISTRY_ADDRESS"), os.environ.get("DEPLOYER_PRIVATE_KEY")
        if os.environ.get("CLEARCREDIT_READ_ONLY") == "1":
            # Never hold a real relayer key on a public read-only host: reads only need a signer object.
            key = "0x" + secrets.token_hex(32)
        if not (addr and key):
            return None
        return cls(os.environ.get("CHAIN_RPC_URL") or os.environ.get("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org"), key, addr)

    def typed_data(self, project_key: str, claim_hash: str, vintage: int, credits: int, cell_commitment: str) -> dict:
        return typed_data(self.chain_id, self.address, project_key, claim_hash, vintage, credits, cell_commitment)

    # ------------------------------------------------------------ reads

    @property
    def _read_scope(self) -> str:
        return f"{self.chain_id}:{self.address.lower()}"

    def snapshot_block(self, minimum: int = 0) -> int:
        floor = max(minimum, self.journal.chain_head(self._read_scope))
        cached_at, cached_block = self._latest_cache
        if self.block_reuse_seconds and time.monotonic() - cached_at < self.block_reuse_seconds and cached_block >= floor:
            return cached_block  # a real, already-verified block no older than anything we know was confirmed
        try:
            # One call: the latest block both names the height and proves this node serves it.
            latest = self.w3.eth.get_block("latest")["number"]
            block = max(floor, latest)
            # Below our floor (a lagging node): it must serve the explicit height or fail, never substitute.
            if block != latest and self.w3.eth.get_block(block)["number"] != block:
                raise ChainReadUnavailable("RPC returned a different block")
            self.journal.advance_chain_head(self._read_scope, block)
            self._latest_cache = (time.monotonic(), block)
            return block
        except Exception as e:
            raise ChainReadUnavailable("Required chain block is unavailable; retry shortly") from e

    @contextmanager
    def read_at(self, block: int):
        previous = getattr(self._reads, "block", None)
        self._reads.block = block
        try:
            yield
        finally:
            self._reads.block = previous

    def _read_block(self) -> int:
        block = getattr(self._reads, "block", None)
        return self.snapshot_block() if block is None else block

    def _call(self, fn, block: int | None = None):
        try:
            return fn.call(block_identifier=self._read_block() if block is None else block)
        except Exception as e:
            raise ChainReadUnavailable("Required contract state is unavailable; retry shortly") from e

    def snapshot(self, project_key: str, minimum: int = 0) -> dict:
        block = self.snapshot_block(minimum)
        try:
            pk = _b32(project_key)
            project, atts, rets = self._batch_calls([self.c.functions.getProject(pk), self.c.functions.getAttestations(pk),
                                                     self.c.functions.getRetirements(pk)], block)
            attestations = self._attestation_dicts(atts)
            with self.read_at(block):
                if len(attestations) < self.journal.attestation_count(self._read_scope, project_key):
                    attestations = self._visible_attestations(project_key)  # rare: wait for our own confirmed append
                else:
                    self.journal.remember_attestations(self._read_scope, project_key, len(attestations))
            return {"observedBlock": block, "project": self._project_dict(project),
                    "attestations": attestations, "retirements": self._retirement_dicts(rets)}
        except Exception as e:
            raise ChainReadUnavailable("Chain snapshot is unavailable; retry shortly") from e

    def _batch_calls(self, fns: list, block: int) -> list:
        """eth_calls pinned to `block`, sent as small JSON-RPC batches; returns each decoded single output.

        State at a fixed block is immutable, so results are cached per (calldata, block). Batches stay
        small and are retried with back-off when the RPC rate-limits (-32007 / HTTP 429). Any other
        error, or an incomplete response, fails closed."""
        datas = [fn._encode_transaction_data() for fn in fns]
        with self._cache_lock:
            raw = {d: self._call_cache.get((d, block)) for d in datas}
        missing = list(dict.fromkeys(d for d in datas if raw[d] is None))
        try:
            for i in range(0, len(missing), self.BATCH_SIZE):
                chunk = missing[i : i + self.BATCH_SIZE]
                calls = [("eth_call", [{"to": self.address, "data": d}, hex(block)]) for d in chunk]
                for attempt in range(self.RATE_LIMIT_RETRIES + 1):
                    responses = self.w3.provider.make_batch_request(calls)
                    if not isinstance(responses, list):
                        responses = [responses]  # whole-batch error object (e.g. HTTP 429)
                    limited = any(r.get("error", {}).get("code") == -32007 for r in responses if isinstance(r, dict))
                    if not limited:
                        break
                    if attempt == self.RATE_LIMIT_RETRIES:
                        raise ValueError("RPC rate limit persisted")
                    time.sleep(0.6 * (attempt + 1))
                if len(responses) != len(chunk) or any("error" in r for r in responses):
                    raise ValueError("incomplete batch response")
                for d, r in zip(chunk, sorted(responses, key=lambda r: r["id"])):
                    raw[d] = r["result"]
            with self._cache_lock:
                if len(self._call_cache) > 4096:
                    self._call_cache.clear()
                self._call_cache.update({(d, block): raw[d] for d in missing})
            return [self.w3.codec.decode(get_abi_output_types(fn.abi), bytes.fromhex(raw[d][2:]))[0] for fn, d in zip(fns, datas)]
        except Exception as e:
            raise ChainReadUnavailable("Required contract state is unavailable; retry shortly") from e

    def project(self, project_key: str) -> dict:
        return self._project_dict(self._call(self.c.functions.getProject(_b32(project_key))))

    def projects(self, project_keys: list[str]) -> dict[str, dict]:
        """Many getProject reads in ONE JSON-RPC batch per 50 keys, all pinned to the same block.
        One round trip instead of one per project (a 20-row registry page: ~18 s -> well under 1 s)."""
        block = self._read_block()
        out = {}
        for i in range(0, len(project_keys), 50):
            keys = project_keys[i : i + 50]
            results = self._batch_calls([self.c.functions.getProject(_b32(k)) for k in keys], block)
            out.update({k: self._project_dict(p) for k, p in zip(keys, results)})
        return out

    @staticmethod
    def _project_dict(p) -> dict:
        return {
            "developer": Web3.to_checksum_address(p[0]), "claimHash": _hex(p[1]), "vintageYear": p[2], "status": STATUS[p[3]],
            "claimedCredits": p[4], "issued": p[5], "retired": p[6], "cellCount": p[7], "registeredAt": p[8],
            "cellsRoot": _hex(p[9]), "cellsHash": _hex(p[10]), "lastCell": p[11],
            "registeredBlock": p[12],
        }

    def check_cells(self, cells: list[int], vintage: int) -> dict[int, str]:
        """Cells already held by another project for this vintage → owner projectKey."""
        out = {}
        block = self._read_block()
        for i in range(0, len(cells), 2000):
            chunk = cells[i : i + 2000]
            owners = self._call(self.c.functions.checkCells(chunk, vintage), block)
            out.update({c: _hex(o) for c, o in zip(chunk, owners) if _hex(o) != ZERO32})
        return out

    def attestations(self, project_key: str) -> list[dict]:
        return self._attestation_dicts(self._call(self.c.functions.getAttestations(_b32(project_key))))

    def retirements(self, project_key: str) -> list[dict]:
        return self._retirement_dicts(self._call(self.c.functions.getRetirements(_b32(project_key))))

    @staticmethod
    def _attestation_dicts(rows) -> list[dict]:
        return [{"scoreBps": a[0], "evidenceHash": _hex(a[1]), "modelVersion": a[2],
                 "verifier": Web3.to_checksum_address(a[3]), "timestamp": a[4]} for a in rows]

    @staticmethod
    def _retirement_dicts(rows) -> list[dict]:
        return [{"serialStart": r[0], "amount": r[1], "from": Web3.to_checksum_address(r[2]),
                 "beneficiary": r[3], "timestamp": r[4]} for r in rows]

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
        # Persist before clearing uncertainty: restarts must not read behind this receipt.
        self.journal.relay_confirm(self._scope, self._read_scope, row, receipt)
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
        block = self.snapshot_block()
        fields = {"from": self.account.address, "chainId": self.chain_id}
        # Gas estimation is a state read. Supply gas explicitly so build_transaction
        # cannot silently estimate against an older load-balanced node's latest state.
        gas = fn.estimate_gas({"from": self.account.address}, block_identifier=block)
        nonce = max(self.w3.eth.get_transaction_count(self.account.address, "pending"),
                    self.w3.eth.get_transaction_count(self.account.address, block))
        tx = fn.build_transaction({**fields, "nonce": nonce, "gas": gas + gas // 5})
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
        if state["status"] == "cancelled":
            raise RegistrationCancelled("registration was cancelled; its identity cannot be reused")
        if state["status"] == "none":
            first = cells[: self.batch]
            txs.append({"step": "registerProject", "tx": self._send(self.c.functions.registerProject(
                pk, _b32(claim_hash), Web3.to_checksum_address(developer), vintage, credits, _b32(cells_root(cells)), first, signature))})
            state = self._await_project(project_key, lambda s: s["status"] != "none", "pending")
        if state["status"] == "pending":
            owners = self.check_cells(cells, vintage)
            todo = [c for c in cells if owners.get(c) != project_key]
            for i in range(0, len(todo), self.batch):  # re-adding owned cells is a no-op on-chain
                txs.append({"step": "addCells", "tx": self._send(self.c.functions.addCells(pk, todo[i : i + self.batch]))})
            # finalize's gas estimate simulates against the node's view; on a lagging node the last
            # batch is missing, the cell hash mismatches and the estimate reverts. Wait it out first.
            self._await_project(project_key, lambda s: s["cellCount"] >= len(cells) and s["cellsHash"] == s["cellsRoot"],
                                "all cells added")
            txs.append({"step": "finalizeRegistration", "tx": self._send(self.c.functions.finalizeRegistration(pk))})
        # Never report success on the strength of a possibly stale read: require the chain to say so.
        self._await_project(project_key, lambda s: s["status"] == "registered", "registered")

    def _await_project(self, project_key: str, ok, want: str) -> dict:
        """Re-read until our confirmed writes are visible. Load-balanced public RPCs can answer
        from a node a block or two behind; a stale read must never skip steps or fake success."""
        for attempt in range(self.read_attempts):
            state = self.project(project_key)
            if ok(state):
                return state
            time.sleep(self.read_retry_delay)
        raise RuntimeError(f"on-chain status did not reach {want!r} (RPC lagging?); retrying resumes safely")

    @_serialized
    def post_attestation(self, project_key, score_bps, evidence_hash, model_version) -> dict | None:
        """Append an attestation unless the latest one already says exactly this (retry-safe)."""
        recovered = self._reconcile(project_key)
        existing = self._visible_attestations(project_key)
        latest = (existing or [None])[-1]
        if latest and (latest["scoreBps"], latest["evidenceHash"], latest["modelVersion"]) == (score_bps, evidence_hash, model_version):
            return next((t for t in recovered if t["step"] == "postAttestation"), None)
        tx = self._send(self.c.functions.postAttestation(_b32(project_key), score_bps, _b32(evidence_hash), model_version))
        self.journal.remember_attestations(self._read_scope, project_key, len(existing) + 1)
        self._visible_attestations(project_key)
        return {"step": "postAttestation", "tx": tx}

    def _visible_attestations(self, project_key: str) -> list[dict]:
        minimum = self.journal.attestation_count(self._read_scope, project_key)
        for attempt in range(self.read_attempts):
            values = self.attestations(project_key)
            if len(values) >= minimum:
                self.journal.remember_attestations(self._read_scope, project_key, len(values))
                return values
            if attempt + 1 < self.read_attempts:
                time.sleep(self.read_retry_delay)
        raise ChainReadUnavailable("Confirmed attestations are not visible; retry shortly")
