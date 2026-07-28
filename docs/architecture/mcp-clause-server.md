# MCP Clause Server

Slices 5.3.2 and 5.3.3 add a read-only Model Context Protocol inbound adapter to Standards Atlas.
The server is a separately started process, but remains part of the same package and uses the
transport-neutral `ClauseProvider` application port introduced in Slice 5.3.1.

## Dependency direction

```text
MCP client
    |
    v
adapters/mcp
    |
    v
application/services/evaluation/ClauseProvider
    |
    v
adapters/evaluation/EngineeringDocumentClauseProvider
    |
    v
persisted EngineeringDocument objects
```

The MCP adapter does not parse persistence files and does not call an LLM. Its responsibility is
limited to protocol registration, request validation, exposure policy, and serialization.

## Installation and startup

MCP support is optional:

```bash
uv sync --extra mcp
uv run standards-atlas mcp serve --config cfg/mcp.yaml
```

The adapter supports local STDIO and remote Streamable HTTP operation. Remote bindings require
authentication; TLS termination remains the responsibility of a reverse proxy, VPN, or controlled
tunnel in front of the server.

The optional dependency is constrained to the stable MCP Python SDK v1 line:

```toml
mcp = ["mcp>=1.27,<2"]
```

## Exposed tools

- `list_standards`
- `get_clause`
- `list_clauses`
- `search_clauses`
- `sample_clauses`

All operations are read-only. Search and sampling delegate to `ClauseProvider` rather than
reimplementing corpus behavior in the transport adapter.

## Exposed resources

- `standards-atlas://documents`
- `standards-atlas://clauses/{clause_id}`

Resources return JSON and are intended for direct contextual reads. Parameterized queries remain
tools because they perform filtering, search, or sampling.

## Exposure policy

`cfg/mcp.yaml` controls:

- the `.atlas` workspace to read;
- an optional allowlist of document keys;
- maximum result and sample sizes;
- maximum returned clause text length;
- whether clause text is exposed at all.

The server never exposes source file paths, PDFs, or arbitrary filesystem operations. Configuration
fields for source paths and internal metadata default to disabled and reserve explicit policy points
for future descriptors containing such data.

## Failure behavior

Invalid limits, unsupported sampling strategies, hidden documents, and unknown clauses are returned
as MCP tool errors. They do not terminate the server process.

## Remote operation

A Streamable HTTP ASGI adapter runs around the same FastMCP server.
Transport security remains outside the application services. The adapter
validates Origin headers, optionally enforces a bearer token, limits request
body size and emits privacy-conscious JSON-lines audit records.

The built-in token mode is intended for a controlled single-client deployment
or a protected tunnel. Enterprise multi-user deployments should replace it
with an OAuth 2.1 authorization server and the MCP SDK's `TokenVerifier`
integration without changing the clause-access services.


## Transport host validation

The HTTP configuration owns the allow-lists used by the MCP SDK DNS-rebinding
protection. `allowed_hosts` validates the HTTP `Host` header, while
`allowed_origins` validates browser origins. The adapter passes both lists into
`TransportSecuritySettings`; unknown HTTP configuration fields are rejected to
prevent security settings from being silently ignored.

## Compatibility boundary

The adapter includes a small protocol-level compatibility probe. It acts as an
independent client and verifies the externally visible contract instead of
calling server internals. This covers:

- Streamable HTTP JSON-RPC initialization
- protocol-version negotiation
- discovery of the required read-only tools
- execution of `list_standards`
- discovery of `standards-atlas://documents`

Keeping the probe independent from FastMCP's internal server API makes it a
regression guard for SDK upgrades and client interoperability.
