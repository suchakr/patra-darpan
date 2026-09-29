"""Small OAuth authorization-server implementation for the MCP edge.

The MCP SDK supplies the protocol handlers.  This module supplies the provider
state and the Google OIDC step, while the retrieval tools remain unchanged.
The allowlist is deliberately a text file so a server operator can edit it
without rebuilding a release or restarting the MCP process.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse


class OAuthConfigurationError(ValueError):
    """Raised when OAuth mode is enabled without a complete configuration."""


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def parse_allowlist(text: str) -> set[str]:
    """Parse one email per line; ``#`` comments through end of line."""

    emails: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        value = raw_line.split("#", 1)[0].strip()
        if not value:
            continue
        if "@" not in value or any(character.isspace() for character in value):
            raise ValueError(f"invalid allowlist email on line {line_number}")
        emails.add(normalize_email(value))
    return emails


class EmailAllowlist:
    """Cached allowlist that reloads when the file's stat signature changes."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self._signature: tuple[int, int, int] | None = None
        self._emails: set[str] = set()
        self._lock = threading.RLock()

    def _file_signature(self) -> tuple[int, int, int]:
        stat = self.path.stat()
        return (stat.st_ino, stat.st_mtime_ns, stat.st_size)

    def _reload_if_changed(self) -> None:
        signature = self._file_signature()
        if signature == self._signature:
            return
        emails = parse_allowlist(self.path.read_text(encoding="utf-8"))
        self._emails = emails
        self._signature = signature

    def emails(self) -> set[str]:
        with self._lock:
            self._reload_if_changed()
            return set(self._emails)

    def allows(self, email: str) -> bool:
        try:
            return normalize_email(email) in self.emails()
        except (OSError, ValueError):
            # A partially edited or malformed file fails closed. Startup still
            # validates the file so an operator sees configuration errors early.
            return False


class OAuthStateStore:
    """Tiny SQLite store for OAuth clients, codes, and tokens."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_records (
                    kind TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    expires_at REAL,
                    PRIMARY KEY (kind, record_key)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def put(self, kind: str, key: str, payload: Any, expires_at: float | None = None) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO oauth_records(kind, record_key, payload, expires_at) VALUES (?, ?, ?, ?)",
                (kind, key, encoded, expires_at),
            )

    def get(self, kind: str, key: str, *, consume: bool = False) -> Any | None:
        now = time.time()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload, expires_at FROM oauth_records WHERE kind = ? AND record_key = ?",
                (kind, key),
            ).fetchone()
            if row is None:
                return None
            payload, expires_at = row
            if expires_at is not None and expires_at < now:
                connection.execute(
                    "DELETE FROM oauth_records WHERE kind = ? AND record_key = ?",
                    (kind, key),
                )
                return None
            if consume:
                connection.execute(
                    "DELETE FROM oauth_records WHERE kind = ? AND record_key = ?",
                    (kind, key),
                )
            return json.loads(payload)

    def delete(self, kind: str, key: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM oauth_records WHERE kind = ? AND record_key = ?",
                (kind, key),
            )

    def put_model(self, kind: str, key: str, model: Any, expires_at: float | None = None) -> None:
        self.put(kind, key, json.loads(model.model_dump_json()), expires_at)

    def get_model(self, kind: str, key: str, model_type: Any, *, consume: bool = False) -> Any | None:
        payload = self.get(kind, key, consume=consume)
        return model_type.model_validate(payload) if payload is not None else None

    def put_client(self, client: OAuthClientInformationFull) -> None:
        self.put("client", str(client.client_id), json.loads(client.model_dump_json()))

    def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        payload = self.get("client", client_id)
        return OAuthClientInformationFull.model_validate(payload) if payload is not None else None


class GoogleOAuthProvider(OAuthAuthorizationServerProvider[Any, Any, Any]):
    """MCP OAuth provider that uses Google as the upstream OIDC provider."""

    def __init__(
        self,
        *,
        issuer_url: str,
        resource_url: str,
        redirect_uri: str,
        google_client_id: str,
        google_client_secret: str,
        allowlist: EmailAllowlist,
        state_store: OAuthStateStore,
        tokeninfo_url: str = "https://oauth2.googleapis.com/tokeninfo",
        scopes: list[str] | None = None,
    ):
        self.issuer_url = issuer_url.rstrip("/")
        self.resource_url = resource_url.rstrip("/")
        self.redirect_uri = redirect_uri
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret
        self.allowlist = allowlist
        self.state_store = state_store
        self.tokeninfo_url = tokeninfo_url
        self.scopes = scopes or ["mcp"]

    @classmethod
    def from_env(cls) -> "GoogleOAuthProvider":
        def required(name: str) -> str:
            value = os.getenv(name, "").strip()
            if not value or value.startswith("replace-"):
                raise OAuthConfigurationError(f"{name} must be set for OAuth mode")
            return value

        issuer_url = required("MCP_OAUTH_ISSUER_URL")
        resource_url = os.getenv("MCP_OAUTH_RESOURCE_URL", "").strip() or f"{issuer_url.rstrip('/')}/mcp"
        redirect_uri = os.getenv("MCP_OAUTH_REDIRECT_URI", "").strip() or f"{issuer_url.rstrip('/')}/oauth/callback"
        allowlist_path = required("MCP_OAUTH_ALLOWLIST_FILE")
        state_db = required("MCP_OAUTH_STATE_DB")
        scopes = [item for item in os.getenv("MCP_OAUTH_SCOPE", "mcp").split() if item]
        if not scopes:
            raise OAuthConfigurationError("MCP_OAUTH_SCOPE must contain at least one scope")
        allowlist = EmailAllowlist(allowlist_path)
        allowlist.emails()  # Fail closed at startup when the file is absent or malformed.
        return cls(
            issuer_url=issuer_url,
            resource_url=resource_url,
            redirect_uri=redirect_uri,
            google_client_id=required("MCP_OAUTH_GOOGLE_CLIENT_ID"),
            google_client_secret=required("MCP_OAUTH_GOOGLE_CLIENT_SECRET"),
            allowlist=allowlist,
            state_store=OAuthStateStore(state_db),
            tokeninfo_url=os.getenv(
                "MCP_OAUTH_GOOGLE_TOKENINFO_URL",
                "https://oauth2.googleapis.com/tokeninfo",
            ).strip(),
            scopes=scopes,
        )

    def auth_settings(self) -> AuthSettings:
        return AuthSettings(
            issuer_url=self.issuer_url,
            resource_server_url=self.resource_url,
            validate_token_resource=True,
            required_scopes=self.scopes,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=self.scopes,
                default_scopes=self.scopes,
            ),
            revocation_options=RevocationOptions(enabled=True),
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.state_store.get_client(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("client registration requires a client_id")
        self.state_store.put_client(client_info)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        upstream_state = secrets.token_urlsafe(32)
        pending = {
            "client_id": client.client_id,
            "state": params.state,
            "scopes": params.scopes or self.scopes,
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "resource": params.resource or self.resource_url,
        }
        self.state_store.put("pending", upstream_state, pending, time.time() + 600)
        query = urlencode(
            {
                "client_id": self.google_client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": upstream_state,
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    async def handle_callback(self, request: Request):
        query = request.query_params
        upstream_state = query.get("state", "")
        pending = self.state_store.get("pending", upstream_state, consume=True)
        if not pending:
            return JSONResponse({"error": "invalid_or_expired_oauth_state"}, status_code=400)
        if query.get("error"):
            return self._redirect_error(pending, query.get("error", "access_denied"), query.get("error_description"))
        code = query.get("code", "")
        if not code:
            return self._redirect_error(pending, "invalid_request", "Google returned no authorization code")
        try:
            email = await self._google_email(code)
        except Exception:
            return self._redirect_error(pending, "server_error", "upstream identity verification failed")
        if not self.allowlist.allows(email):
            return self._redirect_error(pending, "access_denied", "account is not on the MCP allowlist")

        authorization_code = secrets.token_urlsafe(48)
        record = AuthorizationCode(
            code=authorization_code,
            scopes=pending["scopes"],
            expires_at=time.time() + 60,
            client_id=pending["client_id"],
            code_challenge=pending["code_challenge"],
            redirect_uri=pending["redirect_uri"],
            redirect_uri_provided_explicitly=pending["redirect_uri_provided_explicitly"],
            resource=pending["resource"],
            subject=email,
        )
        self.state_store.put_model("authorization_code", authorization_code, record, record.expires_at)
        return RedirectResponse(
            construct_redirect_uri(
                pending["redirect_uri"],
                code=authorization_code,
                state=pending["state"],
            ),
            status_code=302,
            headers={"Cache-Control": "no-store"},
        )

    async def _google_email(self, code: str) -> str:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self.google_client_id,
                    "client_secret": self.google_client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            id_token = token_data.get("id_token")
            if not id_token:
                raise OAuthConfigurationError("Google token response did not contain an id_token")
            identity_response = await client.get(self.tokeninfo_url, params={"id_token": id_token})
            identity_response.raise_for_status()
            identity = identity_response.json()
        if identity.get("aud") != self.google_client_id:
            raise OAuthConfigurationError("Google token audience did not match this MCP")
        if identity.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
            raise OAuthConfigurationError("Google token issuer was not Google")
        if str(identity.get("email_verified", "")).lower() not in {"true", "1"}:
            raise OAuthConfigurationError("Google account email is not verified")
        email = normalize_email(str(identity.get("email", "")))
        if "@" not in email:
            raise OAuthConfigurationError("Google token did not contain an email")
        return email

    def _redirect_error(self, pending: dict[str, Any], error: str, description: str | None):
        return RedirectResponse(
            construct_redirect_uri(
                pending["redirect_uri"],
                error=error,
                error_description=description,
                state=pending["state"],
            ),
            status_code=302,
            headers={"Cache-Control": "no-store"},
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        record = self.state_store.get_model("authorization_code", authorization_code, AuthorizationCode)
        return record if record and record.client_id == client.client_id else None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self.state_store.delete("authorization_code", authorization_code.code)
        return self._issue_tokens(
            client_id=client.client_id or authorization_code.client_id,
            scopes=authorization_code.scopes,
            subject=authorization_code.subject,
            resource=authorization_code.resource or self.resource_url,
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        record = self.state_store.get_model("refresh_token", refresh_token, RefreshToken)
        if not record or record.client_id != client.client_id:
            return None
        return record if record.subject and self.allowlist.allows(record.subject) else None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        self.state_store.delete("refresh_token", refresh_token.token)
        return self._issue_tokens(
            client_id=client.client_id or refresh_token.client_id,
            scopes=scopes,
            subject=refresh_token.subject,
            resource=refresh_token.resource or self.resource_url,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        record = self.state_store.get_model("access_token", token, AccessToken)
        if not record or not record.subject:
            return None
        return record if self.allowlist.allows(record.subject) else None

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self.state_store.delete("access_token", token.token)
        self.state_store.delete("refresh_token", token.token)

    def _issue_tokens(
        self,
        *,
        client_id: str,
        scopes: list[str],
        subject: str | None,
        resource: str,
    ) -> OAuthToken:
        access_value = secrets.token_urlsafe(48)
        refresh_value = secrets.token_urlsafe(48)
        access = AccessToken(
            token=access_value,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + 3600,
            resource=resource,
            subject=subject,
            claims={"iss": self.issuer_url, "email": subject},
        )
        refresh = RefreshToken(
            token=refresh_value,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            resource=resource,
            subject=subject,
        )
        self.state_store.put_model("access_token", access_value, access, access.expires_at)
        self.state_store.put_model("refresh_token", refresh_value, refresh, refresh.expires_at)
        return OAuthToken(
            access_token=access_value,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=refresh_value,
            scope=" ".join(scopes),
        )
