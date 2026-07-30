#!/usr/bin/env bash
set -euo pipefail

profile="${1:-fast}"

case "${profile}" in
  fast)
    uv run --extra mcp pytest -m "not docling and not doorstop and not qualification"
    ;;
  full)
    uv run --all-extras pytest
    ;;
  qualification)
    uv run standards-atlas qualification golden-corpus
    ;;
  coverage)
    uv run --extra mcp pytest \
      -m "not docling and not doorstop" \
      --cov=standards_atlas \
      --cov-report=term-missing \
      --cov-report=xml
    ;;
  *)
    echo "usage: $0 {fast|full|qualification|coverage}" >&2
    exit 2
    ;;
esac
