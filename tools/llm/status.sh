#!/usr/bin/env bash
set -euo pipefail

PORT="${RAMALAMA_PORT:-8080}"
STATE_DIR="${RAMALAMA_STATE_DIR:-.atlas/llm/runtime}"
PID_FILE="${STATE_DIR}/ramalama.pid"
URL="${STANDARDS_ATLAS_LLM_BASE_URL:-http://127.0.0.1:${PORT}/v1}"

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "RamaLama process: running (PID $(cat "${PID_FILE}"))"
else
    echo "RamaLama process: not running"
fi

if curl --silent --fail --show-error "${URL%/}/models"; then
    echo
    echo "LLM endpoint: available"
else
    echo "LLM endpoint: unavailable" >&2
    exit 1
fi

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu \
        --format=csv,noheader
fi
