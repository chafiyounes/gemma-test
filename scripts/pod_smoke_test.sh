#!/usr/bin/env bash
# Quick end-to-end smoke test for the inference + API stack on the pod.
# Run on the pod itself.
set -u
PROJ="/workspace/gemma-test"
cd "$PROJ"

echo "== /health (vllm 8002) =="
curl -s http://localhost:8002/health; echo

echo "== /health (api 8000) =="
curl -s http://localhost:8000/health; echo

echo "== direct /v1/chat/completions =="
cat > /tmp/req.json <<'EOF'
{"messages":[{"role":"user","content":"Say hi in one short sentence."}],"max_tokens":48,"temperature":0}
EOF
T0=$(date +%s)
curl -s -X POST http://localhost:8002/v1/chat/completions \
  -H "content-type: application/json" --data @/tmp/req.json > /tmp/direct.out
T1=$(date +%s)
echo "elapsed=$((T1 - T0))s"
head -c 1200 /tmp/direct.out; echo

echo "== auth =="
USER_PW=$(awk -F= '/^USER_SITE_PASSWORD=/{print $2; exit}' "$PROJ/.env")
ADMIN_PW=$(awk -F= '/^ADMIN_SITE_PASSWORD=/{print $2; exit}' "$PROJ/.env")
echo "user_pw_len=${#USER_PW} admin_pw_len=${#ADMIN_PW}"

LOGIN=$(curl -s -c /tmp/cj_user.txt -X POST http://localhost:8000/auth/login \
  -H "content-type: application/json" \
  --data "{\"password\":\"$USER_PW\"}")
echo "user_login=$LOGIN"

echo "== /chat (FastAPI) =="
cat > /tmp/chat.json <<'EOF'
{"user_id":"smoke-user","session_id":"smoke-session","message":"Bonjour, dis-moi en une phrase que tu fonctionnes.","conversation_history":[],"category":null}
EOF
T0=$(date +%s)
curl -s -b /tmp/cj_user.txt -X POST http://localhost:8000/chat \
  -H "content-type: application/json" --data @/tmp/chat.json > /tmp/api.out
T1=$(date +%s)
echo "elapsed=$((T1 - T0))s"
head -c 1500 /tmp/api.out; echo

echo "== /categories =="
curl -s -b /tmp/cj_user.txt http://localhost:8000/categories | head -c 500; echo

echo "== /models =="
curl -s -b /tmp/cj_user.txt http://localhost:8000/models | head -c 500; echo

echo "== admin login + /admin/interactions =="
ALOGIN=$(curl -s -c /tmp/cj_admin.txt -X POST http://localhost:8000/auth/login \
  -H "content-type: application/json" \
  --data "{\"password\":\"$ADMIN_PW\"}")
echo "admin_login=$ALOGIN"
curl -s -b /tmp/cj_admin.txt "http://localhost:8000/admin/interactions?limit=3" | head -c 700; echo
