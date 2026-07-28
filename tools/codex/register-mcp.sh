#!/usr/bin/env bash
set -euo pipefail

MCP_URL="${MCP_URL:-http://127.0.0.1:8765/mcp/}"
TOKEN_ENV="${TOKEN_ENV:-STANDARDS_ATLAS_MCP_TOKEN}"
SERVER_NAME="${SERVER_NAME:-standards-atlas}"

command -v codex >/dev/null || {
  echo "codex executable not found" >&2
  exit 2
}

if [[ -z "${!TOKEN_ENV:-}" ]]; then
  echo "environment variable $TOKEN_ENV is not set" >&2
  exit 2
fi

if codex mcp get "$SERVER_NAME" >/dev/null 2>&1; then
  echo "Codex MCP server '$SERVER_NAME' is already configured." >&2
  echo "Remove it first with: codex mcp remove $SERVER_NAME" >&2
  exit 1
fi

codex mcp add "$SERVER_NAME" \
  --url "$MCP_URL" \
  --bearer-token-env-var "$TOKEN_ENV"

codex mcp get "$SERVER_NAME" --json
