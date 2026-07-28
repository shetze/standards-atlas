# ADR 0043: Integrate Codex as a restricted MCP client

## Status

Accepted

## Context

The Standards Atlas MCP server is interoperable over Streamable HTTP and
provides five read-only operations for standards and clauses. Codex supports
remote Streamable HTTP MCP servers and can source a bearer token from an
environment variable.

A reference integration is needed so maintainers can use Standards Atlas from
Codex without copying protected standard content into repositories, embedding
credentials in configuration, or silently exposing future write-capable tools.

## Decision

Standards Atlas provides a Codex integration profile with these properties:

- the server is registered by URL as a Streamable HTTP MCP server;
- authentication uses `bearer_token_env_var` and never an inline token;
- `enabled_tools` explicitly lists the five qualified read-only tools;
- the generated profile uses automatic approval only for this restricted
  read-only tool set;
- project-scoped configuration is permitted only in trusted projects;
- generated configuration fragments refuse to overwrite existing files unless
  explicitly requested;
- helper scripts refuse to replace an existing Codex server registration;
- the generic MCP compatibility probe remains the protocol qualification
  mechanism, while Codex-specific checks validate client configuration.

The integration is represented by `CodexMcpConfig`, the
`standards-atlas mcp codex-config` command, an example configuration, and
registration and verification scripts.

## Consequences

Codex CLI, its IDE extension, and compatible desktop clients can consume the
same Standards Atlas knowledge interface. Tokens stay outside version control,
and adding a future MCP tool does not automatically make it available to Codex.

The allow list must be updated deliberately when the public MCP contract
changes. Codex configuration confirms registration but does not replace the
protocol-level server probe or an interactive `/mcp` check. A desktop or IDE
process may need restarting after its environment changes.

## Alternatives considered

### Store an Authorization header in config.toml

Rejected because it would persist a secret in a user or project file.

### Enable every tool exposed by the server

Rejected because future tools could broaden Codex capabilities without an
explicit integration review.

### Add Codex-specific behavior to the MCP server

Rejected because the MCP server must remain client-neutral. Codex integration
belongs at the client configuration boundary.
