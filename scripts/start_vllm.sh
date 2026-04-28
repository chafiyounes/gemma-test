#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_vllm.sh  —  Start the vLLM OpenAI-compatible inference server
#
# Usage:
#   bash scripts/start_vllm.sh gemma        # load base Gemma 3 27B-IT
#   bash scripts/start_vllm.sh gemmaroc     # load GemMaroc-27b-it
#   bash scripts/start_vllm.sh atlaschat   # load Atlas-Chat-27B
#
# vLLM will listen on port 8001.
# The FastAPI backend reads VLLM_MODEL_NAME from .env to form the request.
# After switching models, update VLLM_MODEL_NAME in .env to match.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODEL_DIR="/workspace/models"
PORT=8001
GPU_MEM_UTIL=0.85       # 85% of VRAM per GPU (safer for 27B on 2x A40)
MAX_MODEL_LEN=16384     # 16K context — enough for top-5 SOPs + question + history
TENSOR_PARALLEL=2       # use both A40 GPUs

declare -A MODEL_MAP=(
    [gemma4]="$MODEL_DIR/gemma4-26b-it"
    [gemma]="$MODEL_DIR/gemma-3-27b-it"
    [gemmaroc]="$MODEL_DIR/GemMaroc-27b-it"
    [atlaschat]="$MODEL_DIR/Atlas-Chat-27B"
)

TARGET="${1:-gemma4}"

if [[ -z "${MODEL_MAP[$TARGET]+x}" ]]; then
    echo "Unknown model: $TARGET"
    echo "Usage: bash scripts/start_vllm.sh [gemma4|gemma|gemmaroc|atlaschat]"
    exit 1
fi

MODEL_PATH="${MODEL_MAP[$TARGET]}"

if [[ ! -d "$MODEL_PATH" ]]; then
    echo "✗ Model not found at $MODEL_PATH"
    echo "  Run first:  bash scripts/download_models.sh $TARGET"
    exit 1
fi

echo "══════════════════════════════════════════════════"
echo "  Starting vLLM server"
echo "  Model : $TARGET  →  $MODEL_PATH"
echo "  Port  : $PORT"
echo "══════════════════════════════════════════════════"

# Kill any existing vLLM process
pkill -f "vllm.entrypoints" 2>/dev/null && echo "Killed previous vLLM process" || true
sleep 2

nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
echo ""

python3 -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --port "$PORT" \
    --host 0.0.0.0 \
    --gpu-memory-utilization "$GPU_MEM_UTIL" \
    --max-model-len "$MAX_MODEL_LEN" \
    --tensor-parallel-size "$TENSOR_PARALLEL" \
    --dtype bfloat16 \
    --served-model-name "$TARGET" \
    --trust-remote-code \
    2>&1 | tee "/workspace/gemma-test/logs/vllm_${TARGET}.log"
