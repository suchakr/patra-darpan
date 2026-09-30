from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from lib.retrieval_oauth import EmailAllowlist, GoogleOAuthProvider, OAuthStateStore, parse_allowlist
from mcp.shared.auth import OAuthClientInformationFull
from mcp.server.auth.provider import AuthorizationParams
from starlette.requests import Request


class AllowlistTests(unittest.TestCase):
    def test_comments_and_case_are_normalized(self) -> None:
        self.assertEqual(
            parse_allowlist(" Alice@example.com # retained\n# ignored\n\nBOB@example.com\n"),
            {"alice@example.com", "bob@example.com"},
        )

    def test_invalid_line_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 1"):
            parse_allowlist("not-an-email\n")

    def test_file_change_is_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "allowlist.txt"
            path.write_text("alice@example.com\n", encoding="utf-8")
            allowlist = EmailAllowlist(path)
            self.assertTrue(allowlist.allows("ALICE@example.com"))
            path.write_text("bob@example.com\n", encoding="utf-8")
            self.assertFalse(allowlist.allows("alice@example.com"))
            self.assertTrue(allowlist.allows("bob@example.com"))


class OAuthProviderTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _callback_request(query: dict[str, str]) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/oauth/callback",
                "query_string": urlencode(query).encode("utf-8"),
                "headers": [],
            }
        )

    async def test_dynamic_client_and_google_redirect_are_stored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist_path = root / "allowlist.txt"
            allowlist_path.write_text("alice@example.com\n", encoding="utf-8")
            provider = GoogleOAuthProvider(
                issuer_url="https://localhost:8443",
                resource_url="https://localhost:8443/mcp",
                redirect_uri="https://localhost:8443/oauth/callback",
                google_client_id="client-id",
                google_client_secret="client-secret",
                allowlist=EmailAllowlist(allowlist_path),
                state_store=OAuthStateStore(root / "oauth.sqlite3"),
            )
            client = OAuthClientInformationFull(
                client_id="test-client",
                redirect_uris=["http://localhost/callback"],
                token_endpoint_auth_method="none",
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                scope="mcp",
            )
            await provider.register_client(client)
            params = AuthorizationParams(
                state="client-state",
                scopes=["mcp"],
                code_challenge="challenge",
                redirect_uri="http://localhost/callback",
                redirect_uri_provided_explicitly=True,
                resource="https://localhost:8443/mcp",
            )
            location = await provider.authorize(client, params)
            query = parse_qs(urlparse(location).query)
            self.assertEqual(query["client_id"], ["client-id"])
            self.assertEqual(query["redirect_uri"], ["https://localhost:8443/oauth/callback"])
            self.assertEqual(query["scope"], ["openid email profile"])
            self.assertTrue(query["state"][0])
            self.assertIsNotNone(await provider.get_client("test-client"))

    async def test_callback_issues_code_only_for_allowlisted_email(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist_path = root / "allowlist.txt"
            allowlist_path.write_text("alice@example.com\n", encoding="utf-8")
            provider = GoogleOAuthProvider(
                issuer_url="https://localhost:8443",
                resource_url="https://localhost:8443/mcp",
                redirect_uri="https://localhost:8443/oauth/callback",
                google_client_id="client-id",
                google_client_secret="client-secret",
                allowlist=EmailAllowlist(allowlist_path),
                state_store=OAuthStateStore(root / "oauth.sqlite3"),
            )
            client = OAuthClientInformationFull(
                client_id="test-client",
                redirect_uris=["http://localhost/callback"],
                token_endpoint_auth_method="none",
            )
            params = AuthorizationParams(
                state="client-state",
                scopes=["mcp"],
                code_challenge="challenge",
                redirect_uri="http://localhost/callback",
                redirect_uri_provided_explicitly=True,
                resource="https://localhost:8443/mcp",
            )
            location = await provider.authorize(client, params)
            upstream_state = parse_qs(urlparse(location).query)["state"][0]

            async def fake_google_email(_code: str) -> str:
                return "alice@example.com"

            provider._google_email = fake_google_email  # type: ignore[method-assign]
            response = await provider.handle_callback(
                self._callback_request({"state": upstream_state, "code": "google-code"})
            )
            self.assertEqual(response.status_code, 302)
            callback_query = parse_qs(urlparse(response.headers["location"]).query)
            self.assertIn("code", callback_query)
            self.assertEqual(callback_query["state"], ["client-state"])

            allowlist_path.write_text("bob@example.com\n", encoding="utf-8")
            location = await provider.authorize(client, params)
            upstream_state = parse_qs(urlparse(location).query)["state"][0]
            response = await provider.handle_callback(
                self._callback_request({"state": upstream_state, "code": "google-code"})
            )
            denied_query = parse_qs(urlparse(response.headers["location"]).query)
            self.assertEqual(denied_query["error"], ["access_denied"])

    async def test_removed_email_cannot_use_issued_access_or_refresh_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowlist_path = root / "allowlist.txt"
            allowlist_path.write_text("alice@example.com\n", encoding="utf-8")
            provider = GoogleOAuthProvider(
                issuer_url="https://localhost:8443",
                resource_url="https://localhost:8443/mcp",
                redirect_uri="https://localhost:8443/oauth/callback",
                google_client_id="client-id",
                google_client_secret="client-secret",
                allowlist=EmailAllowlist(allowlist_path),
                state_store=OAuthStateStore(root / "oauth.sqlite3"),
            )
            from mcp.server.auth.provider import AccessToken, RefreshToken

            access = AccessToken(
                token="access",
                client_id="client",
                scopes=["mcp"],
                subject="alice@example.com",
            )
            refresh = RefreshToken(
                token="refresh",
                client_id="client",
                scopes=["mcp"],
                subject="alice@example.com",
            )
            provider.state_store.put_model("access_token", access.token, access)
            provider.state_store.put_model("refresh_token", refresh.token, refresh)
            self.assertIsNotNone(await provider.load_access_token(access.token))
            client = OAuthClientInformationFull(
                client_id="client", redirect_uris=["http://localhost/callback"]
            )
            self.assertIsNotNone(await provider.load_refresh_token(client, refresh.token))

            allowlist_path.write_text("bob@example.com\n", encoding="utf-8")
            self.assertIsNone(await provider.load_access_token(access.token))
            self.assertIsNone(await provider.load_refresh_token(client, refresh.token))


if __name__ == "__main__":
    unittest.main()
