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
PORT=8002
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
echo "  Starting transformers inference server"
echo "  Model : $TARGET  →  $MODEL_PATH"
echo "  Port  : $PORT"
echo "══════════════════════════════════════════════════"

# Kill any existing inference server process (including stale OOM-crashed processes)
pkill -9 -f "serve_gemma4" 2>/dev/null && echo "Killed previous serve_gemma4" || true
pkill -9 -f "vllm.entrypoints" 2>/dev/null || true
# Give the OS time to release CUDA contexts fully (important after OOM crashes)
sleep 6

echo "--- GPU state before load ---"
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv,noheader
echo ""

# Restrict to physical GPU 1 only (GPU 0 is inaccessible in this RunPod pod config —
# PyTorch sees it but the CUDA context fails; hiding it avoids caching_allocator_warmup crash)
export CUDA_VISIBLE_DEVICES=1
# Allow PyTorch to expand CUDA memory segments to reduce fragmentation
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

MODEL_DIR="$MODEL_PATH" PORT="$PORT" \
python3 /workspace/gemma-test/scripts/serve_gemma4.py \
    2>&1 | tee "/workspace/gemma-test/logs/vllm_${TARGET}.log"
