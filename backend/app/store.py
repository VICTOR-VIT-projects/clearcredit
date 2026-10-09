"""SQLite persistence: claims and idempotency records (stdlib sqlite3, no ORM)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.environ.get("CLEARCREDIT_DB", str(Path(__file__).resolve().parents[1] / "clearcredit.sqlite3"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    project_id   TEXT PRIMARY KEY,
    project_key  TEXT NOT NULL UNIQUE,
    claim_hash   TEXT NOT NULL UNIQUE,
    vintage_year INTEGER NOT NULL,
    claim_json   TEXT NOT NULL,
    signature    TEXT,
    cells_json   TEXT NOT NULL,
    result_json  TEXT NOT NULL,          -- area, overlaps, score, evidence summary
    status       TEXT NOT NULL,          -- relaying | registered | relay_failed | offline
    txs_json     TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS claims_vintage ON claims (vintage_year);
CREATE TABLE IF NOT EXISTS idempotency (
    key          TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    status_code  INTEGER,                -- NULL while the first request is still in flight
    response     TEXT,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relay_pending (
    scope TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    project_key TEXT,
    step TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    raw_tx TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chain_heads (
    scope TEXT PRIMARY KEY,
    block_number INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS attestation_counts (
    scope TEXT NOT NULL,
    project_key TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (scope, project_key)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str = DB_PATH):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.admission_lock = threading.Lock()
        # Additive migration for existing databases; do not discard request hashes.
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(idempotency)")}
        if "lease_until" not in columns:
            self.db.execute("ALTER TABLE idempotency ADD COLUMN lease_until REAL NOT NULL DEFAULT 0")
        self.lease_seconds = 300
        self._active_idempotency: set[str] = set()

    def relay_pending(self, scope: str) -> dict | None:
        row = self.db.execute("SELECT * FROM relay_pending WHERE scope = ?", (scope,)).fetchone()
        return dict(row) if row else None

    def relay_save(self, scope: str, operation: str, project_key: str | None, step: str, tx_hash: str, raw_tx: str) -> None:
        # Durable before broadcast: raw_tx is public signed calldata, never a private key.
        self.db.execute("INSERT INTO relay_pending VALUES (?, ?, ?, ?, ?, ?)",
                        (scope, operation, project_key, step, tx_hash, raw_tx))

    def relay_clear(self, scope: str) -> None:
        self.db.execute("DELETE FROM relay_pending WHERE scope = ?", (scope,))

    def relay_confirm(self, scope: str, read_scope: str, row: dict, receipt: dict) -> None:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.advance_chain_head(read_scope, receipt["blockNumber"])
                if receipt["status"] == 1 and row["step"] == "postAttestation":
                    self.remember_attestations(read_scope, row["project_key"], self.attestation_count(read_scope, row["project_key"]) + 1)
                self.relay_clear(scope)
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def chain_head(self, scope: str) -> int:
        row = self.db.execute("SELECT block_number FROM chain_heads WHERE scope = ?", (scope,)).fetchone()
        return row[0] if row else 0

    def advance_chain_head(self, scope: str, block: int) -> None:
        self.db.execute("INSERT INTO chain_heads VALUES (?, ?) ON CONFLICT(scope) DO UPDATE "
                        "SET block_number = MAX(block_number, excluded.block_number)", (scope, block))

    def attestation_count(self, scope: str, project_key: str) -> int:
        row = self.db.execute("SELECT count FROM attestation_counts WHERE scope = ? AND project_key = ?", (scope, project_key)).fetchone()
        return row[0] if row else 0

    def remember_attestations(self, scope: str, project_key: str, count: int) -> None:
        self.db.execute("INSERT INTO attestation_counts VALUES (?, ?, ?) ON CONFLICT(scope, project_key) "
                        "DO UPDATE SET count = MAX(count, excluded.count)", (scope, project_key, count))

    # ------------------------------------------------------------ idempotency

    def idem_begin(self, key: str, request_hash: str) -> tuple[str, sqlite3.Row | None]:
        """Returns ('new', None) | ('replay', row) | ('in_flight', row) | ('mismatch', row)."""
        with self.lock:
            row = self.db.execute("SELECT * FROM idempotency WHERE key = ?", (key,)).fetchone()
            if row is None:
                self.db.execute("INSERT INTO idempotency (key, request_hash, created_at, lease_until) VALUES (?, ?, ?, ?)",
                                (key, request_hash, _now(), time.time() + self.lease_seconds))
                self._active_idempotency.add(key)
                return "new", None
            if row["request_hash"] != request_hash:
                return "mismatch", row
            if row["status_code"] is None and row["lease_until"] <= time.time() and key not in self._active_idempotency:
                self.db.execute("UPDATE idempotency SET lease_until = ? WHERE key = ?", (time.time() + self.lease_seconds, key))
                self._active_idempotency.add(key)
                return "new", row  # recovered request: safely resume an already inserted claim
            return ("in_flight", row) if row["status_code"] is None else ("replay", row)

    def idem_finish(self, key: str, status_code: int, response: dict) -> None:
        with self.lock:
            self.db.execute("UPDATE idempotency SET status_code = ?, response = ? WHERE key = ?", (status_code, json.dumps(response), key))
            self._active_idempotency.discard(key)

    def idem_retry(self, key: str) -> None:
        """Invalidate a false cached success while retaining its original request binding."""
        with self.lock:
            self.db.execute("UPDATE idempotency SET status_code = NULL, response = NULL, lease_until = 0 WHERE key = ?", (key,))

    def idem_abort(self, key: str) -> None:
        """Forget an in-flight key after an unexpected server error so the client can retry."""
        with self.lock:
            self.db.execute("DELETE FROM idempotency WHERE key = ? AND status_code IS NULL", (key,))
            self._active_idempotency.discard(key)

    # ------------------------------------------------------------ claims

    def insert_claim(self, *, project_id, project_key, claim_hash, vintage_year, claim, signature, cells, result, status) -> None:
        self.db.execute(
            "INSERT INTO claims (project_id, project_key, claim_hash, vintage_year, claim_json, signature, cells_json, result_json, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, project_key, claim_hash, vintage_year, json.dumps(claim), signature, json.dumps(cells), json.dumps(result), status, _now()),
        )

    def update_claim(self, project_id: str, *, status: str | None = None, txs: list | None = None, result: dict | None = None) -> None:
        if status is not None:
            self.db.execute("UPDATE claims SET status = ? WHERE project_id = ?", (status, project_id))
        if txs is not None:
            self.db.execute("UPDATE claims SET txs_json = ? WHERE project_id = ?", (json.dumps(txs), project_id))
        if result is not None:
            self.db.execute("UPDATE claims SET result_json = ? WHERE project_id = ?", (json.dumps(result), project_id))

    def get(self, project_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM claims WHERE project_id = ?", (project_id,)).fetchone()
        return _row(row) if row else None

    def find(self, *, claim_hash: str | None = None, project_key: str | None = None) -> dict | None:
        col, val = ("claim_hash", claim_hash) if claim_hash else ("project_key", project_key)
        row = self.db.execute(f"SELECT * FROM claims WHERE {col} = ?", (val,)).fetchone()
        return _row(row) if row else None

    def same_vintage(self, vintage_year: int, exclude: str | None = None) -> list[dict]:
        rows = self.db.execute("SELECT * FROM claims WHERE vintage_year = ? AND project_id IS NOT ?", (vintage_year, exclude)).fetchall()
        return [_row(r) for r in rows]

    def page(self, offset: int, limit: int) -> tuple[int, list[dict]]:
        total = self.db.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        rows = self.db.execute("SELECT * FROM claims ORDER BY created_at DESC, project_id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return total, [_row(r) for r in rows]


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("claim_json", "cells_json", "result_json", "txs_json"):
        d[k.removesuffix("_json")] = json.loads(d.pop(k))
    return d
