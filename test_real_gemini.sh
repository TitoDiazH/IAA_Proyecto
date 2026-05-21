#!/usr/bin/env bash
set -euo pipefail

echo "=== Testing Real Gemini Setup ==="

if ! docker compose ps backend --status running >/dev/null 2>&1; then
  echo "The backend container is not running. Start it with: docker compose up"
  exit 1
fi

docker compose exec -T backend python - <<'PY'
from app.services.ai_client import get_json_client

client = get_json_client()
result = client.complete_json(
    system_prompt="Responde exclusivamente JSON valido.",
    user_prompt="Devuelve {\"ok\": true}.",
    schema_name="gemini_healthcheck",
    schema={
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    },
)

print(result)
PY
