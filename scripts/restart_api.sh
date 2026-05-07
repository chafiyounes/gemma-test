#!/usr/bin/env bash
# Restart only the FastAPI / uvicorn pane — leaves the vLLM window running.
# Use after code or static changes that do not require reloading the GPU model.
set -euo pipefail

PROJ="${PROJ:-/workspace/gemma-test}"
SESSION="${TMUX_SESSION:-gemma-test}"
LOG_DIR="$PROJ/logs"
mkdir -p "$LOG_DIR"

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "No tmux session '$SESSION'. Start the stack first: bash start_all.sh gemma4"
  exit 1
fi

if tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx 'api'; then
  tmux kill-window -t "$SESSION:api"
fi

tmux new-window -t "$SESSION" -n api
tmux send-keys -t "$SESSION:api" "cd $PROJ && bash scripts/start_api.sh 2>&1 | tee $LOG_DIR/api.log" Enter
echo "API window restarted (vLLM pane untouched)."
