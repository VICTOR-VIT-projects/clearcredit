"""Precompute and cache satellite evidence for every claim file (resumable: cached ones are skipped).

    python -m scripts.precompute_evidence [data/claims/real data/synthetic ...] [--workers 3]
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app import satellite

ROOT = Path(__file__).resolve().parents[2]


def run(path: Path) -> str:
    claim = json.loads(path.read_text(encoding="utf-8"))
    claim = claim.get("claim", claim)
    if satellite.get_evidence(claim["boundary"], live=False):
        return f"cached  {claim['projectId']}"
    t = time.time()
    e = satellite.get_evidence(claim["boundary"], live=True)
    years = e["ndvi"]["meanNdviByYear"]
    return f"fetched {claim['projectId']} in {time.time() - t:.0f}s (forest2000 {e['forestLoss']['forest2000Ha']:,.0f} ha, NDVI years {len(years)})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*", default=[str(ROOT / "data" / "claims" / "real")])
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    files = sorted(f for d in args.dirs for f in Path(d).glob("*.json"))
    print(f"{len(files)} claim files, cache: {satellite.CACHE_DIR}", flush=True)
    failed = []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(run, f): f for f in files}
        for fut in as_completed(futures):
            try:
                print(fut.result(), flush=True)
            except Exception as e:  # keep going; rerun later to retry just the failures
                failed.append(futures[fut].stem)
                print(f"FAILED  {futures[fut].stem}: {type(e).__name__}: {e}", flush=True)
    print(f"done; {len(failed)} failed: {failed}")


if __name__ == "__main__":
    main()
