import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("demo_runner", ROOT / "scripts/demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_demo_replaces_inherited_public_settings_and_uses_fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAIN_RPC_URL", "https://example.invalid")
    monkeypatch.setenv("ATTACH_ADDRESS", "old-address")
    monkeypatch.setenv("REGISTRY_ADDRESS", "old-address")
    env = demo.environment(tmp_path, 18545, 18000, 15173)
    assert env["CHAIN_RPC_URL"] == env["CLEARCREDIT_LOCAL_RPC_URL"] == "http://127.0.0.1:18545"
    assert env["VITE_LOCAL_RPC_URL"] == env["CHAIN_RPC_URL"]
    assert env["VITE_CHAIN_ID"] == "31337"
    assert env["REGISTRY_ADDRESS"] == env["ATTACH_ADDRESS"] == ""
    assert env["CLEARCREDIT_NO_ENV"] == env["CLEARCREDIT_OFFLINE_EVIDENCE"] == "1"
    assert Path(env["CLEARCREDIT_DB"]).parent == tmp_path


def test_demo_rejects_occupied_ports_before_starting_children():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        with pytest.raises(RuntimeError, match="occupied"):
            demo.check_ports([port, 18000 if port != 18000 else 18001, 15173])
        assert demo.main(["--node-port", str(port), "--api-port", "18000", "--ui-port", "15173", "--smoke"]) == 1


def test_demo_cleanup_stops_owned_process(tmp_path):
    manager = demo.Processes(tmp_path, dict(os.environ))
    child = manager.start("owned", [sys.executable, "-c", "import time; time.sleep(120)"], tmp_path)
    try:
        assert child.poll() is None
    finally:
        manager.close()
    assert child.poll() is not None


def test_interrupt_during_startup_runs_cleanup(monkeypatch, tmp_path):
    closed = []
    monkeypatch.setattr(demo, "check_ports", lambda _: None)
    monkeypatch.setattr(demo.tempfile, "mkdtemp", lambda **_: str(tmp_path))
    class Interrupted:
        def __init__(self, *args):
            pass
        def start(self, *args):
            raise KeyboardInterrupt
        def close(self):
            closed.append(True)
    monkeypatch.setattr(demo, "Processes", Interrupted)
    assert demo.main(["--smoke"]) == 0
    assert closed == [True]


def test_seed_returns_failure_for_skipped_claim_and_writes_requested_report(monkeypatch, tmp_path):
    from scripts import seed
    monkeypatch.setattr(seed, "load_claims", lambda _: [{"projectId": "UNKNOWN", "developer": "0x" + "33" * 20}])
    report = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["seed", "--report", str(report)])
    assert seed.main() == 1
    assert "NO_DEMO_SIGNER" in report.read_text()
