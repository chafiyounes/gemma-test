#!/usr/bin/env bash
# Run on the pod after deploy (called by remote_post_deploy_verify.py).
set -e
cd /workspace/gemma-test

echo "=== pip install (requirements) ==="
python3 -m pip install -q -r requirements.txt

echo "=== agentic map (heuristic, fast) ==="
python3 scripts/bootstrap_agentic_map.py

echo "=== embedding index ==="
echo "skipped (catalog-based agentic retrieval does not require embeddings)"

if grep -q '^AGENTIC_RAG_ENABLED=' .env 2>/dev/null; then
  sed -i 's/^AGENTIC_RAG_ENABLED=.*/AGENTIC_RAG_ENABLED=true/' .env
else
  echo 'AGENTIC_RAG_ENABLED=true' >> .env
fi

echo "=== restart API ==="
bash scripts/restart_api.sh || true
sleep 12

echo "=== wait for vLLM (up to 15 min; model load after start_all) ==="
_ready=0
for _i in $(seq 1 180); do
  if curl -sf -m 5 http://127.0.0.1:8002/v1/models >/dev/null 2>&1; then
    echo "vLLM OK after ${_i} attempts (5s interval)"
    _ready=1
    break
  fi
  sleep 5
done
if [[ "${_ready}" != "1" ]]; then
  echo "[warn] vLLM not ready after wait — tests may fail; check tmux pane vllm"
fi

echo "=== health ==="
curl -sS -m 5 http://127.0.0.1:8000/health | head -c 400 || echo "api health fail"
echo ""
curl -sS -m 5 http://127.0.0.1:8002/health | head -c 200 || echo "vllm health fail"
echo ""

ADMIN_PASSWORD=$(grep -E '^ADMIN_SITE_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' | tr -d "'")
export ADMIN_PASSWORD
ADMIN_USER=$(grep -E '^AUTH_BOOTSTRAP_ADMIN_USERNAME=' .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' | tr -d "'")
ADMIN_USER=${ADMIN_USER:-admin}
export ADMIN_USER
USER_PASSWORD=$(grep -E '^USER_SITE_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' | tr -d "'")
export USER_PASSWORD

echo "=== test_agentic_rag_pod.py ==="
set +e
python3 scripts/test_agentic_rag_pod.py
POD_EC=$?
set -e

echo "=== sample chats (admin, agentic) ==="
rm -f /tmp/gemma_cj.txt /tmp/gemma_login.json
python3 -c "import json,os; open('/tmp/gemma_login.json','w').write(json.dumps({'username':os.environ.get('ADMIN_USER','admin'),'password':os.environ.get('ADMIN_PASSWORD','')}))"
curl -sS -c /tmp/gemma_cj.txt -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d @/tmp/gemma_login.json | head -c 300
echo ""

# Sample questions must match topics in category `procedures` only (no generic support KB).
CHAT1='{"message":"Comment modifier les coordonnées du client pendant une livraison ? Donne les étapes principales.","category":"procedures","agentic_rag":true,"conversation_history":[]}'
echo "--- Chat FR (agentic) ---"
curl -sS -b /tmp/gemma_cj.txt -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d "$CHAT1" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('response','')
print('response_len=', len(r))
print(r[:1200])
print('...')
meta=d.get('metadata') or {}
print('rag_mode=', (meta.get('rag') or {}).get('mode'))
print('tool_rounds=', (meta.get('rag') or {}).get('tool_rounds'))
"

# Same intent as CHAT1 (coordonnées / numéro client, colis en livraison) — Darija, procedures corpus.
CHAT2='{"message":"كيفاش نبدل الرقم ديال الزبون إلا كان الكولي فالليفريزون؟","category":"procedures","agentic_rag":true,"conversation_history":[]}'
echo "--- Chat darija (agentic, procedures topic) ---"
curl -sS -b /tmp/gemma_cj.txt -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d "$CHAT2" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('response','')
print('response_len=', len(r))
print(r[:900])
print('...')
meta=d.get('metadata') or {}
print('rag_mode=', (meta.get('rag') or {}).get('mode'))
print('tool_rounds=', (meta.get('rag') or {}).get('tool_rounds'))
"

echo "VERIFY_DONE pod_ec=$POD_EC"
exit 0
