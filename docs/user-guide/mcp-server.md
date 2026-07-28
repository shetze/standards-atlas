# MCP clause server

The Standards Atlas MCP adapter can run locally over STDIO or as a remote
Streamable HTTP resource server. Both modes expose the same read-only clause
operations.

## Local STDIO

```bash
uv sync --extra mcp
uv run standards-atlas mcp serve --config cfg/mcp.yaml
```

## Streamable HTTP

Set `transport: streamable-http` and configure the listener in `cfg/mcp.yaml`.
Remote bindings require bearer-token authentication.

```bash
export STANDARDS_ATLAS_MCP_TOKEN="$(openssl rand -hex 32)"
uv run standards-atlas mcp serve --config deploy/mcp/mcp.remote.yaml
```

The MCP endpoint is `http://127.0.0.1:8765/mcp`; `/healthz` is available for
local health checks. Put TLS termination in a reverse proxy or controlled
tunnel in front of the server. Never expose the plain HTTP listener directly
to an untrusted network.

Clients send:

```text
Authorization: Bearer <token>
```

The server validates the HTTP `Host` header against `http.allowed_hosts` and browser
`Origin` headers against `http.allowed_origins`. Both lists are passed to the MCP SDK
transport-security layer. Port wildcards such as `192.168.0.77:*` are supported.

For LAN access, configure the actual address explicitly:

```yaml
http:
  host: 0.0.0.0
  allowed_hosts:
    - localhost:*
    - 127.0.0.1:*
    - 192.168.0.77:*
  allowed_origins:
    - http://localhost:*
    - http://127.0.0.1:*
    - http://192.168.0.77:*
```
An empty list rejects every request that contains an Origin header while still
allowing non-browser MCP clients.

## Audit logging

The HTTP adapter writes one JSON object per request to the configured audit
file. Records contain timestamp, method, path, status, origin and remote host.
Tokens, request bodies and clause text are deliberately not logged.

## Container operation

```bash
export STANDARDS_ATLAS_MCP_TOKEN="$(openssl rand -hex 32)"
podman compose -f deploy/mcp/compose.yaml up --build
```

The example publishes the service only on host loopback, mounts `.atlas`
read-only and runs the container without root privileges.

## Compatibility probe

Slice 5.3.6 provides a protocol-level reference client for repeatable
interoperability checks. It validates the negotiated protocol version, the
registered read-only tools, a real `list_standards` tool call, and the document
catalog resource.

```bash
export MCP_URL=http://192.168.0.77:8765/mcp/
export STANDARDS_ATLAS_MCP_TOKEN='<token>'
./tools/mcp/smoke.sh
```

The same check is available directly through the CLI:

```bash
uv run standards-atlas mcp probe \
  --url "$MCP_URL" \
  --token-env STANDARDS_ATLAS_MCP_TOKEN \
  --output .atlas/evaluation/mcp-compatibility.json
```

The report contains server metadata and check results, but never the bearer
token, clause text, or model data. A failed compatibility check exits with code
`1`; connection or protocol errors exit with code `2`.

The probe deliberately uses raw JSON-RPC over Streamable HTTP rather than a
specific graphical client. It therefore complements MCP Inspector testing and
can be used in CI without Node.js or a browser.


## Codex client

Generate a restricted, token-free Codex configuration with:

```bash
uv run standards-atlas mcp codex-config --url "$MCP_URL"
```

See [Codex integration](codex-integration.md) for registration, verification,
security boundaries, and example prompts.
