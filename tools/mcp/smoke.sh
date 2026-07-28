#!/usr/bin/env bash
set -euo pipefail

MCP_URL="${MCP_URL:-http://127.0.0.1:8765/mcp/}"
MCP_TOKEN_ENV="${MCP_TOKEN_ENV:-STANDARDS_ATLAS_MCP_TOKEN}"
OUTPUT="${MCP_SMOKE_REPORT:-.atlas/evaluation/mcp-compatibility.json}"

uv run standards-atlas mcp probe \
  --url "$MCP_URL" \
  --token-env "$MCP_TOKEN_ENV" \
  --output "$OUTPUT"
