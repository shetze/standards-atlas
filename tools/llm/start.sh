#!/usr/bin/env bash
set -euo pipefail

MODEL="${RAMALAMA_MODEL:-${1:-granite}}"
PORT="${RAMALAMA_PORT:-8080}"
SELINUX="${RAMALAMA_SELINUX:-false}"
STATE_DIR="${RAMALAMA_STATE_DIR:-.atlas/llm/runtime}"
LOG_FILE="${STATE_DIR}/ramalama.log"
PID_FILE="${STATE_DIR}/ramalama.pid"

mkdir -p "${STATE_DIR}"

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "RamaLama is already running with PID $(cat "${PID_FILE}")."
    exit 0
fi

nohup ramalama serve \
    --backend auto \
    --selinux="${SELINUX}" \
    --port "${PORT}" \
    "${MODEL}" \
    >"${LOG_FILE}" 2>&1 &

PID=$!
echo "${PID}" >"${PID_FILE}"
echo "Started RamaLama with PID ${PID}; log: ${LOG_FILE}"
