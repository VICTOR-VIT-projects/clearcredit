"""ClearCredit API. Run: uvicorn app.main:create_app --factory --reload  (OpenAPI docs at /docs)."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Header, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from shapely.geometry import shape

from . import canonical, geo, history, satellite, scoring
from .chain import CLAIM_TYPES, ZERO32, Chain, ChainReadUnavailable, RegistrationCancelled, cells_root, recover_signer
from .models import Claim, Submission
from .limits import BodyLimit
from .store import Store

BLOCKING_CODES = ("OVERLAP",)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_env_file(path: Path = ENV_FILE) -> None:
    """Minimal .env reader (KEY=VALUE lines); real environment variables win."""
    if os.environ.get("CLEARCREDIT_NO_ENV") != "1" and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.strip().startswith("#") and v.strip():
                os.environ.setdefault(k.strip(), v.strip())


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None, retryable: bool = False):
        self.status, self.code, self.message, self.details, self.retryable = status, code, message, details or {}, retryable

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def create_app(store: Store | None = None, chain: Chain | None | str = "env", live_evidence: bool = True) -> FastAPI:
    if os.environ.get("CLEARCREDIT_OFFLINE_EVIDENCE") == "1":
        live_evidence = False
    if chain == "env":
        load_env_file()
        chain = Chain.from_env()
    app = FastAPI(
        title="ClearCredit API",
        version="0.1.0",
        responses={413: {"description": "REQUEST_TOO_LARGE: request bodies are limited to 2 MiB before parsing."},
                   503: {"description": "EVIDENCE_INVALID: cached evidence commitment failed; operator review required."}},
        description="Carbon-credit integrity and double-counting checker. Produces integrity scores and "
        "verified integrity attestations; it does not certify emission reductions.",
    )
    app.add_middleware(BodyLimit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Idempotent-Replayed"],  # browsers hide non-safelisted headers otherwise
    )
    store = store or Store()

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return JSONResponse(e.body(), status_code=e.status)

    @app.exception_handler(ChainReadUnavailable)
    async def _chain_read_error(_: Request, e: ChainReadUnavailable):
        return JSONResponse({"error": {"code": "CHAIN_READ_UNAVAILABLE", "message": "Required chain state is unavailable; retry shortly.", "details": {"retryable": True}}}, status_code=503)

    @app.exception_handler(satellite.EvidenceError)
    @app.exception_handler(history.HistoryError)
    async def _evidence_error(_: Request, e: satellite.EvidenceError):
        return JSONResponse({"error": {"code": "EVIDENCE_INVALID", "message": "Cached evidence failed its commitment check; operator review is required.", "details": {}}}, status_code=503)

    # ------------------------------------------------------------ analysis

    def analyze(claim: dict) -> dict:
        try:
            geom = geo.validate_boundary(claim["boundary"])
        except geo.GeometryError as e:
            raise ApiError(422, "INVALID_GEOMETRY", str(e))
        area = geo.area_ha(geom)
        others = {o["project_id"]: shape(o["claim"]["boundary"]) for o in store.same_vintage(claim["vintageYear"], exclude=claim["projectId"])}
        overlaps = [o.__dict__ for o in geo.find_overlaps(geom, others)]
        cells = geo.h3_cover(claim["boundary"])
        own_key = canonical.project_key(claim["projectId"])
        conflicts = {}
        if chain:
            for cell, owner in chain.check_cells(cells, claim["vintageYear"]).items():
                if owner != own_key:
                    known = store.find(project_key=owner)
                    conflicts.setdefault(known["project_id"] if known else owner, []).append(hex(cell))
        evidence = satellite.get_evidence(claim["boundary"], live=live_evidence)
        score = scoring.score_claim(claim, area, overlaps, evidence, history.for_claim(claim))
        blocked = any(r["code"] in BLOCKING_CODES for r in score["reasons"]) or bool(conflicts)
        return {
            "areaHa": round(area, 2),
            "overlaps": overlaps,
            "onChainCellConflicts": [{"projectId": p, "cells": c[:20], "count": len(c)} for p, c in conflicts.items()],
            "cellResolution": geo.CELL_RESOLUTION,
            "cellCount": len(cells),
            "cells": cells,
            "score": score,
            "blocked": blocked,
        }

    def hashes(claim: dict) -> dict:
        h = canonical.claim_hash(claim)
        return {
            "claimHash": h,
            "projectKey": canonical.project_key(claim["projectId"]),
            "submissionKey": canonical.submission_key(h, claim["developer"], claim["vintageYear"]),
        }

    def claim_view(row: dict, minimum_block: int = 0) -> dict:
        res = row["result"]
        view = {
            "projectId": row["project_id"],
            "projectKey": row["project_key"],
            "claimHash": row["claim_hash"],
            "dataLabel": row["claim"]["dataLabel"],
            "status": row["status"],
            "claim": row["claim"],
            "areaHa": res["areaHa"],
            "overlaps": res["overlaps"],
            "cellResolution": res["cellResolution"],
            "cellCount": res["cellCount"],
            "score": res["score"],
            "evidence": satellite.get_evidence(row["claim"]["boundary"], live=False),
            "transactions": [{**t, "url": chain.tx_url(t["tx"]) if chain else None} for t in row["txs"]],
            "onChain": None,
            "createdAt": row["created_at"],
        }
        if chain:
            snapshot = chain.snapshot(row["project_key"], minimum_block)
            if row["status"] == "registered" and snapshot["project"]["status"] in ("none", "pending"):
                raise ChainReadUnavailable("Stored registration is not visible on-chain")
            view["status"] = snapshot["project"]["status"]
            view["onChain"] = {
                "contract": chain.address,
                "chainId": chain.chain_id,
                "explorer": f"{chain.explorer}/address/{chain.address}" if chain.explorer else None,
                **snapshot,
            }
        return view

    def lookup(ref: str) -> dict:
        row = store.find(claim_hash=ref.lower()) if ref.startswith("0x") and len(ref) == 66 else store.get(ref)
        if not row:
            raise ApiError(404, "NOT_FOUND", f"No claim with project ID or claim hash {ref!r}")
        return row

    # ------------------------------------------------------------ endpoints

    @app.post("/claims/preview", tags=["claims"])
    def preview(claim: Claim):
        """Validate, check overlaps, gather evidence and score — without registering anything."""
        c = claim.model_dump()
        a = analyze(c)
        h = hashes(c)
        cells = a.pop("cells")
        root = cells_root(cells)
        out = {**h, **a, "canonicalClaim": canonical.canonical_claim(c), "cellsRoot": root, "cellIds": [hex(cell) for cell in cells]}
        if chain:
            out["typedData"] = chain.typed_data(h["projectKey"], h["claimHash"], c["vintageYear"], c["claimedCredits"], root)
        return out

    @app.post("/claims", status_code=201, tags=["claims"])
    def submit(sub: Submission, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        """Register a signed claim. Requires `Idempotency-Key`; a retry with the same key and body
        returns the original result and never creates a second record or transaction."""
        if not idempotency_key or len(idempotency_key) > 200:
            raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Send an Idempotency-Key header (any unique string, ≤200 chars).")
        body = sub.model_dump()
        request_hash = canonical.keccak(canonical._dumps({"c": canonical.canonical_claim(body["claim"]), "s": body["signature"].lower()}).encode()).hex()
        state, row = store.idem_begin(idempotency_key, request_hash)
        if state == "replay":
            result = json.loads(row["response"])
            if row["status_code"] == 201 and chain:
                with store.admission_lock:
                    saved = lookup(result["projectId"])
                    snapshot = chain.snapshot(saved["project_key"])
                    if snapshot["project"]["status"] != "registered":
                        store.update_claim(saved["project_id"], status="cancelled" if snapshot["project"]["status"] == "cancelled" else "relay_failed")
                        store.idem_retry(idempotency_key)
                        raise ChainReadUnavailable("Cached registration is not confirmed; retry resumes safely")
                    # Refresh chain observations, retain the original response's non-chain fields.
                    result.update(claim_view(saved))
            return JSONResponse(result, status_code=row["status_code"], headers={"Idempotent-Replayed": "true"})
        if state == "in_flight":
            raise ApiError(409, "REQUEST_IN_PROGRESS", "A request with this Idempotency-Key is still being processed; retry shortly.")
        if state == "mismatch":
            raise ApiError(422, "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was already used for a different request body.")
        try:
            # Admission + insertion must be indivisible across different retry keys.
            # Keep same-project relay resumption serialized too. One API worker only.
            with store.admission_lock:
                result = _submit(body["claim"], body["signature"], recovered=row is not None)
        except ApiError as e:
            if e.retryable:
                store.idem_abort(idempotency_key)
            else:
                store.idem_finish(idempotency_key, e.status, e.body())
            raise
        except Exception:
            store.idem_abort(idempotency_key)
            raise
        store.idem_finish(idempotency_key, 201, result)
        return JSONResponse(result, status_code=201)

    def _submit(claim: dict, signature: str, recovered: bool = False) -> dict:
        claim["submittedAt"] = claim.get("submittedAt") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        h = hashes(claim)
        existing = store.get(claim["projectId"]) or store.find(claim_hash=h["claimHash"])
        resumable = existing and existing["claim_hash"] == h["claimHash"] and (existing["status"] in ("relay_failed", "relaying", "cancelled") or recovered)
        if existing and not resumable:
            raise ApiError(409, "DUPLICATE_CLAIM", "This project ID or identical claim is already registered.",
                           {"projectId": existing["project_id"], "claimHash": existing["claim_hash"]})
        if not existing:
            a = analyze(claim)
            if a["blocked"]:
                raise ApiError(409, "OVERLAP_DETECTED", "The boundary overlaps land already claimed for the same vintage.",
                               {"overlaps": a["overlaps"], "onChainCellConflicts": a["onChainCellConflicts"], "score": a["score"]})
            if chain:
                td = chain.typed_data(h["projectKey"], h["claimHash"], claim["vintageYear"], claim["claimedCredits"], cells_root(a["cells"]))
                signer = recover_signer(td, signature)
                if signer.lower() != claim["developer"].lower():
                    raise ApiError(400, "BAD_SIGNATURE", f"Signature was made by {signer}, not the developer {claim['developer']}.")
            cells = a.pop("cells")
            store.insert_claim(project_id=claim["projectId"], project_key=h["projectKey"], claim_hash=h["claimHash"],
                               vintage_year=claim["vintageYear"], claim=claim, signature=signature, cells=cells, result=a,
                               status="relaying" if chain else "offline")
        row = store.get(claim["projectId"])
        if chain:
            txs = list(row["txs"])
            try:
                chain.relay_registration(h["projectKey"], h["claimHash"], claim["developer"], claim["vintageYear"],
                                         claim["claimedCredits"], row["cells"], row["signature"], txs)
                s = row["result"]["score"]
                att = chain.post_attestation(h["projectKey"], s["scoreBps"], s["evidenceHash"] or ZERO32, s["modelVersion"])
                txs += [att] if att else []
            except RegistrationCancelled:
                store.update_claim(claim["projectId"], status="cancelled", txs=txs)
                raise ApiError(409, "REGISTRATION_CANCELLED", "This Pending registration was cancelled. Its project ID and claim hash remain reserved for audit; prepare a new claim after reviewing released cells.")
            except Exception as e:
                store.update_claim(claim["projectId"], status="relay_failed", txs=txs)
                raise ApiError(502, "RELAY_FAILED", "Claim saved but on-chain relay failed; retry the same request to resume.", retryable=True)
            # Build and validate the complete pinned response before storing success.
            row = store.get(claim["projectId"])
            row["txs"] = txs
            try:
                view = claim_view(row)
            except ChainReadUnavailable:
                store.update_claim(claim["projectId"], status="relay_failed", txs=txs)
                raise ApiError(502, "RELAY_FAILED", "Required chain snapshot is unavailable; retry to resume.", retryable=True)
            if view["status"] != "registered":
                store.update_claim(claim["projectId"], status="relay_failed", txs=txs)
                raise ApiError(502, "RELAY_FAILED", "Confirmed registration is not visible; retry to resume.", retryable=True)
            store.update_claim(claim["projectId"], status="registered", txs=txs)
        else:
            view = claim_view(store.get(claim["projectId"]))
        view["submissionKey"] = h["submissionKey"]
        if view["score"]["band"] == "low":
            view["warnings"] = [{"code": "LOW_INTEGRITY_SCORE", "message": "Registered, but the integrity score is low; "
                                 "the contract will refuse issuance until a passing attestation is posted."}]
        return view

    @app.get("/claims/{ref}", tags=["claims"])
    def get_claim(ref: str, minimum_block: int = Query(default=0, ge=0, alias="minBlock")):
        """Claim by project ID or claim hash: canonical hash, overlaps, evidence, score, on-chain state."""
        return claim_view(lookup(ref), minimum_block)

    @app.get("/claims/{ref}/verify", tags=["claims"])
    def verify(ref: str, minimum_block: int = Query(default=0, ge=0, alias="minBlock")):
        """Recompute the hash from the stored claim and compare it with the on-chain value."""
        row = lookup(ref)
        recomputed = canonical.claim_hash(row["claim"])
        snapshot = chain.snapshot(row["project_key"], minimum_block) if chain else None
        onchain = snapshot["project"]["claimHash"] if snapshot else None
        return {
            "projectId": row["project_id"],
            "recomputedHash": recomputed,
            "onChainHash": onchain,
            "match": None if onchain is None else recomputed == onchain,
            "observedBlock": snapshot["observedBlock"] if snapshot else None,
            "note": "A mismatch means the off-chain claim record was altered after registration." if onchain and recomputed != onchain else None,
        }

    @app.get("/overlaps/{ref}", tags=["claims"])
    def overlaps(ref: str):
        row = lookup(ref)
        geom = shape(row["claim"]["boundary"])
        others = {o["project_id"]: shape(o["claim"]["boundary"]) for o in store.same_vintage(row["vintage_year"], exclude=row["project_id"])}
        return {"projectId": row["project_id"], "vintageYear": row["vintage_year"], "overlaps": [o.__dict__ for o in geo.find_overlaps(geom, others)]}

    @app.post("/claims/{ref}/attest", tags=["verifier"])
    def attest(ref: str, x_admin_token: str | None = Header(default=None)):
        """Re-score with fresh evidence and post a new attestation (verifier only)."""
        token = os.environ.get("ADMIN_TOKEN")
        if not token or not x_admin_token or not secrets.compare_digest(x_admin_token.encode(), token.encode()):
            raise ApiError(403, "FORBIDDEN", "Verifier token required.")
        row = lookup(ref)
        a = analyze(row["claim"])
        a.pop("cells")
        att = None
        if chain:
            s = a["score"]
            att = chain.post_attestation(row["project_key"], s["scoreBps"], s["evidenceHash"] or ZERO32, s["modelVersion"])
            if att:
                store.update_claim(row["project_id"], txs=row["txs"] + [att])
        store.update_claim(row["project_id"], result=a)
        return {"projectId": row["project_id"], "score": a["score"], "attestation": att}

    @app.get("/registry", tags=["registry"])
    def registry(offset: int = 0, limit: int = 50):
        total, rows = store.page(max(0, offset), min(max(1, limit), 200))
        if chain:
            block = chain.snapshot_block()
            with chain.read_at(block):
                for row in rows:
                    row["status"] = chain.project(row["project_key"])["status"]
        return {
            "total": total,
            "items": [
                {
                    "projectId": r["project_id"], "claimHash": r["claim_hash"], "dataLabel": r["claim"]["dataLabel"],
                    "projectType": r["claim"]["projectType"], "vintageYear": r["vintage_year"],
                    "claimedCredits": r["claim"]["claimedCredits"], "areaHa": r["result"]["areaHa"],
                    "score": r["result"]["score"]["score"], "band": r["result"]["score"]["band"], "status": r["status"],
                    "sourceRegistry": r["claim"].get("sourceRegistry"),
                }
                for r in rows
            ],
        }

    @app.get("/schema", tags=["schema"])
    def schema():
        return {
            "schemaVersion": "1.0",
            "jsonSchema": Claim.model_json_schema(),
            "canonicalization": canonical.__doc__,
            "eip712": {"domainVersion": "2", "primaryType": "Claim", "types": CLAIM_TYPES},
        }

    @app.get("/health", tags=["meta"])
    def health():
        return {"ok": True, "chain": {"chainId": chain.chain_id, "contract": chain.address} if chain else None}

    return app

