#!/usr/bin/env bash
# Single direct + single API chat test. Short timeouts so we fail fast.
set -uo pipefail
PROJ="/workspace/gemma-test"
cd "$PROJ"

echo "── direct /v1/chat/completions ──"
cat > /tmp/req.json <<'EOF'
{"messages":[{"role":"user","content":"Say hi in one short sentence."}],"max_tokens":40,"temperature":0}
EOF
T0=$(date +%s)
curl -sS --max-time 240 -X POST http://localhost:8002/v1/chat/completions \
     -H "content-type: application/json" --data @/tmp/req.json > /tmp/direct.out 2>/tmp/direct.err
RC=$?
echo "elapsed=$(($(date +%s) - T0))s rc=$RC"
echo "raw: $(head -c 1500 /tmp/direct.out)"
echo "err: $(head -c 500 /tmp/direct.err)"

echo
echo "── tail vllm log ──"
tail -25 /workspace/gemma-test/logs/vllm_gemma4.log 2>&1 | grep -vE 'Loading weights:.*it/s' | tail -25

echo
echo "── api auth + /chat (NO category, no RAG) ──"
USER_PW=$(awk -F= '/^USER_SITE_PASSWORD=/{print $2; exit}' "$PROJ/.env")
curl -sS -c /tmp/cj.txt -X POST http://localhost:8000/auth/login \
     -H "content-type: application/json" --data "{\"password\":\"$USER_PW\"}" > /tmp/login.out
echo "login: $(head -c 200 /tmp/login.out)"

cat > /tmp/chat.json <<'EOF'
{"user_id":"smoke","session_id":"smoke","message":"Bonjour, dis-moi en une phrase que tu fonctionnes.","conversation_history":[],"category":null}
EOF
T0=$(date +%s)
curl -sS --max-time 300 -b /tmp/cj.txt -X POST http://localhost:8000/chat \
     -H "content-type: application/json" --data @/tmp/chat.json > /tmp/api.out 2>/tmp/api.err
RC=$?
echo "elapsed=$(($(date +%s) - T0))s rc=$RC"
echo "api: $(head -c 1500 /tmp/api.out)"

echo
echo "── tail vllm log (after /chat) ──"
tail -15 /workspace/gemma-test/logs/vllm_gemma4.log 2>&1 | grep -vE 'Loading weights:.*it/s' | tail -15
