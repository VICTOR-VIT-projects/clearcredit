import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from conftest import make_claim, sign


def test_live_request_is_not_reclaimed_even_after_timestamp_expiry(db_path):
    store = Store(db_path)
    assert store.idem_begin('key', 'body')[0] == 'new'
    store.db.execute('UPDATE idempotency SET lease_until = 0')
    assert store.idem_begin('key', 'body')[0] == 'in_flight'
    assert store.idem_begin('key', 'different')[0] == 'mismatch'


def test_restart_reclaims_expired_lease_but_not_unexpired_one(db_path):
    first = Store(db_path)
    first.idem_begin('expired', 'body')
    first.idem_begin('live', 'body')
    first.db.execute("UPDATE idempotency SET lease_until = 0 WHERE key = 'expired'")
    restarted = Store(db_path)
    assert restarted.idem_begin('live', 'body')[0] == 'in_flight'
    assert restarted.idem_begin('expired', 'different')[0] == 'mismatch'
    state, row = restarted.idem_begin('expired', 'body')
    assert state == 'new' and row is not None
    assert restarted.idem_begin('expired', 'body')[0] == 'in_flight'


def test_old_database_migrates_and_abandoned_row_is_recoverable(db_path):
    db = sqlite3.connect(db_path)
    db.execute('CREATE TABLE idempotency (key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, status_code INTEGER, response TEXT, created_at TEXT NOT NULL)')
    db.execute("INSERT INTO idempotency VALUES ('old', 'body', NULL, NULL, '2026-01-01')")
    db.commit()
    db.close()
    store = Store(db_path)
    assert store.idem_begin('old', 'body')[0] == 'new'


def test_crash_after_insertion_resumes_same_body_after_lease(db_path):
    store = Store(db_path)
    client = TestClient(create_app(store, chain=None, live_evidence=False))
    body = {'claim': make_claim(), 'signature': sign(None)}
    assert client.post('/claims', json=body, headers={'Idempotency-Key': 'crash'}).status_code == 201
    # Model a killed worker between insertion and idem_finish, retaining its request hash.
    store.db.execute("UPDATE idempotency SET status_code = NULL, response = NULL, lease_until = 0")
    restarted = TestClient(create_app(Store(db_path), chain=None, live_evidence=False))
    response = restarted.post('/claims', json=body, headers={'Idempotency-Key': 'crash'})
    assert response.status_code == 201
    assert restarted.get('/registry').json()['total'] == 1
