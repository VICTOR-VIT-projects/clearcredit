"""Bound request bodies before JSON parsing, and budget requests per client."""
import os
import time

from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 2 * 1024 * 1024


class BodyLimit:
    def __init__(self, app, max_bytes: int = MAX_REQUEST_BYTES):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                response = JSONResponse({"error": {"code": "REQUEST_TOO_LARGE",
                    "message": f"Request body exceeds {self.max_bytes} bytes.", "details": {}}}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, bounded_receive, send)


class RateLimit:
    """Per-client request budget for public deployments (`RATE_LIMIT_PER_MINUTE`, off when unset).

    The client is the first `X-Forwarded-For` hop: the API binds to 127.0.0.1 behind a local
    tunnel (Tailscale Funnel), so only that proxy can set the header.
    """

    # ponytail: in-memory, per process; move to a shared store if the API ever runs >1 worker.
    def __init__(self, app, per_minute: int | None = None):
        self.app = app
        self.per_minute = per_minute if per_minute is not None else int(os.environ.get("RATE_LIMIT_PER_MINUTE") or 0)
        self.hits: dict[str, list[float]] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.per_minute <= 0 or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        forwarded = headers.get(b"x-forwarded-for", b"").split(b",")[0].strip().decode() if headers.get(b"x-forwarded-for") else ""
        client = forwarded or (scope.get("client") or ("unknown",))[0]
        now = time.monotonic()
        recent = [t for t in self.hits.get(client, []) if now - t < 60]
        if len(recent) >= self.per_minute:
            self.hits[client] = recent
            response = JSONResponse({"error": {"code": "RATE_LIMITED",
                "message": f"Too many requests: limit is {self.per_minute} per minute. Try again shortly.", "details": {}}},
                status_code=429, headers={"Retry-After": "30"})
            return await response(scope, receive, send)
        recent.append(now)
        self.hits[client] = recent
        if len(self.hits) > 10_000:  # bound memory: forget idle clients
            self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < 60}
        await self.app(scope, receive, send)
