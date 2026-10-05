"""Guards docs/claim-hash-vectors.json: the browser verifier and third parties rely on it."""
import json
from pathlib import Path

from app import canonical

VECTORS = json.loads((Path(__file__).resolve().parents[2] / "docs" / "claim-hash-vectors.json").read_text(encoding="utf-8"))["vectors"]


def test_vectors_match_implementation():
    for v in VECTORS:
        assert canonical.canonical_bytes(v["claim"]).decode() == v["canonical"], v["name"]
        assert canonical.claim_hash(v["claim"]) == v["claimHash"], v["name"]
        assert canonical.project_key(v["claim"]["projectId"]) == v["projectKey"], v["name"]
