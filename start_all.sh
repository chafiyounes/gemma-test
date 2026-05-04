#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_all.sh  —  Start all services on the RunPod pod
#
# Usage:
#   bash start_all.sh [gemma4|gemma|gemmaroc|atlaschat]
#   (default: gemma4)
#
# Each service runs in a named tmux pane so you can attach and inspect logs.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODEL="${1:-gemma4}"
PROJ="/workspace/gemma-test"
LOG_DIR="$PROJ/logs"
mkdir -p "$LOG_DIR"

echo "══════════════════════════════════════════════════"
echo "  Gemma Test — Starting All Services"
echo "  Model: $MODEL"
echo "══════════════════════════════════════════════════"

# Kill previous session if it exists
tmux kill-session -t gemma-test 2>/dev/null && echo "Killed previous tmux session" || true

# Start new tmux session with vLLM window
tmux new-session -d -s gemma-test -n vllm  \; \
    send-keys "cd $PROJ && bash scripts/start_vllm.sh $MODEL 2>&1 | tee $LOG_DIR/vllm.log" Enter

echo "▶ vLLM starting in tmux window 'vllm' (model: $MODEL)..."
sleep 5

# Open API window
tmux new-window -t gemma-test -n api
tmux send-keys -t gemma-test:api "cd $PROJ && bash scripts/start_api.sh 2>&1 | tee $LOG_DIR/api.log" Enter

echo "▶ API starting in tmux window 'api' (waits for vLLM health)..."

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Services launched in tmux session 'gemma-test'"
echo ""
echo "  Attach:     tmux attach -t gemma-test"
echo "  vLLM logs:  tmux select-window -t gemma-test:vllm"
echo "  API logs :  tmux select-window -t gemma-test:api"
echo ""
echo "  Health check (run after ~2min for model to load):"
echo "  curl http://localhost:8002/health   # inference server"
echo "  curl http://localhost:8000/health   # API"
echo ""
echo "  Run capability tests:"
echo "  python3 scripts/test_capabilities.py --model gemma"
echo ""
echo "  From local machine, open SSH tunnels:"
echo "  ssh -L 8000:localhost:8000 -L 8002:localhost:8002 runpod2"
echo "═══════════════════════════════════════════════════════"
