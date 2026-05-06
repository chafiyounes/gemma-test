#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_api.sh  —  Start the FastAPI backend for the gemma-test project
#
# Must be run from the project root: /workspace/gemma-test/
# Usage:  bash scripts/start_api.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${API_PORT:-8000}"
WORKERS="${API_WORKERS:-1}"

# Fresh RunPod images often have no project venv; vLLM uses /workspace/vllm-venv but the
# API runs on system python3 — missing uvicorn caused silent failure in tmux window "api".
if ! python3 -c "import uvicorn" 2>/dev/null; then
    echo "Installing API dependencies from requirements-api.txt …"
    python3 -m pip install -q -r "$REPO_ROOT/requirements-api.txt"
fi

echo "══════════════════════════════════════════════════"
echo "  Starting Gemma Test API"
echo "  Listening on 0.0.0.0:$PORT"
echo "══════════════════════════════════════════════════"

# Wait for vLLM to accept traffic (Gemma 4 can take many minutes to load shards).
VLLM_URL="http://localhost:8002"
echo "Waiting for vLLM on $VLLM_URL (up to ~18 min)..."
for i in $(seq 1 72); do
    if curl -sf "$VLLM_URL/health" > /dev/null 2>&1 || curl -sf "$VLLM_URL/v1/models" > /dev/null 2>&1; then
        echo "✓ vLLM is up"
        break
    fi
    echo "  attempt $i/72 — model may still be loading weights; retry in 15s..."
    sleep 15
done

python3 -m uvicorn api.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info \
    2>&1 | tee /workspace/gemma-test/logs/api.log
