#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_api.sh  —  Start the FastAPI backend for the gemma-test project
#
# Must be run from the project root: /workspace/gemma-test/
# Usage:  bash scripts/start_api.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PORT="${API_PORT:-8000}"
WORKERS="${API_WORKERS:-1}"

echo "══════════════════════════════════════════════════"
echo "  Starting Gemma Test API"
echo "  Listening on 0.0.0.0:$PORT"
echo "══════════════════════════════════════════════════"

# Wait for vLLM to be healthy before starting
echo "Waiting for vLLM on port 8002..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
        echo "✓ vLLM is up"
        break
    fi
    echo "  attempt $i/30 — retrying in 10s..."
    sleep 10
done

python3 -m uvicorn api.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info \
    2>&1 | tee /workspace/gemma-test/logs/api.log
