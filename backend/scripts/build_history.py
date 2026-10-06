"""Freeze issuance history from an existing local CSV. Never downloads data.

    python -m scripts.build_history

Changing the snapshot requires a new evidence version and cached evaluation run.
"""
import hashlib
import json
from pathlib import Path

from app import canonical, history

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "data/probes/offsets-db-csv/credits.csv"


def main():
    if not CSV.exists():
        raise SystemExit("No local credits.csv; no history snapshot built. Scoring reports no history without a snapshot.")
    ids = {p.stem for p in (ROOT / "data/claims/real").glob("*.json")}
    digest = hashlib.sha256()
    with CSV.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    data = {
        "source": "Berkeley/CarbonPlan OffsetsDB local credits.csv, same source as real seed issuance",
        "sourceSha256": digest.hexdigest(),
        "records": history.read_issuance(CSV, ids),
    }
    data["snapshotHash"] = "0x" + canonical.keccak(canonical._dumps(data).encode()).hex()
    history.SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    history.SNAPSHOT.write_bytes(json.dumps(data, indent=2).encode("utf-8"))
    print(f"Frozen history for {len(data['records'])} projects: {data['snapshotHash']}")


if __name__ == "__main__":
    main()
