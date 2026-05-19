#!/usr/bin/env bash
# Smoke test for GET /api/documents/preview (isolated from /chat).
set -uo pipefail
PROJ="/workspace/gemma-test"
cd "$PROJ"

USER_PW=$(awk -F= '/^USER_SITE_PASSWORD=/{print $2; exit}' "$PROJ/.env")
USER_NAME=$(awk -F= '/^AUTH_BOOTSTRAP_USER_USERNAME=/{print $2; exit}' "$PROJ/.env")
USER_NAME=${USER_NAME:-user}

curl -sS -c /tmp/cj_preview.txt -X POST http://127.0.0.1:8000/auth/login \
  -H "content-type: application/json" \
  --data "{\"username\":\"$USER_NAME\",\"password\":\"$USER_PW\"}" > /dev/null

DOC=$(curl -sS -b /tmp/cj_preview.txt http://127.0.0.1:8000/categories \
  | python3 -c "import sys,json; d=json.load(sys.stdin); cats=d.get('categories') or []; 
for c in cats:
  if c.get('doc_names'):
    print(c['doc_names'][0]); break")

if [ -z "$DOC" ]; then
  echo "SKIP: no indexed documents"
  exit 0
fi

echo "doc=$DOC"
curl -sS -g -b /tmp/cj_preview.txt \
  --get "http://127.0.0.1:8000/api/documents/preview" \
  --data-urlencode "name=${DOC}" \
  --data-urlencode "category=procedures" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('has_docx',d.get('has_docx'),'has_md',d.get('has_md'),'md_len',len(d.get('markdown') or ''))"

echo "preview routes OK"
