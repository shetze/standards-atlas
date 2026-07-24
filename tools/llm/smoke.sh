#!/usr/bin/env bash
set -euo pipefail

PORT="${RAMALAMA_PORT:-8080}"
URL="${STANDARDS_ATLAS_LLM_BASE_URL:-http://127.0.0.1:${PORT}/v1}"
MODEL="${STANDARDS_ATLAS_LLM_MODEL:-${RAMALAMA_MODEL:-granite}}"

curl --silent --fail --show-error \
    --header "Content-Type: application/json" \
    --data "$(cat <<JSON
{
  "model": "${MODEL}",
  "messages": [
    {
      "role": "system",
      "content": "Return only the requested structured result."
    },
    {
      "role": "user",
      "content": "Summarize: The supplier shall verify the safety plan."
    }
  ],
  "temperature": 0,
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "llm_infrastructure_smoke_test",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {
          "summary": {"type": "string"}
        },
        "required": ["summary"],
        "additionalProperties": false
      }
    }
  }
}
JSON
)" \
    "${URL%/}/chat/completions"
echo
