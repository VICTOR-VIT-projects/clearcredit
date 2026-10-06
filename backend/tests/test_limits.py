import asyncio

import pytest

from app.limits import BodyLimit


@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1")]])
def test_chunked_body_cap_precedes_downstream_parsing(headers):
    called, sent = [], []
    messages = iter([{"type": "http.request", "body": b"123", "more_body": True},
                     {"type": "http.request", "body": b"456", "more_body": False}])

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def downstream(*_):
        called.append(True)

    asyncio.run(BodyLimit(downstream, max_bytes=5)(
        {"type": "http", "method": "POST", "headers": headers}, receive, send))
    assert not called
    assert sent[0]["status"] == 413
