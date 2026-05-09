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

# Tear down previous inference first so the **same container** can reclaim VRAM.
# (The old check ran before pkill, so legitimate child processes still held memory.)
pkill -9 -f "vllm.entrypoints" 2>/dev/null || true
pkill -9 -f "vllm serve"       2>/dev/null || true
pkill -9 -f "serve_gemma4"     2>/dev/null || true
sleep 8

# Optional: ask the driver to reset GPUs (sometimes clears zombie contexts). Off by default.
if [[ "${VLLM_TRY_GPU_RESET:-0}" == "1" ]]; then
    echo "── trying nvidia-smi --gpu-reset on each GPU (VLLM_TRY_GPU_RESET=1) ──"
    _gpu_count=$(nvidia-smi -L 2>/dev/null | wc -l | tr -d " ")
    for ((i = 0; i < _gpu_count; i++)); do
        nvidia-smi --gpu-reset -i "$i" 2>/dev/null || true
    done
    sleep 5
fi

# Gemma 4 @ tp=2 + default gpu_memory_util 0.85 needs tens of GiB **free** per GPU.
FREE_MIB=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | sort -n | head -1 || echo "0")
if [[ "${FREE_MIB:-0}" -lt 15000 ]]; then
    echo "══════════════════════════════════════════════════"
    echo "✗ GPU free memory too low for vLLM (min free across GPUs: ${FREE_MIB} MiB; need ~15+ GiB to start)."
    echo "  Try on this pod (same session):"
    echo "    export VLLM_TRY_GPU_RESET=1"
    echo "    bash scripts/start_vllm.sh ${TARGET}"
    echo "  If still low, VRAM is often held **outside** this container — recycle the pod:"
    echo "    • Dashboard: Stop → Start"
    echo "    • Or from your PC: set RUNPOD_API_KEY + RUNPOD_POD_ID, then:"
    echo "      python3 scripts/runpod_recycle_pod.py"
    echo "  Then SSH back in and: bash start_all.sh ${TARGET}"
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
# 16384 offers significantly more RAG headroom on 2× A40 while staying practical.
# If startup OOMs/hangs, lower VLLM_MAX_MODEL_LEN or reduce RAG_INJECT_MAX_CHARS.
export VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-16384}"
export VLLM_GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.85}"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Gemma 4 instruct uses a dedicated tool protocol. Without these flags, vLLM will
# not populate OpenAI-style `tool_calls` on /v1/chat/completions — agentic RAG breaks.
# See: https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html#function-calling-tool-use
VLLM_GEMMA4_TOOLING="${VLLM_GEMMA4_TOOLING:-1}"
VLLM_EXTRA_ARGS=()
if [[ "$TARGET" == "gemma4" && "$VLLM_GEMMA4_TOOLING" != "0" ]]; then
    TMPL="$REPO_ROOT/scripts/vendor/tool_chat_template_gemma4.jinja"
    if [[ ! -f "$TMPL" ]]; then
        mkdir -p "$REPO_ROOT/scripts/vendor"
        echo "── downloading tool_chat_template_gemma4.jinja (vLLM) ──"
        if ! curl -fsSL -o "$TMPL" \
            "https://raw.githubusercontent.com/vllm-project/vllm/main/examples/tool_chat_template_gemma4.jinja"
        then
            rm -f "$TMPL" 2>/dev/null || true
            TMPL=""
        fi
    fi
    if [[ -z "$TMPL" || ! -f "$TMPL" ]]; then
        PY_OUT="$(python3 -c "
import pathlib
try:
    import vllm
    root = pathlib.Path(vllm.__file__).resolve().parent
    p = root / 'examples' / 'tool_chat_template_gemma4.jinja'
    print(p if p.is_file() else '', end='')
except Exception:
    pass
" 2>/dev/null || true)"
        if [[ -n "$PY_OUT" && -f "$PY_OUT" ]]; then
            TMPL="$PY_OUT"
        fi
    fi
    if [[ -n "$TMPL" && -f "$TMPL" ]]; then
        VLLM_EXTRA_ARGS+=( --enable-auto-tool-choice --tool-call-parser gemma4 --chat-template "$TMPL" )
        if [[ "${VLLM_GEMMA4_REASONING:-0}" == "1" ]]; then
            VLLM_EXTRA_ARGS+=( --reasoning-parser gemma4 )
        fi
        echo "── Gemma 4 tool calling: ON (chat template: $TMPL) ──"
    else
        echo "═══════════════════════════════════════════════════════════════════"
        echo "⚠ Gemma 4 tool template missing — agentic RAG will likely NOT get tool_calls."
        echo "  On the pod: curl -fsSL -o scripts/vendor/tool_chat_template_gemma4.jinja \\"
        echo "    https://raw.githubusercontent.com/vllm-project/vllm/main/examples/tool_chat_template_gemma4.jinja"
        echo "  Then re-run this script. Disable tooling: export VLLM_GEMMA4_TOOLING=0"
        echo "═══════════════════════════════════════════════════════════════════"
    fi
fi

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
    "${VLLM_EXTRA_ARGS[@]}" \
    2>&1 | tee "/workspace/gemma-test/logs/vllm_${TARGET}.log"
