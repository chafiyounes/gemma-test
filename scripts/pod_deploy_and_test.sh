#!/usr/bin/env bash
# Deploy synced files, restart inference + API, smoke-test the full chain.
# Run this on the pod after `scp` has placed updated files in /tmp/sync.
set -uo pipefail
PROJ="/workspace/gemma-test"
cd "$PROJ"

echo "── 1. install synced files ──"
for f in serve_gemma4.py start_vllm.sh; do
    if [[ -f /tmp/sync/$f ]]; then
        # Strip any CRLF that may have come from Windows.
        sed 's/\r$//' /tmp/sync/$f > "$PROJ/scripts/$f"
        echo "installed scripts/$f"
    fi
done
[[ -f /tmp/sync/settings.py ]]    && sed 's/\r$//' /tmp/sync/settings.py    > "$PROJ/app_config/settings.py" && echo "installed app_config/settings.py"
[[ -f /tmp/sync/.env.example ]]   && sed 's/\r$//' /tmp/sync/.env.example   > "$PROJ/.env.example"            && echo "installed .env.example"
chmod +x "$PROJ/scripts/start_vllm.sh"

echo "── 2. patch .env to point at gemma4-26b-it ──"
if [[ -f "$PROJ/.env" ]]; then
    sed -i 's|^VLLM_MODEL_NAME=.*|VLLM_MODEL_NAME=gemma4-26b-it|' "$PROJ/.env"
    grep -q "^VLLM_MODEL_NAME=" "$PROJ/.env" || echo "VLLM_MODEL_NAME=gemma4-26b-it" >> "$PROJ/.env"
    grep -q "^VLLM_BASE_URL="   "$PROJ/.env" || echo "VLLM_BASE_URL=http://localhost:8002" >> "$PROJ/.env"
    sed -i 's|^MAX_NEW_TOKENS=.*|MAX_NEW_TOKENS=192|' "$PROJ/.env"
fi
echo "── current .env (sanitised) ──"
sed -E 's/(PASSWORD|SECRET)=.*/\1=***/' "$PROJ/.env"

echo "── 3. python syntax check ──"
python3 -c "import py_compile; py_compile.compile('scripts/serve_gemma4.py', doraise=True); print('serve_gemma4.py OK')"
python3 -c "import py_compile; py_compile.compile('app_config/settings.py',  doraise=True); print('settings.py OK')"

echo "── 4. stop existing services ──"
tmux kill-session -t gemma-test 2>/dev/null || true
pkill -9 -f serve_gemma4 2>/dev/null || true
pkill -9 -f "uvicorn.*api.main" 2>/dev/null || true
pkill -9 -f "python3 .*api/main" 2>/dev/null || true
sleep 4
echo "─── GPU after kill ───"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader

echo "── 5. start inference + api in tmux ──"
mkdir -p logs
# Inference: bf16 multi-GPU + eager attention + max_memory cap to keep weights on GPU.
tmux new-session  -d -s gemma-test -n vllm "cd $PROJ && CUDA_VISIBLE_DEVICES=0,1 USE_INT8=0 USE_INT4=0 ATTN_IMPLEMENTATION=eager GPU_MAX_MEMORY=44GiB bash scripts/start_vllm.sh gemma4 2>&1 | tee logs/vllm.log"
# API: defaults port 8000.
tmux new-window   -t gemma-test  -n api  "cd $PROJ && python3 -m api.main 2>&1 | tee logs/api.log"

echo "── 6. wait for /health on 8002 (model load) ──"
for i in $(seq 1 80); do
    h=$(curl -s --max-time 3 http://localhost:8002/health 2>/dev/null)
    echo "h$i: $h"
    if [[ "$h" == *'"status":"ok"'* ]]; then
        break
    fi
    sleep 5
done

echo "── 7. wait for /health on 8000 ──"
for i in $(seq 1 24); do
    h=$(curl -s --max-time 3 http://localhost:8000/health 2>/dev/null)
    echo "a$i: $h"
    if [[ "$h" == *'"status":"ok"'* ]]; then
        break
    fi
    sleep 3
done

echo "── 8. direct chat ──"
cat > /tmp/req.json <<'EOF'
{"messages":[{"role":"user","content":"Say hi in one short sentence."}],"max_tokens":40,"temperature":0}
EOF
T0=$(date +%s)
curl -s --max-time 240 -X POST http://localhost:8002/v1/chat/completions \
     -H "content-type: application/json" --data @/tmp/req.json > /tmp/direct.out
echo "elapsed=$(($(date +%s) - T0))s"
echo "raw: $(head -c 1500 /tmp/direct.out)"

echo "── 9. /chat through API ──"
USER_PW=$(awk -F= '/^USER_SITE_PASSWORD=/{print $2; exit}' "$PROJ/.env")
curl -s -c /tmp/cj.txt -X POST http://localhost:8000/auth/login \
     -H "content-type: application/json" --data "{\"password\":\"$USER_PW\"}" > /tmp/login.out
echo "login: $(head -c 200 /tmp/login.out)"
cat > /tmp/chat.json <<'EOF'
{"user_id":"smoke","session_id":"smoke","message":"Bonjour, dis-moi en une phrase que tu fonctionnes.","conversation_history":[],"category":null}
EOF
T0=$(date +%s)
curl -s --max-time 300 -b /tmp/cj.txt -X POST http://localhost:8000/chat \
     -H "content-type: application/json" --data @/tmp/chat.json > /tmp/api.out
echo "elapsed=$(($(date +%s) - T0))s"
echo "api: $(head -c 1500 /tmp/api.out)"

echo "── 10. /categories ──"
curl -s -b /tmp/cj.txt http://localhost:8000/categories | head -c 400; echo

echo "── done ──"
