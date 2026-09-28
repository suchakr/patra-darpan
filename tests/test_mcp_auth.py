from __future__ import annotations

import asyncio
import unittest

from scripts.retrieval_mcp_server import BearerAuthMiddleware


async def _invoke(app, *, headers=(), scope_type="http"):
    events = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        events.append(message)

    await app(
        {"type": scope_type, "headers": list(headers)},
        receive,
        send,
    )
    return events


class BearerAuthMiddlewareTests(unittest.TestCase):
    def test_missing_token_is_rejected_without_calling_app(self) -> None:
        calls = []

        async def app(scope, receive, send):
            calls.append(True)

        events = asyncio.run(_invoke(BearerAuthMiddleware(app, "patra-darpan")))

        self.assertEqual(events[0]["status"], 401)
        self.assertIn((b"www-authenticate", b'Bearer realm="retrieval-mcp"'), events[0]["headers"])
        self.assertEqual(calls, [])

    def test_wrong_token_is_rejected(self) -> None:
        async def app(scope, receive, send):
            raise AssertionError("the protected app must not be called")

        events = asyncio.run(
            _invoke(
                BearerAuthMiddleware(app, "patra-darpan"),
                headers=[(b"authorization", b"Bearer wrong")],
            )
        )

        self.assertEqual(events[0]["status"], 401)

    def test_correct_token_reaches_app(self) -> None:
        calls = []

        async def app(scope, receive, send):
            calls.append(scope["type"])
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        events = asyncio.run(
            _invoke(
                BearerAuthMiddleware(app, "patra-darpan"),
                headers=[(b"authorization", b"bearer patra-darpan")],
            )
        )

        self.assertEqual(calls, ["http"])
        self.assertEqual(events[0]["status"], 204)

    def test_non_http_scope_is_not_modified(self) -> None:
        calls = []

        async def app(scope, receive, send):
            calls.append(scope["type"])

        asyncio.run(_invoke(BearerAuthMiddleware(app, "patra-darpan"), scope_type="lifespan"))

        self.assertEqual(calls, ["lifespan"])


if __name__ == "__main__":
    unittest.main()
