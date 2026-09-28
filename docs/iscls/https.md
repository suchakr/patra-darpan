# MCP HTTPS boundary

The retrieval application speaks Streamable HTTP on its private container
port. TLS terminates at Caddy. The MCP service enforces the pilot's shared
bearer token; Caddy supplies the certificate and routing.

## Local harness test

Keep the ordinary local endpoint for host-side smoke tests:

```text
http://127.0.0.1:8787/mcp
```

When a harness insists on HTTPS, start the optional local Caddy terminator:

```bash
docker compose --env-file .env \
  --profile runtime up -d --no-deps retrieval-mcp
docker compose --env-file .env \
  --profile runtime --profile https \
  up -d --no-deps retrieval-https
```

The endpoint is then:

```text
https://localhost:8443/mcp
```

The local MCP client must send `Authorization: Bearer <MCP_BEARER_TOKEN>`.
The same token is configured in the untracked local `.env` file.

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
the retrieval companion with the production overlay so MCP and Caddy share a
private Docker network and no MCP or Qdrant host ports are published:

```bash
docker compose --env-file /etc/patra-darpan/retrieval.env \
  -f docker-compose.retrieval.yml \
  -f docker-compose.retrieval.prod.yml \
  --profile runtime up -d retrieval-mcp qdrant
```

The route is committed in the Sanchaya-Zoekt repository; do not hand-edit it
on the production host:

```caddyfile
@mcp path /mcp /mcp/*
handle @mcp {
    reverse_proxy retrieval-mcp:8787
}
```

The external harness uses:

```text
https://sanchaya.rasowshi.us/mcp
```

The MCP service validates `Authorization: Bearer <MCP_BEARER_TOKEN>` from the
host-only env file. Requests without the token receive `401`. Keep Qdrant and
Zoekt `/api/*` private.

The production overlay is deliberately separate from the local Compose file:
the local file remains runnable with the existing host-side Zoekt and Qdrant,
while production reuses the already deployed Caddy network without publishing
an additional web server.
