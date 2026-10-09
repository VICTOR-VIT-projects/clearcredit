"""Disposable local demo: existing venv/dependencies required; no environment-file reads.

Run from repo root: backend/.venv/Scripts/python.exe scripts/demo.py [--smoke]
Ctrl+C stops only this runner's process trees. Logs and the fresh DB stay in a temp folder.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
# Hardhat's public local account #0; never connect this runner to a public chain.
LOCAL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def environment(workspace: Path, node_port: int, api_port: int, ui_port: int) -> dict:
    rpc, api = f"http://127.0.0.1:{node_port}", f"http://127.0.0.1:{api_port}"
    return {**os.environ, "CLEARCREDIT_NO_ENV": "1", "CLEARCREDIT_OFFLINE_EVIDENCE": "1",
            "CHAIN_RPC_URL": rpc, "CLEARCREDIT_LOCAL_RPC_URL": rpc, "BASE_SEPOLIA_RPC_URL": rpc,
            "DEPLOYER_PRIVATE_KEY": LOCAL_KEY, "ATTACH_ADDRESS": "", "REGISTRY_ADDRESS": "",
            "CELL_RESOLUTION": "8", "ISSUE_THRESHOLD_BPS": "6000",
            "DEPLOYMENT_FILE": str(workspace / "deployment.json"),
            "CLEARCREDIT_DB": str(workspace / "demo.sqlite3"), "ADMIN_TOKEN": "local-demo-only",
            "EVIDENCE_CACHE": str(ROOT / "data/cache/evidence"),
            "CORS_ORIGINS": f"http://127.0.0.1:{ui_port},http://localhost:{ui_port}",
            "VITE_API_URL": api, "VITE_CHAIN_ID": "31337", "VITE_LOCAL_RPC_URL": rpc,
            "NO_PROXY": "localhost,127.0.0.1,::1"}


def check_ports(ports: list[int]) -> None:
    if len(set(ports)) != len(ports) or any(p < 1024 or p > 65535 for p in ports):
        raise RuntimeError("Choose three distinct ports in 1024..65535")
    for port in ports:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError as e:
                raise RuntimeError(f"Local port {port} is occupied; choose another port. No existing process was stopped.") from e


class Processes:
    def __init__(self, workspace: Path, env: dict):
        self.workspace, self.env, self.children, self.logs = workspace, env, [], []

    def start(self, name: str, args: list[str], cwd: Path):
        log = (self.workspace / f"{name}.log").open("w", encoding="utf-8")
        self.logs.append(log)
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        child = subprocess.Popen(args, cwd=cwd, env=self.env, stdout=log, stderr=subprocess.STDOUT, **kwargs)
        self.children.append(child)
        return child

    def run(self, name: str, args: list[str], cwd: Path, timeout: int = 900):
        child = self.start(name, args, cwd)
        child.wait(timeout=timeout)
        if child.returncode:
            raise RuntimeError(f"{name} failed ({child.returncode}); inspect {self.workspace / (name + '.log')}")

    def close(self):
        for child in reversed(self.children):
            if child.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
                else:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        os.killpg(child.pid, signal.SIGKILL)
                    child.kill()
                    child.wait(timeout=10)
        for log in self.logs:
            log.close()


def read_url(url: str) -> bytes:
    # Loopback only; do not inherit a proxy that could route local requests externally.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=2) as response:
        return response.read()


def wait_url(url: str, child, timeout: int = 90) -> bytes:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if child.poll() is not None:
            raise RuntimeError(f"Service exited ({child.returncode}); inspect demo logs")
        try:
            return read_url(url)
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-port", type=int, default=8545)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--ui-port", type=int, default=5173)
    parser.add_argument("--smoke", action="store_true", help="assert seed/hash/API/UI checks, then stop automatically")
    args = parser.parse_args(argv)
    manager = None
    try:
        check_ports([args.node_port, args.api_port, args.ui_port])
        node = shutil.which("node")
        python = ROOT / ("backend/.venv/Scripts/python.exe" if os.name == "nt" else "backend/.venv/bin/python")
        hh = ROOT / "contracts/node_modules/hardhat/internal/cli/cli.js"
        vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
        if not node or not all(p.is_file() for p in (python, hh, vite)):
            raise RuntimeError("Dependencies missing. Complete README Quickstart installation first.")
        workspace = Path(tempfile.mkdtemp(prefix="clearcredit-demo-"))
        env = environment(workspace, args.node_port, args.api_port, args.ui_port)
        manager = Processes(workspace, env)
        print(f"Fresh local demo; logs/database: {workspace}", flush=True)
        rpc, api = env["CHAIN_RPC_URL"], env["VITE_API_URL"]
        hh_args = [node, str(hh)]
        hardhat = manager.start("node", hh_args + ["node", "--hostname", "127.0.0.1", "--port", str(args.node_port)], ROOT / "contracts")
        wait_url(rpc, hardhat)
        manager.run("deploy", hh_args + ["run", "scripts/deploy.ts", "--network", "localhost"], ROOT / "contracts")
        deployment = json.loads(Path(env["DEPLOYMENT_FILE"]).read_text(encoding="utf-8"))
        if deployment["chainId"] != 31337 or deployment["network"] != "localhost":
            raise RuntimeError("Expected a disposable local Hardhat deployment")
        env["REGISTRY_ADDRESS"] = deployment["address"]
        api_child = manager.start("api", [str(python), "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(args.api_port)], ROOT / "backend")
        health = json.loads(wait_url(api + "/health", api_child))
        if health["chain"] != {"chainId": 31337, "contract": deployment["address"]}:
            raise RuntimeError("API is not connected to this fresh local contract")
        print("Local v2 contract/API ready; seeding cached real examples…", flush=True)
        report = workspace / "seed-report.json"
        manager.run("seed", [str(python), "-m", "scripts.seed", "--api", api, "--report", str(report)], ROOT / "backend")
        results = json.loads(report.read_text(encoding="utf-8"))
        expected = len(list((ROOT / "data/claims/real").glob("*.json")))
        if len(results) != expected or any(r["result"] != "registered" for r in results):
            raise RuntimeError("Seed did not register every example; inspect seed-report.json")
        ui_child = manager.start("ui", [node, str(vite), "--configLoader", "runner", "--host", "127.0.0.1", "--port", str(args.ui_port), "--strictPort"], ROOT / "frontend")
        ui = f"http://127.0.0.1:{args.ui_port}"
        wait_url(ui, ui_child)
        print(f"Seed: {len(results)}/{expected}; UI: {ui}; API: {api}/docs; RPC: {rpc}\nCtrl+C stops owned services.", flush=True)
        if args.smoke:
            view = json.loads(read_url(api + "/claims/" + results[0]["projectId"]))
            downloaded = workspace / "downloaded-claim.json"
            downloaded.write_text(json.dumps(view["claim"]), encoding="utf-8")
            digest = subprocess.check_output([str(python), str(ROOT / "backend/app/canonical.py"), str(downloaded)], env=env, text=True).strip()
            if view["claimHash"] not in digest or view["onChain"]["project"]["status"] != "registered":
                raise RuntimeError("Downloaded claim/chain check failed")
            print("SMOKE PASSED: seed, downloaded hash, chain, API and UI HTTP checks", flush=True)
        else:
            while True:
                if any(p.poll() is not None for p in (hardhat, api_child, ui_child)):
                    raise RuntimeError("A demo service exited; stopping the remaining owned services")
                time.sleep(0.5)
        return 0
    except KeyboardInterrupt:
        print("Stopping local demo…", flush=True)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        print(f"Demo failed: {e}", flush=True)
        return 1
    finally:
        if manager:
            manager.close()
            print("Owned demo processes stopped; logs/database retained.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
