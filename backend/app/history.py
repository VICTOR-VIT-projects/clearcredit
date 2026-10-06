"""Frozen, offline project issuance context; no web access or user-supplied histories."""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

from .canonical import _dumps, keccak

SNAPSHOT = Path(__file__).resolve().parents[2] / "data/cache/history/issuance-v1.json"
MIN_VINTAGES = 3
JUMP_MULTIPLIER = 3.0
PROJECT_ID = re.compile(r"^(VCS|GS)[0-9]+$")


def read_issuance(path: Path, project_ids: set[str]) -> dict[str, dict[int, int]]:
    totals = defaultdict(lambda: defaultdict(Decimal))
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid = row.get("project_id")
            if pid not in project_ids or row.get("transaction_type") != "issuance":
                continue
            try:
                vintage, quantity = Decimal(row["vintage"]), Decimal(row["quantity"])
                if not vintage.is_finite() or vintage != vintage.to_integral_value() or not 2000 <= vintage <= 2100:
                    continue
                if not quantity.is_finite() or quantity <= 0 or quantity != quantity.to_integral_value():
                    continue
            except (InvalidOperation, KeyError):
                continue
            totals[pid][int(vintage)] += quantity
    return {p: {y: int(q) for y, q in sorted(years.items())} for p, years in sorted(totals.items())}


class HistoryError(ValueError):
    pass


def load_snapshot(path: Path = SNAPSHOT) -> dict | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    content = {k: v for k, v in data.items() if k != "snapshotHash"}
    if data["snapshotHash"] != "0x" + keccak(_dumps(content).encode()).hex():
        raise HistoryError("issuance history snapshot hash mismatch")
    return data


def for_claim(claim: dict, snapshot: dict | None = None) -> dict:
    # A new submission ID may cite its published registry ID. This is context, not
    # authenticated registry affiliation or proof that historical boundaries match.
    source_id = (claim.get("sourceRegistry") or "").split()
    pid = source_id[-1] if source_id and PROJECT_ID.fullmatch(source_id[-1]) else claim.get("projectId", "")
    snapshot = load_snapshot() if snapshot is None else snapshot
    records = snapshot.get("records", {}).get(pid, {}) if snapshot and PROJECT_ID.fullmatch(pid) else {}
    earlier = {y: q for y, q in records.items() if int(y) < claim["vintageYear"] and q > 0}
    enough = len(earlier) >= MIN_VINTAGES
    return {
        "status": "available" if enough else "no_history",
        "projectId": pid,
        "priorVintages": dict(sorted(earlier.items())),
        "vintageCount": len(earlier),
        "medianCredits": float(median(earlier.values())) if enough else None,
        "snapshotHash": snapshot["snapshotHash"] if snapshot else None,
        "source": snapshot["source"] if snapshot else None,
        "limitation": "Past issuance is normalized with the current boundary area; historical boundaries and methodology changes are unavailable. Registry affiliation is not authenticated.",
    }
