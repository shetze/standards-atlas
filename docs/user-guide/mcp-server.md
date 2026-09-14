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

With the default workspace, every accepted submission is saved under `.atlas/data/enrichments/formula-transcriptions/` with actor, provider/model, confidence and source-image hash before the corresponding `FormulaBlock` is changed to `machine_transcribed`. The visual source remains attached to the block for later review.

## Recovering a stale MCP runtime after a schema update

The current canonical writer emits EngineeringDocument schema **9**; readers support
**8 and 9**. A tool error such as

```text
Unsupported engineering document schema version: 9; readable versions are 8, current is 8
```

therefore identifies an older loaded reader, not a need to downgrade the document.
An already running MCP process retains its imported Python modules when a checkout is
updated. A server launched from another installation/environment can have the same
symptom. `mcp start` is idempotent: it does **not** reload an existing healthy process.
Do not edit the persisted `schema_version` or rebuild documents to conceal the mismatch.

After applying the updated files, explicitly restart a **managed HTTP** process from the
intended project checkout, with the same configuration used to start it:

```bash
uv run standards-atlas mcp restart --config cfg/mcp.yaml
```

The existing bearer-token environment variable must still be set. Restart stops the owned
process before starting a replacement, and does not start a second process if stopping
fails. An endpoint occupied without a managed PID is rejected rather than reported as a
successful startup. A foreground `mcp serve`, container or externally managed service must
instead be stopped/restarted using its original launcher (and rebuilt when its installed
code is outdated). Reconnect the Codex MCP session after replacing the server.

### Verify the server that actually answers requests

The read-only `get_server_info` tool reports the **loaded** Standards Atlas application
version, document reader/writer versions and the formula-writing capability. It does not
read documents or expose tokens, source paths or workspace paths. The MCP initialize
`server.version` field alone is not evidence of a supported EngineeringDocument schema.

`mcp probe` now checks this runtime information in addition to its protocol/catalog checks.
An older server without `get_server_info`, or with incompatible reader/writer versions,
produces a failed check with a restart hint. `--document-key` additionally exercises the
actual formula-listing path; it may be repeated for several documents:

```bash
uv run standards-atlas mcp probe \
  --url http://192.168.0.77:8765/mcp/ \
  --token-env STANDARDS_ATLAS_MCP_TOKEN \
  --document-key IEC61508-3 \
  --output local/evaluation/mcp-schema-formulas.json
```

The report should include:

```json
"engineering_document_schema": {
  "current": 9,
  "readable": [9],
  "writer": 9
}
```

Both `engineering_document_schema` and `list_untranscribed_formulas` checks must pass.
An empty formula list is a valid read result; the probe never submits transcriptions and
does not include source images or clause text in its report. Formula tool errors retain
their diagnostic message instead of becoming a false-positive success. The catalog check
still validates the general inventory, independently of the scoped formula check.

A scoped formula request loads only the selected/allowlisted documents, in stable key order.
Unrelated unsupported or malformed files no longer block it. Unsupported selected files
remain errors; an unfiltered inventory is still strict rather than silently incomplete.

Writing remains opt-in. The supplied `cfg/mcp.yaml` defaults to
`mcp.capabilities.formula_transcription: false`; explicitly enable it in the configuration
used by the server before restarting for a trusted transcription session. A read-only
probe can pass with writing disabled; inspect `runtime.capabilities.formula_transcription`
before asking Codex to submit. Submissions continue to preserve the source image and record
actor, provider/model and source-image hash in the separate transcription artifact.

## Optional source-bound review preparation

The [review preparation guide](partial-review-preparation.md) describes the five optional
read tools and two model-only write tools. They are disabled by default. Enable
`mcp.review.enabled` for reads and additionally `mcp.capabilities.review_preparation` for
selection/annotation proposals. Configure `mcp.review.workspace` explicitly and restart the
server after changing configuration. Holdout assistance remains separately opt-in.

`mcp codex-config --review-preparation` renders a dedicated review-only allowlist, avoiding
bypasses through generic corpus readers. No tool can confirm human decisions, materialize
selections, publish suites or activate releases. Authentication, disclosure and request limits
still apply; source hashes and evidence positions are handled by Atlas.
