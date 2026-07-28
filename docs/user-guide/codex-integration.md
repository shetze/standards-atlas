# Codex integration

Codex CLI, the Codex IDE extension, and the ChatGPT desktop app can use the
Standards Atlas Streamable HTTP MCP server through their shared MCP
configuration.

## Prerequisites

- a running and successfully probed Standards Atlas MCP server;
- Codex CLI available as `codex`;
- the bearer token available in the Codex process environment.

The token must not be written into `config.toml`.

```bash
export MCP_URL=http://192.168.0.77:8765/mcp/
export STANDARDS_ATLAS_MCP_TOKEN='<token>'
```

## Generate a configuration fragment

```bash
uv run standards-atlas mcp codex-config \
  --url "$MCP_URL" \
  --output local/codex/standards-atlas.toml
```

The output can be copied into either:

- `~/.codex/config.toml` for a user-wide registration; or
- `.codex/config.toml` in a trusted project for project-scoped access.

The generated table uses `bearer_token_env_var`, enables only the five
read-only Standards Atlas tools, and contains no token value.

## Register through Codex CLI

The provided helper uses the official Codex MCP registration command:

```bash
./tools/codex/register-mcp.sh
```

Optional variables:

```bash
MCP_URL=https://atlas.example/mcp/ \
TOKEN_ENV=STANDARDS_ATLAS_MCP_TOKEN \
SERVER_NAME=standards-atlas \
./tools/codex/register-mcp.sh
```

The helper refuses to overwrite an existing server registration. Inspect or
remove an existing entry explicitly:

```bash
codex mcp get standards-atlas --json
codex mcp remove standards-atlas
```

## Verify in Codex

```bash
./tools/codex/verify-mcp.sh
```

Then start Codex and run `/mcp`. The server should initialize and expose:

- `list_standards`
- `list_clauses`
- `get_clause`
- `search_clauses`
- `sample_clauses`

Example tasks:

```text
Use Standards Atlas to list the available standards.

Search Standards Atlas for clauses concerning software component
qualification and cite the returned clause identifiers.
```

Codex must be restarted after changing the token environment variable because
already running desktop or IDE processes may retain their previous environment.

## Security boundary

The Codex integration is a read-only client integration. It does not grant
Codex filesystem access through MCP, does not expose write tools, and does not
persist the bearer token. Normal MCP host, origin, TLS, audit, and request-size
controls remain in force.
