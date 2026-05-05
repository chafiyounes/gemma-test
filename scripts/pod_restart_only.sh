#!/usr/bin/env bash
# Restart inference (vLLM) + API services on the pod with the latest code.
set -uo pipefail
PROJ="/workspace/gemma-test"
cd "$PROJ"

echo "── ensure latest scripts are in place ──"
[[ -f /tmp/sync/start_vllm.sh        ]] && sed 's/\r$//' /tmp/sync/start_vllm.sh        > scripts/start_vllm.sh        && echo "synced start_vllm.sh"
[[ -f /tmp/sync/serve_gemma4.py      ]] && sed 's/\r$//' /tmp/sync/serve_gemma4.py      > scripts/serve_gemma4.py      && echo "synced serve_gemma4.py"
[[ -f /tmp/sync/install_vllm.sh      ]] && sed 's/\r$//' /tmp/sync/install_vllm.sh      > scripts/install_vllm.sh      && echo "synced install_vllm.sh"
[[ -f /tmp/sync/pod_quick_test.sh    ]] && sed 's/\r$//' /tmp/sync/pod_quick_test.sh    > scripts/pod_quick_test.sh    && echo "synced pod_quick_test.sh"
[[ -f /tmp/sync/pod_chat_smoke.sh    ]] && sed 's/\r$//' /tmp/sync/pod_chat_smoke.sh    > scripts/pod_chat_smoke.sh    && echo "synced pod_chat_smoke.sh"
chmod +x scripts/*.sh

echo "── kill old services ──"
tmux kill-session -t gemma-test 2>/dev/null || true
pkill -9 -f "vllm serve"       2>/dev/null || true
pkill -9 -f "vllm.entrypoints" 2>/dev/null || true
pkill -9 -f serve_gemma4       2>/dev/null || true
pkill -9 -f "uvicorn.*api.main" 2>/dev/null || true
pkill -9 -f "python3 .*api/main" 2>/dev/null || true
sleep 5
nvidia-smi --query-gpu=memory.used --format=csv,noheader

echo "── start tmux services ──"
mkdir -p logs

# vLLM with Gemma 4 26B MoE on both A40s (TP=2). Tunable via env:
: "${INFER_GPUS:=0,1}"
: "${INFER_TP:=2}"
: "${INFER_MAX_LEN:=8192}"
: "${INFER_GPU_UTIL:=0.85}"

tmux new-session -d -s gemma-test -n vllm \
    "cd $PROJ && \
     CUDA_VISIBLE_DEVICES=$INFER_GPUS \
     VLLM_TENSOR_PARALLEL_SIZE=$INFER_TP \
     VLLM_MAX_MODEL_LEN=$INFER_MAX_LEN \
     VLLM_GPU_MEMORY_UTILIZATION=$INFER_GPU_UTIL \
     bash scripts/start_vllm.sh gemma4 2>&1 | tee logs/vllm.log"

tmux new-window -t gemma-test -n api \
    "cd $PROJ && python3 -m api.main 2>&1 | tee logs/api.log"

echo "── waiting for inference /health ──"
for i in $(seq 1 90); do
    h=$(curl -s --max-time 4 http://localhost:8002/health 2>/dev/null)
    echo "[$i] $h"
    # vLLM /health returns empty body 200 OK when up
    code=$(curl -s --max-time 4 -o /dev/null -w '%{http_code}' http://localhost:8002/health 2>/dev/null || echo 000)
    [[ "$code" == "200" ]] && break
    sleep 5
done

echo "── waiting for api /health ──"
for i in $(seq 1 18); do
    h=$(curl -s --max-time 4 http://localhost:8000/health 2>/dev/null)
    echo "[$i] $h"
    if [[ "$h" == *'"model_available":true'* ]]; then break; fi
    sleep 3
done
echo "── started; logs at $PROJ/logs/{vllm,api}.log ──"
