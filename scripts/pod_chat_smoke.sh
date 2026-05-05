#!/usr/bin/env bash
# End-to-end smoke test that mirrors what the React frontend does:
#   - login as user
#   - hit /categories  (frontend uses this to populate the dropdown)
#   - send /chat with the auto-selected first category (RAG ON)
set -uo pipefail
PROJ="/workspace/gemma-test"
cd "$PROJ"

USER_PW=$(awk -F= '/^USER_SITE_PASSWORD=/{print $2; exit}' "$PROJ/.env")

echo "── 1. login ──"
curl -sS -c /tmp/cj.txt -X POST http://localhost:8000/auth/login \
     -H "content-type: application/json" --data "{\"password\":\"$USER_PW\"}" | head -c 300
echo

echo "── 2. categories ──"
CAT=$(curl -sS --max-time 5 http://localhost:8000/categories \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['categories'][0]['name'] if d.get('categories') else '')")
echo "category = $CAT"

echo "── 3. /chat with RAG ──"
cat > /tmp/chat.json <<EOF
{"user_id":"smoke","session_id":"smoke","message":"En une phrase, comment postuler pour un poste de livreur chez SENDIT ?","conversation_history":[],"category":"$CAT"}
EOF
T0=$(date +%s)
curl -sS --max-time 480 -b /tmp/cj.txt -X POST http://localhost:8000/chat \
     -H "content-type: application/json" --data @/tmp/chat.json
echo
echo "elapsed=$(($(date +%s) - T0))s"

echo "── 4. tail vllm log ──"
tail -10 /workspace/gemma-test/logs/vllm_gemma4.log 2>&1 | grep -vE 'Loading weights:.*it/s' | tail -10
