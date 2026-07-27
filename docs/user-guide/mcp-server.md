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

The server validates browser `Origin` headers against `http.allowed_origins`.
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
