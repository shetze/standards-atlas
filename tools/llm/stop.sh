#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${RAMALAMA_STATE_DIR:-.atlas/llm/runtime}"
PID_FILE="${STATE_DIR}/ramalama.pid"

if [[ ! -f "${PID_FILE}" ]]; then
    echo "RamaLama is not running."
    exit 0
fi

PID="$(cat "${PID_FILE}")"
if kill -0 "${PID}" 2>/dev/null; then
    kill "${PID}"
    wait "${PID}" 2>/dev/null || true
fi
rm -f "${PID_FILE}"
echo "Stopped RamaLama."
