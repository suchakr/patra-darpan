# MCP HTTPS boundary

The retrieval application speaks Streamable HTTP on private container ports.
TLS terminates at Caddy. OAuth is the default `/mcp` route; the existing
bearer flow remains available at `/mcp-bearer`.

## Local harness test

Keep the ordinary local endpoint for host-side smoke tests:

```text
http://127.0.0.1:8787/mcp
```

When a harness insists on HTTPS, populate the OAuth values and allowlist in
the untracked `.env`, then start the local edge:

```bash
make oauth-config
make edge
```

The default endpoint is then:

```text
https://localhost:8443/mcp
```

`https://localhost:8443/mcp-oauth` is an explicit alias for the same OAuth
process.

The `/mcp` client performs OAuth. Existing bearer clients use:

```text
https://localhost:8443/mcp-bearer
```

`make edge-smoke` verifies discovery, protected-resource metadata, and the
unauthenticated challenges. A real Google login remains a manual client test.

The local certificate is issued by Caddy's internal CA and is not publicly
trusted. A harness must trust that CA, or the endpoint is suitable only for a
local test client that explicitly supplies the CA. To export the CA for a
client configuration, use:

```bash
mkdir -p .local/retrieval
docker compose --env-file .env -f docker-compose.retrieval.yml \
  --profile runtime --profile https \
  cp retrieval-https:/data/caddy/pki/authorities/local/root.crt \
  .local/retrieval/caddy-local-root.crt
```

HTTPS does not make a
loopback URL reachable from a hosted ChatGPT service; that requires a public
hostname or an authenticated tunnel.

### Claude connector distinction

Claude's **Settings → Connectors** path is a remote MCP connector. It expects
an Internet-reachable HTTPS server with a publicly trusted certificate; it
cannot use `https://localhost:8443/mcp` or a Caddy internal-CA certificate.
For a local Claude Desktop extension, configure a local stdio/DXT server
instead of adding the loopback URL as a remote connector. See Anthropic's
[remote MCP connector guidance](https://support.anthropic.com/en/articles/11503834-building-custom-integrations-via-remote-mcp-servers)
and [local MCP guidance](https://support.anthropic.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).

## Production

The existing Sanchaya-Zoekt Caddy instance owns the public certificate. Start
the retrieval companion with the production overlay so both MCP processes and
Qdrant share a private Docker network and no MCP or Qdrant host ports are
published:

```text
make mcp
make oauth-config
make edge
```

The route is committed in the Sanchaya-Zoekt repository; do not hand-edit it
on the production host. It should map OAuth and bearer paths separately:

```caddyfile
@oauth path /mcp /mcp/* /.well-known/* /authorize /token /register /revoke /oauth/callback
handle @oauth {
    reverse_proxy retrieval-mcp-oauth:8788
}

@oauth_alias path /mcp-oauth /mcp-oauth/*
handle @oauth_alias {
    handle_path /mcp-oauth* {
        rewrite * /mcp
        reverse_proxy retrieval-mcp-oauth:8788
    }
}

@bearer path /mcp-bearer /mcp-bearer/*
handle @bearer {
    uri strip_prefix /mcp-bearer
    rewrite * /mcp
    reverse_proxy retrieval-mcp:8787
}
```

The external harness uses:

```text
https://sanchaya.rasowshi.us/mcp
```

The OAuth process validates Google identity and the server-side allowlist.
The bearer process continues to validate `Authorization: Bearer
<MCP_BEARER_TOKEN>` from the host-only env file. Keep Qdrant and Zoekt `/api/*`
private.

The production overlay is deliberately separate from the local Compose file:
the local file remains runnable with the existing host-side Zoekt and Qdrant,
while production reuses the already deployed Caddy network without publishing
an additional web server.
