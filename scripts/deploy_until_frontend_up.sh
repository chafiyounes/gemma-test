#!/usr/bin/env bash
set -euo pipefail

# deploy_until_frontend_up.sh
# Repeatedly runs deployment steps and starts services until the frontend is reachable.
# Usage: sudo bash scripts/deploy_until_frontend_up.sh [model]

MODEL="${1:-gemma4}"
PROJ="/workspace/gemma-test"
LOG_DIR="$PROJ/logs"
VLLM_PORT=8002
API_PORT=8000
FRONTEND_URL="http://localhost:${API_PORT}/"

mkdir -p "$LOG_DIR"

echo "Starting deployment loop (model=$MODEL). Will not exit until frontend is serving." 

while true; do
  echo "\n════════════════════════════════════════════════"
  echo "Deployment attempt: $(date)"
  echo "Working dir: $PROJ"
  set -x
  cd "$PROJ"

  # Sync code
  git fetch origin main || true
  git reset --hard FETCH_HEAD || true

  # Normalize scripts and make executable
  sed -i 's/\r$//' scripts/*.sh || true
  chmod +x scripts/*.sh || true

  # Install Python deps (no-op if already present)
  pip install -r requirements.txt || true

  # Build frontend
  if [ -d "$PROJ/web_test" ]; then
    echo "Building frontend..."
    cd "$PROJ/web_test"
    npm ci --silent || npm install --silent || true
    npm run build --silent || true
    cd "$PROJ"
  fi

  mkdir -p "$LOG_DIR"

  # Start vLLM (background)
  pkill -9 -f "serve_gemma4" || true
  pkill -9 -f "vllm.entrypoints" || true
  sleep 2
  echo "Starting vLLM on port $VLLM_PORT (model=$MODEL)..."
  export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-1}
  export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
  nohup bash scripts/start_vllm.sh "$MODEL" > "$LOG_DIR/vllm_${MODEL}.log" 2>&1 &

  # Wait for vLLM health
  echo "Waiting for vLLM health on port $VLLM_PORT..."
  for i in $(seq 1 60); do
    if curl -sf "http://localhost:${VLLM_PORT}/health" > /dev/null 2>&1; then
      echo "vLLM healthy"
      break
    fi
    echo "  vLLM not ready (attempt $i), waiting 5s..."
    sleep 5
  done

  # Start API (background)
  pkill -9 -f "uvicorn api.main:app" || true
  sleep 1
  echo "Starting API (uvicorn) on port $API_PORT..."
  nohup bash scripts/start_api.sh > "$LOG_DIR/api.log" 2>&1 &

  # Wait for API health
  echo "Waiting for API health on port $API_PORT..."
  for i in $(seq 1 60); do
    if curl -sf "http://localhost:${API_PORT}/health" > /dev/null 2>&1; then
      echo "API healthy"
      break
    fi
    echo "  API not ready (attempt $i), waiting 5s..."
    sleep 5
  done

  # Verify frontend is serving index and contains a known marker
  echo "Checking frontend at $FRONTEND_URL"
  success=false
  for i in $(seq 1 60); do
    if curl -sS "${FRONTEND_URL}" -m 5 | grep -q "<div id=\"root\"\|<div id=\"app\"\|<title>"; then
      echo "Frontend is serving HTML (attempt $i). SUCCESS"
      success=true
      break
    fi
    echo "  Frontend not ready (attempt $i), waiting 5s..."
    sleep 5
  done

  if [ "$success" = true ]; then
    echo "All services are up. Frontend reachable at $FRONTEND_URL"
    echo "Tail logs: $LOG_DIR/vllm_${MODEL}.log  $LOG_DIR/api.log"
    exit 0
  fi

  echo "Frontend check failed after retries. Collecting diagnostics and retrying in 30s..."
  echo "--- vLLM tail ---"
  tail -n 200 "$LOG_DIR/vllm_${MODEL}.log" || true
  echo "--- API tail ---"
  tail -n 200 "$LOG_DIR/api.log" || true
  echo "--- nvidia-smi ---"
  nvidia-smi || true
  sleep 30
done
