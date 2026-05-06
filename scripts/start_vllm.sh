#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_vllm.sh  —  Start the vLLM OpenAI-compatible server on the pod.
#
# vLLM 0.19.0 added Gemma 4 support (Gemma4ForConditionalGeneration, MoE).
# It lives in an isolated venv at /workspace/vllm-venv so it doesn't fight
# with the transformers 5.x stack used by the FastAPI backend.
#
# Usage:
#   bash scripts/start_vllm.sh gemma4       # default
#   bash scripts/start_vllm.sh gemma        # gemma 3 27B (if downloaded)
#
# Listens on port 8002, OpenAI-compatible /v1/chat/completions endpoint.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

VENV=/workspace/vllm-venv
MODEL_DIR=/workspace/models
PORT=8002

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
    exit 1
fi

if [[ ! -f "$VENV/bin/activate" ]]; then
    echo "✗ vLLM venv missing at $VENV — run scripts/install_vllm.sh first"
    exit 1
fi

# Gemma 4 @ tp=2 + default gpu_memory_util 0.85 needs tens of GiB **free** per GPU.
# If a previous vLLM crashed, the host can keep GPU memory with no visible PID in the
# container — only a RunPod stop/start (or support reset) clears it.
FREE_MIB=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | sort -n | head -1 || echo "0")
if [[ "${FREE_MIB:-0}" -lt 15000 ]]; then
    echo "══════════════════════════════════════════════════"
    echo "✗ GPU free memory too low for vLLM (min free across GPUs: ${FREE_MIB} MiB; need ~15+ GiB to start)."
    echo "  This often happens after an engine crash: VRAM stays allocated on the host."
    echo "  Fix: stop the pod in the RunPod dashboard, start it again, then:"
    echo "       bash start_all.sh ${TARGET}"
    echo "══════════════════════════════════════════════════"
    exit 1
fi

# Both A40s for tensor parallelism. vLLM ≥0.19 dispatches Gemma 4 MoE
# correctly across two GPUs (the transformers-direct path was broken).
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
export VLLM_TENSOR_PARALLEL_SIZE="${VLLM_TENSOR_PARALLEL_SIZE:-2}"
# RAG: full-category inject can be tens of thousands of characters (~3 chars/token
# for FR). If prompt_tokens + max_tokens would exceed --max-model-len, vLLM shrinks
# the completion budget → mid-sentence stops (same place each time).
# 12288 is a practical default on 2× A40 for Gemma 4; raise to 16384 if stable.
# If startup OOMs/hangs, lower VLLM_MAX_MODEL_LEN or reduce RAG_INJECT_MAX_CHARS.
export VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-12288}"
export VLLM_GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.85}"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# Kill any previous vllm / serve_gemma4 process
pkill -9 -f "vllm.entrypoints" 2>/dev/null || true
pkill -9 -f "vllm serve"       2>/dev/null || true
pkill -9 -f "serve_gemma4"     2>/dev/null && echo "Killed previous serve_gemma4" || true
sleep 5

echo "══════════════════════════════════════════════════"
echo "  Starting vLLM server"
echo "  Model      : $TARGET  →  $MODEL_PATH"
echo "  Port       : $PORT"
echo "  GPUs       : $CUDA_VISIBLE_DEVICES (tp=$VLLM_TENSOR_PARALLEL_SIZE)"
echo "  Max len    : $VLLM_MAX_MODEL_LEN"
echo "  GPU mem    : $VLLM_GPU_MEMORY_UTILIZATION"
echo "══════════════════════════════════════════════════"

echo "--- GPU state before load ---"
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv,noheader
echo ""

mkdir -p /workspace/gemma-test/logs

# shellcheck source=/dev/null
source "$VENV/bin/activate"

# `--served-model-name` lets the FastAPI client send model="gemma4-26b-it"
# without hitting a 404 on the actual filesystem path.
exec vllm serve "$MODEL_PATH" \
    --served-model-name gemma4-26b-it \
    --host 0.0.0.0 \
    --port "$PORT" \
    --tensor-parallel-size "$VLLM_TENSOR_PARALLEL_SIZE" \
    --max-model-len "$VLLM_MAX_MODEL_LEN" \
    --gpu-memory-utilization "$VLLM_GPU_MEMORY_UTILIZATION" \
    --limit-mm-per-prompt '{"image":0,"audio":0,"video":0}' \
    --disable-custom-all-reduce \
    --trust-remote-code \
    2>&1 | tee "/workspace/gemma-test/logs/vllm_${TARGET}.log"
