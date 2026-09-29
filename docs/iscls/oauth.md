# MCP OAuth edge

The retrieval image is used by two MCP processes:

- `retrieval-mcp`: the existing bearer-token endpoint, exposed through
  `/mcp-bearer`.
- `retrieval-mcp-oauth`: the OAuth endpoint, exposed through `/mcp` and the
  explicit alias `/mcp-oauth`.

Both processes read the same read-only release and use the same retrieval
adapters. OAuth is implemented with the Python MCP SDK authorization-server
hooks. Google is the upstream OIDC provider. The MCP provider issues the
short-lived MCP access token only after the returned, verified Google email is
found in the allowlist.

The process paths stay `/mcp` inside the private container network. The
edge-level `/mcp-bearer` and `/mcp-oauth` names are Caddy routes, so the tool
implementation does not know or care which public authentication path was
used.

## Allowlist

`MCP_OAUTH_ALLOWLIST_FILE` names a server-side text file. Each nonblank line is
one email address. A `#` comments through the end of the line. The parser
normalizes case and whitespace. The process caches the parsed set and checks
the file stat signature before each authorization decision, so edits take
effect without an index rebuild or service restart. The same check is applied
when loading access or refresh tokens: adding an address permits a new login,
while removing it blocks new login and existing token use after the next
request.

The OAuth state database is separate from the corpus release and is configured
with `MCP_OAUTH_STATE_DB`. It stores registered clients, short-lived codes,
access tokens, and refresh tokens.

## Local route shape

The local Caddy edge routes `/mcp` and OAuth discovery/callback paths to the
OAuth process, and rewrites `/mcp-bearer` to the bearer process. `/mcp` is an
internal route alias, not an HTTP redirect, because MCP clients use streaming
POST requests.

Run `make oauth-config`, then `make edge` after populating the OAuth values in
the untracked `.env`. `make edge-smoke` checks discovery, protected-resource
metadata, and both unauthenticated challenges. A real Google login remains a
manual client test.

The production Caddy instance must apply the same path mapping on its private
Docker network. Qdrant, Zoekt, the release, and the indexing workflow do not
change.
