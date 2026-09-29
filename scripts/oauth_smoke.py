#!/usr/bin/env python3
"""Check the local OAuth MCP edge without performing an interactive login."""

from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://retrieval-https:8443")
    parser.add_argument("--allow-insecure", action="store_true")
    args = parser.parse_args()

    try:
        import httpx
    except ModuleNotFoundError as exc:  # pragma: no cover - image dependency guard
        raise SystemExit(f"OAuth smoke dependencies are missing: {exc}") from exc

    base = args.base_url.rstrip("/")
    verify = not args.allow_insecure
    with httpx.Client(verify=verify, follow_redirects=False, timeout=20) as client:
        authorization = client.get(f"{base}/.well-known/oauth-authorization-server")
        protected = client.get(f"{base}/.well-known/oauth-protected-resource/mcp")
        oauth_mcp = client.post(
            f"{base}/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        bearer_mcp = client.post(
            f"{base}/mcp-bearer",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )

    if authorization.status_code != 200:
        raise SystemExit(f"OAuth authorization metadata returned {authorization.status_code}")
    if protected.status_code != 200:
        raise SystemExit(f"Protected resource metadata returned {protected.status_code}")
    if oauth_mcp.status_code != 401:
        raise SystemExit(f"OAuth MCP challenge returned {oauth_mcp.status_code}, expected 401")
    if bearer_mcp.status_code != 401:
        raise SystemExit(f"Bearer MCP challenge returned {bearer_mcp.status_code}, expected 401")

    metadata = authorization.json()
    protected_metadata = protected.json()
    print(
        json.dumps(
            {
                "authorization_issuer": metadata.get("issuer"),
                "authorization_endpoint": metadata.get("authorization_endpoint"),
                "token_endpoint": metadata.get("token_endpoint"),
                "protected_resource": protected_metadata.get("resource"),
                "oauth_mcp_status": oauth_mcp.status_code,
                "bearer_mcp_status": bearer_mcp.status_code,
                "interactive_login": "required for an end-to-end OAuth tool call",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
