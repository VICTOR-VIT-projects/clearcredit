"""Bounded project event reads; no partial success after RPC failure."""
from web3 import Web3

from .chain import ChainReadUnavailable, _hex

MAX_BLOCKS = 10_000
MAX_EVENTS = 1_000
MAX_CALLS = 128
PROJECT_EVENTS = ("ProjectRegistered", "CellsAdded", "ProjectFinalized", "CellListCommitted",
                  "PendingCancelled", "AttestationPosted", "CreditsIssued", "Retired")


def history(chain, project_key: str, start: int, end: int) -> list[dict]:
    if start < 0 or end < start or end - start + 1 > MAX_BLOCKS:
        raise ValueError(f"Choose an ordered range of at most {MAX_BLOCKS} blocks")
    decoders = {}
    for name in PROJECT_EVENTS:
        event = getattr(chain.c.events, name)()
        abi = event.abi
        signature = abi["name"] + "(" + ",".join(i["type"] for i in abi["inputs"]) + ")"
        decoders[bytes(Web3.keccak(text=signature))] = event
    calls, entries = 0, []

    def read(lo, hi):
        nonlocal calls
        calls += 1
        if calls > MAX_CALLS:
            raise ChainReadUnavailable("Event RPC request budget exceeded; choose a smaller range")
        try:
            values = chain.w3.eth.get_logs({"address": chain.address, "fromBlock": lo, "toBlock": hi,
                                           "topics": [None, project_key]})
        except Exception as e:
            if lo == hi:
                raise ChainReadUnavailable("Event block unavailable; retry or use a smaller range") from e
            middle = (lo + hi) // 2
            read(lo, middle)
            read(middle + 1, hi)
            return
        entries.extend(values)
        if len(entries) > MAX_EVENTS:
            raise ChainReadUnavailable("Too many events; choose a smaller range")

    try:
        # Explicit endpoints must exist; never silently fall back to latest.
        chain.w3.eth.get_block(end)
        for lo in range(start, end + 1, 2000):
            read(lo, min(lo + 1999, end))
        output, seen = [], set()
        for log in sorted(entries, key=lambda x: (x["blockNumber"], x["logIndex"])):
            identity = (bytes(log["transactionHash"]), log["logIndex"])
            if identity in seen:
                continue
            seen.add(identity)
            decoder = decoders.get(bytes(log["topics"][0]))
            if decoder is None:
                continue
            event = decoder.process_log(log)
            args = {k: _hex(v) if isinstance(v, bytes) else str(v) if isinstance(v, int) and abs(v) > 2**53 - 1 else v
                    for k, v in event["args"].items()}
            output.append({"event": event["event"], "blockNumber": log["blockNumber"], "logIndex": log["logIndex"],
                           "transactionHash": _hex(log["transactionHash"]), "url": chain.tx_url(_hex(log["transactionHash"])),
                           "args": args})
        return output
    except ChainReadUnavailable:
        raise
    except Exception as e:
        raise ChainReadUnavailable("Required event history unavailable; retry shortly") from e


def timestamp_range(chain, timestamp: int, start: int, end: int) -> tuple[int, int]:
    """Binary search all blocks with the record's timestamp, without scanning its lifetime."""
    cache = {}
    def value(block):
        if block not in cache:
            try:
                header = chain.w3.eth.get_block(block)
                if header["number"] != block:
                    raise ValueError("Wrong block")
                cache[block] = header["timestamp"]
            except Exception as e:
                raise ChainReadUnavailable("Retirement block unavailable; retry shortly") from e
        return cache[block]
    def bound(strict):
        lo, hi = start, end + 1
        while lo < hi:
            mid = (lo + hi) // 2
            current = value(mid)
            if current > timestamp or (not strict and current == timestamp):
                hi = mid
            else:
                lo = mid + 1
        return lo
    first, after = bound(False), bound(True)
    if first == after or after - first > MAX_BLOCKS:
        raise ChainReadUnavailable("Retirement timestamp cannot be resolved to a bounded block range")
    return first, after - 1
