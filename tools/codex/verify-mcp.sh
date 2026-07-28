#!/usr/bin/env bash
set -euo pipefail

SERVER_NAME="${SERVER_NAME:-standards-atlas}"
TOKEN_ENV="${TOKEN_ENV:-STANDARDS_ATLAS_MCP_TOKEN}"

command -v codex >/dev/null || {
  echo "codex executable not found" >&2
  exit 2
}

if [[ -z "${!TOKEN_ENV:-}" ]]; then
  echo "environment variable $TOKEN_ENV is not set" >&2
  exit 2
fi

codex mcp get "$SERVER_NAME" --json
printf '\nOpen Codex and run /mcp to verify the initialized tools.\n'
