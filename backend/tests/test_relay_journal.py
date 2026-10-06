"""Uncertain broadcasts must retain their nonce and survive a relayer restart."""
import threading
from types import SimpleNamespace

import pytest
from web3 import Web3
from web3.exceptions import TimeExhausted

from app.chain import Chain
from app.store import Store


class FakeEth:
    def __init__(self):
        self.sent = []
        self.receipts = {}
        self.nonce_reads = 0

    def get_transaction_count(self, *_):
        self.nonce_reads += 1
        return len(set(self.sent))

    def send_raw_transaction(self, raw):
        h = Web3.keccak(raw)
        self.sent.append(bytes(raw))
        return h

    def wait_for_transaction_receipt(self, h, **_):
        if bytes(h) not in self.receipts:
            raise TimeExhausted("still pending")
        return self.receipts[bytes(h)]

    def get_transaction_receipt(self, h):
        return self.wait_for_transaction_receipt(h)


class FakeFunction:
    fn_name = "postAttestation"

    def __init__(self, data="0x1234"):
        self.data = data

    def _encode_transaction_data(self):
        return self.data

    def build_transaction(self, fields):
        return {**fields, "data": self.data}


def relayer(eth, journal):
    chain = Chain.__new__(Chain)
    chain.w3 = SimpleNamespace(eth=eth)
    chain.account = SimpleNamespace(address="0x" + "11" * 20,
        sign_transaction=lambda tx: SimpleNamespace(raw_transaction=str(tx).encode()))
    chain.chain_id = 31337
    chain.address = "0x" + "22" * 20
    chain._lock = threading.RLock()
    chain.journal = journal
    return chain


def test_timeout_then_restart_reuses_identical_transaction(db_path):
    eth = FakeEth()
    first = relayer(eth, Store(db_path))
    with pytest.raises(TimeExhausted):
        first._send(FakeFunction())
    raw = eth.sent[0]
    second = relayer(eth, Store(db_path))
    with pytest.raises(TimeExhausted):
        second._send(FakeFunction())
    assert eth.nonce_reads == 1
    assert set(eth.sent) == {raw}
    h = Web3.keccak(raw)
    eth.receipts[bytes(h)] = {"status": 1}
    assert second._send(FakeFunction()) == "0x" + bytes(h).hex()
    assert len(set(eth.sent)) == 1


def test_unresolved_send_blocks_a_different_operation(db_path):
    eth = FakeEth()
    chain = relayer(eth, Store(db_path))
    with pytest.raises(TimeExhausted):
        chain._send(FakeFunction())
    with pytest.raises(TimeExhausted):
        chain._send(FakeFunction("0x5678"))
    assert eth.nonce_reads == 1
    assert len(set(eth.sent)) == 1
