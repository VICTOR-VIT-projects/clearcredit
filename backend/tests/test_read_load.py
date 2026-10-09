"""Read-side load control for rate-limited public RPCs: small batches, back-off, per-block cache."""
import json
import threading
from pathlib import Path

import pytest
from eth_abi import encode
from web3 import Web3

from app import chain as chain_module
from app.chain import Chain, ChainReadUnavailable

ABI = json.loads((Path(__file__).resolve().parents[1] / "app" / "abi.json").read_text())
PROJECT = ("0x" + "11" * 20, b"\x22" * 32, 2023, 2, 1000, 0, 0, 5, 1, b"\x33" * 32, b"\x33" * 32, 9, 7)
TYPES = ["(address,bytes32,uint16,uint8,uint64,uint64,uint64,uint32,uint64,bytes32,bytes32,uint64,uint64)"]


class FakeProvider:
    """Answers every eth_call with the same encoded project; rate-limits the first `limited` batches."""

    def __init__(self, limited=1):
        self.batches, self.limited = [], limited

    def make_batch_request(self, calls):
        self.batches.append(len(calls))
        if self.limited:
            self.limited -= 1
            return [{"jsonrpc": "2.0", "id": i, "error": {"code": -32007, "message": "25/second request limit reached"}}
                    for i in range(len(calls))]
        result = "0x" + encode(TYPES, [PROJECT]).hex()
        return [{"jsonrpc": "2.0", "id": i, "result": result} for i in range(len(calls))]


def make_chain(provider):
    c = Chain.__new__(Chain)
    c.w3 = Web3()
    c.w3.provider = provider
    c.address = Web3.to_checksum_address("0x" + "44" * 20)
    c.c = c.w3.eth.contract(address=c.address, abi=ABI)
    c._call_cache, c._cache_lock = {}, threading.Lock()
    return c


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(chain_module.time, "sleep", lambda *_: None)


def test_rate_limited_batch_is_retried_then_cached_per_block():
    provider = FakeProvider(limited=1)
    ch = make_chain(provider)
    keys = ["0x" + f"{i:064x}" for i in range(25)]
    fns = [ch.c.functions.getProject(bytes.fromhex(k[2:])) for k in keys]
    out = ch._batch_calls(fns, 100)
    assert len(out) == 25 and out[0][3] == 2  # status field decoded
    assert max(provider.batches) <= Chain.BATCH_SIZE  # never more than BATCH_SIZE calls per request
    calls_before = len(provider.batches)
    assert ch._batch_calls(fns, 100) == out  # same block: served from cache
    assert len(provider.batches) == calls_before
    ch._batch_calls(fns[:1], 101)  # different block: real read
    assert len(provider.batches) == calls_before + 1


def test_persistent_rate_limit_fails_closed():
    ch = make_chain(FakeProvider(limited=99))
    with pytest.raises(ChainReadUnavailable):
        ch._batch_calls([ch.c.functions.getProject(b"\x01" * 32)], 100)
