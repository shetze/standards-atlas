# MCP clause server

The Standards Atlas MCP adapter can run locally over STDIO or as a remote
Streamable HTTP resource server. Both modes expose the same read-only clause and knowledge-table
operations.

## Knowledge-table operations

The server exposes structured table projections without flattening them into clause text:

- `list_knowledge_tables` lists addressable tables, optionally filtered by document;
- `get_knowledge_table` returns table metadata, headers, records, kind, and evidence;
- `list_knowledge_records` pages through logical rows of one table;
- `get_knowledge_record` retrieves one record by stable identifier.

Supported tables may include portable concepts and relations or IEC 61508-specific
recommendation semantics. Generic tables still expose their lossless cells and evidence.
Source locators follow the configured exposure policy and are omitted when private source
paths are not enabled.

The resource template
`standards-atlas://knowledge-tables/{table_id}` provides the same read-only table view.
These artefacts are deterministic projections of canonical engineering documents and are
intended to become retrieval units for the future IntelliDoc RAG integration.

## Local STDIO

```bash
uv sync --extra mcp
uv run standards-atlas mcp serve --config cfg/mcp.yaml
```

## Managed Streamable HTTP process

Set `transport: streamable-http` and configure the listener in `cfg/mcp.yaml`.
Remote bindings require bearer-token authentication. The CLI manages the server
as a detached process with PID and log files below `.atlas/work/mcp`.

```bash
export STANDARDS_ATLAS_MCP_TOKEN="$(openssl rand -hex 32)"
uv run standards-atlas mcp start --config deploy/mcp/mcp.remote.yaml
uv run standards-atlas mcp status --config deploy/mcp/mcp.remote.yaml
uv run standards-atlas mcp stop --config deploy/mcp/mcp.remote.yaml
```

For diagnostics, `mcp serve` still runs the server in the foreground. Managed
background operation is intentionally unavailable for the STDIO transport.

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

## Transcribing preserved formulas

Slice 2 adds a controlled formula-enrichment workflow for MCP clients such as Codex. `list_untranscribed_formulas` discovers preserved visual formulas, and `get_formula` returns the PNG data URI plus source evidence and adjacent clause text. After inspecting the image, a client may submit a LaTeX transcription with `submit_formula_transcription`.

Writing is disabled by default. Enable it explicitly when running a trusted transcription workflow:

```yaml
mcp:
  capabilities:
    formula_transcription: true
```

Every accepted submission is saved under `.atlas/enrichments/formula-transcriptions/` with actor, provider/model, confidence and source-image hash before the corresponding `FormulaBlock` is changed to `machine_transcribed`. The visual source remains attached to the block for later review.
